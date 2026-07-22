# coding=utf-8
# !/usr/bin/python
"""JAVDAY - javday.app（纯 Python）"""
from __future__ import annotations

import re
import sys
from typing import Dict, List
from urllib.parse import quote, urljoin

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.host = "https://javday.app"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.host}/",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
        self.categories = [
            ("新作上市", "new-release"),
            ("有碼", "censored"),
            ("國產AV", "chinese-av"),
            ("無碼流出", "uncensored-leaked"),
            ("糖心VLOG", "txvlog"),
            ("蘿莉社", "luolisheus"),
            ("HongKongDoll", "hongkongdoll"),
        ]
        return self

    def getName(self) -> str:
        return "JAVDAYTV"

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
        return {"list": self._parse_list(self._get(f"{self.host}/"))}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        if page_number == 1:
            url = f"{self.host}/category/{tid}/"
        else:
            url = f"{self.host}/category/{tid}/page/{page_number}/"
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
                r'class="title"[^>]*>(.*?)</',
                r"<h1[^>]*>(.*?)</h1>",
                r"<title>(.*?)</title>",
            ],
            html,
            "JAVDAY",
        )
        title = re.sub(r"<[^>]+>", "", title).strip()
        pic = self._first(
            [
                r'property="og:image"\s+content="([^"]+)"',
                r'background-image:\s*url\(([^)]+)\)',
            ],
            html,
            "",
        )
        if pic and pic.startswith("/"):
            pic = urljoin(self.host + "/", pic)
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
                    "vod_play_from": "JAVDAY",
                    "vod_play_url": "#".join(play_urls),
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        """
        MacCMS 搜索（站点真实可用）：
          列表页：/index.php/search/wd/{keyword}/
          翻页：  /index.php/search/wd/{keyword}/page/{n}/
          联想：  /index.php/ajax/suggest?mid=1&wd=...
        详情页用 /videos/{en}/ （en 为番號去横杠，如 SSIS234）
        """
        keyword = (key or "").strip()
        page_number = max(int(pg or "1"), 1)
        if not keyword:
            return {"list": [], "page": page_number, "pagecount": 1, "limit": 20, "total": 0}

        encoded_keyword = quote(keyword, safe="")
        if page_number <= 1:
            search_url = f"{self.host}/index.php/search/wd/{encoded_keyword}/"
        else:
            search_url = f"{self.host}/index.php/search/wd/{encoded_keyword}/page/{page_number}/"

        html = self._get(search_url)
        videos = self._parse_list(html)

        # 列表页偶发空结果时，回退 suggest（至少给出第一页联想）
        if not videos and page_number <= 1:
            videos = self._search_via_suggest(keyword)

        pagecount = self._parse_search_pagecount(html, page_number, bool(videos))
        return {
            "list": videos,
            "page": page_number,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }

    def _search_via_suggest(self, keyword: str) -> List[Dict[str, str]]:
        suggest_url = (
            f"{self.host}/index.php/ajax/suggest"
            f"?mid=1&wd={quote(keyword, safe='')}&limit=20"
        )
        try:
            response = self.fetch(suggest_url, headers=self.headers, timeout=15)
            payload = response.json()
        except Exception:
            return []
        videos: List[Dict[str, str]] = []
        for item in payload.get("list") or []:
            name = str(item.get("name") or "").strip()
            english_slug = str(item.get("en") or "").strip()
            picture = str(item.get("pic") or "").strip()
            if picture and picture.startswith("/"):
                picture = urljoin(self.host + "/", picture)
            if english_slug:
                detail_url = f"{self.host}/videos/{english_slug}/"
            elif name:
                detail_url = f"{self.host}/videos/{name.replace('-', '')}/"
            else:
                continue
            videos.append(
                {
                    "vod_id": detail_url,
                    "vod_name": name or english_slug,
                    "vod_pic": picture,
                    "vod_remarks": "搜索",
                }
            )
        return videos

    def _parse_search_pagecount(self, html: str, page_number: int, has_videos: bool) -> int:
        page_numbers = [int(item) for item in re.findall(r"/search/[^\"']*/page/(\d+)/?", html)]
        page_numbers += [int(item) for item in re.findall(r"/page/(\d+)/", html)]
        if page_numbers:
            return max(page_numbers)
        if has_videos:
            return page_number + 1
        return max(page_number, 1)

    def playerContent(self, flag: str, play_id: str, vipFlags: List[str]):
        return {"parse": 0, "url": play_id, "header": self.headers}

    def localProxy(self, param: dict):
        return None

    def _get(self, url: str) -> str:
        response = self.fetch(url, headers=self.headers, timeout=15)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _normalize_video_url(self, href: str) -> str:
        """
        统一详情地址：
          /index.php/videos/SSIS234/  -> https://javday.app/videos/SSIS234/
          /videos/SSIS234/            -> https://javday.app/videos/SSIS234/
        """
        full = urljoin(self.host + "/", href)
        match = re.search(r"/videos/([^/?#]+)/?", full)
        if match:
            return f"{self.host}/videos/{match.group(1)}/"
        return full

    def _parse_list(self, html: str) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        # 列表/搜索页同时存在：
        #   /videos/CODE/
        #   /index.php/videos/CODE/
        blocks = re.split(r'(?=<a[^>]+href="[^"]*/videos/)', html)
        for block in blocks:
            href_match = re.search(
                r'href="((?:https?://[^"]+)?(?:/index\.php)?/videos/[^"]+)"',
                block,
            )
            if not href_match:
                continue
            href = self._normalize_video_url(href_match.group(1))
            title = self._first(
                [
                    r'class="title"[^>]*>(.*?)</',
                    r'title="([^"]+)"',
                ],
                block,
                "",
            )
            title = re.sub(r"<[^>]+>", "", title).strip()
            pic = self._first(
                [
                    r'background-image:\s*url\(([^)]+)\)',
                    r'data-src="([^"]+)"',
                    r'src="([^"]+)"',
                ],
                block,
                "",
            )
            if pic and pic.startswith("/"):
                pic = urljoin(self.host + "/", pic)
            remark = self._first([r'class="number"[^>]*>(.*?)</'], block, "")
            remark = re.sub(r"<[^>]+>", "", remark).strip()
            if not title:
                title = href.rstrip("/").split("/")[-1]
            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                }
            )
        # 去重
        unique: List[Dict[str, str]] = []
        seen = set()
        for item in videos:
            if item["vod_id"] in seen:
                continue
            seen.add(item["vod_id"])
            unique.append(item)
        return unique

    @staticmethod
    def _first(patterns: List[str], text: str, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.S | re.I)
            if match:
                return match.group(1).strip()
        return default
