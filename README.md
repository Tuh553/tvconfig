# tvconfig（江湖 7 源 · 纯 Python）

接口：`https://raw.githubusercontent.com/Tuh553/tvconfig/main/江湖.json`

## 为什么改成 Python？

`csp_XBPQ` / `csp_XYQHiker` 依赖 spider jar。若客户端 jar 加载失败，会出现**只有 Python 源能开**的情况。

当前源全部改为 `./py/*.py`，与 Stripchat 同机制。

## 源列表

| 名称 | 脚本 | 备注 |
|------|------|------|
| 花都影视 | py_huadu.py | hdys.pro，`/search/{kw}/` 搜索 |
| MissAV | py_missav.py | missav.app MacCMS |
| JAVDAYTV | py_javday.py | javday.app MacCMS 搜索 `/index.php/search/wd/` |
| NOWAV | py_nowav.py | pigav.ws PeerTube API 搜索 |
| 18JAV | py_18jav.py | 18jav.tv；官方搜索失效时多分类兜底 |
| 黄色仓库 | py_hsck.py | hsck4.26img.com |
| Stripchat | py_stripchat.py | 直播；固定 pkey + 多 CDN 直链 |

## 使用

1. 订阅上述 raw 地址  
2. **强制刷新**接口（清缓存）  
3. 客户端需支持 **Python 爬虫**（FongMi / 影视仓等常见壳）  
4. 播放失败时先试「直链」画质（Stripchat）
