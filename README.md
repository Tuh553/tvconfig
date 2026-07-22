# tvconfig

## 接口地址

| 配置 | Raw 地址 |
|------|----------|
| 江湖（纯 Python 7 源） | `https://raw.githubusercontent.com/Tuh553/tvconfig/main/江湖.json` |
| XYQ（清洗后完整配置） | `https://raw.githubusercontent.com/Tuh553/tvconfig/main/xyq/XYQ.json` |

## 江湖 · 纯 Python 源

`csp_XBPQ` / `csp_XYQHiker` 依赖 spider jar。若客户端 jar 加载失败，会出现**只有 Python 源能开**的情况。

当前源全部改为 `./py/*.py`，与 Stripchat 同机制。

| 名称 | 脚本 | 备注 |
|------|------|------|
| 花都影视 | py_huadu.py | hdys.pro |
| MissAV | py_missav.py | missav.app MacCMS |
| JAVDAYTV | py_javday.py | javday.app MacCMS |
| NOWAV | py_nowav.py | pigav.ws PeerTube API |
| 18JAV | py_18jav.py | 18jav.tv |
| 黄色仓库 | py_hsck.py | hsck 系列 |
| Stripchat | py_stripchat.py | 直播；固定 pkey + 多 CDN |

## XYQ 配置说明

来源：[xyq254245/xyqonlinerule](https://github.com/xyq254245/xyqonlinerule)

已清洗内容：

- 删除磁力站（新6V / 电影天堂 / 七妹 / 美剧天堂 / 80S / 迅雷吧 等）
- 删除早教 / 戏曲 / 课堂类（哔哩幼儿少儿课堂、兔小贝、戏曲多多、播视童趣等）
- 保留荐片、正片/动漫/直播等常规源（约 33 站）

本地目录含 `custom_spider.jar`、`dr_py`、`XYQHiker`、`biliext` 等相对路径资源，**建议整夹使用**。

## 使用

1. 订阅上表 raw 地址（江湖或 XYQ 二选一，或都加）
2. **强制刷新**接口（清缓存）
3. 江湖源：客户端需支持 **Python 爬虫**
4. XYQ 源：客户端需能加载本地/同目录 jar 与相对路径资源
