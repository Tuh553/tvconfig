# coding=utf-8
# !/usr/bin/python
"""小黄书 xchina（纯 Python；遇 Cloudflare 时返回提示项）"""
from __future__ import annotations

import re
import sys
from typing import Dict, List
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.hosts = [
            "https://xchina.fit",
            "https://xchina.co",
            "https://xchina.io",
            "https://xchina.xyz",
        ]
        self.host = self.hosts[0]
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": f"{self.host}/",
        }
        return self

    def getName(self) -> str:
        return "小黄书"

    def isVideoFormat(self, url: str) -> bool:
        return any(token in (url or "") for token in [".m3u8", ".mp4"])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter: bool):
        html = self._get_any("/categories.html")
        classes = self._parse_categories(html)
        if not classes:
            classes = [{"type_name": "视频", "type_id": "video"}]
        videos = self._parse_list(html) if html else self._blocked_list()
        return {"class": classes, "list": videos}

    def homeVideoContent(self):
        html = self._get_any("/")
        return {"list": self._parse_list(html) if html else self._blocked_list()}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        if tid == "video":
            path = f"/videos/{page_number}.html" if page_number > 1 else "/videos.html"
        else:
            path = f"/videos/series-{tid}/{page_number}.html"
        html = self._get_any(path)
        videos = self._parse_list(html) if html else self._blocked_list()
        return {
            "list": videos,
            "page": page_number,
            "pagecount": page_number + (1 if videos and videos[0].get("vod_id") != "blocked" else 0),
            "limit": 24,
            "total": page_number * 24,
        }

    def detailContent(self, array: List[str]):
        detail_url = array[0]
        if detail_url == "blocked":
            return {
                "list": [
                    {
                        "vod_id": "blocked",
                        "vod_name": "小黄书被 Cloudflare 拦截",
                        "vod_pic": "",
                        "vod_content": "当前网络无法直连 xchina，请使用可访问该站的代理环境后重试。",
                        "vod_play_from": "提示",
                        "vod_play_url": "说明$https://xchina.fit/",
                    }
                ]
            }
        if not detail_url.startswith("http"):
            detail_url = urljoin(self.host + "/", detail_url)
        html = self._get(detail_url)
        if not html:
            return self.detailContent(["blocked"])
        title = self._first(
            [
                r'property="og:title"\s+content="([^"]+)"',
                r'name="twitter:title"\s+content="([^"]+)"',
                r"<title>(.*?)</title>",
            ],
            html,
            "小黄书",
        )
        title = re.sub(r"<[^>]+>", "", title).strip()
        pic = self._first(
            [
                r'property="og:image"\s+content="([^"]+)"',
                r"background-image:url\('([^']+)'\)",
            ],
            html,
            "",
        )
        m3u8_list = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", html)
        mp4_list = re.findall(r"https?://[^\"'\s]+\.mp4[^\"'\s]*", html)
        play_urls = []
        for index, url in enumerate(m3u8_list + mp4_list):
            play_urls.append(f"线路{index + 1}${url}")
        if not play_urls:
            play_urls = [f"原页${detail_url}"]
        return {
            "list": [
                {
                    "vod_id": detail_url,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_play_from": "小黄书",
                    "vod_play_url": "#".join(play_urls),
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        page_number = max(int(pg or "1"), 1)
        path = f"/videos/series-id/{page_number}.html?wd={quote(key)}"
        html = self._get_any(path)
        return {"list": self._parse_list(html) if html else self._blocked_list(), "page": page_number}

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        return {"parse": 1 if "xchina." in play_id else 0, "url": play_id, "header": self.headers}

    def localProxy(self, param: dict):
        return None

    def _get_any(self, path: str) -> str:
        for host in self.hosts:
            html = self._get(urljoin(host + "/", path.lstrip("/")))
            if html and "Just a moment" not in html and "cf-browser-verification" not in html:
                self.host = host
                self.headers["Referer"] = f"{host}/"
                return html
        return ""

    def _get(self, url: str) -> str:
        try:
            response = self.fetch(url, headers=self.headers, timeout=12)
            if response.status_code >= 400:
                return ""
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except Exception:
            return ""

    def _parse_categories(self, html: str) -> List[Dict[str, str]]:
        if not html:
            return []
        classes: List[Dict[str, str]] = []
        for block in re.findall(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", html, flags=re.S):
            href, body = block
            type_id_match = re.search(r"/videos/series-([^.]+)\.html", href)
            if not type_id_match:
                continue
            title = re.sub(r"<[^>]+>", "", body).strip()
            if not title:
                title = type_id_match.group(1)
            classes.append({"type_name": title, "type_id": type_id_match.group(1)})
        unique = []
        seen = set()
        for item in classes:
            if item["type_id"] in seen:
                continue
            seen.add(item["type_id"])
            unique.append(item)
        return unique[:40]

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        if not html:
            return self._blocked_list()
        videos: List[Dict[str, str]] = []
        blocks = re.findall(r'item video">(.*?)</a', html, flags=re.S)
        for block in blocks:
            href = self._first([r'href="([^"]+)"'], block, "")
            title = self._first([r'title="([^"]+)"'], block, "")
            pic = self._first([r"background-image:url\('([^']+)'\)"], block, "")
            if not href:
                continue
            videos.append(
                {
                    "vod_id": urljoin(self.host + "/", href),
                    "vod_name": title or href,
                    "vod_pic": pic,
                    "vod_remarks": "小黄书",
                }
            )
        return videos or self._blocked_list()

    @staticmethod
    def _blocked_list() -> List[Dict[str, str]]:
        return [
            {
                "vod_id": "blocked",
                "vod_name": "小黄书当前网络被 Cloudflare 拦截",
                "vod_pic": "",
                "vod_remarks": "需代理",
            }
        ]

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
