# coding=utf-8
# !/usr/bin/python
"""18JAV.tv（纯 Python）

翻页说明：
站点为 KVS，分页走 AJAX：
  /{path}?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=...&from={page}
AJAX 片段里的视频链接多为相对路径 /videos/xxx。
"""
from __future__ import annotations

import re
import sys
from typing import Dict, List, Tuple
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    BLOCK_ID = "list_videos_common_videos_list"

    def init(self, extend: str = ""):
        self.host = "https://18jav.tv"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": f"{self.host}/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
        }
        # 用 path 作为 type_id；(显示名, path, sort_by)
        self.categories: List[Tuple[str, str, str]] = [
            ("最新", "latest-updates", "release_at"),
            ("热门", "hot", "views"),
            ("中文字幕", "categories/chinese-subtitle", "release_at"),
            ("无码", "categories/uncensored", "release_at"),
            ("台湾AV", "categories/taiwan-av", "release_at"),
            ("角色剧情", "categories/roleplay", "release_at"),
            ("制服", "categories/uniform", "release_at"),
        ]
        self.sort_by_map = {path: sort_by for _, path, sort_by in self.categories}
        return self

    def getName(self) -> str:
        return "18JAV"

    def isVideoFormat(self, url: str) -> bool:
        return any(token in (url or "") for token in [".m3u8", ".mp4"])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter: bool):
        return {
            "class": [{"type_name": name, "type_id": path} for name, path, _ in self.categories],
            "list": self._load_page("latest-updates", "release_at", 1)[0],
        }

    def homeVideoContent(self):
        videos, _ = self._load_page("latest-updates", "release_at", 1)
        return {"list": videos}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        path = (tid or "latest-updates").strip("/")
        sort_by = self.sort_by_map.get(path, "release_at")
        videos, pagecount = self._load_page(path, sort_by, page_number)
        return {
            "list": videos,
            "page": page_number,
            "pagecount": max(pagecount, page_number + (1 if videos else 0)),
            "limit": 12,
            "total": max(pagecount, page_number) * 12,
        }

    def detailContent(self, array: List[str]):
        detail_url = array[0]
        if not detail_url.startswith("http"):
            detail_url = urljoin(self.host + "/", detail_url.lstrip("/"))
        html = self._get(detail_url, ajax=False)
        title = self._first(
            [
                r"<h1[^>]*>(.*?)</h1>",
                r'property="og:title"\s+content="([^"]+)"',
                r"<title>(.*?)</title>",
            ],
            html,
            "18JAV",
        )
        title = re.sub(r"<[^>]+>", "", title).strip()
        pic = self._first(
            [
                r'property="og:image"\s+content="([^"]+)"',
                r'data-src="(https?://[^"]+)"',
            ],
            html,
            "",
        )
        m3u8_list = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", html)
        play_urls = []
        seen = set()
        for index, url in enumerate(m3u8_list):
            cleaned = url.replace("\\/", "/")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            play_urls.append(f"线路{index + 1}${cleaned}")
        if not play_urls:
            play_urls = [f"原页${detail_url}"]
        return {
            "list": [
                {
                    "vod_id": detail_url,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_play_from": "18JAV",
                    "vod_play_url": "#".join(play_urls),
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        page_number = max(int(pg or "1"), 1)
        path = f"search/{quote(key)}"
        if page_number <= 1:
            html = self._get(f"{self.host}/{path}/", ajax=False)
            videos = self._parse_list(html)
            pagecount = self._parse_pagecount(html)
        else:
            videos, pagecount = self._load_page(path, "release_at", page_number)
        return {
            "list": videos,
            "page": page_number,
            "pagecount": pagecount,
            "limit": 12,
            "total": pagecount * 12,
        }

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        return {
            "parse": 0,
            "url": play_id,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": f"{self.host}/",
            },
        }

    def localProxy(self, param: dict):
        return None

    def _load_page(self, path: str, sort_by: str, page_number: int) -> Tuple[List[Dict[str, str]], int]:
        path = path.strip("/")
        if page_number <= 1:
            html = self._get(f"{self.host}/{path}", ajax=False)
        else:
            # KVS AJAX 分页（与站点 site.js 一致）
            params = {
                "mode": "async",
                "function": "get_block",
                "block_id": self.BLOCK_ID,
                "sort_by": sort_by,
                "from": str(page_number),
            }
            html = self._get(f"{self.host}/{path}", ajax=True, params=params)
            # 个别分类若返回空，再试 from 补零
            if not self._parse_list(html):
                params["from"] = f"{page_number:02d}"
                html = self._get(f"{self.host}/{path}", ajax=True, params=params)
        videos = self._parse_list(html)
        pagecount = self._parse_pagecount(html)
        if pagecount < page_number and videos:
            pagecount = page_number + 1
        if pagecount < 1:
            pagecount = 1
        return videos, pagecount

    def _get(self, url: str, ajax: bool = False, params: dict | None = None) -> str:
        headers = dict(self.headers)
        if not ajax:
            headers.pop("X-Requested-With", None)
        response = self.fetch(url, headers=headers, timeout=15, params=params)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        # 同时兼容完整链接与 AJAX 相对链接
        hrefs = re.findall(r'href="((?:https://18jav\.tv)?/videos/[^"]+)"', html)
        unique_hrefs: List[str] = []
        seen = set()
        for href in hrefs:
            full = href if href.startswith("http") else urljoin(self.host + "/", href.lstrip("/"))
            if full in seen:
                continue
            seen.add(full)
            unique_hrefs.append(full)

        # 按卡片解析，避免封面 <a> 把时长当成标题
        card_pattern = re.compile(
            r'class="video-img-box[^"]*".*?'
            r'href="((?:https://18jav\.tv)?/videos/[^"]+)".*?'
            r'data-src="(https?://[^"]+)".*?'
            r'class="label"[^>]*>(.*?)</span>.*?'
            r'class="title"[^>]*>\s*<a[^>]*>(.*?)</a>',
            flags=re.S | re.I,
        )
        for href, pic, remark, title in card_pattern.findall(html):
            full = href if href.startswith("http") else urljoin(self.host + "/", href.lstrip("/"))
            title_text = re.sub(r"<[^>]+>", "", title).strip()
            remark_text = re.sub(r"<[^>]+>", "", remark).strip()
            if full in seen:
                # seen 已在上面用于 href 去重，这里用另一集合
                pass
            videos.append(
                {
                    "vod_id": full,
                    "vod_name": title_text or full.rstrip("/").split("/")[-1],
                    "vod_pic": pic,
                    "vod_remarks": remark_text,
                }
            )
        if videos:
            # 卡片去重
            unique_videos: List[Dict[str, str]] = []
            seen_ids = set()
            for item in videos:
                if item["vod_id"] in seen_ids:
                    continue
                seen_ids.add(item["vod_id"])
                unique_videos.append(item)
            return unique_videos

        # fallback：仅有链接时
        for href in unique_hrefs:
            code = href.rstrip("/").split("/")[-1]
            title = self._first(
                [
                    rf'class="title"[^>]*>\s*<a[^>]+href="[^"]*{re.escape(code)}"[^>]*>(.*?)</a>',
                    rf'<a[^>]+href="[^"]*{re.escape(code)}"[^>]*>([^<]{3,80})</a>',
                ],
                html,
                code,
            )
            title = re.sub(r"<[^>]+>", "", title).strip() or code
            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": "",
                    "vod_remarks": "",
                }
            )
        return videos

    def _parse_pagecount(self, html: str) -> int:
        # data-parameters="sort_by:release_at;from:1417"
        pages = [int(item) for item in re.findall(r"from:(\d+)", html)]
        if pages:
            return max(pages)
        # 普通分页数字
        nums = [int(item) for item in re.findall(r'class="page-link"[^>]*>\s*(\d+)\s*<', html)]
        if nums:
            return max(nums)
        return 1

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
