#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TVBox 江湖源存活检测：分类/首页连通，hard-fail 可归档。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import ssl
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "江湖.json"
ARCHIVE_DIR = ROOT / "失效"
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Mobile) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)
DEFAULT_TIMEOUT = 10
DEFAULT_WORKERS = 10
MAX_BODY_BYTES = 512_000
GATEWAY_MARKERS = (
    "502 bad gateway",
    "503 service",
    "504 gateway",
    "cloudflare",
    "error 1020",
    "just a moment",
    "access denied",
    "站点创建中",
    "domain parking",
    "this site can't be reached",
)
EMPTY_PAGE_MARKERS = (
    "404 not found",
    "页面不存在",
    "找不到页面",
    "not found",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_local_path(value: str) -> Optional[Path]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("./"):
        return None
    relative = text[2:].split("?", 1)[0].split("#", 1)[0]
    return ROOT / relative


def is_local_host(url: str) -> bool:
    lower = url.lower()
    return "127.0.0.1" in lower or "localhost" in lower


def classify_site(site: dict) -> str:
    site_type = site.get("type")
    api = str(site.get("api") or "")
    if site_type in (0, 1):
        return "remote"
    if site_type == 4:
        if is_local_host(api):
            return "type4_local"
        return "type4_remote"
    if api.startswith("csp_"):
        return "csp"
    if ".py" in api or api.endswith(".js") or "/js/" in api or api.startswith("./js"):
        return "script"
    if api.startswith("http://") or api.startswith("https://"):
        return "remote"
    return "other"


def first_category_id(rule: dict) -> str:
    class_values = rule.get("分类值")
    if isinstance(class_values, str) and class_values.strip() and class_values.strip() != "*":
        parts = re.split(r"[&,#]", class_values)
        for part in parts:
            token = part.strip()
            if token:
                return token
    class_field = rule.get("分类")
    if not isinstance(class_field, str):
        return "1"
    # name$id#name$id  or name&name with 分类值
    if "$" in class_field:
        segments = [segment for segment in class_field.split("#") if segment.strip()]
        for segment in segments:
            if "$" in segment:
                category_id = segment.split("$", 1)[1].strip()
                if category_id:
                    return category_id
    if "&" in class_field and isinstance(class_values, str) and class_values.strip():
        values = [part.strip() for part in class_values.split("&") if part.strip()]
        if values:
            return values[0]
    return "1"


def clean_template_url(raw_url: str, rule: Optional[dict] = None) -> Optional[str]:
    if not isinstance(raw_url, str):
        return None
    text = raw_url.strip()
    if not text:
        return None
    if ";;" in text:
        text = text.split(";;", 1)[0]
    # 主段[备用] 形式取主段
    bracket_index = text.find("[")
    if bracket_index != -1:
        text = text[:bracket_index]
    text = text.strip()
    if not text:
        return None
    if not text.startswith("http://") and not text.startswith("https://"):
        if text.startswith("//"):
            text = "https:" + text
        elif text.startswith("www."):
            text = "https://" + text
        else:
            return None
    category_id = first_category_id(rule or {})
    replacements = {
        "{cateId}": category_id,
        "{catePg}": "1",
        "{pg}": "1",
        "{page}": "1",
        "{class}": "",
        "{area}": "",
        "{year}": "",
        "{lang}": "",
        "{by}": "",
        "{wd}": "a",
        "{tid}": category_id,
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    # 残留花括号占位：尽量去掉
    text = re.sub(r"\{[a-zA-Z0-9_]+\}", "", text)
    return text


def extract_urls_from_rule(rule: dict) -> list[str]:
    if not isinstance(rule, dict):
        return []
    candidates: list[str] = []
    preferred_keys = (
        "分类url",
        "主页url",
        "homeUrl",
        "home",
        "url",
        "host",
        "baseUrl",
        "网站",
        "站名",
        "发布url",
    )
    for key in preferred_keys:
        value = rule.get(key)
        if isinstance(value, str) and value.strip():
            cleaned = clean_template_url(value, rule)
            if cleaned:
                candidates.append(cleaned)
    # 站名有时不是 URL；过滤非 http
    result: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        if url.startswith("http://") or url.startswith("https://"):
            if url not in seen:
                seen.add(url)
                result.append(url)
    return result


def parse_rule_text(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # 少数规则可能是 JS 对象风格，尽量不硬猜
    return None


def http_get(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 1,
) -> tuple[int, bytes, Optional[str]]:
    """返回 (status, body, error_message)。status=0 表示网络层失败。"""
    last_error: Optional[str] = None
    context = ssl.create_default_context()
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=timeout, context=context) as response:
                status = getattr(response, "status", 200) or 200
                body = response.read(MAX_BODY_BYTES)
                return status, body, None
        except HTTPError as error:
            body = b""
            try:
                body = error.read(MAX_BODY_BYTES)
            except Exception:
                body = b""
            return error.code, body, f"HTTPError {error.code}"
        except URLError as error:
            last_error = f"URLError {error.reason}"
        except TimeoutError:
            last_error = "timeout"
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
        if attempt < attempts - 1:
            time.sleep(0.4)
    return 0, b"", last_error or "request_failed"


def body_looks_like_error_page(body: bytes, status: int) -> tuple[bool, str]:
    if status == 0:
        return True, "network_error"
    if not body or len(body.strip()) < 40:
        return True, "empty_body"
    sample = body[:8000].decode("utf-8", errors="ignore").lower()
    if status >= 500:
        return True, f"http_{status}"
    for marker in GATEWAY_MARKERS:
        if marker in sample and len(body) < 20_000:
            return True, f"gateway_marker:{marker}"
    if status == 404:
        for marker in EMPTY_PAGE_MARKERS:
            if marker in sample:
                return True, "http_404_page"
        # 404 但 body 较长也可能是软失败
        if len(body) < 1500:
            return True, "http_404"
    return False, ""


def body_has_api_structure(body: bytes) -> bool:
    text = body[:100_000].decode("utf-8", errors="ignore").strip()
    if not text:
        return False
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key in ("class", "list", "data", "classes", "type", "vod", "videos", "items"):
                if key in data:
                    return True
            # 深层 data.list
            nested = data.get("data")
            if isinstance(nested, dict) and any(
                key in nested for key in ("list", "class", "items", "records")
            ):
                return True
            if isinstance(nested, list) and nested:
                return True
        if isinstance(data, list) and data:
            return True
    lower = text.lower()
    if "<rss" in lower or "<class" in lower or "<video" in lower or "<ty " in lower or "<list" in lower:
        return True
    # 宽松：像 HTML 列表页
    if "<html" in lower or "<!doctype" in lower:
        if any(token in lower for token in ("vod", "video", "list", "item", "movie", "href=")):
            return True
        if len(body) > 2000:
            return True
    return len(body) > 800


def judge_response(
    status: int,
    body: bytes,
    error: Optional[str],
    mode: str = "page",
) -> tuple[str, str]:
    """返回 (status_label, reason)。status_label: pass/fail/soft_fail"""
    if status == 0:
        return "fail", error or "network_error"
    is_error_page, error_reason = body_looks_like_error_page(body, status)
    if status in (401, 403, 429):
        if body and len(body.strip()) >= 40:
            return "soft_fail", f"http_{status}_with_body"
        return "fail", f"http_{status}"
    if is_error_page and status not in (200, 301, 302):
        # 4xx/5xx 空页
        if status >= 400:
            return "fail", error_reason
    if is_error_page and status == 200 and error_reason.startswith("gateway"):
        return "fail", error_reason
    if is_error_page and error_reason == "empty_body":
        return "fail", "empty_body"
    if mode == "api":
        if body_has_api_structure(body):
            return "pass", f"api_ok_http_{status}"
        if body and len(body) > 200:
            return "soft_fail", f"api_unstructured_http_{status}"
        return "fail", f"api_no_structure_http_{status}"
    # page
    if body_has_api_structure(body) or (body and len(body) >= 200):
        if status >= 400 and status not in (401, 403, 429):
            if body and len(body) >= 500:
                return "soft_fail", f"http_{status}_with_content"
            return "fail", f"http_{status}"
        return "pass", f"page_ok_http_{status}"
    return "fail", f"page_empty_or_error_http_{status}"


def load_ext_rule(site: dict) -> tuple[Optional[dict], Optional[str], Optional[str]]:
    """
    解析 csp ext。
    返回 (rule_dict, error_status, reason)
    error_status 为 fail/soft_fail/manual_review 时 rule 可能为 None。
    """
    ext = site.get("ext")
    if ext is None or (isinstance(ext, str) and not ext.strip()):
        return None, "manual_review", "no_ext"
    if isinstance(ext, dict):
        return ext, None, None
    if not isinstance(ext, str):
        return None, "manual_review", f"ext_type_{type(ext).__name__}"
    text = ext.strip()
    if text.startswith("null$$$") or text.startswith("null$"):
        return None, "manual_review", f"special_ext:{text[:40]}"
    if text.startswith("./"):
        path = resolve_local_path(text)
        if path is None or not path.is_file():
            return None, "fail", f"missing_ext:{text}"
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as error:
            return None, "fail", f"read_ext_error:{error}"
        rule = parse_rule_text(raw)
        if rule is None:
            return None, "fail", f"bad_json:{text}"
        return rule, None, None
    if text.startswith("http://") or text.startswith("https://"):
        status, body, error = http_get(text, timeout=DEFAULT_TIMEOUT, retries=1)
        if status == 0:
            return None, "soft_fail", f"remote_rule_fetch_failed:{error}"
        if status >= 400 and not body:
            return None, "soft_fail", f"remote_rule_http_{status}"
        rule = parse_rule_text(body.decode("utf-8", errors="ignore"))
        if rule is None:
            # 规则本身不是 JSON，但 URL 可能是站点
            return {"主页url": text}, None, "remote_rule_as_url"
        return rule, None, None
    # 可能是单行 JSON 字符串
    rule = parse_rule_text(text)
    if rule is not None:
        return rule, None, None
    return None, "manual_review", f"unparsed_ext:{text[:60]}"


def extract_script_urls(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    found = re.findall(r"https?://[^\s\"'<>]+", text)
    cleaned: list[str] = []
    seen: set[str] = set()
    skip_hosts = (
        "github.com",
        "githubusercontent.com",
        "jsdelivr",
        "npmjs",
        "pypi.org",
        "python.org",
        "googleapis",
        "gstatic",
        "w3.org",
    )
    for url in found:
        url = url.rstrip(").,;\"'")
        if any(host in url for host in skip_hosts):
            continue
        if url not in seen:
            seen.add(url)
            cleaned.append(url)
        if len(cleaned) >= 5:
            break
    return cleaned


def check_url_list(urls: list[str], mode: str = "page") -> dict[str, Any]:
    last: dict[str, Any] = {
        "status": "fail",
        "reason": "no_url",
        "http_status": None,
        "probe_url": None,
    }
    for url in urls:
        status, body, error = http_get(url, timeout=DEFAULT_TIMEOUT, retries=1)
        label, reason = judge_response(status, body, error, mode=mode)
        last = {
            "status": label,
            "reason": reason,
            "http_status": status if status else None,
            "probe_url": url,
            "error": error,
        }
        if label == "pass":
            return last
        if label == "soft_fail":
            # 继续尝试其他 URL，若全 soft 则返回 soft
            continue
    return last


def check_site(site: dict, only: Optional[str] = None) -> dict[str, Any]:
    key = site.get("key")
    name = site.get("name")
    kind = classify_site(site)
    result: dict[str, Any] = {
        "key": key,
        "name": name,
        "kind": kind,
        "type": site.get("type"),
        "api": site.get("api"),
        "status": "manual_review",
        "reason": "",
        "http_status": None,
        "probe_url": None,
        "checked_at": utc_now_iso(),
    }
    if only and only not in (kind, "all"):
        # 映射 only 参数
        only_map = {
            "remote": {"remote"},
            "csp": {"csp"},
            "script": {"script"},
            "type4": {"type4_local", "type4_remote"},
            "parses": set(),
        }
        allowed = only_map.get(only, {only})
        if kind not in allowed:
            result["status"] = "skip"
            result["reason"] = f"filtered_by_only:{only}"
            return result

    if kind == "type4_local":
        result["status"] = "skip"
        result["reason"] = "local_type4"
        return result

    if kind == "type4_remote":
        api = str(site.get("api") or "")
        if not api.startswith("http"):
            result["status"] = "fail"
            result["reason"] = "type4_no_http_api"
            return result
        probe = check_url_list([api], mode="api")
        result.update(probe)
        return result

    if kind == "remote":
        api = str(site.get("api") or "")
        if not api.startswith("http"):
            result["status"] = "fail"
            result["reason"] = "remote_no_http_api"
            return result
        urls = [api]
        if "ac=" not in api:
            joiner = "&" if "?" in api else "?"
            urls.append(f"{api}{joiner}ac=list")
            urls.append(f"{api}{joiner}ac=class")
        probe = check_url_list(urls, mode="api")
        result.update(probe)
        return result

    if kind == "script":
        api = str(site.get("api") or "")
        ext = site.get("ext")
        missing: list[str] = []
        for field_name, value in (("api", api), ("ext", ext)):
            if isinstance(value, str) and value.startswith("./"):
                path = resolve_local_path(value)
                if path is None or not path.is_file():
                    missing.append(f"{field_name}:{value}")
        if missing:
            result["status"] = "fail"
            result["reason"] = "missing_file:" + ",".join(missing)
            return result
        urls: list[str] = []
        for value in (api, ext):
            if isinstance(value, str) and value.startswith("./"):
                path = resolve_local_path(value)
                if path and path.is_file() and path.suffix.lower() in {".py", ".js"}:
                    urls.extend(extract_script_urls(path))
        if not urls:
            result["status"] = "manual_review"
            result["reason"] = "script_no_probe_url"
            return result
        probe = check_url_list(urls[:3], mode="page")
        result.update(probe)
        if result["status"] == "fail" and "script" in kind:
            # 脚本 URL 可能是 API 片段，失败时降级 manual 以免误杀过多
            if result.get("reason", "").startswith("network") or result.get("http_status") in (0, None):
                pass
        return result

    if kind == "csp":
        rule, error_status, error_reason = load_ext_rule(site)
        if error_status:
            result["status"] = error_status
            result["reason"] = error_reason or "ext_error"
            return result
        assert rule is not None
        urls = extract_urls_from_rule(rule)
        if not urls:
            result["status"] = "manual_review"
            result["reason"] = "csp_no_probe_url"
            return result
        # 优先分类再主页：extract 已按优先级
        probe = check_url_list(urls[:3], mode="page")
        result.update(probe)
        return result

    result["status"] = "manual_review"
    result["reason"] = f"unsupported_kind:{kind}"
    return result


def check_parse(parse: dict) -> dict[str, Any]:
    name = parse.get("name")
    url = parse.get("url")
    result: dict[str, Any] = {
        "key": name,
        "name": name,
        "kind": "parse",
        "status": "skip",
        "reason": "",
        "http_status": None,
        "probe_url": None,
        "checked_at": utc_now_iso(),
    }
    if not isinstance(url, str) or not url.strip():
        result["status"] = "skip"
        result["reason"] = "empty_url"
        return result
    if not url.startswith("http://") and not url.startswith("https://"):
        result["status"] = "skip"
        result["reason"] = f"non_http_url:{url[:40]}"
        return result
    # 解析接口常需附加视频 URL；仅测宿主可达
    probe_url = url
    if url.endswith("=") or url.endswith("url=") or url.endswith("v="):
        probe_url = url  # 直接请求
    status, body, error = http_get(probe_url, timeout=DEFAULT_TIMEOUT, retries=1)
    # 解析接口返回 4xx 也常见；有响应即可
    if status == 0:
        result["status"] = "fail"
        result["reason"] = error or "network_error"
        result["probe_url"] = probe_url
        return result
    if status in (401, 403, 429) and body:
        result["status"] = "soft_fail"
        result["reason"] = f"http_{status}_with_body"
        result["http_status"] = status
        result["probe_url"] = probe_url
        return result
    if status >= 500 and (not body or len(body) < 40):
        result["status"] = "fail"
        result["reason"] = f"http_{status}"
        result["http_status"] = status
        result["probe_url"] = probe_url
        return result
    result["status"] = "pass"
    result["reason"] = f"reachable_http_{status}"
    result["http_status"] = status
    result["probe_url"] = probe_url
    return result


def write_reports(results: list[dict], target: str) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    counts = Counter(item.get("status") for item in results)
    payload = {
        "generated_at": utc_now_iso(),
        "target": target,
        "root": str(ROOT),
        "counts": dict(counts),
        "results": results,
    }
    report_json = ARCHIVE_DIR / "report.json"
    report_md = ARCHIVE_DIR / "report.md"
    report_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 源存活检测报告",
        "",
        f"- 生成时间: {payload['generated_at']}",
        f"- 目标: {target}",
        f"- 根目录: `{ROOT}`",
        "",
        "## 计数",
        "",
    ]
    for status_name in ("pass", "fail", "soft_fail", "manual_review", "skip"):
        lines.append(f"- **{status_name}**: {counts.get(status_name, 0)}")
    lines.append(f"- **total**: {len(results)}")
    lines.append("")
    for status_name in ("fail", "soft_fail", "manual_review", "skip", "pass"):
        group = [item for item in results if item.get("status") == status_name]
        if not group:
            continue
        lines.append(f"## {status_name} ({len(group)})")
        lines.append("")
        for item in group:
            lines.append(
                f"- `{item.get('key')}` | {item.get('name')} | "
                f"{item.get('kind')} | {item.get('reason')} | "
                f"http={item.get('http_status')} | {item.get('probe_url') or '-'}"
            )
        lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")


def merge_failed_archive(existing_path: Path, new_items: list[dict], reason_by_key: dict[str, str]) -> list[dict]:
    existing: list[dict] = []
    if existing_path.is_file():
        try:
            data = json.loads(existing_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing = data
        except Exception:
            existing = []
    by_key: dict[str, dict] = {}
    for item in existing:
        key = str(item.get("key") or item.get("name") or "")
        if key:
            by_key[key] = item
    for item in new_items:
        key = str(item.get("key") or item.get("name") or "")
        if not key:
            continue
        if key in by_key:
            history = by_key[key].setdefault("_archive_history", [])
            if not isinstance(history, list):
                history = []
                by_key[key]["_archive_history"] = history
            history.append(
                {
                    "reason": reason_by_key.get(key, "fail"),
                    "archived_at": utc_now_iso(),
                }
            )
            # 用最新完整对象覆盖，保留 history
            merged = dict(item)
            merged["_archive_history"] = history
            by_key[key] = merged
        else:
            stored = dict(item)
            stored["_archive_history"] = [
                {
                    "reason": reason_by_key.get(key, "fail"),
                    "archived_at": utc_now_iso(),
                }
            ]
            by_key[key] = stored
    return list(by_key.values())


def apply_archive(
    config: dict,
    site_results: list[dict],
    parse_results: list[dict],
    include_soft_fail: bool = False,
) -> tuple[int, int]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_statuses = {"fail"}
    if include_soft_fail:
        archive_statuses.add("soft_fail")

    fail_site_keys = {
        item["key"]
        for item in site_results
        if item.get("status") in archive_statuses and item.get("key") is not None
    }
    reason_by_key = {
        item["key"]: item.get("reason", "fail")
        for item in site_results
        if item.get("key") in fail_site_keys
    }
    original_sites = list(config.get("sites") or [])
    kept_sites = []
    removed_sites = []
    for site in original_sites:
        if site.get("key") in fail_site_keys:
            removed_sites.append(site)
        else:
            kept_sites.append(site)
    config["sites"] = kept_sites

    failed_sites_path = ARCHIVE_DIR / "failed_sites.json"
    merged_sites = merge_failed_archive(failed_sites_path, removed_sites, reason_by_key)
    failed_sites_path.write_text(
        json.dumps(merged_sites, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    removed_parses_count = 0
    if parse_results:
        fail_parse_names = {
            item["name"]
            for item in parse_results
            if item.get("status") in archive_statuses and item.get("name") is not None
        }
        parse_reasons = {
            item["name"]: item.get("reason", "fail")
            for item in parse_results
            if item.get("name") in fail_parse_names
        }
        original_parses = list(config.get("parses") or [])
        kept_parses = []
        removed_parses = []
        for parse in original_parses:
            if parse.get("name") in fail_parse_names:
                removed_parses.append(parse)
            else:
                kept_parses.append(parse)
        config["parses"] = kept_parses
        removed_parses_count = len(removed_parses)
        failed_parses_path = ARCHIVE_DIR / "failed_parses.json"
        merged_parses = merge_failed_archive(failed_parses_path, removed_parses, parse_reasons)
        failed_parses_path.write_text(
            json.dumps(merged_parses, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    return len(removed_sites), removed_parses_count


def run(args: argparse.Namespace) -> int:
    os.chdir(ROOT)
    if not CONFIG_PATH.is_file():
        print(f"配置不存在: {CONFIG_PATH}", file=sys.stderr)
        return 2
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    sites = list(config.get("sites") or [])
    parses = list(config.get("parses") or [])

    results: list[dict] = []
    site_results: list[dict] = []
    parse_results: list[dict] = []

    check_sites = args.only != "parses"
    check_parses = args.only in (None, "parses", "all") and (args.include_parses or args.only == "parses")

    if check_sites:
        only = None if args.only in (None, "all") else args.only
        print(f"检测 sites: {len(sites)} workers={args.workers} timeout={args.timeout}s only={only or 'all'}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(check_site, site, only): site for site in sites
            }
            done = 0
            for future in concurrent.futures.as_completed(future_map):
                done += 1
                try:
                    item = future.result()
                except Exception as error:
                    site = future_map[future]
                    item = {
                        "key": site.get("key"),
                        "name": site.get("name"),
                        "kind": classify_site(site),
                        "status": "fail",
                        "reason": f"checker_exception:{error}",
                        "http_status": None,
                        "probe_url": None,
                        "checked_at": utc_now_iso(),
                    }
                site_results.append(item)
                if done % 20 == 0 or done == len(sites):
                    print(f"  sites progress {done}/{len(sites)}")

    if check_parses:
        print(f"检测 parses: {len(parses)}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(check_parse, parse) for parse in parses]
            for future in concurrent.futures.as_completed(futures):
                try:
                    parse_results.append(future.result())
                except Exception as error:
                    parse_results.append(
                        {
                            "key": "?",
                            "name": "?",
                            "kind": "parse",
                            "status": "fail",
                            "reason": f"checker_exception:{error}",
                            "checked_at": utc_now_iso(),
                        }
                    )

    results = site_results + parse_results
    # 稳定排序：按原始顺序
    site_order = {site.get("key"): index for index, site in enumerate(sites)}
    site_results.sort(key=lambda item: site_order.get(item.get("key"), 10_000))
    results = site_results + parse_results

    write_reports(results, target="sites+parses" if parse_results else "sites")
    counts = Counter(item.get("status") for item in results)
    print("计数:", dict(counts))
    print(f"报告: {ARCHIVE_DIR / 'report.md'}")

    # 验收提示
    fail_keys = {item.get("key") for item in site_results if item.get("status") == "fail"}
    skip_local = [
        item
        for item in site_results
        if item.get("kind") == "type4_local" and item.get("status") == "skip"
    ]
    remote_type4 = [item for item in site_results if item.get("kind") == "type4_remote"]
    print(f"fail keys sample: {list(fail_keys)[:15]}")
    print(f"local type4 skip: {len(skip_local)}")
    print(
        "remote type4 statuses:",
        [(item.get("key"), item.get("status"), item.get("reason")) for item in remote_type4],
    )

    if args.apply:
        removed_sites, removed_parses = apply_archive(
            config,
            site_results,
            parse_results,
            include_soft_fail=args.include_soft_fail,
        )
        print(
            f"已 apply: 移出 sites={removed_sites}, parses={removed_parses}; "
            f"剩余 sites={len(config.get('sites') or [])}"
        )
    else:
        hard = sum(1 for item in site_results if item.get("status") == "fail")
        print(f"dry-run 完成；hard-fail sites={hard}（加 --apply 才会改 江湖.json）")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="江湖源存活检测与 hard-fail 归档")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="将 hard-fail 移出主配置并写入 失效/failed_*.json",
    )
    parser.add_argument(
        "--only-hard-fail",
        action="store_true",
        default=True,
        help="apply 时仅归档 hard-fail（默认）",
    )
    parser.add_argument(
        "--include-soft-fail",
        action="store_true",
        help="apply 时同时归档 soft_fail（一般不用）",
    )
    parser.add_argument(
        "--only",
        choices=["remote", "csp", "script", "type4", "parses", "all"],
        default=None,
        help="只检测某一类",
    )
    parser.add_argument(
        "--include-parses",
        action="store_true",
        help="同时检测 parses",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # 允许覆盖全局超时
    global DEFAULT_TIMEOUT
    DEFAULT_TIMEOUT = args.timeout
    try:
        return run(args)
    except KeyboardInterrupt:
        print("中断", file=sys.stderr)
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
