import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  TrendingUp, TrendingDown, Zap, Activity, ArrowLeftRight, SortDesc
} from 'lucide-react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, LabelList, Cell
} from 'recharts';
import { useFundData, type SectorFlowItem } from '@/hooks/useFundData';

interface SectorHeatmapProps {
  detailed?: boolean;
}

// 颜色分级（基于4周累计的主力净流入，单位：亿元）
const flowColors: Record<string, { bg: string; text: string; border: string }> = {
  'inflow-heavy':   { bg: 'bg-orange-500', text: 'text-white', border: 'border-orange-600' },
  'inflow-mid':     { bg: 'bg-orange-400', text: 'text-white', border: 'border-orange-500' },
  'inflow-light':   { bg: 'bg-orange-300', text: 'text-orange-900', border: 'border-orange-400' },
  'inflow-min':     { bg: 'bg-orange-200', text: 'text-orange-800', border: 'border-orange-300' },
  'neutral':        { bg: 'bg-slate-200', text: 'text-slate-600', border: 'border-slate-300' },
  'outflow-min':    { bg: 'bg-sky-200', text: 'text-sky-800', border: 'border-sky-300' },
  'outflow-light':  { bg: 'bg-sky-300', text: 'text-white', border: 'border-sky-400' },
  'outflow-mid':    { bg: 'bg-sky-400', text: 'text-white', border: 'border-sky-500' },
  'outflow-heavy':  { bg: 'bg-sky-500', text: 'text-white', border: 'border-sky-600' },
};

function getFlowLevel(flow: number): string {
  if (flow >= 100) return 'inflow-heavy';
  if (flow >= 50) return 'inflow-mid';
  if (flow >= 20) return 'inflow-light';
  if (flow > 0) return 'inflow-min';
  if (flow === 0) return 'neutral';
  if (flow >= -20) return 'outflow-min';
  if (flow >= -50) return 'outflow-light';
  if (flow >= -100) return 'outflow-mid';
  return 'outflow-heavy';
}

const formatMoney = (value?: number | null) => (
  value == null || !Number.isFinite(value)
    ? '—'
    : `${value > 0 ? '+' : ''}${value.toFixed(1)}亿`
);

const shortTagClass: Record<string, string> = {
  新晋: 'bg-amber-100 text-amber-700',
  转流出: 'bg-amber-100 text-amber-700',
  加速: 'bg-orange-100 text-orange-700',
  降温: 'bg-slate-100 text-slate-600',
  持续: 'bg-cyan-100 text-cyan-700',
};

function ResonanceEvidence({ flow }: { flow: SectorFlowItem }) {
  if (!flow.eci && !flow.bottom && !flow.resonance) {
    return <span className="text-slate-400">—</span>;
  }
  return (
    <div className="min-w-56 space-y-0.5 text-[10px] leading-snug">
      {flow.eci && (
        <p className="text-cyan-700">
          ECI {flow.eci.parent} 第{flow.eci.rank} · {flow.eci.score.toFixed(1)}
        </p>
      )}
      {flow.bottom && (
        <p className="text-teal-700">
          积聚{flow.bottom.both ? '·双档' : ''} 30日{formatMoney(flow.bottom.inflow30d)} / 60日{formatMoney(flow.bottom.inflow60d)}
        </p>
      )}
      {flow.resonance && (
        <p className="text-indigo-700">
          {flow.resonance.source === 'step2'
            ? `${flow.resonance.lifecycle || '板块入选'} · ${flow.resonance.pattern || '形态已确认'}`
            : `VCP ${flow.resonance.signal}`}
        </p>
      )}
    </div>
  );
}

