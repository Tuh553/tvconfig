# -*- coding: utf-8 -*-
"""Chaturbate 直播源。

注意：chaturbate.com 常被 Cloudflare 拦截。
本脚本尽量用完整浏览器头 + 多接口回退；若你所在网络被墙/被盾，
需在 App/系统侧开代理后再进源。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from base.spider import Spider


class Spider(Spider):
    def getName(self) -> str:
        return "Chaturbate 直播"

    def init(self, extend: str = ""):
        self.base = "https://chaturbate.com"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Referer": "https://chaturbate.com/",
            "Origin": "https://chaturbate.com",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
        }
        self.page_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.headers["Accept-Language"],
            "Referer": "https://chaturbate.com/",
        }
        return self

    def homeContent(self, filter):  # noqa: A002
        return {
            "class": [
                {"type_id": "f", "type_name": "女性"},
                {"type_id": "c", "type_name": "情侣"},
                {"type_id": "m", "type_name": "男性"},
                {"type_id": "s", "type_name": "TS"},
            ]
        }

    def _safe_json(self, response) -> Optional[dict]:
        if response is None:
            return None
        try:
            text = response.text if hasattr(response, "text") else str(response)
        except Exception:
            return None
        text = (text or "").strip()
        if not text or text.startswith("<!DOCTYPE") or text.startswith("<html"):
            return None
        try:
            data = response.json() if hasattr(response, "json") else json.loads(text)
        except Exception:
            try:
                data = json.loads(text)
            except Exception:
                return None
        return data if isinstance(data, (dict, list)) else None

    def _fetch_roomlist(self, gender: str, page_index: int, query: str = "") -> Dict[str, Any]:
        offset = max(page_index, 0) * 90
        gender_map = {"f": "f", "m": "m", "c": "c", "s": "s", "": ""}
        gender_code = gender_map.get(gender, gender or "")
        candidates = [
            (
                f"{self.base}/api/ts/roomlist/room-list/"
                f"?enable_recommendations=false&genders={gender_code}"
                f"&limit=90&offset={offset}"
                + (f"&query={query}" if query else "")
            ),
            (
                f"{self.base}/api/ts/roomlist/room-list/"
                f"?genders={gender_code}&limit=90&offset={offset}"
                + (f"&keywords={query}" if query else "")
            ),
        ]
        last_error = ""
        for url in candidates:
            try:
                response = self.fetch(url, headers=self.headers, timeout=15)
                data = self._safe_json(response)
                if isinstance(data, dict) and ("rooms" in data or "total_count" in data):
                    return data
                status = getattr(response, "status_code", "?")
                last_error = f"bad_json_status={status}"
            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"
        # HTML 兜底：从分类页抠 username（部分网络可过首页但拦 API）
        html_paths = {
            "f": "/female-cams/",
            "c": "/couple-cams/",
            "m": "/male-cams/",
            "s": "/trans-cams/",
        }
        path = html_paths.get(gender_code, "/female-cams/")
        page_url = f"{self.base}{path}"
        if page_index > 0:
            page_url = f"{self.base}{path}?page={page_index + 1}"
        try:
            response = self.fetch(page_url, headers=self.page_headers, timeout=15)
            html = response.text if hasattr(response, "text") else ""
            rooms = self._parse_rooms_from_html(html)
            if rooms:
                return {"rooms": rooms, "total_count": len(rooms)}
            if "Just a moment" in html or "cf-browser-verification" in html:
                last_error = "cloudflare_challenge"
            else:
                last_error = "html_no_rooms"
        except Exception as error:
            last_error = f"html_{type(error).__name__}: {error}"
        return {"rooms": [], "total_count": 0, "_error": last_error}

    def _parse_rooms_from_html(self, html: str) -> List[dict]:
        if not html:
            return []
        # data-room / data-slug / href="/username/"
        usernames = []
        for pattern in (
            r'data-room=["\']([a-zA-Z0-9_]+)["\']',
            r'data-slug=["\']([a-zA-Z0-9_]+)["\']',
            r'href=["\']/(?!accounts|female|male|couple|trans|tags|auth|tipping)([a-zA-Z0-9_]{3,30})/["\']',
        ):
            usernames.extend(re.findall(pattern, html))
        # 去重保序
        seen = set()
        rooms = []
        for username in usernames:
            if username in seen:
                continue
            seen.add(username)
            rooms.append(
                {
                    "username": username,
                    "img": f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg",
                    "display_age": "",
                }
            )
            if len(rooms) >= 90:
                break
        return rooms

    def _rooms_to_videos(self, rooms: List[dict]) -> List[dict]:
        videos = []
        for room in rooms:
            username = room.get("username") or room.get("slug") or ""
            if not username:
                continue
            age = room.get("display_age")
            name = f"{username}"
            if age not in (None, "", 0, "0"):
                name = f"{username} ({age})"
            image = (
                room.get("img")
                or room.get("image_url")
                or room.get("thumbnail")
                or f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg"
            )
            videos.append(
                {
                    "vod_id": username,
                    "vod_name": name,
                    "vod_pic": image,
                    "vod_remarks": room.get("current_show") or room.get("tags") or "LIVE",
                }
            )
        return videos

    def categoryContent(self, tid, pg, filter, extend):  # noqa: A002
        page_index = int(pg) if str(pg).isdigit() else 0
        # TVBox 页码有的从 1 开始
        if page_index >= 1:
            page_index = page_index - 1
        data = self._fetch_roomlist(str(tid or "f"), page_index)
        rooms = data.get("rooms") or []
        videos = self._rooms_to_videos(rooms)
        if not videos:
            reason = data.get("_error") or "empty"
            videos = [
                {
                    "vod_id": "help_cloudflare",
                    "vod_name": f"Chaturbate 被拦截({reason})，请开代理后重试",
                    "vod_pic": "",
                    "vod_remarks": "CF/网络",
                }
            ]
            total = 1
            pagecount = 1
        else:
            total = int(data.get("total_count") or len(videos))
            pagecount = max(1, (total + 89) // 90)
        return {
            "list": videos,
            "page": page_index + 1,
            "pagecount": pagecount,
            "limit": 90,
            "total": total,
        }

    def detailContent(self, ids):
        room_slug = ids[0] if ids else ""
        if room_slug == "help_cloudflare":
            return {
                "list": [
                    {
                        "vod_id": room_slug,
                        "vod_name": "Chaturbate 网络提示",
                        "vod_pic": "",
                        "vod_content": "当前网络无法直连 chaturbate.com（Cloudflare）。请给 TVBox/设备开启代理后重进源。",
                        "vod_play_from": "提示",
                        "vod_play_url": "无播放地址$https://chaturbate.com",
                    }
                ]
            }
        return {
            "list": [
                {
                    "vod_id": room_slug,
                    "vod_name": f"Chaturbate - {room_slug}",
                    "vod_pic": f"https://roomimg.stream.highwebmedia.com/ri/{room_slug}.jpg",
                    "vod_play_from": "Chaturbate",
                    "vod_play_url": f"直播源${room_slug}",
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):  # noqa: A002
        if id == "help_cloudflare":
            return {
                "parse": 0,
                "playUrl": "",
                "url": "https://chaturbate.com",
                "header": self.page_headers,
            }
        play_url = id
        post_headers = dict(self.headers)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        post_headers["Referer"] = f"{self.base}/{id}/"
        try:
            response = self.post(
                f"{self.base}/get_edge_hls_url_ajax/",
                data={"room_slug": id},
                headers=post_headers,
                timeout=15,
            )
            data = self._safe_json(response)
            if isinstance(data, dict) and data.get("url"):
                play_url = data["url"]
            elif isinstance(data, dict) and data.get("success") and data.get("url"):
                play_url = data["url"]
        except Exception:
            play_url = id
        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": f"{self.base}/{id}/",
                "Origin": self.base,
            },
        }

    def searchContent(self, key, quick, pg="0"):
        page_index = int(pg) if str(pg).isdigit() else 0
        if page_index >= 1:
            page_index = page_index - 1
        data = self._fetch_roomlist("", page_index, query=key or "")
        videos = self._rooms_to_videos(data.get("rooms") or [])
        return {"list": videos}

    def isVideoFormat(self, url):
        return isinstance(url, str) and (".m3u8" in url or "playlist" in url)

    def manualVideoCheck(self):
        return True
