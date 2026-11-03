# 任务109：总览两个明细入口导航修复

## 根因

`WeeklySummary.tsx` 两个按钮均错误调用 `onNavigate('tools', anchor)`，但目标卡只在 `App.tsx` 的 `sectors` tab 中以 `<SectorHeatmap detailed />` 条件渲染，因此线上点击后进入【工具】且找不到目标。原 `App.tsx` 还使用固定 150ms `setTimeout`，没有等待目标挂载和可见，存在条件渲染时序竞态。

## 修复

- 两个按钮改跳 `sectors`，分别定位唯一稳定 id：`oversold-value-directions`、`rsi6-dividend-top20`。
- 保留原生 `button type="button"` 与既有样式，增加 `aria-controls`，支持键盘激活。
- 新增 `src/navigation.ts`：切换 tab 后通过 `requestAnimationFrame` 等待 DOM 存在且 `getClientRects().length > 0`，再执行 `scrollIntoView`；最多等待120帧，快速连续导航以最后一次为准。
- `prefers-reduced-motion: reduce` 时使用 `auto`，否则保留平滑滚动。
- 两个目标卡均在详细板块页且带 `scroll-mt-20`；按钮和卡片使用相同的极端窗及数据可见条件，未开窗时不显示按钮。
- 仅将相关 `App.tsx` 导航链路改用共享可靠滚动函数，不改其它功能。

## 验证

- 任务109源码/DOM契约：21/21；可执行 DOM 延迟挂载、不可见不滚动、可见后滚动及 reduced-motion 测试通过。
- 任务108：40/40；任务107：29/29；任务103：40/40、VCP十例10/10、六窗口6/6。
- `npm run build` 成功，仅既有大 chunk 提示。
- Windows 本地 JS：`dist/assets/index-CjcnNGdo-v25.js`，1,399,847 字节，SHA-256 `ce9683dc3358c527c41fbdcae2112fed52fa7aa0ef3875f546c41e2f3a9ccc8d`。
- CSS：`dist/assets/index-CAAZ_2W_.css`，109,684 字节，SHA-256 `f360bc63d4f5797e191c48a8a41716ddb6fa8870d0a9390b42a930a8885237c9`。
- 不重新生成、不覆盖 `public/fund_data.json` 或 `src/data/fund_data.json`；不修改 workflow/计划任务，不手动 dispatch。

## 主代理线上点击验收

1. 点击“查看行业/大概念自身历史估值、双龙头与数据限制 →”，应激活【板块】并可见 `#oversold-value-directions`。
2. 点击“查看全A股息率TTM Top20完整原榜 →”，应激活【板块】并可见 `#rsi6-dividend-top20`。
