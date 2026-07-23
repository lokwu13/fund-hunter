import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  TrendingUp, TrendingDown, Minus, Zap,
  Activity, Waves, Target, Gauge, ArrowRight, Lightbulb,
  SortDesc, Filter, Star, AlertTriangle, CheckCircle2,
  Crown, Trophy, TrendingDown as TrendDown, Radar, Flame
} from 'lucide-react';
import type { FundData } from '@/hooks/useFundData';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

interface ECIPanelProps {
  data: FundData;
}

const TREND_ICONS: Record<string, typeof TrendingUp> = {
  '↑上升': TrendingUp,
  '↓下降': TrendingDown,
  '→震荡': Minus,
};

const TREND_COLORS: Record<string, string> = {
  '↑上升': '#22c55e',
  '↓下降': '#ef4444',
  '→震荡': '#f59e0b',
};

const INDICATOR_ICONS: Record<string, typeof Activity> = {
  'volConvergence': Waves,
  'fundConcentration': Target,
  'trendSync': Zap,
  'consistencyMomentum': TrendingUp,
  'activity': Activity,
  'policy': Star,
};

const INDICATOR_COLORS: Record<string, string> = {
  'volConvergence': '#3b82f6',
  'fundConcentration': '#8b5cf6',
  'trendSync': '#f59e0b',
  'consistencyMomentum': '#22c55e',
  'activity': '#ec4899',
  'policy': '#06b6d4',
};

