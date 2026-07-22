# coding=utf-8
# !/usr/bin/python
"""MissAV.app MacCMS 壳站（纯 Python）"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, List
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.host = "https://missav.app"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.host}/",
        }
        self.categories = [
            ("国产", "20"),
            ("日本有码", "21"),
            ("日本无码", "22"),
            ("中文字幕", "28"),
            ("欧美", "23"),
            ("动漫", "24"),
            ("伦理", "25"),
        ]
        return self

    def getName(self) -> str:
        return "MissAV"

    def isVideoFormat(self, url: str) -> bool:
        return any(token in (url or "") for token in [".m3u8", ".mp4"])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter: bool):
        return {
            "class": [{"type_name": name, "type_id": type_id} for name, type_id in self.categories],
            "list": self._parse_list(self._get(f"{self.host}/")),
        }

    def homeVideoContent(self):
        return {"list": self._parse_list(self._get(f"{self.host}/label/new/"))}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        if page_number <= 1:
            url = f"{self.host}/vodtype/{tid}/"
        else:
            url = f"{self.host}/vodtype/{tid}-{page_number}/"
        videos = self._parse_list(self._get(url))
        return {
            "list": videos,
            "page": page_number,
            "pagecount": page_number + (1 if videos else 0),
            "limit": 24,
            "total": page_number * 24,
        }

    def detailContent(self, array: List[str]):
        detail_url = array[0]
        if not detail_url.startswith("http"):
            detail_url = urljoin(self.host + "/", detail_url)
        # 详情页可能是 /voddetail/ 或 /vodplay/
        html = self._get(detail_url)
        if "/voddetail/" in detail_url and "player_aaaa" not in html:
            play_link = self._first([r'href="(/vodplay/[^"]+)"'], html, "")
            if play_link:
                detail_url = urljoin(self.host + "/", play_link)
                html = self._get(detail_url)
        title = self._first(
            [
                r'"vod_name"\s*:\s*"([^"]+)"',
                r"<h1[^>]*>(.*?)</h1>",
                r"<title>(.*?)</title>",
            ],
            html,
            "MissAV",
        )
        title = re.sub(r"<[^>]+>", "", title).strip()
        try:
            title = json.loads(f'"{title}"')
        except Exception:
            title = title.encode("utf-8").decode("unicode_escape", errors="ignore")
        pic = self._first(
            [
                r'property="og:image"\s+content="([^"]+)"',
                r'data-src="(https?://[^"]+)"',
            ],
            html,
            "",
        )
        play_url = self._extract_player_url(html)
        if not play_url:
            play_url = detail_url
        return {
            "list": [
                {
                    "vod_id": detail_url,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_play_from": "MissAV",
                    "vod_play_url": f"正片${play_url}",
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        page_number = max(int(pg or "1"), 1)
        url = f"{self.host}/vodsearch/{quote(key)}-------------/"
        if page_number > 1:
            url = f"{self.host}/vodsearch/{quote(key)}----------{page_number}---/"
        return {"list": self._parse_list(self._get(url)), "page": page_number}

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        play_url = play_id
        if play_url.startswith("http") and ".m3u8" not in play_url and ".mp4" not in play_url:
            html = self._get(play_url)
            extracted = self._extract_player_url(html)
            if extracted:
                play_url = extracted
        return {"parse": 0, "url": play_url, "header": self.headers}

    def localProxy(self, param: dict):
        return None

    def _get(self, url: str) -> str:
        response = self.fetch(url, headers=self.headers, timeout=15)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        blocks = re.split(r'(?=class="thumbnail group")', html)
        for block in blocks:
            if "thumbnail group" not in block:
                continue
            href = self._first(
                [
                    r'href="(/vodplay/[^"]+)"',
                    r'href="(/voddetail/[^"]+)"',
                    r'href="([^"]+)"',
                ],
                block,
                "",
            )
            if not href or href.startswith("javascript"):
                continue
            detail_url = urljoin(self.host + "/", href)
            title = self._first(
                [
                    r'class="[^"]*text-nord4[^"]*"[^>]*>(.*?)</',
                    r'title="([^"]+)"',
                    r'alt="([^"]+)"',
                ],
                block,
                "",
            )
            title = re.sub(r"<[^>]+>", "", title).strip()
            pic = self._first(
                [
                    r'data-src="(https?://[^"]+)"',
                    r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                ],
                block,
                "",
            )
            if not title:
                title = detail_url.rstrip("/").split("/")[-1]
            videos.append(
                {
                    "vod_id": detail_url,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": "MissAV",
                }
            )
        unique: List[Dict[str, str]] = []
        seen = set()
        for item in videos:
            if item["vod_id"] in seen:
                continue
            seen.add(item["vod_id"])
            unique.append(item)
        return unique

    def _extract_player_url(self, html: str) -> str:
        match = re.search(r"var\s+player_aaaa\s*=\s*(\{.*?\})\s*;", html, flags=re.S)
        if match:
            raw = match.group(1)
            try:
                data = json.loads(raw)
            except Exception:
                try:
                    data = json.loads(raw.encode("utf-8").decode("unicode_escape"))
                except Exception:
                    data = {}
            url = str(data.get("url") or "").replace("\\/", "/")
            if url:
                return url
        match = re.search(r'"url"\s*:\s*"(https?:\\?/\\?/[^"]+\.m3u8[^"]*)"', html)
        if match:
            return match.group(1).replace("\\/", "/")
        match = re.search(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", html)
        return match.group(0).replace("\\/", "/") if match else ""

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
