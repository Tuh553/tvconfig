# tvconfig（精简 8 源）

只保留用户指定源，其余已删除。

| 源 | 实现 | 状态 |
|----|------|------|
| 花都影视 | csp_XBPQ → hdys.pro | 列表可用 |
| MissAV | csp_XYQHiker → lib/missav.txt | missav.app 可用 |
| JAVDAYTV | csp_XBPQ → javday.tv | 列表可用 |
| NOWAV | csp_XYQHiker → lib/nowav_xyq.json | 站方页面异常时可能空列表 |
| 小黄书 | csp_XBPQ → xchina | 部分网络 Cloudflare，需代理 |
| 18JAV | csp_XYQHiker → lib/18jav.txt | 18jav.tv 可用 |
| 黄色仓库 | csp_XYQHiker → lib/黄色仓库.txt | hsck 可用 |
| Stripchat | py/py_stripchat.py | API 可用 |

## 订阅

```
https://raw.githubusercontent.com/Tuh553/tvconfig/main/江湖.json
```

依赖：`jar/yt.jar`、`lib/*`、`py/py_stripchat.py`、`base/spider.py`
