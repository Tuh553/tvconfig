# -*- coding: utf-8 -*-
"""
本地调试用的 TVBox/CatVod Python Spider 基类（精简版）。

目的：
- 让本仓库的 `py/*.py` 能在本机 Python 直接 import / 运行 / 调试
- 提供常用的 `fetch/post/getProxyUrl/log` 等接口

注意：
- 这不是 TVBox App 里 jar/Chaquopy 环境的完整实现，只覆盖本仓库脚本的常用调用点
- 如需严格对齐官方实现，可参考用户提供的 FongMi/TV `chaquo/.../base/spider.py`
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import requests


class Spider:
    """
    子类通常会实现：
    - init / homeContent / categoryContent / detailContent / playerContent / searchContent
    """

    def __init__(self):
        self.session = requests.Session()
        self._proxy_url = "proxy://do=py"

    # --- 生命周期 / 基础信息 ---
    def init(self, extend: str = ""):
        return self

    def getName(self) -> str:
        return self.__class__.__name__

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    # --- 框架常用工具方法 ---
    def log(self, message: str):
        # 本地运行时直接打印，TVBox 内通常会接入日志系统
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {message}")

    def getProxyUrl(self, local: bool = False) -> str:
        # TVBox 常见：proxy://do=py
        return self._proxy_url

    # --- HTTP 封装（requests 版）---
    def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        **kwargs: Any,
    ):
        return self.session.get(url, headers=headers, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,  # noqa: A002 (match requests signature)
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        **kwargs: Any,
    ):
        return self.session.post(url, data=data, json=json, headers=headers, timeout=timeout, **kwargs)

    # --- 常见返回结构辅助（可选）---
    @staticmethod
    def json_dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))



