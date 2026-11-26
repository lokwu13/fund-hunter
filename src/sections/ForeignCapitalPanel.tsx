import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Globe, ChevronRight, Activity, TrendingDown, FileText, ExternalLink } from 'lucide-react';
import { useFundData, type ShortSellingBoard } from '@/hooks/useFundData';

const fmtCompact = (value?: number | null, currency = '') => {
  if (value == null) return '—';
  const abs = Math.abs(value);
  const formatted = abs >= 1e8 ? `${(value / 1e8).toFixed(2)}亿` : abs >= 1e4 ? `${(value / 1e4).toFixed(0)}万` : value.toLocaleString('zh-CN');
  return `${formatted}${currency}`;
};

function ShortSellingCard({ board }: { board?: ShortSellingBoard }) {
  return (
    <Card id="northbound-short-selling" className="min-w-0 border-slate-200 shadow-sm">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="text-sm font-bold flex items-center gap-2 text-slate-800">
              <TrendingDown className="w-4 h-4 text-orange-600" />
              北向渠道卖空成交TOP10（A股）
            </CardTitle>
            <CardDescription className="text-[10px] mt-1">沪深北向官方完整收盘文件 · 人民币成交额排名</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs bg-slate-50 text-slate-600">
            日更检查 · {board?.asOf ?? '待取得'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-1">
        {board?.status === 'stale' && (
          <p className="text-[10px] text-amber-700 bg-amber-50 rounded px-2 py-1 mb-2">本次未获新文件，沿用 {board.asOf} 最近完整快照。</p>
        )}
        {board?.items.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] min-w-[520px]">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="text-left py-1.5 font-medium">排名 / 标的</th>
                  <th className="text-right font-medium">卖空股数</th>
                  <th className="text-right font-medium">卖空金额</th>
                  <th className="text-right font-medium">较上一有效日</th>
                </tr>
              </thead>
              <tbody>
                {board.items.map((item) => (
                  <tr key={item.code} className="border-b border-slate-50 hover:bg-slate-50/60">
                    <td className="py-1.5">
                      <span className="font-bold text-slate-400 mr-2">{item.rank}</span>
                      <span className="font-semibold text-slate-700">{item.name}</span>
                      <span className="block text-[9px] text-slate-400 ml-5">{item.code}</span>
                    </td>
                    <td className="text-right text-slate-600">{fmtCompact(item.shares, '股')}</td>
                    <td className="text-right font-semibold text-slate-800">{fmtCompact(item.value, '元')}</td>
                    <td className={`text-right font-medium ${(item.valueChg ?? 0) > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                      {item.valueChg == null ? '—' : item.changeFromZero ? '由0新增' : `${item.valueChg > 0 ? '+' : ''}${fmtCompact(item.valueChg)}`}
                      {item.valueChgPct != null && <span className="block text-[9px] text-slate-400">{item.valueChgPct > 0 ? '+' : ''}{item.valueChgPct.toFixed(2)}%</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : board?.status !== 'unavailable' ? (
          <div className="rounded-md bg-slate-50 border border-slate-100 px-3 py-4 text-center">
            <p className="text-xs font-medium text-slate-700">官方完整名单无卖空成交，本期无 TOP10</p>
            <p className="text-[10px] text-slate-500 mt-1">{board?.asOf} · 沪深合计 {board?.universeCount?.toLocaleString('zh-CN') ?? '—'} 只，非零记录 0 只</p>
          </div>
        ) : (
          <p className="text-[11px] text-slate-500 rounded-md bg-slate-50 px-3 py-3">有效官方快照尚未取得，不展示空榜或替代排名；下一交易日夜间自动重试。</p>
        )}
        <div className="mt-2 flex items-start justify-between gap-2">
          <p className="text-[10px] text-slate-400 leading-relaxed">{board?.note}</p>
          <a href={board?.pageUrl} target="_blank" rel="noreferrer" className="shrink-0 inline-flex items-center gap-1 text-[10px] text-sky-600 hover:text-sky-800 underline underline-offset-2">
            官方源<ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ForeignCapitalPanel() {
  const { data } = useFundData();

  // ── CCASS 外资托管持股月末快照（2026-09-30 用户指令：港交所月底月初公布的外资加减仓）──
  const cf = data.ccassForeign;
  const fmtShares = (v?: number | null) => {
    if (v == null) return '—';
    const sign = v < 0 ? '-' : '';
    const a = Math.abs(v);
    return a >= 1e8 ? `${sign}${(a / 1e8).toFixed(2)}亿股` : `${sign}${(a / 1e4).toFixed(0)}万股`;
  };
  const chgCls = (v?: number | null) => v == null ? 'text-slate-300' : v >= 0 ? 'text-red-500' : 'text-emerald-600';

  // ── 外资机构权益披露（2026-09-30 用户指令：披露易 DI 大股东申报）──
  const di = data.diForeign;
  const diDirCls = (d: string) =>
    d === '增持' || d === '新进' ? 'bg-red-50 text-red-600' :
    d === '减持' || d === '清仓退出' ? 'bg-emerald-50 text-emerald-700' :
    d === '淡仓增' ? 'bg-orange-50 text-orange-600' :
    d === '淡仓减' ? 'bg-teal-50 text-teal-600' :
    'bg-slate-100 text-slate-500';

  return (
    <div className="space-y-6">
      <p className="text-[10px] text-slate-400 -mb-3">📌 本栏服务总览漏斗「第2步验证 · 北向态度」：外资流向佐证/证伪板块选择</p>
      {/* ====== CCASS 外资托管持股月末快照（港交所 SDW，月底/月初双触发；2026-09-30 用户指令） ====== */}
      {cf && (
        <Card id="ccass-foreign" className="border-indigo-200 shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Globe className="w-4 h-4 text-indigo-500" />
                外资托管持股动向（CCASS 月末快照）
                <span className="text-[10px] font-normal text-slate-400">20 只港股蓝筹 · 外资托管行合计持股量环比</span>
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-indigo-50 text-indigo-700 border-indigo-200">
                {cf.asOf ?? '待积累'}{cf.prevAsOf ? ` vs ${cf.prevAsOf}` : ''}
              </Badge>
            </div>
            <p className="text-[10px] text-amber-600 bg-amber-50 rounded px-2 py-1 mt-1 leading-relaxed">
              口径免责：CCASS 托管行持股≠纯外资最终持仓（nominee 混合账户含该行全部客户），仅作参考口径；港股通内资（中国结算）单列对照。
            </p>
          </CardHeader>
          <CardContent>
            {cf.missing && (
              <p className="text-[10px] text-slate-400 mb-2">⚠ 本月快照缺失（SDW 不可达，下月初自动重试），以下为最近可得快照。</p>
            )}
            {cf.items.length === 0 ? (
              <p className="text-[11px] text-slate-400">CCASS 快照积累中（首次月末触发后展示）</p>
            ) : (
              <>
                {/* 增持/减仓 top5 */}
                {cf.prevAsOf && (
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div className="rounded-lg border border-red-100 bg-red-50/40 p-2">
                      <p className="text-[10px] font-semibold text-red-600 mb-1">📈 外资增持 Top5（股数）</p>
                      {cf.topUp.map((i) => (
                        <div key={i.code} className="flex items-center justify-between text-[11px] py-0.5">
                          <span className="text-slate-700">{i.name} <span className="text-slate-400 text-[9px]">{i.code}</span></span>
                          <span className="font-semibold text-red-500">+{fmtShares(i.chg)}{i.chgPct != null && <span className="text-[9px] text-slate-400 ml-1">{i.chgPct >= 0 ? '+' : ''}{i.chgPct}%</span>}</span>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-2">
                      <p className="text-[10px] font-semibold text-emerald-700 mb-1">📉 外资减持 Top5（股数）</p>
                      {cf.topDown.map((i) => (
                        <div key={i.code} className="flex items-center justify-between text-[11px] py-0.5">
                          <span className="text-slate-700">{i.name} <span className="text-slate-400 text-[9px]">{i.code}</span></span>
                          <span className="font-semibold text-emerald-600">{fmtShares(i.chg)}{i.chgPct != null && <span className="text-[9px] text-slate-400 ml-1">{i.chgPct >= 0 ? '+' : ''}{i.chgPct}%</span>}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* 全量表 */}
                <div className="overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-[11px] min-w-[560px]">
                    <thead className="sticky top-0 bg-white z-10">
                      <tr className="text-slate-500 border-b border-slate-200">
                        <th className="text-left py-1.5 font-medium">标的</th>
                        <th className="text-right font-medium">外资托管持股</th>
                        <th className="text-right font-medium">环比变动</th>
                        <th className="text-right font-medium">环比%</th>
                        <th className="text-right font-medium">港股通对照</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cf.items.map((i) => (
                        <tr key={i.code} className="border-b border-slate-50 hover:bg-slate-50/60">
                          <td className="py-1.5 font-medium text-slate-700">{i.name} <span className="text-slate-400 text-[9px]">{i.code}</span></td>
                          <td className="text-right text-slate-600">{fmtShares(i.foreign)}</td>
                          <td className={`text-right font-semibold ${chgCls(i.chg)}`}>{i.chg == null ? '—' : `${i.chg >= 0 ? '+' : ''}${fmtShares(i.chg)}`}</td>
                          <td className={`text-right ${chgCls(i.chgPct)}`}>{i.chgPct == null ? '—' : `${i.chgPct >= 0 ? '+' : ''}${i.chgPct}%`}</td>
                          <td className="text-right text-slate-500">{fmtShares(i.south)}{i.southChg != null && <span className={`text-[9px] ml-1 ${chgCls(i.southChg)}`}>({i.southChg >= 0 ? '+' : ''}{fmtShares(i.southChg)})</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <p className="text-[10px] text-slate-400 mt-1.5">{cf.note}</p>
          </CardContent>
        </Card>
      )}

      {/* ====== 外资机构增减仓（港交所权益披露 DI 大股东申报，每日增量；2026-09-30 用户指令） ====== */}
      {di && (
        <Card id="di-foreign" className="border-sky-200 shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <FileText className="w-4 h-4 text-sky-500" />
                外资机构增减仓（权益披露）
                <span className="text-[10px] font-normal text-slate-400">港交所披露易 · 大股东申报 · 近{di.windowDays}天 {di.total} 条</span>
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-sky-50 text-sky-700 border-sky-200">
                截至 {di.asOf ?? '—'}
              </Badge>
            </div>
            <p className="text-[10px] text-amber-600 bg-amber-50 rounded px-2 py-1 mt-1 leading-relaxed">
              口径说明：仅持股跨越 5% 整数关口才强制申报（非全量持仓变动），申报滞后≤3 个交易日；「性质变化」多为借券/质押等非买卖操作；(S)=淡仓（做空方向）。机构为主流外资白名单，不代表全部外资。
            </p>
          </CardHeader>
          <CardContent>
            {di.missing ? (
              <p className="text-[11px] text-slate-400">近{di.windowDays}天暂无白名单外资机构申报（或披露易不可达，nightly 自动重试）</p>
            ) : (
              <>
                {/* 机构活跃度榜 */}
                {di.topInst.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {di.topInst.map((t) => (
                      <span key={t.name} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-sky-50 border border-sky-100 text-sky-700">
                        {t.name} ×{t.n}
                        {t.up > 0 && <span className="text-red-500">↑{t.up}</span>}
                        {t.down > 0 && <span className="text-emerald-600">↓{t.down}</span>}
                      </span>
                    ))}
                  </div>
                )}
                {/* 申报列表 */}
                <div className="overflow-x-auto max-h-80 overflow-y-auto">
                  <table className="w-full text-[11px] min-w-[640px]">
                    <thead className="sticky top-0 bg-white z-10">
                      <tr className="text-slate-500 border-b border-slate-200">
                        <th className="text-left py-1.5 font-medium">事件日</th>
                        <th className="text-left font-medium">机构</th>
                        <th className="text-left font-medium">标的</th>
                        <th className="text-left font-medium">方向</th>
                        <th className="text-right font-medium">涉及股数</th>
                        <th className="text-right font-medium">变动后持股</th>
                        <th className="text-right font-medium">公告</th>
                      </tr>
                    </thead>
                    <tbody>
                      {di.items.map((it) => (
                        <tr key={it.ref} className="border-b border-slate-50 hover:bg-slate-50/60">
                          <td className="py-1.5 text-slate-500 whitespace-nowrap">{it.date.slice(5)}</td>
                          <td className="text-slate-700 font-medium whitespace-nowrap">{it.inst ?? it.holder}</td>
                          <td className="text-slate-600 max-w-[180px] truncate" title={it.corp}>
                            {it.corpCn ? (
                              <span className="font-medium text-slate-700">{it.corpCn}
                                <span className="text-[9px] text-slate-400 ml-1">{it.stockCode}</span>
                              </span>
                            ) : it.corp}
                          </td>
                          <td className="whitespace-nowrap">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${diDirCls(it.direction)}`}>
                              {it.direction}{it.pos === 'S' && '(S)'}
                            </span>
                          </td>
                          <td className="text-right text-slate-600">
                            {fmtShares(it.shares)}
                            {it.pctOfHolding != null && (
                              <span className={`block text-[9px] ${it.pctOfHolding >= 0 ? 'text-red-400' : 'text-emerald-500'}`}>
                                持仓{it.pctOfHolding >= 0 ? '+' : ''}{it.pctOfHolding}%
                                {it.pctOfTotal != null && <span className="text-slate-300"> · 股本{it.pctOfTotal}%</span>}
                              </span>
                            )}
                            {it.pctOfHolding == null && it.holdingNote && (
                              <span className="block text-[9px] text-slate-400">{it.holdingNote}</span>
                            )}
                          </td>
                          <td className="text-right text-slate-700 font-semibold">
                            {it.resultPct != null ? `${it.resultPct}%` : '—'}
                            {it.resultShares != null && <span className="text-[9px] text-slate-400 ml-1">{fmtShares(it.resultShares)}</span>}
                          </td>
                          <td className="text-right">
                            <a href={it.url} target="_blank" rel="noreferrer"
                               className="text-sky-600 hover:text-sky-800 text-[10px] underline underline-offset-2">申报书</a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {di.total > di.items.length && (
                  <p className="text-[10px] text-slate-400 mt-1">仅展示最近 {di.items.length} 条（窗口共 {di.total} 条）</p>
                )}
              </>
            )}
            <p className="text-[10px] text-slate-400 mt-1.5">{di.note}</p>
          </CardContent>
        </Card>
      )}

      {/* ====== A 股北向卖空监测：日更检查 + 真实 last-good ====== */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ShortSellingCard board={data.shortSellingMonitor?.a} />
      </div>

      {/* Tips */}
      <Card className="bg-violet-50 border-violet-200">
        <CardContent className="p-4">
          <h4 className="font-bold text-violet-800 mb-2 flex items-center gap-2">
            <Activity className="w-4 h-4" />
            如何理解内外资分歧
          </h4>
          <ul className="text-sm text-violet-700 space-y-1">
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
              分歧越大 = 内资越看好、外资越看空，定价权之争越激烈
            </li>
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
              腾讯/小米/阿里：外资因美股映射/地缘政治减持，内资因估值洼地接盘
            </li>
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
              美团/信达生物：内外资一致看好，分歧较小，属于共识品种
            </li>
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
              数据来源：港交所权益披露系统 · 统计口径：月度累计
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
