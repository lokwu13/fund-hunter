import { Fragment } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Activity, Quote, Radar, ArrowLeftRight, Gauge, Shapes, LayoutGrid } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

export default function NationalTeamPanel() {
  const { data } = useFundData();

  const trendItems = data.broadTrend?.items ?? [];
  const vcpItems = data.broadVcp?.items ?? [];
  const volItems = data.indexVol?.items ?? [];

  const tierBadge = (tier?: string) => {
    if (tier === '低位') return <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">低位</Badge>;
    if (tier === '高位') return <Badge className="bg-red-100 text-red-700 text-[10px]">高位</Badge>;
    return <Badge className="bg-slate-100 text-slate-600 text-[10px]">半路</Badge>;
  };

  const statusText = (status?: string) => {
    if (status === '✅趋势候选') return <span className="text-emerald-600 font-semibold">{status}</span>;
    if (status === '低位观察（份额流出）') return <span className="text-amber-600">{status}</span>;
    if (status === '高位·仅展示') return <span className="text-slate-400">{status}</span>;
    return <span className="text-slate-500">{status ?? '--'}</span>;
  };

  const vcpBadge = (state?: string) => {
    if (state === '已突破') return <Badge className="bg-emerald-600 text-white text-[10px]">已突破</Badge>;
    if (state === '临近买点') return <Badge className="bg-amber-500 text-white text-[10px]">临近买点</Badge>;
    if (state === '未突破·观察') return <Badge className="bg-blue-100 text-blue-700 text-[10px]">未突破·观察</Badge>;
    return <span className="text-slate-300">无形态</span>;
  };

  return (
    <div className="space-y-6">
      {/* ====== 宽基市场短评 ====== */}
      {data.nationalTeamComment && (
        <Card id="nt-comment" className="bg-gradient-to-r from-red-50 to-orange-50 border-red-200">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <Quote className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-bold text-red-800 mb-1">宽基市场短评</h3>
                <p className="text-sm text-slate-700 leading-relaxed">{data.nationalTeamComment}</p>
                <p className="text-[10px] text-slate-400 mt-1.5">规则自动生成 · 基于份额异动 / 位置层 / 形态 / 波动率</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基指数全景（趋势 + 波动 + 形态 三合一） ====== */}
      {trendItems.length > 0 && (
        <Card id="index-vol">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <LayoutGrid className="w-5 h-5 text-red-600" />
              宽基指数全景（截至 {data.broadTrend?.trade_date}）
            </CardTitle>
            <CardDescription>{data.broadTrend?.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[900px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">指数</TableHead>
                    <TableHead className="text-xs text-right">现价</TableHead>
                    <TableHead className="text-xs text-right">近20日</TableHead>
                    <TableHead className="text-xs text-right">距60日高点</TableHead>
                    <TableHead className="text-xs text-center">位置层</TableHead>
                    <TableHead className="text-xs text-right">HV年分位</TableHead>
                    <TableHead className="text-xs text-right">PE TTM</TableHead>
                    <TableHead className="text-xs text-center">VCP形态</TableHead>
                    <TableHead className="text-xs">代表ETF</TableHead>
                    <TableHead className="text-xs text-center">状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trendItems.map((t) => {
                    const vol = volItems.find((v) => v.code === t.indexCode);
                    const vcp = vcpItems.find((v) => v.indexCode === t.indexCode);
                    return (
                      <TableRow key={t.indexCode} className="hover:bg-slate-50">
                        <TableCell className="text-xs font-semibold whitespace-nowrap">{t.indexName}</TableCell>
                        <TableCell className="text-xs text-right font-semibold">{t.close?.toFixed(2) ?? '--'}</TableCell>
                        <TableCell className={`text-xs text-right ${(t.ret20 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {t.ret20 != null ? `${t.ret20 >= 0 ? '+' : ''}${t.ret20.toFixed(1)}%` : '--'}
                        </TableCell>
                        <TableCell className={`text-xs text-right ${(t.distHigh60 ?? 0) > -3 ? 'text-red-600' : 'text-slate-600'}`}>
                          {t.distHigh60 != null ? `${t.distHigh60.toFixed(1)}%` : '--'}
                        </TableCell>
                        <TableCell className="text-xs text-center">{tierBadge(t.tier)}</TableCell>
                        <TableCell className="text-xs text-right">
                          {t.hvPct1y != null ? `${t.hvPct1y.toFixed(0)}%` : '--'}
                        </TableCell>
                        <TableCell className="text-xs text-right text-slate-500">
                          {vol?.peTtm ?? '--'}
                          {vol?.pePct2y != null && <span className="text-slate-400"> / {vol.pePct2y.toFixed(0)}%</span>}
                        </TableCell>
                        <TableCell className="text-xs text-center whitespace-nowrap">
                          {vcpBadge(vcp?.state)}
                          {vcp?.pattern && vcp.distPct != null && (
                            <div className="text-[10px] text-slate-400 mt-0.5">
                              {vcp.pattern} · 距枢轴{vcp.distPct}%
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="text-xs whitespace-nowrap">
                          {t.etfName}
                          <span className="text-slate-400 ml-1">{t.etfCode.split('.')[0]}</span>
                          <div className="text-[10px] text-slate-400">{t.shareNote}</div>
                        </TableCell>
                        <TableCell className="text-xs text-center whitespace-nowrap">{statusText(t.status)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基形态监测（VCP 三档） ====== */}
      {vcpItems.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Shapes className="w-5 h-5 text-red-600" />
              宽基形态监测（截至 {data.broadVcp?.trade_date}）
            </CardTitle>
            <CardDescription>{data.broadVcp?.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[760px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">指数</TableHead>
                    <TableHead className="text-xs">形态</TableHead>
                    <TableHead className="text-xs text-right">天数</TableHead>
                    <TableHead className="text-xs text-right">枢轴价</TableHead>
                    <TableHead className="text-xs text-right">距枢轴</TableHead>
                    <TableHead className="text-xs text-right">振幅</TableHead>
                    <TableHead className="text-xs text-right">量比</TableHead>
                    <TableHead className="text-xs text-center">状态</TableHead>
                    <TableHead className="text-xs">跟踪ETF</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vcpItems.map((v) => (
                    <TableRow key={v.indexCode} className={v.state === '临近买点' || v.state === '已突破' ? 'bg-amber-50/50' : 'hover:bg-slate-50'}>
                      <TableCell className="text-xs font-semibold whitespace-nowrap">{v.indexName}</TableCell>
                      <TableCell className="text-xs">{v.pattern ?? <span className="text-slate-300">—</span>}</TableCell>
                      <TableCell className="text-xs text-right">{v.days ?? '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.pivot != null ? v.pivot.toFixed(2) : '--'}</TableCell>
                      <TableCell className={`text-xs text-right font-semibold ${(v.distPct ?? 99) < 5 ? 'text-amber-600' : 'text-slate-600'}`}>
                        {v.distPct != null ? `${v.distPct}%` : '--'}
                      </TableCell>
                      <TableCell className="text-xs text-right">{v.amplitude != null ? `${v.amplitude}%` : '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.volRatio != null ? v.volRatio.toFixed(2) : '--'}</TableCell>
                      <TableCell className="text-xs text-center">{vcpBadge(v.state)}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">
                        {v.etfName}
                        <span className="text-slate-400 ml-1">{v.etfCode.split('.')[0]}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基份额资金流（ETF 份额雷达） ====== */}
      {data.etfShareRadar && data.etfShareRadar.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Radar className="w-5 h-5 text-red-600" />
                宽基份额资金流（截至 {data.etfShareRadar.trade_date}）
              </CardTitle>
              {data.etfShareRadar.alertCount > 0 && (
                <Badge className="bg-red-600 text-white text-xs">{data.etfShareRadar.alertCount} 只异动</Badge>
              )}
            </div>
            <CardDescription>{data.etfShareRadar.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[860px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">名称</TableHead>
                    <TableHead className="text-xs text-right">份额(亿)</TableHead>
                    <TableHead className="text-xs text-right">1日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-right">折算金额(亿)</TableHead>
                    <TableHead className="text-xs text-right">5日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-right">20日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-center">信号</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.etfShareRadar.items.map((e) => (
                    <TableRow key={e.code} className={e.alert ? 'bg-red-50/60' : 'hover:bg-slate-50'}>
                      <TableCell className="text-xs font-semibold whitespace-nowrap">
                        {e.name}
                        <span className="text-slate-400 ml-1">{e.code.split('.')[0]}</span>
                      </TableCell>
                      <TableCell className="text-xs text-right">{e.share.toFixed(2)}</TableCell>
                      <TableCell className={`text-xs text-right font-semibold ${(e.chg1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.chg1 != null ? `${e.chg1 >= 0 ? '+' : ''}${e.chg1.toFixed(2)}` : '--'}
                        {e.chg1Pct != null && <span className="text-slate-400 font-normal"> ({e.chg1Pct >= 0 ? '+' : ''}{e.chg1Pct.toFixed(1)}%)</span>}
                      </TableCell>
                      <TableCell className={`text-xs text-right font-bold ${(e.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.amt1 != null ? `${e.amt1 >= 0 ? '+' : ''}${e.amt1.toFixed(1)}` : '--'}
                      </TableCell>
                      <TableCell className={`text-xs text-right ${(e.chg5 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.chg5 != null ? `${e.chg5 >= 0 ? '+' : ''}${e.chg5.toFixed(2)}` : '--'}
                      </TableCell>
                      <TableCell className={`text-xs text-right ${(e.chg20 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.chg20 != null ? `${e.chg20 >= 0 ? '+' : ''}${e.chg20.toFixed(2)}` : '--'}
                      </TableCell>
                      <TableCell className="text-xs text-center">
                        {e.signal === '强信号'
                          ? <Badge className="bg-red-600 text-white text-[10px]">强信号</Badge>
                          : e.signal === '关注'
                            ? <Badge className="bg-amber-100 text-amber-700 text-[10px]">关注</Badge>
                            : <span className="text-slate-300">—</span>}
                        {e.trend3 && <div className="text-[10px] text-blue-600 mt-0.5">{e.trend3}</div>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基份额轮动（按系列分节） ====== */}
      {data.ntRotation && data.ntRotation.groups.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <ArrowLeftRight className="w-5 h-5 text-red-600" />
                宽基份额轮动（截至 {data.ntRotation.trade_date}）
              </CardTitle>
              {data.ntRotation.resonance.hit && (
                <Badge className="bg-amber-500 text-white text-xs">
                  共振·大资金{data.ntRotation.resonance.direction}信号
                </Badge>
              )}
            </div>
            <CardDescription>{data.ntRotation.note}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.ntRotation.resonance.hit && (
              <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 text-xs text-amber-800">
                <span className="font-bold">⚠ 共振信号：</span>
                {data.ntRotation.resonance.count} 只核心宽基ETF（{data.ntRotation.resonance.names.slice(0, 4).join('、')}
                {data.ntRotation.resonance.names.length > 4 ? ' 等' : ''}）同日同向{data.ntRotation.resonance.direction}，
                属于大资金情绪信号，关注后续 1-2 日是否延续。
              </div>
            )}
            {data.ntRotation.groups.map((g) => (
              <div key={g.key}>
                <h4 className="text-sm font-bold mb-2 text-red-800">{g.name}</h4>
                <div className="overflow-x-auto">
                  <Table className="min-w-[760px]">
                    <TableHeader>
                      <TableRow className="bg-red-50">
                        <TableHead className="text-xs">ETF</TableHead>
                        <TableHead className="text-xs text-right">最新份额(亿)</TableHead>
                        <TableHead className="text-xs text-right">日变化</TableHead>
                        <TableHead className="text-xs text-right">5日累计</TableHead>
                        <TableHead className="text-xs text-right">金额(亿)</TableHead>
                        <TableHead className="text-xs text-center">信号</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {g.series.map((s) => (
                        <Fragment key={s.name}>
                          <TableRow className="bg-slate-50">
                            <TableCell colSpan={6} className="text-[11px] font-bold text-slate-500 py-1">
                              {s.name}
                            </TableCell>
                          </TableRow>
                          {s.items.map((r) => (
                            <TableRow key={r.code} className={r.signal ? 'bg-red-50/50' : 'hover:bg-slate-50'}>
                              <TableCell className="text-xs font-semibold whitespace-nowrap">
                                {r.name}
                                <span className="text-slate-400 ml-1">{r.code.split('.')[0]}</span>
                              </TableCell>
                              <TableCell className="text-xs text-right">{r.share.toFixed(2)}</TableCell>
                              <TableCell className={`text-xs text-right font-semibold ${(r.chg1Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.chg1Pct != null ? `${r.chg1Pct >= 0 ? '+' : ''}${r.chg1Pct.toFixed(1)}%` : '--'}
                                {r.chg1 != null && <span className="text-slate-400 font-normal"> ({r.chg1 >= 0 ? '+' : ''}{r.chg1.toFixed(2)})</span>}
                              </TableCell>
                              <TableCell className={`text-xs text-right ${(r.chg5Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.chg5Pct != null ? `${r.chg5Pct >= 0 ? '+' : ''}${r.chg5Pct.toFixed(1)}%` : '--'}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(r.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.amt1 != null ? `${r.amt1 >= 0 ? '+' : ''}${r.amt1.toFixed(1)}` : '--'}
                              </TableCell>
                              <TableCell className="text-xs text-center">
                                {r.signal === '强信号'
                                  ? <Badge className="bg-red-600 text-white text-[10px]">强信号</Badge>
                                  : r.signal === '关注'
                                    ? <Badge className="bg-amber-100 text-amber-700 text-[10px]">关注</Badge>
                                    : <span className="text-slate-300">—</span>}
                                {r.trend3 && <div className="text-[10px] text-blue-600 mt-0.5">{r.trend3}</div>}
                              </TableCell>
                            </TableRow>
                          ))}
                          {s.total && (
                            <TableRow className="bg-slate-100 font-bold">
                              <TableCell className="text-xs">{s.name}合计</TableCell>
                              <TableCell className="text-xs text-right">{s.total.share?.toFixed(2) ?? '--'}</TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.chg1Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.chg1Pct != null ? `${s.total.chg1Pct >= 0 ? '+' : ''}${s.total.chg1Pct.toFixed(1)}%` : '--'}
                                {s.total.chg1 != null && <span className="text-slate-400 font-normal"> ({s.total.chg1 >= 0 ? '+' : ''}{s.total.chg1.toFixed(2)})</span>}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.chg5Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.chg5Pct != null ? `${s.total.chg5Pct >= 0 ? '+' : ''}${s.total.chg5Pct.toFixed(1)}%` : '--'}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.amt1 != null ? `${s.total.amt1 >= 0 ? '+' : ''}${s.total.amt1.toFixed(1)}` : '--'}
                              </TableCell>
                              <TableCell className="text-xs text-center text-slate-300">—</TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ))}
            <p className="text-[10px] text-slate-400">
              金额=份额变化×当日收盘价 · 系列合计百分比按份额加权
            </p>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基波动率说明卡（浅色版） ====== */}
      {volItems.length > 0 && (
        <Card className="bg-slate-50 border-slate-200">
          <CardContent className="p-4 space-y-3">
            <div>
              <h4 className="text-sm font-bold text-slate-800 mb-1">🌡️ 这张表量的是什么？——市场的"颠簸程度"</h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                把大盘想象成一辆车：<b>HV20 是最近 1 个月的路面颠簸度，HV60 是最近 3 个月的</b>。数字越大路越烂，坐在车里（持仓）越难受。
              </p>
              <div className="bg-white border-l-2 border-blue-400 rounded-r-lg px-3 py-2 mt-2 text-xs text-slate-600 leading-relaxed">
                <b>"近一年分位"就是排名：</b>把过去一年每个交易日的颠簸度排个队，今天站在什么位置。
                比如 <b>94% 分位</b> = 今天比过去一年 94% 的日子都颠簸，属于一年里最烂的那 6% 路况。
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-red-50 border border-red-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-red-600 mb-1">🔴 高热（分位 &gt;80%）</b>
                路面最烂的一段。不加仓、不抄底、不追热点，安全带系紧（收紧止损），等路况变好再说。
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-amber-600 mb-1">🟡 升温 / 降温途中</b>
                HV20 明显高于 HV60 = 路在变坏（升温），反过来是在变好（降温）。升温期减减速，降温期可以开始看路边的上车点。
              </div>
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-emerald-600 mb-1">🟢 低位（分位 &lt;25%）</b>
                一年里最平静的路段。平静往往是大行情前的"憋劲"期——这时去翻 VCP 栏目，若有板块🟢收缩共振，就是高质量伏击区。
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基波动率明细（ETF VIX） ====== */}
      {data.indexVol && data.indexVol.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Gauge className="w-5 h-5 text-red-600" />
              宽基波动率明细（截至 {data.indexVol.trade_date}）
            </CardTitle>
            <CardDescription>{data.indexVol.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[720px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">指数</TableHead>
                    <TableHead className="text-xs text-right">HV20(%)</TableHead>
                    <TableHead className="text-xs text-right">HV60(%)</TableHead>
                    <TableHead className="text-xs text-right">5日变化</TableHead>
                    <TableHead className="text-xs text-right">年分位</TableHead>
                    <TableHead className="text-xs text-right">PE TTM</TableHead>
                    <TableHead className="text-xs text-right">PE 2年分位</TableHead>
                    <TableHead className="text-xs text-center">状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.indexVol.items.map((v) => (
                    <TableRow key={v.code} className="hover:bg-slate-50">
                      <TableCell className="text-xs font-semibold">{v.name}</TableCell>
                      <TableCell className="text-xs text-right font-semibold">{v.hv20 ?? '--'}</TableCell>
                      <TableCell className="text-xs text-right text-slate-500">{v.hv60 ?? '--'}</TableCell>
                      <TableCell className={`text-xs text-right ${(v.hv20Chg5 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {v.hv20Chg5 != null ? `${v.hv20Chg5 >= 0 ? '+' : ''}${v.hv20Chg5.toFixed(1)}` : '--'}
                      </TableCell>
                      <TableCell className="text-xs text-right">{v.hvPct1y != null ? `${v.hvPct1y.toFixed(0)}%` : '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.peTtm ?? '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.pePct2y != null ? `${v.pePct2y.toFixed(0)}%` : '--'}</TableCell>
                      <TableCell className="text-xs text-center">
                        <Badge className={`text-[10px] ${
                          v.status === '升温' ? 'bg-red-100 text-red-700' :
                          v.status === '降温' ? 'bg-green-100 text-green-700' :
                          'bg-slate-100 text-slate-600'
                        }`}>
                          {v.status}{v.low ? '·低位' : ''}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 数据更新说明 ====== */}
      <Card className="bg-slate-50 border-slate-200">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-slate-600" />
            <h4 className="font-bold text-slate-800">数据更新说明</h4>
          </div>
          <div className="grid grid-cols-3 gap-4 text-xs text-slate-600">
            <div>
              <p className="font-semibold mb-1">份额资金流 / 轮动</p>
              <p>13 只核心宽基 ETF 份额逐日跟踪，每个交易日更新（T 日份额 T+1 披露）</p>
            </div>
            <div>
              <p className="font-semibold mb-1">位置层 / 形态</p>
              <p>基于宽基指数日线（60 日高点 / 20 日涨幅 / VCP 平台口径），每日收盘后更新</p>
            </div>
            <div>
              <p className="font-semibold mb-1">波动率 / 估值</p>
              <p>HV20/HV60 历史波动率与 PE TTM 分位，每日更新</p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-3">数据来源：Tushare（指数日线 / ETF 份额 / 指数估值） · 口径详见各卡片说明</p>
        </CardContent>
      </Card>
    </div>
  );
}
