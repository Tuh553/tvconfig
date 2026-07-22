# coding=utf-8
# !/usr/bin/python
"""NOWAV / pigav PeerTube API（纯 Python）"""
from __future__ import annotations

import sys
from typing import Any, Dict, List
from urllib.parse import quote

from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend: str = ""):
        self.host = "https://pigav.ws"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.host}/",
        }
        self.categories = [
            ("全部", "all"),
            ("日韓線上", "20"),
            ("亞洲線上", "21"),
            ("自拍線上", "22"),
            ("歐美線上", "23"),
            ("動漫線上", "24"),
            ("寫真系列", "25"),
        ]
        return self

    def getName(self) -> str:
        return "NOWAV"

    def isVideoFormat(self, url: str) -> bool:
        return any(token in (url or "") for token in [".m3u8", ".mp4"])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter: bool):
        return {
            "class": [{"type_name": name, "type_id": type_id} for name, type_id in self.categories],
            "list": self._list_videos(category_id="all", page=1),
        }

    def homeVideoContent(self):
        return {"list": self._list_videos(category_id="all", page=1)}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: dict):
        page_number = max(int(pg or "1"), 1)
        videos = self._list_videos(category_id=tid, page=page_number)
        return {
            "list": videos,
            "page": page_number,
            "pagecount": page_number + (1 if videos else 0),
            "limit": 24,
            "total": page_number * 24,
        }

    def detailContent(self, array: List[str]):
        video_id = array[0]
        data = self._get_json(f"{self.host}/api/v1/videos/{video_id}")
        name = str(data.get("name") or video_id)
        pic = str(data.get("thumbnailPath") or "")
        if pic and pic.startswith("/"):
            pic = self.host + pic
        description = str(data.get("description") or data.get("truncatedDescription") or "")
        play_urls: List[str] = []
        playlists = data.get("streamingPlaylists") or []
        for index, playlist in enumerate(playlists):
            playlist_url = str(playlist.get("playlistUrl") or "").strip()
            if playlist_url:
                play_urls.append(f"HLS{index + 1}${playlist_url}")
            files = playlist.get("files") or []
            for media_file in files:
                file_url = str(media_file.get("fileUrl") or media_file.get("fileDownloadUrl") or "").strip()
                resolution = media_file.get("resolution") or {}
                label = str(resolution.get("label") or media_file.get("resolution") or "FILE")
                if file_url:
                    play_urls.append(f"{label}${file_url}")
        files = data.get("files") or []
        for media_file in files:
            file_url = str(media_file.get("fileUrl") or media_file.get("fileDownloadUrl") or "").strip()
            resolution = media_file.get("resolution") or {}
            label = str(resolution.get("label") or "FILE")
            if file_url:
                play_urls.append(f"{label}${file_url}")
        if not play_urls:
            play_urls = [f"原页${self.host}/w/{data.get('shortUUID') or video_id}"]
        return {
            "list": [
                {
                    "vod_id": str(data.get("uuid") or video_id),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_content": description[:500],
                    "vod_remarks": self._format_duration(data.get("duration")),
                    "vod_play_from": "NOWAV",
                    "vod_play_url": "#".join(play_urls),
                }
            ]
        }

    def searchContent(self, key: str, quick: bool, pg: str = "1"):
        """
        PeerTube 搜索：
          /api/v1/search/videos?search=...&start=&count=&sort=-publishedAt
        失败时回退 /api/v1/videos?search=...
        """
        keyword = (key or "").strip()
        page_number = max(int(pg or "1"), 1)
        count = 24
        start = (page_number - 1) * count
        if not keyword:
            return {"list": [], "page": page_number, "pagecount": 1, "limit": count, "total": 0}

        encoded_keyword = quote(keyword, safe="")
        candidates = [
            (
                f"{self.host}/api/v1/search/videos"
                f"?search={encoded_keyword}&start={start}&count={count}"
                f"&sort=-publishedAt&searchTarget=local"
            ),
            (
                f"{self.host}/api/v1/search/videos"
                f"?search={encoded_keyword}&start={start}&count={count}&sort=-publishedAt"
            ),
            (
                f"{self.host}/api/v1/videos"
                f"?search={encoded_keyword}&start={start}&count={count}&sort=-publishedAt"
            ),
        ]
        payload: Dict[str, Any] = {}
        for url in candidates:
            try:
                payload = self._get_json(url)
            except Exception:
                payload = {}
            if payload.get("data"):
                break

        items = payload.get("data") or []
        total = 0
        try:
            total = int(payload.get("total") or 0)
        except Exception:
            total = len(items)
        pagecount = max((total + count - 1) // count, 1) if total else (page_number if items else 1)
        if items and pagecount < page_number:
            pagecount = page_number
        return {
            "list": self._map_items(items),
            "page": page_number,
            "pagecount": pagecount,
            "limit": count,
            "total": total or len(items),
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

    def _list_videos(self, category_id: str, page: int) -> List[Dict[str, str]]:
        count = 24
        start = (max(page, 1) - 1) * count
        if category_id and category_id != "all":
            url = (
                f"{self.host}/api/v1/videos?categoryOneOf={category_id}"
                f"&start={start}&count={count}&sort=-publishedAt"
            )
        else:
            url = f"{self.host}/api/v1/videos?start={start}&count={count}&sort=-publishedAt"
        payload = self._get_json(url)
        return self._map_items(payload.get("data") or [])

    def _map_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        videos: List[Dict[str, str]] = []
        for item in items:
            pic = str(item.get("thumbnailPath") or "")
            if pic.startswith("/"):
                pic = self.host + pic
            videos.append(
                {
                    "vod_id": str(item.get("uuid") or item.get("id")),
                    "vod_name": str(item.get("name") or ""),
                    "vod_pic": pic,
                    "vod_remarks": self._format_duration(item.get("duration")),
                }
            )
        return videos

    def _get_json(self, url: str) -> Dict[str, Any]:
        response = self.fetch(url, headers=self.headers, timeout=15)
        return response.json()

    @staticmethod
    def _format_duration(seconds: Any) -> str:
        try:
            total = int(seconds or 0)
        except Exception:
            return ""
        minutes, sec = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"
