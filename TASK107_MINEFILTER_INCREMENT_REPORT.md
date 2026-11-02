# 任务107增量：排雷明确命中剔除并顺延补足

## 实现口径

- 全A有效 `dv_ttm>0` 候选仍先按原始股息率降序、代码升序排列，并记录 `originalRank`。
- 截取Top20之前，对全部候选应用既有 `mineWatch.items`：只有存在明确 `types` 或 `details` 的命中项才剔除；后续候选按原始顺序自动顺延，最终重新生成连续 `rank`，不是从原Top20删除后留空。
- 每项保留最终排名与原始股息率名次。数据块新增 `excludedCount`、`excludedItems`、`remainingCandidateCount`、`mineCoverageStatus`；剔除项含原始名次、代码、名称、股息率、命中类型、明细与原因。
- 排雷未覆盖项保留并标“未核验”；已覆盖未命中明确“不代表无风险”。排雷数据整体缺失时 `mineCoverageStatus=missing`，不剔除、不把未知视为未命中，全部标未核验。
- ST未明确命中保留并继续标ST；ST明确命中剔除。候选或剔除后不足20只时如实展示并披露候选不足/数据限制。
- API失败、空快照、陈旧快照继续锁榜清空，不沿用旧清单。原RSI14高股息模块、任务106超跌榜与任务103 VCP不改。
- 总览摘要披露剔除数量与顺延；板块原唯一完整卡展示最终/原始排名和剔除原因，不新增重复卡，不再使用“只标记不删除”旧口径。

## 真实验证

| 命令 | 结果 |
|---|---|
| `PYTHONPATH=scripts python zz_regress107.py` | 29/29通过 |
| `PYTHONPATH=scripts python zz_regress106.py` | 37/37通过 |
| `PYTHONPATH=scripts python zz_regress105.py` | 40/40通过；任务103十例10/10、六窗口6/6，失败案例/窗口为空 |
| `PYTHONPATH=scripts python zz_regress87.py` | 21/21通过 |
| `PYTHONPATH=scripts python zz_regress102.py` | 44/44通过 |
| `PYTHONPATH=scripts python zz_regress104.py` | 26/26通过 |
| `npm run build` | `tsc -b && vite build`成功；本地JS `dist/assets/index-BFKLBSY0-v25.js`，CSS `dist/assets/index-CAAZ_2W_.css` |

任务107受控样例包含23只有效候选、2只明确命中剔除、21只剩余候选、最终20只；原第21与22名补位。还覆盖排雷整体缺失不剔除、ST未命中保留与命中剔除、并列代码排序、不足20、API失败、陈旧与空快照、全A范围和生产数据字节不变。

## 发布边界

仅通过Git Data API发布本增量明确文件，使用实时main基树和父提交、`force=False`；不手动dispatch nightly、不修改工作流或计划任务，不提交/覆盖两份生产 `fund_data.json`。生产数据仍等待既有计划任务使用新代码重生成，本报告不声称线上已生成新Top20实际清单。
