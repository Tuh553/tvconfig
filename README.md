# tvconfig

## 接口地址

| 配置 | Raw 地址 |
|------|----------|
| 江湖（纯 Python 7 源） | `https://raw.githubusercontent.com/Tuh553/tvconfig/main/江湖.json` |
| XYQ（清洗后完整配置） | `https://raw.githubusercontent.com/Tuh553/tvconfig/main/xyq/XYQ.json` |

## 江湖 · 纯 Python 源

当前源全部为 `./py/*.py`，客户端需支持 Python 爬虫。

| 名称 | 脚本 |
|------|------|
| 花都影视 | py_huadu.py |
| MissAV | py_missav.py |
| JAVDAYTV | py_javday.py |
| NOWAV | py_nowav.py |
| 18JAV | py_18jav.py |
| 黄色仓库 | py_hsck.py |
| Stripchat | py_stripchat.py |

## XYQ 配置说明

来源：[xyq254245/xyqonlinerule](https://github.com/xyq254245/xyqonlinerule)

### 已清洗

- 磁力站（新6V / 电影天堂 / 七妹 / 美剧天堂 / 80S / 迅雷吧 等）
- 早教 / 戏曲 / 课堂类
- 失效解析：`zui`、`夜幕`；重复咸鱼条目

### XYQHiker 修复（2026-07）

**已修复：**

| 源 | 处理 |
|----|------|
| 樱花动漫 | 换新域名 `yinghuadh.com`，重写 stui 规则 |
| 风铃动漫 | 修正分类排序模板 + 搜索改为 `bbfun.cc/feng-s/...` |
| 短剧五五 | 修正搜索分页与片单链接选择器 |

**已删除（站挂/规则无法续命）：**

去看吧、嗷呜、路漫漫、爱看电影、低端影视、番茶动漫

**保留可用：** 动漫巴士、AGE、骚火、看影网、好影快看、农民、虎牙、斗鱼 等

整夹含 `custom_spider.jar` / `dr_py` / `XYQHiker` / `biliext`，相对路径建议本地或同目录部署。

## 使用

1. 订阅上表 raw 地址  
2. 强制刷新接口（清缓存）  
3. 江湖源需 Python 爬虫支持；XYQ 源需 jar + 相对资源完整  
