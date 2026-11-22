# 任务 115：低量窄幅独立 VCP 入口

## 规则口径

- 新入口 `low_vol_tight` 沿用主分类 `VCP收缩型`，展示为 `VCP·低量窄幅`；在 strict、fixed、周线、杯柄之后补位，不抢占旧入口。
- 任一当时可见的 31～250 个交易日窗口完整满足五门即可。区间持续严格大于 30 个交易日；振幅沿用 `(区间最高价-区间最低价)/区间最低价`，严格小于 8%，8.00% 不通过。
- VOL20 含当日及此前 19 根。仅当日量严格小于当日 VOL20 才计缩量，等于不算；缩量天数除以区间全部交易日，严格大于 90%，恰好 90% 不通过。不足 20 根的日期保留在分母但不计缩量。
- 复用任务 113 的至少 200 根日线及 `close > MA50 > MA150 > MA200` 严格门；复用任务 114 孕育期新高门，接近新高允许，最后一天实际 `close > pivot` 的正常突破豁免。
- 新入口枢轴取最后一天之前的区间高点，避免突破日自身高点误杀。不调用传统三次收缩、规律摆动、近期量、右侧质量或阶段量比门。
- 新增 `vcpEntryId`、`vcpEntryLabel`、`vcpStructure`、`lowVolTight` 证据，含起止、天数、振幅、高低点、VOL20 天数/比例/样本覆盖、逐日 `volumeChecks`、均线及孕育证据。
- pending、episode、active candidate 历史链透传入口与证据；旧前端快照要求新入口 `vcpStructure.pass === true`。工具页和总览共振、精选、储备共用证据文案。
- AST 对照确认 `_vcp_level_strict`、`_vcp_fixed_base`、`_platform_vcp_attribute`、`_vcp_daily_trend_gate`、`_vcp_gestation_new_high_gate`、`_cup_handle_strict`、`_cup_weekly_trend`、`_platform_price_pattern`、`_bottom_weekly_price_pattern` 均未改。

## 验证结果

- 任务 115：23/23 通过，覆盖全部指定边界、PIT、历史标签、age 9/10、漏斗字段和旧函数不变。
- 任务 113：309/309 通过；任务 114：34/34 通过。
- 联合回归：任务 95、96、98、99、101、102、104、105、106、107、108、109、110、111、112、113、114、115，共 18/18 通过；逐项日志为 `zz_regress*_task115.log`，汇总为 `zz_joint_regress115.json`。
- `npm run build` 成功，2363 个模块；只有既有的大包体积警告。构建证据为 `zz_build115.json` 和 `zz_build115.log`。
- 测试和构建前后 `public/fund_data.json`、`src/data/fund_data.json` SHA-256 均为 `3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1`，未生成或改写生产数据。
- 发布前机器核验 `zz_task115_machine_verification.json` 全部通过；实时预检 `zz_task115_live_preflight.json` 确认 main 基线与任务 114 源码逐字节一致。

## 发布边界

本次发布只含白名单源码、测试和构建/验证证据；不包含生产 `fund_data.json`、`dist/**`、`.github/**` 或非白名单缓存，不手动 dispatch nightly，不修改 workflow 或计划任务。发布结果见 `zz_push115.json`，线上只读核验见 `zz_task115_online_verification.json`。既有线上生产名单不会因本次源码发布而立即按新规则重算，需由原有正常数据更新流程处理。
