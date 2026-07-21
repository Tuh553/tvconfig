#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
离线/可控测试 py/py_stripchat.py 的核心逻辑（不依赖 TVBox jar 环境，不发真实网络请求）。

用法（可选）：
  python tools/stripchat_offline_test.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import unquote


@dataclass
class DummyResponse:
    status_code: int = 200
    text: str = ""
    _json: Dict[str, Any] | None = None

    def json(self):
        if self._json is None:
            raise ValueError("No json attached")
        return self._json


class DummySession:
    def __init__(self):
        self.routes: Dict[str, DummyResponse] = {}

    def get(self, url, **_kwargs):
        resp = self.routes.get(url)
        if resp is None:
            return DummyResponse(status_code=404, text="not found", _json=None)
        return resp

    def close(self):
        return None


def load_stripchat_module():
    """在导入前注入 base.spider stub，避免本机缺少 TVBox jar 环境导致 import 失败。"""
    base_mod = types.ModuleType("base")
    spider_mod = types.ModuleType("base.spider")

    class _BaseSpider:
        def getProxyUrl(self, local: bool = False):
            # TVBox 常见：proxy://do=py
            return "proxy://do=py" if local else "proxy://do=py"

    spider_mod.Spider = _BaseSpider
    sys.modules["base"] = base_mod
    sys.modules["base.spider"] = spider_mod

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target = os.path.join(root, "py", "py_stripchat.py")
    spec = importlib.util.spec_from_file_location("py_stripchat_under_test", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load py_stripchat.py spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StripChatOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_stripchat_module()

    def setUp(self):
        self.spider = self.mod.Spider()
        # init 会创建真实 requests.Session，这里替换成 DummySession 做离线测试
        self.spider.session = DummySession()
        self.spider.headers = {"User-Agent": "UA"}
        self.spider.host = "https://zh.stripchat.com"
        self.spider.stripchat_key = self.spider.decode_key_compact()
        self.spider._hash_cache = {}

    def test_process_key(self):
        self.assertEqual(self.spider.process_key("g alice"), ("girls", "alice"))
        self.assertEqual(self.spider.process_key("M Bob"), ("men", "Bob"))
        self.assertEqual(self.spider.process_key("xxx"), ("girls", "xxx"))

    def test_country_flag(self):
        self.assertNotEqual(self.spider.country_code_to_flag("CN"), "CN")
        self.assertEqual(self.spider.country_code_to_flag(""), "")
        self.assertEqual(self.spider.country_code_to_flag("USA"), "USA")

    def test_player_master_parse(self):
        master_url = "https://edge-hls.doppiocdn.net/hls/123/master/123_auto.m3u8?playlistType=lowLatency"
        self.spider.session.routes[master_url] = DummyResponse(
            status_code=200,
            text="\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-MOUFLON:V1:psch_value:pkey_value",
                    '#EXT-X-STREAM-INF:BANDWIDTH=1,NAME="720p"',
                    "https://edge-hls.doppiocdn.net/hls/123/720p.m3u8?x=y",
                ]
            ),
        )
        out = self.spider.playerContent("StripChat", "123", [])
        self.assertEqual(out.get("parse"), "0")
        self.assertIsInstance(out.get("url"), list)
        self.assertEqual(out["url"][0], "720p")
        # 注意：full_url 会被 quote 编码后再塞进 proxy url
        decoded = unquote(out["url"][1])
        self.assertIn("psch=psch_value", decoded)
        self.assertIn("pkey=pkey_value", decoded)

    def test_process_m3u8_content_v2_replaces_media(self):
        # 构造一个最简 MOUFLON:FILE 场景（密文随便给，走 try/except fallback）
        self.spider.decrypt = lambda *_args, **_kwargs: "decrypted.mp4"
        content = "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-MOUFLON:FILE:QUJD",  # base64("ABC")，会被 decrypt 处理
                "https://example.com/media.mp4",
            ]
        )
        out = self.spider.process_m3u8_content_v2(content)
        self.assertNotIn("media.mp4", out)

    def test_localproxy_absolutizes_relative_urls(self):
        # 模拟 localProxy 返回的 m3u8 里有相对分片地址，必须改成绝对地址，否则会相对 proxy:// 去拼导致卡顿
        playlist_url = "https://edge-hls.doppiocdn.net/hls/123/720p.m3u8?x=y&psch=a&pkey=b"
        self.spider.session.routes[playlist_url] = DummyResponse(
            status_code=200,
            text="\n".join(
                [
                    "#EXTM3U",
                    "#EXTINF:2,",
                    "seg-0001.ts",
                    "#EXTINF:2,",
                    "/abs/seg-0002.ts",
                ]
            ),
        )
        code, ctype, body = self.spider.localProxy({"url": playlist_url})
        self.assertEqual(code, 200)
        self.assertIn("https://edge-hls.doppiocdn.net/hls/123/seg-0001.ts", body)
        self.assertIn("https://edge-hls.doppiocdn.net/abs/seg-0002.ts", body)

    def test_process_mouflon_uri_replaces_media_placeholder(self):
        content = "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-MOUFLON:URI:https://real.example.com/seg1.mp4",
                '#EXT-X-PART:DURATION=0.500,URI="https://media.example.com/media.mp4",INDEPENDENT=YES',
                "#EXT-X-MOUFLON:URI:https://real.example.com/seg2.mp4",
                "https://media.example.com/media.mp4",
            ]
        )
        out = self.spider.process_m3u8_content_v2(content)
        self.assertIn('URI="https://real.example.com/seg1.mp4"', out)
        self.assertIn("https://real.example.com/seg2.mp4", out)
        self.assertNotIn("media.example.com/media.mp4", out)

    def test_category_content_parsing(self):
        url = (
            "https://zh.stripchat.com/api/front/models?improveTs=false&removeShows=false&limit=60&offset=0"
            "&primaryTag=girls&sortBy=stripRanking&rcmGrp=A&rbCnGr=true&prxCnGr=false&nic=false"
        )
        self.spider.session.routes[url] = DummyResponse(
            status_code=200,
            _json={
                "models": [
                    {
                        "id": 1,
                        "username": "alice",
                        "snapshotTimestamp": 123,
                        "country": "CN",
                        "status": "groupShow",
                    }
                ],
                "filteredCount": 1,
            },
        )
        out = self.spider.categoryContent("girls", "1", {}, {})
        self.assertEqual(out["total"], 1)
        self.assertEqual(len(out["list"]), 1)
        self.assertEqual(out["list"][0]["vod_id"], "alice")

    def test_search_content_filters_isLive(self):
        url = (
            "https://zh.stripchat.com/api/front/v4/models/search/group/username?query=ali&limit=900&primaryTag=girls"
        )
        self.spider.session.routes[url] = DummyResponse(
            status_code=200,
            _json={
                "models": [
                    {
                        "id": 1,
                        "username": "alice",
                        "snapshotTimestamp": 123,
                        "country": "CN",
                        "status": "public",
                        "isLive": True,
                    },
                    {
                        "id": 2,
                        "username": "bob",
                        "snapshotTimestamp": 456,
                        "country": "US",
                        "status": "public",
                        "isLive": False,
                    },
                ]
            },
        )
        out = self.spider.searchContent("ali", 1, "1")
        self.assertEqual(len(out["list"]), 1)
        self.assertEqual(out["list"][0]["vod_id"], "alice")


if __name__ == "__main__":
    unittest.main(verbosity=2)


