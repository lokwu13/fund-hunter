# 任务106：资金猎人 RSI6 单口径开窗与超跌排序报告

## 一、最终规则对照

### 1. RSI6 极端临时窗

- 只使用已完成周的 Wilder RSI6：上一完成周 `RSI6 <= 20`，最近完成周 `RSI6 > 20`。
- 最近完成周必须新鲜并属于当前上一 ISO 周；指数日线最后日期必须等于本批有效交易日。未完结周的动态 RSI6 只观察，不触发开窗。
- 固定六宽基及顺序：上证50 `000016.SH`、沪深300 `000300.SH`、中证A500 `000510.SH`、中证500 `000905.SH`、科创50 `000688.SH`、创业板50 `399673.SZ`。
- 任意一只单独满足即触发，`requiredCount = 1`；不使用 `399300`，沪深300不重复计算。
- 普通逻辑先完整计算并保留 `standardWindow`，RSI6 极端门最后覆盖 `open`。冷水温、债券降级、旧顶部风险、强硬减仓、指数数量及 PE/PB 均不否决新门。
- 保留5个交易日临时窗生命周期；没有 RSI6 收复证据时，不借旧极端逻辑开窗。该信号不是趋势反转或买点。
- `broadObservation` 是同一 RSI6 证据镜像；估值只展示，不进入开窗链。

### 2. 超跌方向与排序

- 仅在现行 RSI6 极端强制开窗时展示，不反向开门。
- 行业与概念按真实指数完成周 RSI6 升序，辅以日 RSI6、20/60日回撤；周 RSI6≤20 或刚上穿者标为优先。
- PE/PB 仅参考，不参与方向入围、排序或过滤；高估值与覆盖不足只统计。
- 概念成员只认 `ths_members` 真实关系，不用关系不标股票凑数。

### 3. 估值与龙头降级

- `daily_basic` 失败、为空或日期陈旧时，保留 RSI6 榜单和开窗结果，估值状态明确标为 `missing` 或 `stale`。
- 有效快照按 `total_mv` 选前2名；失败或陈旧快照使用 `vcp_cache.circ_mv` 并明确“非总市值”。没有市值时不凑数。
- 亏损/非正 PE、缺失估值、ST 与既有排雷覆盖状态分别披露，不补0、不混同。

### 4. A500覆盖及缓存限制

- 中证A500已纳入六宽基，并有真实缓存与受控正例覆盖。
- 本地 A500 缓存共300行，日期范围 `20250612—20260924`；末尾孤立点前存在缺口，不能伪称当前新鲜。
- 真实缓存回归采用最后密集交易日 `20260831` 作为 as-of；该时点最近完成周 RSI6=42.06、上一完成周 RSI6=39.83，仅用于验证真实数据可复算，不伪造触发。
- 任务102真实历史扫描自2025年以来找到10个正例；首个为 `20260413` 上证50，上一完成周 RSI6=16.72、最近完成周 RSI6=40.39。历史正例不依赖估值低位。

## 二、防回退范围

- 任务103 VCP/杯柄/底部平台函数逐字保护；`OSC_INDICES`、独立高股息 RSI14、其他 RSI14 状态机未全局替换。
- 普通 `standardWindow`、5日生命周期、动态周不开窗、高股息独立边界均保留。
- 前端类型、周总览、漏斗、板块热力与 ECI 文案已同步同一 RSI6 契约。

## 三、发布前机器验证

| 命令 | 真实结果 |
|---|---|
| `PYTHONPATH=scripts python zz_regress87.py` | 21/21，通过 |
| `PYTHONPATH=scripts python zz_regress96.py` | 命令成功；38个样本，8/8边界检查通过 |
| `PYTHONPATH=scripts python zz_regress98.py` | 30/30，通过 |
| `PYTHONPATH=scripts python zz_regress99.py` | 21/21，通过；样本基线无变化 |
| `PYTHONPATH=scripts python zz_regress101.py` | 19/19，通过 |
| `PYTHONPATH=scripts python zz_regress102.py` | 44/44，通过；2025年以来真实正例10个 |
| `PYTHONPATH=scripts python zz_regress104.py` | 26/26，通过 |
| `PYTHONPATH=scripts python zz_regress105.py` | 40/40，通过；任务103十例10/10、六窗口6/6，失败窗口为空 |
| `PYTHONPATH=scripts python zz_regress106.py` | 37/37，通过 |
| `npm run build` | `tsc -b && vite build` 成功；JS `dist/assets/index-Dua-zYHz-v25.js`，CSS `dist/assets/index-BiaatRQU.css` |

任务105窗口证据：`000776.SZ`、`603392.SH`、`002027.SZ`、`600030.SH`、`601328.SH`、`600118.SH` 全部通过。该回归是固定历史区间（point-in-time）验证，不是市场胜率统计。

## 四、发布前数据冻结基线

实时 main：`6bd9cc82e9673a40e968fd016436fc527eb0b5da`。

| 文件 | 本地字节数 | 本地 SHA-256 | 远端字节数 | 远端 SHA-256 | 远端 Git blob SHA |
|---|---:|---|---:|---|---|
| `public/fund_data.json` | 594886 | `3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1` | 778908 | `38bf8a7acb67ce04a0ff6dc4e3649deedaae09f925f0f87b6c9c03f8bd0199d8` | `cea2cf6d2c93e1e5b47e66ebb5942d873cf771ef` |
| `src/data/fund_data.json` | 594886 | `3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1` | 778908 | `38bf8a7acb67ce04a0ff6dc4e3649deedaae09f925f0f87b6c9c03f8bd0199d8` | `cea2cf6d2c93e1e5b47e66ebb5942d873cf771ef` |

本地与远端是发布前已经不同的快照；本次只发布规则、测试与报告，不提交两份生产数据、不改工作流、不手动 dispatch nightly。发布后规则代码生效，但生产数据保持远端原快照，等待既有计划任务生成，不能据此声称线上已出现新的 RSI6 信号。
