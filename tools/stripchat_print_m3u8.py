#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地打印 StripChat 的 master/variant m3u8 链接，辅助定位“卡顿/黑屏”是否是链接/代理问题。

用法：
  python tools/stripchat_print_m3u8.py <username>

说明：
  - 会先请求用户详情拿到数值 id
  - 再请求 master m3u8，并输出 playerContent 生成的画质/代理URL列表
"""

from __future__ import annotations

import importlib.util
import os
import sys
from urllib.parse import unquote

def load_spider_cls():
    """从文件路径加载 py/py_stripchat.py，避免因为 sys.path 不含项目根目录导致无法 import `py.*`"""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target = os.path.join(root, "py", "py_stripchat.py")
    spec = importlib.util.spec_from_file_location("py_stripchat_under_test", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载脚本: {target}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Spider


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/stripchat_print_m3u8.py <username> [proxy_url]")
        return 2

    username = sys.argv[1].strip()
    if not username:
        print("username 不能为空")
        return 2
    proxy_url = sys.argv[2].strip() if len(sys.argv) >= 3 else ""

    Spider = load_spider_cls()
    ext = {"debug": True}
    if proxy_url:
        ext["proxy"] = proxy_url
    s = Spider().init(__import__("json").dumps(ext, ensure_ascii=False))
    detail = s.detailContent([username])
    vod = detail["list"][0]
    vid = vod["vod_id"]

    print(f"username={username}")
    print(f"numeric_id={vid}")

    player = s.playerContent("StripChat", vid, [])
    urls = player.get("url", [])
    print("\n=== playerContent url 列表（qn, proxyUrl 成对）===\n")
    for i in range(0, len(urls), 2):
        qn = urls[i] if i < len(urls) else ""
        pu = urls[i + 1] if i + 1 < len(urls) else ""
        print(f"{qn}\n{pu}\n")

    # 额外：尝试取第一条清晰度，模拟 TVBox 调用 localProxy 后的 m3u8 内容（看分片是否为绝对地址）
    if len(urls) >= 2:
        first_proxy = urls[1]
        full_url = ""
        if "&url=" in first_proxy:
            full_url = unquote(first_proxy.split("&url=", 1)[1])
        if full_url:
            print("=== localProxy 处理后的 variant m3u8 前 25 行 ===\n")
            code, ctype, body = s.localProxy({"url": full_url})
            print(f"status={code} contentType={ctype}\n")
            print("\n".join((body or "").splitlines()[:25]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