function getECILevel(eci: number) {
  if (eci >= 65) return { label: '强预期一致', color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200', badge: 'bg-emerald-500' };
  if (eci >= 50) return { label: '中等预期', color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200', badge: 'bg-amber-500' };
  return { label: '预期分化', color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', badge: 'bg-red-500' };
}

function getCorrLevel(corr: number) {
  if (corr >= 0.6) return { label: '强一致', color: '#22c55e' };
  if (corr >= 0.3) return { label: '中等', color: '#f59e0b' };
  return { label: '分化', color: '#ef4444' };
}

const MY_HOLDING_SECTORS = ['医药生物'];

const SCAN_STATUS_COLORS: Record<string, string> = {
  '吸筹中': 'bg-blue-500 text-white',
  '启动确认': 'bg-emerald-500 text-white',
  '高潮风险': 'bg-orange-500 text-white',
  '无信号': 'bg-slate-200 text-slate-500',
};

export default function ECIPanel({ data }: ECIPanelProps) {
  const eciData = data.eciData;
  const [sortBy, setSortBy] = useState<'eci' | 'trend'>('eci');
  const [filterLevel, setFilterLevel] = useState<'all' | 'high' | 'mid' | 'low'>('all');

  if (!eciData || !eciData.sectors || eciData.sectors.length === 0) {
    return (
      <Card className="border-slate-200">
        <CardContent className="p-8 text-center text-slate-400">
          <Activity className="w-8 h-8 mx-auto mb-2" />
          <p>预期一致性监测数据加载中...</p>
        </CardContent>
      </Card>
    );
  }

  let sectors = [...eciData.sectors];

  if (filterLevel === 'high') sectors = sectors.filter(s => s.eci >= 65);
  else if (filterLevel === 'mid') sectors = sectors.filter(s => s.eci >= 50 && s.eci < 65);
  else if (filterLevel === 'low') sectors = sectors.filter(s => s.eci < 50);

  if (sortBy === 'eci') sectors.sort((a, b) => b.eci - a.eci);
  else if (sortBy === 'trend') {
    const order = { '↑上升': 0, '→震荡': 1, '↓下降': 2 };
    sectors.sort((a, b) => (order[a.trend as keyof typeof order] || 1) - (order[b.trend as keyof typeof order] || 1));
  }

  const indicators = eciData.indicators;
  const divergentSectors = eciData.sectors.filter((s: any) => s.eci < 50);

  // 柱状图数据
  const barData = sectors.map(s => ({
    sector: s.sector,
    eci: s.eci,
    currentCorr: s.currentCorr,
    predictedCorr: s.predictedCorr,
  }));

  const highCount = eciData.sectors.filter((s: any) => s.eci >= 65).length;
  const midCount = eciData.sectors.filter((s: any) => s.eci >= 50 && s.eci < 65).length;
  const lowCount = eciData.sectors.filter((s: any) => s.eci < 50).length;
  const risingCount = eciData.sectors.filter((s: any) => s.trend === '↑上升').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Gauge className="w-6 h-6 text-cyan-600" />
            预期一致性监测 (ECI)
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            31个申万一级行业 · 6维模型 · 覆盖全部A股行业板块
          </p>
        </div>
        <Badge variant="outline" className="text-xs bg-cyan-50 text-cyan-700 border-cyan-200">
          <Activity className="w-3 h-3 mr-1" />
          {eciData.period}
        </Badge>
      </div>

      {/* 板块资金扫描榜 */}
      {data.sectorScan && data.sectorScan.items && data.sectorScan.items.length > 0 && (
        <Card className="border-indigo-200 shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Radar className="w-4 h-4 text-indigo-500" />
                板块资金扫描榜
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-indigo-50 text-indigo-700 border-indigo-200">
                {data.sectorScan.trade_date}
              </Badge>
            </div>
            {data.sectorScan.summary && (
              <p className="text-[11px] text-indigo-800 bg-indigo-50 rounded-md px-2 py-1.5 mt-1 leading-relaxed">
                {data.sectorScan.summary}
              </p>
            )}
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-xs min-w-[560px]">
                <thead className="sticky top-0 bg-white z-10">
                  <tr className="text-slate-500 border-b border-slate-200">
                    <th className="text-left py-1.5 font-medium">行业</th>
                    <th className="text-right font-medium">连续天数</th>
                    <th className="text-right font-medium">今日净流入</th>
                    <th className="text-right font-medium">5日净流入</th>
                    <th className="text-right font-medium">板块涨跌</th>
                    <th className="text-right font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sectorScan.items.map((it: any) => (
                    <tr key={it.sector} className="border-b border-slate-50 hover:bg-slate-50/60">
                      <td className="py-1.5 font-medium text-slate-700">{it.sector}</td>
                      <td className="text-right">
                        {it.consecutiveDays > 0
                          ? <span className="text-emerald-600 font-semibold">{it.consecutiveDays}天</span>
                          : <span className="text-slate-300">-</span>}
                      </td>
                      <td className={`text-right font-semibold ${it.netInflow1d >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                        {it.netInflow1d >= 0 ? '+' : ''}{it.netInflow1d}亿
                      </td>
                      <td className={`text-right ${it.netInflow5d >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                        {it.netInflow5d >= 0 ? '+' : ''}{it.netInflow5d}亿
                      </td>
                      <td className={`text-right ${it.sectorPctChg >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                        {it.sectorPctChg >= 0 ? '+' : ''}{it.sectorPctChg}%
                      </td>
                      <td className="text-right">
                        <Badge className={`text-[10px] border-0 ${SCAN_STATUS_COLORS[it.status] || SCAN_STATUS_COLORS['无信号']}`}>
                          {it.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-slate-400 mt-1.5">主力净流入数据来自东方财富板块资金流；吸筹中=资金连续流入但价格未动，启动确认=资金流入+当日大涨，高潮风险=连续流入+5日涨幅过热</p>
          </CardContent>
        </Card>
      )}

      {/* 主题概念领涨 */}
      {data.conceptHot && data.conceptHot.items && data.conceptHot.items.length > 0 && (
        <Card className="border-fuchsia-200 shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Flame className="w-4 h-4 text-fuchsia-500" />
                主题概念领涨（5日主力净流入 Top{data.conceptHot.items.length}）
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200">
                {data.conceptHot.trade_date}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
              {data.conceptHot.items.map((c: any) => (
                <div key={c.concept} className="rounded-lg border border-slate-200 p-2.5 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="text-xs font-bold text-slate-800 truncate">{c.concept}</span>
                    <span className={`text-xs font-semibold shrink-0 ${c.pctChg >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                      {c.pctChg >= 0 ? '+' : ''}{c.pctChg}%
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 mb-1.5">5日主力 {c.netInflow5d >= 0 ? '+' : ''}{c.netInflow5d}亿</p>
                  <div className="space-y-0.5">
                    {(c.leaders || []).map((l: any, idx: number) => (
                      <div key={l.code || idx} className="flex items-center justify-between text-[10px] gap-1">
                        <span className="text-slate-600 truncate">{idx + 1}. {l.name}</span>
                        <span className={`shrink-0 ${l.pctChg >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                          {l.pctChg >= 0 ? '+' : ''}{l.pctChg}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 统计概览 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card className="border-slate-200">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-slate-800">{eciData.totalIndustries}</p>
            <p className="text-[10px] text-slate-500">检测行业</p>
          </CardContent>
        </Card>
        <Card className="border-emerald-200 bg-emerald-50">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-emerald-600">{highCount}</p>
            <p className="text-[10px] text-emerald-700">强预期一致</p>
            <p className="text-[9px] text-emerald-500">ECI ≥ 65</p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-amber-600">{midCount}</p>
            <p className="text-[10px] text-amber-700">中等预期</p>
            <p className="text-[9px] text-amber-500">ECI 50~65</p>
          </CardContent>
        </Card>
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-red-600">{lowCount}</p>
            <p className="text-[10px] text-red-700">预期分化</p>
            <p className="text-[9px] text-red-500">ECI &lt; 50</p>
          </CardContent>
        </Card>
        <Card className="border-blue-200 bg-blue-50">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-blue-600">{risingCount}</p>
            <p className="text-[10px] text-blue-700">一致性上升</p>
            <p className="text-[9px] text-blue-500">趋势↑</p>
          </CardContent>
        </Card>
      </div>

      {/* 六维指标说明 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        {Object.entries(indicators).map(([key, info]: [string, any]) => {
          const Icon = INDICATOR_ICONS[key] || Activity;
          const color = INDICATOR_COLORS[key] || '#64748b';
          return (
            <Card key={key} className="border-slate-200 shadow-sm">
              <CardContent className="p-2.5">
                <div className="flex items-center gap-1.5 mb-1">
                  <Icon className="w-3.5 h-3.5" style={{ color }} />
                  <span className="text-[11px] font-bold text-slate-700">{info.name}</span>
                  <span className="text-[9px] text-slate-400 ml-auto">{info.weight}</span>
                </div>
                <p className="text-[9px] text-slate-500 leading-tight">{info.desc}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>
      {eciData.note && (
        <p className="text-[10px] text-slate-400 -mt-4">{eciData.note}</p>
      )}

      {/* 筛选排序 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs text-slate-500">筛选:</span>
          {[
            { key: 'all', label: `全部(${eciData.totalIndustries})` },
            { key: 'high', label: `强预期(${highCount})` },
            { key: 'mid', label: `中等(${midCount})` },
            { key: 'low', label: `分化(${lowCount})` },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setFilterLevel(f.key as any)}
              className={`text-xs px-2 py-1 rounded-md transition-colors ${
                filterLevel === f.key ? 'bg-cyan-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <SortDesc className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs text-slate-500">排序:</span>
          {[
            { key: 'eci', label: 'ECI得分' },
            { key: 'trend', label: '趋势方向' },
          ].map(s => (
            <button
              key={s.key}
              onClick={() => setSortBy(s.key as any)}
              className={`text-xs px-2 py-1 rounded-md transition-colors ${
                sortBy === s.key ? 'bg-cyan-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* ECI柱状图 - 垂直排列，31个行业全部显示 */}
      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold">31行业ECI得分排名（可横向滚动查看全部）</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <div style={{ minWidth: '900px' }}>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={barData} margin={{ left: 10, right: 10, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="sector"
                    type="category"
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                    interval={0}
                  />
                  <YAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(_value: number, _name: string, props: any) => {
                      const d = props.payload;
                      return [`ECI:${d.eci} 当前一致性:${(d.currentCorr*100).toFixed(1)}% 预测:${(d.predictedCorr*100).toFixed(1)}%`, d.sector];
                    }}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Bar dataKey="eci" barSize={20} radius={[4, 4, 0, 0]}>
                    {barData.map((d, i) => {
                      const color = d.eci >= 65 ? '#22c55e' : d.eci >= 50 ? '#f59e0b' : '#ef4444';
                      return <Cell key={i} fill={color} />;
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <p className="text-[10px] text-slate-400 text-center mt-1">绿色=强预期 黄色=中等 红色=分化 | 左右滑动或缩小页面查看全部31个行业</p>
        </CardContent>
      </Card>

      {/* 分化行业龙头专区 */}
      {divergentSectors.length > 0 && (
        <Card className="border-red-200 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold flex items-center gap-2 text-red-700">
              <AlertTriangle className="w-4 h-4" />
              预期分化行业 — 龙头个股参考（ECI &lt; 50）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {divergentSectors.map((s: any) => (
              <div key={s.sector} className="rounded-lg border border-red-100 bg-red-50/50 p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-800">{s.sector}</span>
                    <Badge className="text-[10px] bg-red-500 text-white border-0">ECI {s.eci}</Badge>
                    <Badge className="text-[10px] bg-red-100 text-red-600 border-0">
                      {s.trend}
                    </Badge>
                  </div>
                  <span className="text-xs text-slate-500">
                    当前一致性: {(s.currentCorr * 100).toFixed(1)}% → 预测: {(s.predictedCorr * 100).toFixed(1)}%
                  </span>
                </div>

                {s.leaders ? (
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    <div className="bg-white rounded-lg p-2 border border-amber-200">
                      <div className="flex items-center gap-1 text-amber-600 mb-1">
                        <Crown className="w-3.5 h-3.5" />
                        <span className="font-semibold">市值龙头</span>
                      </div>
                      <p className="font-bold text-slate-800">{s.leaders.mvLeader.name}</p>
                      <p className="text-[10px] text-slate-500">{s.leaders.mvLeader.code} · {s.leaders.mvLeader.mv}</p>
                    </div>
                    <div className="bg-white rounded-lg p-2 border border-emerald-200">
                      <div className="flex items-center gap-1 text-emerald-600 mb-1">
                        <Trophy className="w-3.5 h-3.5" />
                        <span className="font-semibold">近一月领涨</span>
                      </div>
                      <p className="font-bold text-slate-800">{s.leaders.gainLeader.name}</p>
                      <p className="text-[10px] text-emerald-600 font-semibold">{s.leaders.gainLeader.return}</p>
                    </div>
                    <div className="bg-white rounded-lg p-2 border border-red-200">
                      <div className="flex items-center gap-1 text-red-600 mb-1">
                        <TrendDown className="w-3.5 h-3.5" />
                        <span className="font-semibold">近一月领跌</span>
                      </div>
                      <p className="font-bold text-slate-800">{s.leaders.lossLeader.name}</p>
                      <p className="text-[10px] text-red-600 font-semibold">{s.leaders.lossLeader.return}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">龙头数据获取中...</p>
                )}

                {/* 操作建议 */}
                <div className="mt-2 bg-white/80 rounded px-2 py-1.5 text-[11px] text-amber-900 flex items-start gap-1.5">
                  <Lightbulb className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                  <span>{s.advice}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* 行业详细卡片 */}
      <div className="space-y-3">
        {sectors.map((s: any, i: number) => {
          const level = getECILevel(s.eci);
          const TrendIcon = TREND_ICONS[s.trend] || Minus;
          const trendColor = TREND_COLORS[s.trend] || '#94a3b8';
          const currentLevel = getCorrLevel(s.currentCorr);
          const predictedLevel = getCorrLevel(s.predictedCorr);
          const isMyHolding = MY_HOLDING_SECTORS.includes(s.sector);
          const isDivergent = s.eci < 50;

          return (
            <Card
              key={s.sector}
              className={`border shadow-sm transition-all hover:shadow-md ${
                isMyHolding ? 'border-pink-300 ring-1 ring-pink-100' :
                isDivergent ? 'border-red-200' : level.border
              }`}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-lg font-bold text-slate-400 w-7">{i + 1}</span>
                    <span className="font-bold text-slate-800 text-base">{s.sector}</span>
                    {isMyHolding && (
                      <Badge className="text-[10px] bg-pink-500 text-white border-0">
                        <Star className="w-2.5 h-2.5 mr-0.5" />持仓
                      </Badge>
                    )}
                    {isDivergent && (
                      <Badge className="text-[10px] bg-red-500 text-white border-0">分化</Badge>
                    )}
                    <Badge className={`text-[10px] ${level.bg} ${level.color} border-0`}>
                      {level.label}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <span className="text-2xl font-bold text-slate-800">{s.eci}</span>
                      <span className="text-xs text-slate-400 ml-1">ECI</span>
                    </div>
                    <div className="flex flex-col items-center">
                      <TrendIcon className="w-5 h-5" style={{ color: trendColor }} />
                      <span className="text-[9px]" style={{ color: trendColor }}>{s.trend.replace(/[↑↓→]/, '')}</span>
                    </div>
                  </div>
                </div>

                {/* 六维得分条 */}
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
                  {[
                    { key: 'volConvergence', label: '波动收敛', val: s.volConvergence, max: 20, color: '#3b82f6' },
                    { key: 'fundConcentration', label: '资金集中', val: s.fundConcentration, max: 20, color: '#8b5cf6' },
                    { key: 'trendSync', label: '趋势同步', val: s.trendSync, max: 20, color: '#f59e0b' },
                    { key: 'consistencyMomentum', label: '一致性动量', val: s.consistencyMomentum, max: 20, color: '#22c55e' },
                    { key: 'activity', label: '成交活跃', val: s.activity, max: 10, color: '#ec4899' },
                    { key: 'policy', label: '政策景气', val: s.policy, max: 10, color: '#06b6d4' },
                  ].map(dim => (
                    <div key={dim.key}>
                      <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
                        <span>{dim.label}</span>
                        <span style={{ color: dim.color }} className="font-semibold">{dim.val}</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all" style={{ width: `${(dim.val / dim.max) * 100}%`, backgroundColor: dim.color }} />
                      </div>
                    </div>
                  ))}
                </div>

                {/* 当前→预测 + 操作建议 */}
                <div className="flex flex-col md:flex-row md:items-center gap-2 md:gap-4">
                  <div className="flex items-center gap-2 text-xs shrink-0">
                    <span className="text-slate-500">当前:</span>
                    <span className="font-semibold" style={{ color: currentLevel.color }}>{(s.currentCorr * 100).toFixed(1)}%</span>
                    <ArrowRight className="w-3 h-3 text-slate-400" />
                    <span className="text-slate-500">预测:</span>
                    <span className="font-semibold" style={{ color: predictedLevel.color }}>{(s.predictedCorr * 100).toFixed(1)}%</span>
                    <span className="text-[10px] text-slate-400 ml-1">({s.stocks}只样本)</span>
                  </div>
                  <div className="flex-1 bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
                    <Lightbulb className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    <div className="text-[11px] text-amber-900 leading-relaxed">
                      {s.advice.split(' | ').map((part: string, idx: number) => (
                        <span key={idx}>
                          {idx > 0 && <span className="text-amber-300 mx-1">|</span>}
                          {part}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* 交易总策略 */}
      <Card className="border-cyan-200 bg-gradient-to-r from-cyan-50 to-blue-50">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold flex items-center gap-2 text-cyan-800">
            <Zap className="w-4 h-4 text-cyan-600" />
            ECI交易总策略
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-cyan-900 space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-white/60 rounded-lg p-3">
              <p className="font-bold text-emerald-700 mb-1 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> ECI ≥ 65 强预期一致 ({highCount}个)
              </p>
              <p className="text-[11px] leading-relaxed">板块即将强联动，适合ETF或龙头一揽子买入。一致性在高位，减少选股风险。代表行业: {eciData.sectors.filter((s: any) => s.eci >= 65).map((s: any) => s.sector).join('、')}</p>
            </div>
            <div className="bg-white/60 rounded-lg p-3">
              <p className="font-bold text-amber-700 mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> ECI 50~65 中等预期 ({midCount}个)
              </p>
              <p className="text-[11px] leading-relaxed">关注龙头个股，避开一致性动量最低的子领域。动量向上可试探建仓，动量不足等回调。</p>
            </div>
            <div className="bg-white/60 rounded-lg p-3">
              <p className="font-bold text-red-700 mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> ECI &lt; 50 预期分化 ({lowCount}个)
              </p>
              <p className="text-[11px] leading-relaxed">必须精选个股，板块参考意义不大。参考上方"分化行业龙头"专区，只买市值龙头或近月强势龙头。</p>
            </div>
          </div>
          <div className="bg-white/80 rounded-lg p-3 mt-2">
            <p className="font-bold text-cyan-800 mb-1">您的持仓板块分析:</p>
            <p className="text-[11px] leading-relaxed">
              <span className="text-pink-600 font-semibold">医药生物 ECI=74.7 ↑</span> — 31行业中排名第1，一致性最强且上升，恒瑞/心脉/南微可持有或加仓，适合ETF策略
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
