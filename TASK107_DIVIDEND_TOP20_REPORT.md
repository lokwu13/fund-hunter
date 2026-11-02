# 任务107：RSI6极端窗全A股息率TTM Top20报告

## 一、实现口径

### 展示门与模块整合

- 新数据块为 `dividendWatch.rsi6Top20`，仅任务106现行 RSI6 极端强制开窗同时满足 `window=open`、`windowType=extreme_rebound`、`extremeRebound.active=true` 时展示。
- 普通开、半、关窗及观察窗均不展示，不请求 `daily_basic`，并清空旧 Top20；本清单不反向修改 `longWindow`。
- 原行业/概念 RSI14 独立催化高股息模块保持原逻辑和原数据；总览第0步只放 Top20 精简摘要与入口，板块 RSI6 区域承接唯一完整原榜，不重复堆两张同功能卡。

### 全A排名

- 使用同一本批有效交易日的 Tushare `daily_basic`，请求字段：`ts_code,trade_date,close,total_mv,dv_ttm,pe_ttm,pb`。
- 范围为沪深北真实全A股，不限原宽基或 VCP 池；显式排除指数、ETF、B股和无法确认的代码。
- 仅数值有效且 `dv_ttm>0` 的记录参与；缺失、NaN、0、负值不补0、不入榜。
- 按原始 `dv_ttm` 降序，并列时代码升序，确定性取前20；不足20显示实际数量，不凑数。
- 不按 PE/PB、概念、行业、市值或原 VCP 池过滤；亏损/非正PE、ST、小市值和缺市值均不删除排名项。

### 字段、排雷与风险

- 每项披露排名、代码、中文名、所属行业、股息率TTM、PE_TTM、PB、总市值、数据日期、ST及既有排雷状态。
- 名称和行业复用既有 `stock_info`、`stock_industry`，行业缺失时依次使用真实申万成员关系，仍无证据则标“行业未标注”。
- 排雷命中、已覆盖未命中、未覆盖严格区分；只标记，不删除或重排。未覆盖不写成无风险，已覆盖未命中也注明“不代表无风险”。
- 明示快照日期和 `daily_basic.dv_ttm` 历史滚动TTM口径；高股息不等于安全或买点，警惕一次性/特别分红、分红持续性、基本面和除权风险。

### 失败与陈旧

- API失败、空快照或快照日期不等于本批有效日时，子模块仍显示明确降级原因，但 `rankingLocked=true`、`count=0`、`items=[]`，不沿用旧清单。
- 陈旧快照保留实际旧日期用于诊断，绝不伪装成本批当前日期；不足20与失败锁榜分别披露。

## 二、机器验证

| 命令 | 真实结果 |
|---|---|
| `PYTHONPATH=scripts python zz_regress107.py` | 25/25通过 |
| `PYTHONPATH=scripts python zz_regress87.py` | 21/21通过 |
| `PYTHONPATH=scripts python zz_regress102.py` | 44/44通过 |
| `PYTHONPATH=scripts python zz_regress104.py` | 26/26通过 |
| `PYTHONPATH=scripts python zz_regress105.py` | 40/40通过；任务103十例10/10、六窗口6/6，失败案例/窗口为空 |
| `PYTHONPATH=scripts python zz_regress106.py` | 37/37通过 |
| `npm run build` | `tsc -b && vite build`成功；JS `dist/assets/index-Cfe0YJ3g-v25.js`，CSS `dist/assets/index-C4iuyN-6.css` |

任务107受控测试覆盖：仅RSI6窗展示、普通开/半/关及观察窗清空、零请求、不反向开门、全A与北交所、排除指数/ETF/B股、股息率降序与并列代码升序、缺失/NaN/0/负值、亏损PE、ST保留、不足20、陈旧、API失败、空快照、行业归属、排雷未覆盖、总览摘要、前端日期与TTM文案，以及两份生产数据字节不变。

原 `_dividend_group_catalyst` 与 `build_dividend_watch` 函数和任务106基线逐字一致；任务106 RSI6与任务103 VCP完整回归均通过。任务103验证为固定历史区间PIT检查，不是市场胜率统计。

## 三、发布前数据冻结基线

实时 main：`4bc77467096708efe971c8934fd813389ad0c521`（任务106，尚未发现任务107部分发布）。

| 文件 | 本地字节数 | 本地 SHA-256 | 远端字节数 | 远端 SHA-256 | 远端 Git blob SHA |
|---|---:|---|---:|---|---|
| `public/fund_data.json` | 594886 | `3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1` | 778908 | `38bf8a7acb67ce04a0ff6dc4e3649deedaae09f925f0f87b6c9c03f8bd0199d8` | `cea2cf6d2c93e1e5b47e66ebb5942d873cf771ef` |
| `src/data/fund_data.json` | 594886 | `3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1` | 778908 | `38bf8a7acb67ce04a0ff6dc4e3649deedaae09f925f0f87b6c9c03f8bd0199d8` | `cea2cf6d2c93e1e5b47e66ebb5942d873cf771ef` |

本地与远端仍是发布前已经不同的快照。本次只发布规则、前端、测试和报告；不提交生产 `fund_data`、不改工作流、不手动dispatch。发布后生产数据仍等待既有计划任务生成，不能提前声称线上已出现Top20实际清单。
