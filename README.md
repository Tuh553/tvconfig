# tvconfig（江湖 8 源 · 纯 Python）

接口：`https://raw.githubusercontent.com/Tuh553/tvconfig/main/江湖.json`

## 为什么改成 Python？

`csp_XBPQ` / `csp_XYQHiker` 依赖 spider jar。若客户端 jar 加载失败，会出现**只有 Python 源能开**的情况。

当前 8 源全部改为 `./py/*.py`，与 Stripchat 同机制。

## 源列表

| 名称 | 脚本 | 备注 |
|------|------|------|
| 花都影视 | py_huadu.py | hdys.pro，直出 m3u8 |
| MissAV | py_missav.py | missav.app MacCMS |
| JAVDAYTV | py_javday.py | javday.app |
| NOWAV | py_nowav.py | pigav.ws PeerTube API |
| 小黄书 | py_xchina.py | 遇 Cloudflare 需代理 |
| 18JAV | py_18jav.py | 18jav.tv |
| 黄色仓库 | py_hsck.py | hsck4.26img.com |
| Stripchat | py_stripchat.py | 直播；优先 480p + 代理解密兜底 |

## 使用

1. 订阅上述 raw 地址  
2. **强制刷新**接口（清缓存）  
3. 客户端需支持 **Python 爬虫**（FongMi / 影视仓等常见壳）  
4. 播放失败时先试「直链」画质（Stripchat）
