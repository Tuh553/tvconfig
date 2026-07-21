#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""准备上传到 GitHub 的配置：活跃 sites + 失效源注释字段。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "_github_upload"
CONFIG_PATH = ROOT / "江湖.json"
FAILED_PATH = ROOT / "失效" / "failed_sites.json"
REPORT_PATH = ROOT / "失效" / "report.json"

SKIP_DIR_NAMES = {
    "node_modules",
    ".git",
    "_github_upload",
    "__pycache__",
    ".cursor",
    "agent-tools",
    "agent-transcripts",
}
SKIP_FILE_NAMES = {
    "$null)",
}
SKIP_SUFFIXES = {".pyc"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_local_refs(config: dict) -> set[str]:
    refs: set[str] = set()

    def add_ref(value) -> None:
        if isinstance(value, str) and value.startswith("./"):
            relative = value[2:].split("?", 1)[0].split("#", 1)[0]
            if relative:
                refs.add(relative)

    add_ref(config.get("spider"))
    for site in config.get("sites") or []:
        if not isinstance(site, dict):
            continue
        for field_name in ("api", "ext", "jar", "indexs", "click"):
            add_ref(site.get(field_name))
    for parse in config.get("parses") or []:
        if isinstance(parse, dict):
            add_ref(parse.get("url"))
    for live in config.get("lives") or []:
        if not isinstance(live, dict):
            continue
        add_ref(live.get("url"))
        for channel in live.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            urls = channel.get("urls") or []
            if isinstance(urls, list):
                for url in urls:
                    add_ref(url)
            add_ref(channel.get("url"))
    return refs


def is_skipped_relative(relative_path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in relative_path.parts):
        return True
    if relative_path.name in SKIP_FILE_NAMES:
        return True
    if relative_path.suffix in SKIP_SUFFIXES:
        return True
    return False


def copy_tree_filtered(src_root: Path, dst_root: Path) -> None:
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True)

    for path in src_root.rglob("*"):
        relative_path = path.relative_to(src_root)
        if is_skipped_relative(relative_path):
            continue
        target = dst_root / relative_path
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main() -> None:
    config = load_json(CONFIG_PATH)
    # 若已含 _失效源，以 sites 为准；否则从 failed 合并注释
    failed = []
    if FAILED_PATH.is_file():
        failed = load_json(FAILED_PATH)
    if isinstance(config.get("_失效源"), list) and config["_失效源"]:
        # 刷新注释
        failed = config["_失效源"]

    reason_by_key = {}
    if REPORT_PATH.is_file():
        report = load_json(REPORT_PATH)
        for item in report.get("results") or []:
            if item.get("status") == "fail" and item.get("key") is not None:
                reason_by_key[item["key"]] = {
                    "status": item.get("status"),
                    "reason": item.get("reason"),
                    "kind": item.get("kind"),
                    "probe_url": item.get("probe_url"),
                    "http_status": item.get("http_status"),
                    "checked_at": item.get("checked_at"),
                }

    annotated_failed = []
    for site in failed:
        if not isinstance(site, dict):
            continue
        item = dict(site)
        # 去掉仅本地归档用字段也可保留
        meta = reason_by_key.get(item.get("key"), {})
        item["_失效注释"] = item.get("_失效注释") or meta.get("reason") or "hard-fail"
        if meta:
            item["_检测详情"] = meta
        annotated_failed.append(item)

    # 标准 JSON：播放器读 sites；未知字段 _* 作注释归档
    out_config = {
        key: value
        for key, value in config.items()
        if not str(key).startswith("_")
    }
    out_config["_说明"] = (
        "sites=当前可用/保留源；"
        "_失效源_注释=失效摘要；"
        "_失效源=完整失效 site 对象（已从 sites 移出，便于恢复）；"
        "播放器一般忽略未知顶层字段。"
    )
    out_config["_失效源_注释"] = [
        "{key} | {name} | {reason}".format(
            key=site.get("key"),
            name=site.get("name"),
            reason=site.get("_失效注释") or "hard-fail",
        )
        for site in annotated_failed
    ]
    out_config["_失效源"] = annotated_failed

    # 写回项目内 江湖.json（带注释字段）
    CONFIG_PATH.write_text(
        json.dumps(out_config, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    comment_md = ROOT / "失效" / "失效源注释.md"
    lines = [
        "# 失效源注释（检测归档）",
        "",
        f"共 **{len(annotated_failed)}** 条 hard-fail，已从 `sites` 移出。",
        "",
        "完整对象：`江湖.json` → `_失效源`，以及 `失效/failed_sites.json`。",
        "",
        "| key | name | 原因 |",
        "|-----|------|------|",
    ]
    for site in annotated_failed:
        reason = str(site.get("_失效注释") or "").replace("|", "\\|")
        lines.append(
            f"| `{site.get('key')}` | {site.get('name')} | {reason} |"
        )
    comment_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 同步 failed_sites.json 注释
    if FAILED_PATH.parent.is_dir():
        FAILED_PATH.write_text(
            json.dumps(annotated_failed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # 全量拷贝到 staging（排除 node_modules 等）
    copy_tree_filtered(ROOT, STAGING)
    # staging 内保证 江湖.json 为最新
    (STAGING / "江湖.json").write_text(
        json.dumps(out_config, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    # README
    readme = f"""# tvconfig

TVBox 配置：江湖源（已做存活检测）

- 主配置：[`江湖.json`](./江湖.json)
- 活跃 `sites`：**{len(out_config.get('sites') or [])}**
- 失效归档（注释字段 `_失效源` / `_失效源_注释`）：**{len(annotated_failed)}**
- 检测报告：[`失效/report.md`](./失效/report.md)
- 失效列表：[`失效/失效源注释.md`](./失效/失效源注释.md)
- 检测脚本：[`tools/source_health_check.py`](./tools/source_health_check.py)

## 说明

1. `sites` 内为当前保留源（pass / soft_fail / manual_review / skip）。
2. 标准 JSON **不支持** `//` 注释，故失效源放在顶层 `_失效源`、`_失效源_注释`（播放器通常忽略未知字段）。
3. 恢复某源：将 `_失效源` 中对象移回 `sites` 即可。
4. 未验证播放链路；存活标准为分类/首页可连通。

## 本地复检

```bash
python tools/source_health_check.py
python tools/source_health_check.py --apply
```
"""
    (STAGING / "README.md").write_text(readme, encoding="utf-8")

    refs = collect_local_refs(out_config)
    missing = [rel for rel in sorted(refs) if not (ROOT / rel).is_file()]
    print(f"active_sites={len(out_config.get('sites') or [])}")
    print(f"failed_annotated={len(annotated_failed)}")
    print(f"local_refs={len(refs)} missing={len(missing)}")
    for rel in missing[:20]:
        print(f"MISSING {rel}")
    print(f"staging={STAGING}")


if __name__ == "__main__":
    main()
