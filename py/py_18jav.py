# coding=utf-8
# !/usr/bin/python
"""18JAV.tv（纯 Python）"""
from __future__ import annotations

import re
import sys
from typing import Dict, List
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.host = "https://18jav.tv"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": f"{self.host}/",
        }
        self.categories = [
            ("最新", "latest-updates"),
            ("热门", "hot"),
            ("中文字幕", "categories/chinese-subtitle"),
            ("无码", "categories/uncensored"),
            ("台湾AV", "categories/taiwan-av"),
            ("角色剧情", "categories/roleplay"),
            ("制服", "categories/uniform"),
        ]
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
            "class": [{"type_name": name, "type_id": type_id} for name, type_id in self.categories],
            "list": self._parse_list(self._get(f"{self.host}/latest-updates")),
        }

    def homeVideoContent(self):
        return {"list": self._parse_list(self._get(f"{self.host}/latest-updates"))}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        base = f"{self.host}/{tid.strip('/')}"
        url = base if page_number <= 1 else f"{base}/{page_number}/"
        # 兼容 query 类分类
        if "?" in tid:
            url = f"{self.host}/{tid}&from={page_number}" if page_number > 1 else f"{self.host}/{tid}"
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
        html = self._get(detail_url)
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
        url = f"{self.host}/search/{quote(key)}/"
        if page_number > 1:
            url = f"{self.host}/search/{quote(key)}/{page_number}/"
        return {"list": self._parse_list(self._get(url)), "page": page_number}

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        return {"parse": 0, "url": play_id, "header": self.headers}

    def localProxy(self, param: dict):
        return None

    def _get(self, url: str) -> str:
        response = self.fetch(url, headers=self.headers, timeout=15)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        hrefs = re.findall(r'href="(https?://18jav\.tv/videos/[^"]+)"', html)
        if not hrefs:
            hrefs = [urljoin(self.host + "/", path) for path in re.findall(r'href="(/videos/[^"]+)"', html)]
        # 去重保序
        unique_hrefs = []
        seen = set()
        for href in hrefs:
            if href in seen:
                continue
            seen.add(href)
            unique_hrefs.append(href)
        # 用邻近块取标题图片
        for href in unique_hrefs:
            block_match = re.search(
                rf'href="{re.escape(href)}".{{0,800}}?',
                html,
                flags=re.S,
            )
            block = block_match.group(0) if block_match else ""
            # 扩大上下文
            pos = html.find(href)
            if pos >= 0:
                block = html[max(0, pos - 200) : pos + 900]
            title = self._first(
                [
                    r'class="title"[^>]*>(.*?)</',
                    r'title="([^"]+)"',
                    r'alt="([^"]+)"',
                ],
                block,
                href.rstrip("/").split("/")[-1],
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
            remark = self._first([r'class="label"[^>]*>(.*?)</'], block, "")
            remark = re.sub(r"<[^>]+>", "", remark).strip()
            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                }
            )
        return videos

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