export default function SectorHeatmap({ detailed = false }: SectorHeatmapProps) {
  const { data } = useFundData();
  const [rotTab, setRotTab] = useState<'tushare' | 'em'>('tushare');
  const flows = data.sectorFlows;
  const inflowTop = flows?.inflowTop || [];
  const outflowTop = flows?.outflowTop || [];
  const limit = detailed ? 10 : 5;
  const unifiedRows: Array<{ flow: SectorFlowItem; direction: 'inflow' | 'outflow' }> = [
    ...inflowTop.slice(0, limit).map(flow => ({ flow, direction: 'inflow' as const })),
    ...outflowTop.slice(0, limit).map(flow => ({ flow, direction: 'outflow' as const })),
  ];
  const totalInflow = inflowTop.reduce((sum, flow) => sum + flow.net5, 0);
  const totalOutflow = outflowTop.reduce((sum, flow) => sum + flow.net5, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between bg-white rounded-lg border border-slate-200 px-4 py-3 flex-wrap gap-2">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-orange-400" />
            <span className="text-xs text-slate-600">近5日流入TOP10 <b className="text-orange-600">{formatMoney(totalInflow)}</b></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-sky-400" />
            <span className="text-xs text-slate-600">近5日流出TOP10 <b className="text-sky-600">{formatMoney(totalOutflow)}</b></span>
          </div>
        </div>
        <Badge variant="outline" className="text-xs bg-slate-50">{flows?.trade_date || '等待有效资金数据'}</Badge>
      </div>

      {/* 总览与板块页共用同一数据源、同一排序；仅展示条数不同。 */}
      <Card id="short-term-sector-flows" className="shadow-sm border-orange-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2 flex-wrap">
            <TrendingUp className="w-5 h-5 text-orange-600" />
            短期资金统一表
            <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600">流入/流出 TOP{limit}</Badge>
          </CardTitle>
          <CardDescription className="text-[11px]">
            加速度=近5日−前5日；流入按加速度、5日流入天数、5日净流入降序，流出镜像。20日仅作背景，不参与排序。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table className="min-w-[1080px]">
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="text-xs">板块</TableHead>
                  <TableHead className="text-xs text-right">当日</TableHead>
                  <TableHead className="text-xs text-right">近5日</TableHead>
                  <TableHead className="text-xs text-right" title="加速度=近5日净流入−前5日净流入">较前5日</TableHead>
                  <TableHead className="text-xs">持续性</TableHead>
                  <TableHead className="text-xs">共振结论</TableHead>
                  <TableHead className="text-xs">双龙头</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unifiedRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-8 text-center text-xs text-slate-400">
                      {flows?.stale ? '资金历史有效日不符合预期，本期不展示旧榜。' : '完整20日资金历史不足，暂无可展示榜单。'}
                    </TableCell>
                  </TableRow>
                ) : unifiedRows.map(({ flow, direction }, index) => {
                  const isInflow = direction === 'inflow';
                  const days5 = isInflow ? flow.inflowDays5 : flow.outflowDays5;
                  const days10 = isInflow ? flow.inflowDays10 : flow.outflowDays10;
                  const rank = unifiedRows.slice(0, index + 1).filter(row => row.direction === direction).length;
                  return (
                    <TableRow key={`${direction}-${flow.name}`} className="hover:bg-slate-50 align-top">
                      <TableCell className="min-w-44">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs font-bold text-slate-800">#{rank} {flow.name}</span>
                          <Badge className={`text-[9px] border-0 ${isInflow ? 'bg-orange-100 text-orange-700' : 'bg-sky-100 text-sky-700'}`}>
                            {isInflow ? '流入' : '流出'}
                          </Badge>
                          {(flow.tags || []).map(tag => (
                            <Badge key={tag} className={`text-[9px] border-0 ${shortTagClass[tag] || 'bg-slate-100 text-slate-500'}`}>{tag}</Badge>
                          ))}
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1" title="20日资金仅作背景，不参与排名">20日背景 {formatMoney(flow.net20)}</p>
                      </TableCell>
                      <TableCell className={`text-xs text-right font-bold ${flow.net1 >= 0 ? 'text-orange-600' : 'text-sky-600'}`}>{formatMoney(flow.net1)}</TableCell>
                      <TableCell className={`text-xs text-right font-bold ${flow.net5 >= 0 ? 'text-orange-600' : 'text-sky-600'}`}>{formatMoney(flow.net5)}</TableCell>
                      <TableCell className="text-right">
                        <p className={`text-xs font-bold ${flow.accel5 >= 0 ? 'text-orange-600' : 'text-sky-600'}`}>{formatMoney(flow.accel5)}</p>
                        <p className="text-[10px] text-slate-400 mt-0.5">前5日 {formatMoney(flow.prevNet5)}</p>
                      </TableCell>
                      <TableCell className="min-w-28">
                        <p className="text-xs font-semibold text-slate-700">{days5}/5 · {days10}/10</p>
                        <p className="text-[10px] text-slate-400 mt-0.5">近5日 / 近10日同向</p>
                      </TableCell>
                      <TableCell><ResonanceEvidence flow={flow} /></TableCell>
                      <TableCell className="min-w-36">
                        {flow.leaders?.length ? (
                          <div className="space-y-1">
                            {flow.leaders.slice(0, 2).map(leader => (
                              <p key={leader.code || leader.name} className="text-[11px] font-semibold text-slate-700">
                                {leader.name}<span className="text-[9px] font-normal text-slate-400 ml-1">{leader.code || ''}</span>
                              </p>
                            ))}
                          </div>
                        ) : <span className="text-xs text-slate-400">—</span>}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <p className="text-[10px] text-slate-400 mt-3">
            金额单位：亿元；缺日或非数值行业不补0、不入榜。{flows?.incompleteSectors?.length ? `本期不完整行业 ${flows.incompleteSectors.length} 个。` : ''}
          </p>
        </CardContent>
      </Card>

      {/* ====== 板块页专属：行业/概念拥挤度简表（必须在每日涨幅轮动榜正上方） ====== */}
      {detailed && data.sectorCrowding && (
        <Card id="sector-crowding" className="shadow-sm border-amber-200">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Activity className="w-4 h-4 text-amber-500" />
                行业 / 概念拥挤度
                <span className="text-[10px] font-normal text-slate-400">行业 5 + 概念 5 · 透明分档</span>
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                {data.sectorCrowding.trade_date || '等待有效日'}
              </Badge>
            </div>
            <CardDescription className="text-[10px] leading-relaxed">{data.sectorCrowding.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[720px]">
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead className="text-xs">名称</TableHead>
                    <TableHead className="text-xs">类型</TableHead>
                    <TableHead className="text-xs text-right">20日涨幅</TableHead>
                    <TableHead className="text-xs text-right">成交热度</TableHead>
                    <TableHead className="text-xs text-right">10日热榜</TableHead>
                    <TableHead className="text-xs text-right">拥挤度</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.sectorCrowding.items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-7 text-center text-xs text-slate-400">
                        本批有效日无可用行业或概念，陈旧对象未入榜。
                      </TableCell>
                    </TableRow>
                  ) : data.sectorCrowding.items.map((item) => (
                    <TableRow key={`${item.type}-${item.name}`} className="hover:bg-slate-50">
                      <TableCell className="text-xs font-semibold text-slate-800">{item.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${item.type === '行业' ? 'bg-cyan-50 text-cyan-700' : 'bg-purple-50 text-purple-700'}`}>
                          {item.type}
                        </Badge>
                      </TableCell>
                      <TableCell className={`text-xs text-right font-semibold ${item.ret20 == null ? 'text-slate-400' : item.ret20 >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {item.ret20 == null ? '—' : `${item.ret20 >= 0 ? '+' : ''}${item.ret20.toFixed(1)}%`}
                      </TableCell>
                      <TableCell className="text-xs text-right text-slate-600" title={item.amountPct == null ? '无可靠成交额，不补0' : '最新成交额在过去250交易日中的分位'}>
                        {item.amountPct == null ? '—' : `${item.amountPct.toFixed(1)}%`}
                      </TableCell>
                      <TableCell
                        className="text-xs text-right text-slate-600"
                        title={!item.heatReady || item.hits10 == null || item.streak == null
                          ? (item.heatReason || '热榜样本不足')
                          : '近10日每日涨幅Top10命中与当前连续天数'}
                      >
                        {!item.heatReady || item.hits10 == null || item.streak == null
                          ? '样本不足'
                          : `${item.hits10}次 · 连${item.streak}天`}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge title={item.reason} className={`text-[10px] border-0 ${
                          item.level === '过热' ? 'bg-rose-100 text-rose-700' :
                          item.level === '偏高' ? 'bg-amber-100 text-amber-700' :
                          item.level === '低' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'
                        }`}>{item.level}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ===== 每日涨幅轮动榜（原工具栏目整块迁入；双口径、网格、summary、徽章不变） ===== */}
      {detailed && data.sectorRotation && data.sectorRotation.grid.length > 0 && (() => {
        const rot = data.sectorRotation;
        // 同一板块跨列同色系追踪：按上榜热度顺序分配调色板（描边+角标底色）
        const ROT_PALETTE = ['#dc2626', '#ea580c', '#d97706', '#65a30d', '#0d9488', '#0284c7',
                             '#4f46e5', '#9333ea', '#db2777', '#57534e', '#16a34a', '#0891b2'];
        const colorOf: Record<string, string> = {};
        rot.stats.forEach((s, i) => { colorOf[s.sector] = ROT_PALETTE[i % ROT_PALETTE.length]; });
        const statOf: Record<string, (typeof rot.stats)[number]> = {};
        rot.stats.forEach((s) => { statOf[s.sector] = s; });
        // 涨幅深浅：红色深浅（A股红涨），<=0 的榜首格给灰
        const cellBg = (ret: number) => ret <= 0
          ? 'rgba(100,116,139,0.18)'
          : `rgba(220,38,38,${Math.min(0.88, 0.18 + ret / 7).toFixed(2)})`;
        const overheatN = rot.stats.filter((s) => s.overheat).length;
        // ── 东财双轨（2026-09-29 用户批准）：em 可用则可切 tab；不可用灰态说明 ──
        const em = rot.em;
        const emOk = !!(em && em.available && em.grid.length > 0);
        const isEm = rotTab === 'em' && emOk;
        const view = isEm ? { days: em!.days, grid: em!.grid } : { days: rot.days, grid: rot.grid };
        // 东财口径的同色追踪：按上榜顺序（网格首次出现）分配调色板
        const emColorOf: Record<string, string> = {};
        if (isEm) {
          let ci = 0;
          for (const g of view.grid) for (const r of g.rows) {
            if (!(r.sector in emColorOf)) { emColorOf[r.sector] = ROT_PALETTE[ci % ROT_PALETTE.length]; ci++; }
          }
        }
        return (
          <Card id="sector-rotation" className="border-rose-200 shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <SortDesc className="w-4 h-4 text-rose-500" />
                  每日涨幅轮动榜
                  <span className="text-[10px] font-normal text-slate-400">近{view.days.length}交易日 × 每日行业涨幅前10 · 同色描边=同一板块跨日追踪</span>
                </CardTitle>
                <div className="flex items-center gap-1.5">
                  {overheatN > 0 && (
                    <Badge className="text-[10px] border-0 bg-rose-600 text-white">🔥过热 {overheatN} 个</Badge>
                  )}
                  <Badge variant="outline" className="text-xs bg-rose-50 text-rose-700 border-rose-200">
                    {rot.trade_date}
                  </Badge>
                </div>
              </div>
              {/* 口径切换 tab（东财快照自 2026-09-29 起积累，首日列少如实展示） */}
              <div className="flex items-center gap-1 mt-1.5">
                <button type="button" onClick={() => setRotTab('tushare')}
                        className={`text-[10px] px-2 py-0.5 rounded-full border ${!isEm ? 'bg-rose-600 text-white border-rose-600' : 'text-slate-500 border-slate-200 hover:border-rose-300'}`}>
                  Tushare口径（L2等权·250日历史）
                </button>
                <button type="button" onClick={() => emOk && setRotTab('em')}
                        title={em?.note}
                        className={`text-[10px] px-2 py-0.5 rounded-full border ${isEm ? 'bg-orange-500 text-white border-orange-500' : emOk ? 'text-slate-500 border-slate-200 hover:border-orange-300' : 'text-slate-300 border-slate-100 cursor-not-allowed'}`}>
                  东财口径{emOk ? `（快照${em!.snapshotDays}天·积累中）` : '（待补·快照积累中）'}
                </button>
                {isEm && (
                  <span className="text-[9px] text-orange-600/80">东财无历史回补，仅作对照；过热判定以 Tushare 口径为准</span>
                )}
              </div>
              {!isEm && (
                <p className="text-[11px] text-rose-800 bg-rose-50 rounded-md px-2 py-1.5 mt-1 leading-relaxed">
                  轮动解读：{rot.summary}
                </p>
              )}
              {isEm && (
                <p className="text-[11px] text-orange-800 bg-orange-50 rounded-md px-2 py-1.5 mt-1 leading-relaxed">
                  {em!.note}
                </p>
              )}
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="text-[10px] border-separate" style={{ borderSpacing: '2px', minWidth: '900px' }}>
                  <thead>
                    <tr>
                      <th className="text-slate-400 font-medium text-left px-1 py-0.5 sticky left-0 bg-white z-10">名次</th>
                      {view.days.map((d) => (
                        <th key={d} className="text-slate-500 font-medium px-1 py-0.5 whitespace-nowrap">{d}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: 10 }, (_, rankIdx) => (
                      <tr key={rankIdx}>
                        <td className="text-slate-400 px-1 py-0.5 sticky left-0 bg-white z-10">{rankIdx + 1}</td>
                        {view.grid.map((g) => {
                          const cell = g.rows[rankIdx];
                          if (!cell) return <td key={g.date} />;
                          const st = isEm ? undefined : statOf[cell.sector];
                          const c = (isEm ? emColorOf[cell.sector] : colorOf[cell.sector]) || '#64748b';
                          return (
                            <td key={g.date}
                                title={`${g.date} 第${cell.rank}名：${cell.sector} ${cell.ret >= 0 ? '+' : ''}${cell.ret}%${st ? `｜近10日上榜${st.hits10}次·连${st.streak}天·${st.phase}` : ''}${isEm ? '｜东财口径' : ''}`}
                                className="px-1 py-0.5 rounded-sm whitespace-nowrap text-center font-medium"
                                style={{
                                  background: cellBg(cell.ret),
                                  color: cell.ret >= 2 ? '#fff' : '#7f1d1d',
                                  borderBottom: `2px solid ${c}`,
                                }}>
                              {st?.overheat && '🔥'}{cell.sector} {cell.ret >= 0 ? '+' : ''}{cell.ret}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 轮动热度统计（上榜板块，Tushare 口径） */}
              {!isEm && (
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  {rot.stats.slice(0, 12).map((s) => (
                    <Badge key={s.sector} variant="outline"
                           className={`text-[10px] ${s.overheat ? 'border-rose-400 bg-rose-50 text-rose-700 font-semibold' : s.phase === '中段' ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-slate-200 text-slate-500'}`}
                           title={`近10日上榜${s.hits10}次 · 当前连续${s.streak}天 · 距上次上榜${s.sinceLast}天 · 近10日累计${s.cum10 != null ? (s.cum10 >= 0 ? '+' : '') + s.cum10 + '%' : '—'}`}>
                      <span className="inline-block w-1.5 h-1.5 rounded-full mr-1" style={{ background: colorOf[s.sector] }} />
                      {s.label} {s.sector}（{s.hits10}次{s.streak > 0 ? `/连${s.streak}天` : ''}）
                    </Badge>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-slate-400 mt-1.5">{isEm ? em!.note : rot.note}</p>
            </CardContent>
          </Card>
        );
      })()}

      {/* ====== CONCEPT INFLOW HEATMAP (TOP 10) ====== */}
      {data.conceptSectors && data.conceptSectors.length > 0 && (
        <>
          <div className="border-t border-dashed border-slate-300 my-4" />
          <Card className="shadow-sm border-purple-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Zap className="w-5 h-5 text-purple-600" />
                概念板块资金流向
                <Badge variant="outline" className="text-xs bg-purple-50 text-purple-600">4周累计 · 24个热点概念</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* 概念流入 TOP */}
              <div>
                <p className="text-xs font-semibold text-orange-600 mb-2 flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />主力净流入
                </p>
                <div className="grid gap-2 grid-cols-5">
                  {data.conceptSectors.filter((c: any) => (c.mainFlow || 0) > 0).map((concept: any) => {
                    const flow = concept.mainFlow || 0;
                    const level = getFlowLevel(flow);
                    const colors = flowColors[level];
                    return (
                      <div
                        key={concept.name}
                        className={`${colors.bg} ${colors.text} rounded-lg p-3 border ${colors.border} transition-all hover:scale-105 hover:shadow-md cursor-pointer relative`}
                      >
                        {concept.isAnomaly && (
                          <div className="absolute -top-1.5 -right-1.5 z-10">
                            <Zap className="w-5 h-5 text-amber-500 fill-amber-500 drop-shadow" />
                          </div>
                        )}
                        <p className="text-sm font-bold truncate pr-2">{concept.name}</p>
                        <p className="text-lg font-bold mt-1">+{flow}亿</p>
                        {concept.isAnomaly && (
                          <p className="text-[10px] mt-0.5 opacity-90 font-semibold">单周+{concept.maxWeeklyFlow}亿</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              {/* 概念流出 TOP */}
              <div>
                <p className="text-xs font-semibold text-sky-600 mb-2 flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5" />主力净流出
                </p>
                <div className="grid gap-2 grid-cols-5">
                  {data.conceptSectors.filter((c: any) => (c.mainFlow || 0) <= 0).map((concept: any) => {
                    const flow = concept.mainFlow || 0;
                    const level = getFlowLevel(flow);
                    const colors = flowColors[level];
                    return (
                      <div
                        key={concept.name}
                        className={`${colors.bg} ${colors.text} rounded-lg p-3 border ${colors.border} transition-all hover:scale-105 hover:shadow-md cursor-pointer relative`}
                      >
                        {concept.isAnomaly && (
                          <div className="absolute -top-1.5 -right-1.5 z-10">
                            <Zap className="w-5 h-5 text-amber-500 fill-amber-500 drop-shadow" />
                          </div>
                        )}
                        <p className="text-sm font-bold truncate pr-2">{concept.name}</p>
                        <p className="text-lg font-bold mt-1">{flow}亿</p>
                        {concept.isAnomaly && (
                          <p className="text-[10px] mt-0.5 opacity-90 font-semibold">单周{concept.maxWeeklyFlow}亿</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 text-xs text-slate-500 flex-wrap">
        <div className="flex items-center gap-1">
          <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
          <span>单周突增：某一周流入占4周总量的50%以上且≥20亿</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-orange-400" />
          <span>颜色深浅代表资金规模</span>
        </div>
      </div>

      {/* ====== 板块资金轮动（份额口径，从宽基栏目迁入） ====== */}
      {data.etfRotation && data.etfRotation.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <ArrowLeftRight className="w-5 h-5 text-orange-600" />
              板块资金轮动 · 份额口径（截至 {data.etfRotation.trade_date}）
            </CardTitle>
            <CardDescription>{data.etfRotation.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {data.etfRotation.items.map((c) => {
                const maxAbs = Math.max(...data.etfRotation!.items.map((x) => Math.abs(x.net5d)), 1);
                const pct = Math.abs(c.net5d) / maxAbs * 100;
                return (
                  <div key={c.cat} className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-700 w-16 flex-shrink-0">{c.cat}</span>
                    <span className="text-[10px] text-slate-400 w-10 flex-shrink-0">{c.count}只</span>
                    <div className="flex-1 h-4 bg-slate-50 rounded relative overflow-hidden">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-slate-200" />
                      <div
                        className={`absolute inset-y-0.5 rounded-sm ${c.net5d >= 0 ? 'bg-red-400 left-1/2' : 'bg-green-500 right-1/2'}`}
                        style={{ width: `${pct / 2}%` }}
                      />
                    </div>
                    <span className={`text-xs font-bold w-16 text-right flex-shrink-0 ${c.net5d >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {c.net5d >= 0 ? '+' : ''}{c.net5d.toFixed(1)}亿
                    </span>
                    <span className={`text-[10px] w-14 text-right flex-shrink-0 ${c.todayNet >= 0 ? 'text-red-400' : 'text-green-500'}`}>
                      当日{c.todayNet >= 0 ? '+' : ''}{c.todayNet.toFixed(1)}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="text-[10px] text-slate-400 mt-3">
              条形为近5日净额（份额变化×收盘价，亿元），右侧小字为当日净额 · 全市场ETF当日合计 {data.etfRotation.totalToday >= 0 ? '+' : ''}{data.etfRotation.totalToday.toFixed(1)} 亿
            </p>
          </CardContent>
        </Card>
      )}

      {/* ====== 板块页专属：板块生命周期分布与分组（与总览漏斗第2步同口径） ====== */}
      {detailed && data.funnel?.lifecycleAll && (() => {
        const lcAll = data.funnel.lifecycleAll;
        const order = ['积聚期', '启动期', '主升期', '高潮期', '退潮期', '半路'];
        const barColor: Record<string, string> = {
          '积聚期': 'bg-teal-500', '启动期': 'bg-orange-500', '主升期': 'bg-red-500',
          '高潮期': 'bg-purple-500', '退潮期': 'bg-slate-400', '半路': 'bg-slate-300',
        };
        const chipCls: Record<string, string> = {
          '积聚期': 'bg-teal-50 text-teal-700 border-teal-200',
          '启动期': 'bg-orange-50 text-orange-700 border-orange-200',
          '主升期': 'bg-red-50 text-red-700 border-red-200',
          '高潮期': 'bg-purple-50 text-purple-700 border-purple-200',
          '退潮期': 'bg-slate-100 text-slate-600 border-slate-300',
          '半路': 'bg-slate-50 text-slate-500 border-slate-200',
        };
        const byStage: Record<string, string[]> = {};
        order.forEach(o => { byStage[o] = []; });
        Object.entries(lcAll).forEach(([sec, st]) => {
          (byStage[st] = byStage[st] || []).push(sec);
        });
        const total = Object.keys(lcAll).length || 1;
        const rest = ['主升期', '高潮期', '退潮期', '半路']
          .map(o => `${o}${(byStage[o] || []).length}`).join(' / ');
        return (
          <Card id="lifecycle-map" className="shadow-sm border-orange-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Activity className="w-4 h-4 text-orange-500" />
                板块生命周期分布
                <span className="text-[10px] font-normal text-slate-400">与总览第2步同口径 · {Object.keys(lcAll).length} 个细分板块</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <div className="flex h-3 rounded-full overflow-hidden border border-slate-200">
                {order.filter(o => (byStage[o] || []).length > 0).map(o => (
                  <div key={o} className={barColor[o]} style={{ width: `${((byStage[o].length / total) * 100).toFixed(1)}%` }} title={`${o} ${byStage[o].length}个`} />
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {order.map(o => (
                  <Badge key={o} variant="outline" className={`text-[10px] ${chipCls[o]}`}>{o} {(byStage[o] || []).length}</Badge>
                ))}
              </div>
              {(['积聚期', '启动期'] as const).map(o => (byStage[o] || []).length > 0 && (
                <div key={o} className="flex flex-wrap items-center gap-1">
                  <span className={`text-[11px] font-bold mr-1 ${o === '积聚期' ? 'text-teal-700' : 'text-orange-700'}`}>{o}（{byStage[o].length}）：</span>
                  {byStage[o].map(sec => (
                    <Badge key={sec} variant="outline" className={`text-[10px] ${chipCls[o]}`}>{sec}</Badge>
                  ))}
                </div>
              ))}
              <p className="text-[10px] text-slate-400">其余阶段（折叠）：{rest} · 明细见总览第2步「圈板块」</p>
            </CardContent>
          </Card>
        );
      })()}

      {/* ====== 板块页专属：细分指数短评（速览跳转锚点） ====== */}
      {detailed && data.sectorCommentary && data.sectorCommentary.length > 0 && (
        <Card id="sector-commentary" className="shadow-sm border-indigo-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" />
              细分指数每日短评
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2">
              {data.sectorCommentary.map((s) => (
                <div key={s.code} className={`border rounded-lg px-3 py-2 ${
                  s.tone === 'up' ? 'bg-red-50 border-red-100' :
                  s.tone === 'down' ? 'bg-green-50 border-green-100' : 'bg-slate-50 border-slate-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-800">{s.name}</span>
                    <span className={`text-xs font-bold ${s.pctChg >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {s.pctChg >= 0 ? '+' : ''}{s.pctChg.toFixed(2)}%
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">{s.comment}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 板块页专属：行业景气四象限（ECI 口径·日更） ====== */}
      {detailed && data.eciQuadrant && data.eciQuadrant.items.length > 0 && (() => {
        const q = data.eciQuadrant!;
        const actMap = new Map((data.actionableSectors?.items || []).map(a => [a.sector, a.priority]));
        const quadColor: Record<string, string> = {
          '景气高位·持续改善': '#10b981',
          '景气低位·边际修复': '#0ea5e9',
          '景气低位·仍在筑底': '#94a3b8',
          '景气高位·边际走弱': '#f59e0b',
        };
        const QuadTooltip = ({ active, payload }: any) => {
          if (!active || !payload?.length) return null;
          const p = payload[0].payload;
          const pr = actMap.get(p.sector);
          return (
            <div className="bg-white border border-slate-200 rounded-lg shadow-md px-3 py-2 text-xs">
              <p className="font-bold text-slate-800">{p.sector}</p>
              <p className="text-slate-500 mt-0.5">ECI {p.eci} · {q.yMode === 'monthly' ? '月变化' : '5日变化'} {p.chg >= 0 ? '+' : ''}{p.chg}</p>
              <p style={{ color: quadColor[p.quadrant] }} className="font-semibold mt-0.5">{p.quadrant}</p>
              <p className="text-slate-400 mt-0.5">
                {pr ? (pr === 1 ? '✅ 能投名单·双确认' : '✅ 能投名单') : '不在能投/积聚名单'}
              </p>
            </div>
          );
        };
        const corner = 'absolute text-[10px] font-semibold pointer-events-none px-1.5 py-0.5 rounded bg-white/80 border';
        return (
          <Card id="eci-quadrant" className="shadow-sm border-cyan-200">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-600" />
                  行业景气四象限（ECI 预期一致性口径·日更）
                </CardTitle>
                <div className="flex items-center gap-2">
                  {q.yMode === '5d' && (
                    <Badge className="text-[10px] bg-amber-100 text-amber-700 border-0">
                      Y 轴暂为近 5 日变化，月度口径数据积累中
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-xs bg-cyan-50 text-cyan-700 border-cyan-200">
                    {q.trade_date}
                  </Badge>
                </div>
              </div>
              <CardDescription className="text-[10px]">
                以 ECI 预期一致性指数近似行业景气度，较券商产业景气指数（月更）更及时 · X=ECI 当前值，Y=较上月变化（同口径重算）· 中线=31 行业中位数
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="relative">
                <span className={`${corner} left-14 top-2 text-sky-600 border-sky-200`}>景气低位·边际修复</span>
                <span className={`${corner} right-2 top-2 text-emerald-600 border-emerald-200`}>景气高位·持续改善</span>
                <span className={`${corner} left-14 bottom-10 text-slate-500 border-slate-200`}>景气低位·仍在筑底</span>
                <span className={`${corner} right-2 bottom-10 text-amber-600 border-amber-200`}>景气高位·边际走弱</span>
                <ResponsiveContainer width="100%" height={430}>
                  <ScatterChart margin={{ top: 24, right: 20, bottom: 24, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      type="number" dataKey="eci" domain={['dataMin - 3', 'dataMax + 3']}
                      tick={{ fontSize: 10, fill: '#94a3b8' }}
                      label={{ value: 'ECI 景气指数（当前值）', position: 'insideBottom', offset: -14, fontSize: 10, fill: '#64748b' }}
                    />
                    <YAxis
                      type="number" dataKey="chg" domain={['dataMin - 2', 'dataMax + 2']}
                      tick={{ fontSize: 10, fill: '#94a3b8' }}
                      label={{ value: q.yMode === 'monthly' ? '较上月变化' : '近5日变化(暂)', angle: -90, position: 'insideLeft', offset: 2, fontSize: 10, fill: '#64748b' }}
                    />
                    <ReferenceLine x={q.xMedian} stroke="#64748b" strokeDasharray="6 4" />
                    <ReferenceLine y={q.yMedian} stroke="#64748b" strokeDasharray="6 4" />
                    <Tooltip content={<QuadTooltip />} />
                    <Scatter data={q.items} isAnimationActive={false}>
                      {q.items.map((it) => (
                        <Cell key={it.sector} fill={quadColor[it.quadrant]} fillOpacity={actMap.has(it.sector) ? 1 : 0.75} />
                      ))}
                      <LabelList dataKey="sector" position="top" style={{ fontSize: 9, fill: '#475569' }} />
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-3 mt-2 flex-wrap">
                {Object.entries(quadColor).map(([k, c]) => (
                  <span key={k} className="flex items-center gap-1 text-[10px] text-slate-500">
                    <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: c }} />{k}
                  </span>
                ))}
                <span className="text-[10px] text-slate-400 ml-auto">实心点=在能投名单 · 悬停看详情</span>
              </div>
            </CardContent>
          </Card>
        );
      })()}

      {/* ====== 板块页专属：能投板块（详细版） ====== */}
      {detailed && data.actionableSectors && (
        <Card id="actionable-detail" className="shadow-sm border-emerald-300">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-600" />
                今日能投板块（多信号交叉验证）
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-200">
                {data.actionableSectors.trade_date}
              </Badge>
            </div>
            {data.actionableSectors.note && (
              <CardDescription className="text-[10px]">{data.actionableSectors.note}</CardDescription>
            )}
            <CardDescription className="text-[10px] text-emerald-600/80">口径关系：能投名单 = 总览第1步趋势轴的输入之一（趋势轴 = 能投 ∪ 底部积聚 ∪ 吸筹⭐观察）</CardDescription>
          </CardHeader>
          <CardContent>
            {data.actionableSectors.items.length > 0 ? (
              <div className="space-y-2">
                {data.actionableSectors.items.map((it) => (
                  <div key={it.sector} className="rounded-lg border border-emerald-100 bg-emerald-50/40 px-3 py-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-slate-800">{it.sector}</span>
                      <Badge className={`text-[10px] border-0 ${
                        it.priority === 1 ? 'bg-red-500 text-white' :
                        it.priority === 2 ? 'bg-orange-400 text-white' :
                        it.priority === 3 ? 'bg-indigo-400 text-white' : 'bg-teal-400 text-white'
                      }`}>
                        {it.priority === 1 ? '✅双确认' : it.priority === 2 ? '🔥双档' : it.priority === 3 ? '60日档' : '30日档'}
                      </Badge>
                      {it.pricePosition != null && (
                        <span className="text-[10px] text-slate-400">价格位置{it.pricePosition}%</span>
                      )}
                      {it.firstSeen && (
                        <span className="text-[10px] text-slate-400">首触{it.firstSeen}·连续{it.streakDays}天</span>
                      )}
                    </div>
                    <ul className="mt-1 space-y-0.5">
                      {it.reasons.map((r, i) => (
                        <li key={i} className="text-[11px] text-slate-600 leading-snug">· {r}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 py-2 text-center">今日无能投板块（底部积聚名单为空或全部被否决）</p>
            )}
            {data.actionableSectors.vetoed.length > 0 && (
              <p className="text-[10px] text-slate-400 mt-3">
                已否决：
                {data.actionableSectors.vetoed.map((v, i) => (
                  <span key={v.sector}>{i > 0 && '；'}<span className="text-slate-500 font-medium">{v.sector}</span>（{v.veto}）</span>
                ))}
              </p>
            )}
          </CardContent>
        </Card>
      )}

    </div>
  );
}
