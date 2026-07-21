# tvconfig

TVBox 配置：江湖源（已做存活检测）

- 主配置：[`江湖.json`](./江湖.json)
- 活跃 `sites`：**169**
- 失效归档（注释字段 `_失效源` / `_失效源_注释`）：**32**
- 检测报告：[`失效/report.md`](./失效/report.md)
- 失效列表：[`失效/失效源注释.md`](./失效/失效源注释.md)
- 检测脚本：[`tools/source_health_check.py`](./tools/source_health_check.py)

## 说明

1. `sites` 内为当前保留源（pass / soft_fail / manual_review / skip）。
2. 标准 JSON **不支持** `//` 注释，故失效源放在顶层 `_失效源`、`_失效源_注释`（播放器通常忽略未知字段）。
3. 恢复某源：将 `_失效源` 中对象移回 `sites` 即可。
4. 未验证播放链路；存活标准为分类/首页可连通。

## 本地复检

```bash
python tools/source_health_check.py
python tools/source_health_check.py --apply
```
