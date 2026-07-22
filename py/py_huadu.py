# coding=utf-8
# !/usr/bin/python
"""花都影视 - hdys.pro（纯 Python，不依赖 jar/XBPQ）"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.host = "https://hdys.pro"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": f"{self.host}/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.categories = [
            ("UP精选乱伦", "cate3"),
            ("黑瓜剧场", "cate5"),
            ("国产AV", "cate6"),
            ("无码流出", "cate7"),
            ("原创自制", "cate8"),
            ("AI换脸", "cate9"),
            ("户外露出", "cate10"),
            ("黑人专区", "cate11"),
            ("强奸迷奸", "cate12"),
            ("OnlyFans", "cate14"),
            ("日本有码", "cate21"),
            ("日本无码", "cate22"),
        ]
        return self

    def getName(self) -> str:
        return "花都影视"

    def isVideoFormat(self, url: str) -> bool:
        return any(token in (url or "") for token in [".m3u8", ".mp4"])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter: bool):
        return {
            "class": [{"type_name": name, "type_id": type_id} for name, type_id in self.categories],
            "filters": {},
            "list": self._parse_list(self._get(f"{self.host}/")),
        }

    def homeVideoContent(self):
        return {"list": self._parse_list(self._get(f"{self.host}/"))}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        html = self._get(f"{self.host}/category/{tid}/{page_number}/")
        videos = self._parse_list(html)
        return {
            "list": videos,
            "page": page_number,
            "pagecount": page_number + (1 if videos else 0),
            "limit": 24,
            "total": page_number * 24 + len(videos),
        }

    def detailContent(self, array: List[str]):
        video_id = array[0]
        detail_url = video_id if video_id.startswith("http") else f"{self.host}/video/{video_id.strip('/')}/"
        html = self._get(detail_url)
        title = self._first(
            [
                r'<h1[^>]*>(.*?)</h1>',
                r'property="og:title"\s+content="([^"]+)"',
                r"<title>(.*?)</title>",
            ],
            html,
            "花都影视",
        )
        title = re.sub(r"<[^>]+>", "", title).strip()
        pic = self._first(
            [
                r'property="og:image"\s+content="([^"]+)"',
                r'data-original="(https?://[^"]+)"',
            ],
            html,
            "",
        )
        play_urls = self._extract_play_urls(html)
        if not play_urls:
            play_urls = [f"原页${detail_url}"]
        return {
            "list": [
                {
                    "vod_id": detail_url,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_content": title,
                    "vod_play_from": "花都",
                    "vod_play_url": "#".join(play_urls),
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        """
        站方真实搜索：
          /search/{keyword}/
          /search/{keyword}/{page}/
        """
        keyword = (key or "").strip()
        page_number = max(int(pg or "1"), 1)
        if not keyword:
            return {"list": [], "page": page_number, "pagecount": 1, "limit": 24, "total": 0}

        encoded_keyword = quote(keyword, safe="")
        if page_number <= 1:
            search_url = f"{self.host}/search/{encoded_keyword}/"
        else:
            search_url = f"{self.host}/search/{encoded_keyword}/{page_number}/"

        html = self._get(search_url)
        videos = self._parse_list(html)
        pagecount = self._parse_search_pagecount(html, encoded_keyword, page_number, bool(videos))
        return {
            "list": videos,
            "page": page_number,
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
        }

    def _parse_search_pagecount(
        self,
        html: str,
        encoded_keyword: str,
        page_number: int,
        has_videos: bool,
    ) -> int:
        # 分页链接形如 /search/关键词/234/
        page_numbers = [
            int(item)
            for item in re.findall(
                rf"/search/{re.escape(encoded_keyword)}/(\d+)/",
                html,
            )
        ]
        if page_numbers:
            return max(page_numbers)
        if has_videos:
            return page_number + 1
        return max(page_number, 1)

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        play_url = play_id
        if play_url.startswith("http") and ".m3u8" not in play_url and ".mp4" not in play_url:
            html = self._get(play_url)
            extracted = self._extract_play_urls(html)
            if extracted:
                play_url = extracted[0].split("$", 1)[-1]
        return {
            "parse": 0,
            "url": play_url,
            "header": self.headers,
        }

    def localProxy(self, param: Dict[str, Any]):
        return None

    def _get(self, url: str) -> str:
        response = self.fetch(url, headers=self.headers, timeout=15)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        pattern = re.compile(
            r'class="stui-vodlist__item".*?href="(/video/[^"]+)".*?title="([^"]+)".*?data-original="([^"]+)"',
            flags=re.S,
        )
        for href, title, pic in pattern.findall(html):
            videos.append(
                {
                    "vod_id": urljoin(self.host + "/", href),
                    "vod_name": title.strip(),
                    "vod_pic": pic.strip(),
                    "vod_remarks": "花都",
                }
            )
        if videos:
            return videos
        # fallback
        for href, title in re.findall(r'href="(/video/\d+/)"[^>]*title="([^"]+)"', html):
            videos.append(
                {
                    "vod_id": urljoin(self.host + "/", href),
                    "vod_name": title.strip(),
                    "vod_pic": "",
                    "vod_remarks": "花都",
                }
            )
        return videos

    def _extract_play_urls(self, html: str) -> List[str]:
        relative_path = self._first(
            [
                r'data-url="(/video/[^"]+\.m3u8)"',
                r'["\'](/video/\d{4}-\d{2}-\d{2}/[^"\']+\.m3u8)["\']',
            ],
            html,
            "",
        )
        cdn_lines = self._parse_cdn_lines(html)
        play_urls: List[str] = []
        seen = set()
        if relative_path and cdn_lines:
            for index, line in enumerate(cdn_lines):
                cdn = str(line.get("cdnLine") or "").rstrip("/")
                name = str(line.get("lineName") or line.get("cdnName") or f"线路{index + 1}")
                if not cdn:
                    continue
                full_url = cdn + relative_path
                if full_url in seen:
                    continue
                seen.add(full_url)
                play_urls.append(f"{name}${full_url}")
        absolute = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", html)
        for index, url in enumerate(absolute):
            cleaned = url.replace("\\/", "/")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            play_urls.append(f"直链{index + 1}${cleaned}")
        return play_urls

    def _parse_cdn_lines(self, html: str) -> List[Dict[str, Any]]:
        match = re.search(r"var\s+cdn_lines\s*=\s*'(\[.*?\])'\s*;", html, flags=re.S)
        if not match:
            return []
        raw = match.group(1)
        try:
            return json.loads(raw.encode("utf-8").decode("unicode_escape"))
        except Exception:
            try:
                return json.loads(raw.replace("\\/", "/"))
            except Exception:
                return []

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
