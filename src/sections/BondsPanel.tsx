import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, LineChart, Line, Cell, ReferenceLine, Area, AreaChart, ComposedChart
} from 'recharts';
import { TrendingDown, TrendingUp, Clock, ArrowUpDown, Newspaper, Activity, Droplets, Scale } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

export default function BondsPanel() {
  const { data } = useFundData();
  const bd = data.bondData;

  if (!bd) return <div className="text-center py-12 text-slate-400">债券数据加载中...</div>;

  const daily = bd.daily || [];
  const stats = bd.stats || {};
  const latest = stats.latest || {};
  const chg1m = stats['1m_change'] || {};
  const curves = bd.curveCompare || {};
  const us = bd.us || null;
  const news = bd.news || [];

  const upColor = '#ef4444';
  const downColor = '#22c55e';
  const violet600 = '#7c3aed';

  // ====== 累计偏离数据（核心：从基准日开始的涨跌累积） ======
  const calcDeviation = (startIdx: number) => {
    const result: Array<{
      date: string; d2: number; d5: number; d10: number; d30: number;
    }> = [];
    const base = daily[startIdx];
    if (!base) return [];
    let cum2 = 0, cum5 = 0, cum10 = 0, cum30 = 0;
    for (let i = startIdx; i < daily.length; i++) {
      const d = daily[i];
      if (i > startIdx) {
        const prev = daily[i - 1];
        cum2 += d.y2 - prev.y2;
        cum5 += d.y5 - prev.y5;
        cum10 += d.y10 - prev.y10;
        cum30 += d.y30 - prev.y30;
      }
      result.push({
        date: d.date,
        d2: Math.round(cum2 * 1000) / 1000,
        d5: Math.round(cum5 * 1000) / 1000,
        d10: Math.round(cum10 * 1000) / 1000,
        d30: Math.round(cum30 * 1000) / 1000,
      });
    }
    return result;
  };

  // 近半年(120天)、近3月(60天)、近1月(20天)的累计偏离
  const dev6M = calcDeviation(Math.max(0, daily.length - 120));
  const dev1M = calcDeviation(Math.max(0, daily.length - 22));

  // ====== 波动率数据（20日滚动标准差） ======
  const volatilityData: Array<{
    date: string; vol2: number; vol5: number; vol10: number; vol30: number;
  }> = [];
  for (let i = 20; i < daily.length; i++) {
    const slice = daily.slice(i - 20, i);
    const changes2 = slice.map((d, j) => j > 0 ? d.y2 - slice[j - 1].y2 : 0).slice(1);
    const changes5 = slice.map((d, j) => j > 0 ? d.y5 - slice[j - 1].y5 : 0).slice(1);
    const changes10 = slice.map((d, j) => j > 0 ? d.y10 - slice[j - 1].y10 : 0).slice(1);
    const changes30 = slice.map((d, j) => j > 0 ? d.y30 - slice[j - 1].y30 : 0).slice(1);
    const std = (arr: number[]) => {
      const m = arr.reduce((a, b) => a + b, 0) / arr.length;
      return Math.sqrt(arr.reduce((a, b) => a + Math.pow(b - m, 2), 0) / arr.length);
    };
    volatilityData.push({
      date: daily[i].date,
      vol2: Math.round(std(changes2) * 10000) / 10000,
      vol5: Math.round(std(changes5) * 10000) / 10000,
      vol10: Math.round(std(changes10) * 10000) / 10000,
      vol30: Math.round(std(changes30) * 10000) / 10000,
    });
  }

  // ====== 收益率变动对比柱状图 ======
  const curveChangeData = [
    { term: '2Y',
      y1y: curves.latest && curves['1Y_ago'] ? +(curves.latest.y2 - curves['1Y_ago'].y2).toFixed(3) : 0,
      m6: curves.latest && curves['6M_ago'] ? +(curves.latest.y2 - curves['6M_ago'].y2).toFixed(3) : 0,
      m3: curves.latest && curves['3M_ago'] ? +(curves.latest.y2 - curves['3M_ago'].y2).toFixed(3) : 0,
      m1: curves.latest && curves['1M_ago'] ? +(curves.latest.y2 - curves['1M_ago'].y2).toFixed(3) : 0,
    },
    { term: '5Y',
      y1y: curves.latest && curves['1Y_ago'] ? +(curves.latest.y5 - curves['1Y_ago'].y5).toFixed(3) : 0,
      m6: curves.latest && curves['6M_ago'] ? +(curves.latest.y5 - curves['6M_ago'].y5).toFixed(3) : 0,
      m3: curves.latest && curves['3M_ago'] ? +(curves.latest.y5 - curves['3M_ago'].y5).toFixed(3) : 0,
      m1: curves.latest && curves['1M_ago'] ? +(curves.latest.y5 - curves['1M_ago'].y5).toFixed(3) : 0,
    },
    { term: '10Y',
      y1y: curves.latest && curves['1Y_ago'] ? +(curves.latest.y10 - curves['1Y_ago'].y10).toFixed(3) : 0,
      m6: curves.latest && curves['6M_ago'] ? +(curves.latest.y10 - curves['6M_ago'].y10).toFixed(3) : 0,
      m3: curves.latest && curves['3M_ago'] ? +(curves.latest.y10 - curves['3M_ago'].y10).toFixed(3) : 0,
      m1: curves.latest && curves['1M_ago'] ? +(curves.latest.y10 - curves['1M_ago'].y10).toFixed(3) : 0,
    },
    { term: '30Y',
      y1y: curves.latest && curves['1Y_ago'] ? +(curves.latest.y30 - curves['1Y_ago'].y30).toFixed(3) : 0,
      m6: curves.latest && curves['6M_ago'] ? +(curves.latest.y30 - curves['6M_ago'].y30).toFixed(3) : 0,
      m3: curves.latest && curves['3M_ago'] ? +(curves.latest.y30 - curves['3M_ago'].y30).toFixed(3) : 0,
      m1: curves.latest && curves['1M_ago'] ? +(curves.latest.y30 - curves['1M_ago'].y30).toFixed(3) : 0,
    },
  ];

  // 月度涨跌
  const monthlyChange: Array<{ month: string; y10_change: number; y30_change: number }> = [];
  let lastMonth = '';
  let monthFirstY10 = 0;
  let monthFirstY30 = 0;
  for (const d of daily) {
    const m = d.date.slice(0, 7);
    if (m !== lastMonth) {
      if (lastMonth && monthFirstY10 > 0) {
        monthlyChange.push({
          month: lastMonth,
          y10_change: +(d.y10 - monthFirstY10).toFixed(3),
          y30_change: +(d.y30 - monthFirstY30).toFixed(3),
        });
      }
      lastMonth = m;
      monthFirstY10 = d.y10;
      monthFirstY30 = d.y30;
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Clock className="w-5 h-5 text-emerald-600" />
            国债收益率监测
          </h2>
          <p className="text-sm text-slate-500">AKShare中债登 · {daily.length}个交易日</p>
        </div>
        <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-600">{latest.date}</Badge>
      </div>

      {/* 当前收益率卡片 */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: '2年期', val: latest.y2, chg: chg1m.y2 },
          { label: '5年期', val: latest.y5, chg: chg1m.y5 },
          { label: '10年期', val: latest.y10, chg: chg1m.y10 },
          { label: '30年期', val: latest.y30, chg: chg1m.y30 },
        ].map((item) => (
          <Card key={item.label} className="border-0 shadow-sm">
            <CardContent className="p-3">
              <p className="text-xs text-slate-500">{item.label}国债</p>
              <p className="text-2xl font-bold text-slate-800">{item.val}%</p>
              <div className="flex items-center gap-1 mt-1">
                {item.chg >= 0 ? (
                  <TrendingUp className="w-3 h-3 text-red-500" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-green-500" />
                )}
                <span className={`text-xs font-bold ${item.chg >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {item.chg >= 0 ? '+' : ''}{item.chg}bp
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 期限利差 */}
      <Card className="bg-amber-50 border-amber-200">
        <CardContent className="p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ArrowUpDown className="w-4 h-4 text-amber-600" />
            <span className="text-sm font-bold">利差 10Y-2Y: <span className="text-amber-700">{latest.spread}%</span></span>
            <Badge className="text-[10px] bg-amber-100 text-amber-700">{latest.spread > 0 ? '正常' : '倒挂'}</Badge>
          </div>
        </CardContent>
      </Card>

      {/* ====== 1. 累计偏离图（核心改进） ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <Activity className="w-5 h-5 text-violet-600" />
            收益率累计偏离（近半年）
          </CardTitle>
          <p className="text-xs text-slate-400">从6个月前开始=0，每日涨跌累加 · 单位: % · 正值=累计上行(债跌) · 负值=累计下行(债涨)</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={dev6M} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="g10" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={violet600} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={violet600} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v.slice(5)} interval={8} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
              <Tooltip formatter={(v: number, n: string) => [`${v > 0 ? '+' : ''}${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="d2" name="2Y偏离" stroke="#3b82f6" strokeWidth={1.5} fill="transparent" />
              <Area type="monotone" dataKey="d5" name="5Y偏离" stroke="#6366f1" strokeWidth={1.5} fill="transparent" />
              <Area type="monotone" dataKey="d10" name="10Y偏离" stroke={violet600} strokeWidth={2.5} fill="url(#g10)" />
              <Area type="monotone" dataKey="d30" name="30Y偏离" stroke="#a855f7" strokeWidth={1.5} fill="transparent" strokeDasharray="4 4" />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>

        {/* 半年累计偏离下方 - 今日债市要闻 */}
        {news.length > 0 && (
          <CardContent className="pt-0 pb-4">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5">
                <Newspaper className="w-3.5 h-3.5 text-slate-500" />
                今日债市要闻 · 东方财富
              </p>
              <div className="space-y-1.5">
                {news.filter(n => n.date === latest.date).map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span className="text-[9px] text-slate-400 flex-shrink-0 mt-0.5">{item.time?.slice(11, 16) || ''}</span>
                    <p className="text-[11px] text-slate-600 leading-snug">{item.title}</p>
                  </div>
                ))}
                {news.filter(n => n.date === latest.date).length === 0 && (
                  <p className="text-[11px] text-slate-400">今日暂无债券相关新闻</p>
                )}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* ====== 2. 近1月累计偏离（放大看细节） ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold">累计偏离放大（近1月）</CardTitle>
          <p className="text-xs text-slate-400">近距离观察近期波动细节</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={dev1M} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v.slice(5)} interval={2} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
              <Tooltip formatter={(v: number, n: string) => [`${v > 0 ? '+' : ''}${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="d2" name="2Y" stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="d10" name="10Y" stroke={violet600} strokeWidth={3} dot={{ r: 3, fill: violet600 }} />
              <Line type="monotone" dataKey="d30" name="30Y" stroke="#a855f7" strokeWidth={2} dot={false} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>

        {/* 近1月放大下方 - 近期债市动态 */}
        {news.length > 0 && (
          <CardContent className="pt-0 pb-4">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5">
                <Newspaper className="w-3.5 h-3.5 text-slate-500" />
                近期债市动态
              </p>
              <div className="space-y-1.5">
                {news.filter(n => n.date !== latest.date).slice(0, 5).map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span className="text-[9px] text-slate-400 flex-shrink-0 mt-0.5">{item.date}</span>
                    <p className="text-[11px] text-slate-600 leading-snug">{item.title}</p>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* ====== 3. 20日滚动波动率 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold">滚动波动率（20日标准差）</CardTitle>
          <p className="text-xs text-slate-400">数值越大=波动越剧烈 · 单位: %</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={volatilityData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v.slice(5)} interval={15} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v * 100).toFixed(0)}bp`} />
              <Tooltip formatter={(v: number, n: string) => [`${(v * 100).toFixed(2)}bp`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="vol10" name="10Y波动率" stroke="#f59e0b" strokeWidth={2.5} fill="url(#volGrad)" />
              <Line type="monotone" dataKey="vol2" name="2Y波动率" stroke="#3b82f6" strokeWidth={1} dot={false} />
              <Line type="monotone" dataKey="vol30" name="30Y波动率" stroke="#a855f7" strokeWidth={1} dot={false} strokeDasharray="4 4" />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ====== 4. 各期限变动对比柱状图 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold">各期限收益率变动（最新 vs 历史）</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={curveChangeData} margin={{ top: 10, right: 30, left: 0, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="term" tick={{ fontSize: 13, fontWeight: 'bold' }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
              <Tooltip formatter={(v: number, n: string) => [`${v > 0 ? '+' : ''}${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#64748b" />
              <Bar dataKey="y1y" name="vs 1年前" barSize={14} fill="#94a3b8" radius={[3, 3, 0, 0]} />
              <Bar dataKey="m6" name="vs 6月前" barSize={14} fill="#64748b" radius={[3, 3, 0, 0]} />
              <Bar dataKey="m3" name="vs 3月前" barSize={14} fill="#475569" radius={[3, 3, 0, 0]} />
              <Bar dataKey="m1" name="vs 1月前" barSize={14} fill={violet600} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ====== 5. 月度涨跌 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold">月度涨跌幅</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={monthlyChange} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={45} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
              <Tooltip formatter={(v: number, n: string) => [`${v > 0 ? '+' : ''}${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#64748b" />
              <Bar dataKey="y10_change" name="10Y月度涨跌" barSize={18}>
                {monthlyChange.map((e, i) => <Cell key={i} fill={e.y10_change >= 0 ? upColor : downColor} />)}
              </Bar>
              <Bar dataKey="y30_change" name="30Y月度涨跌" barSize={18}>
                {monthlyChange.map((e, i) => <Cell key={i} fill={e.y30_change >= 0 ? '#fca5a5' : '#86efac'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ====== 6. 央行短期流动性工具 ====== */}
      {bd.liquidityTools && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Droplets className="w-4 h-4 text-sky-500" />
                央行短期流动性工具
              </CardTitle>
              <Badge variant="outline" className="text-[10px]">
                {bd.liquidityTools.updateTime}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 关键指标 */}
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-slate-500">7天逆回购利率</p>
                <p className="text-lg font-bold text-slate-800">{bd.liquidityTools.policyRate}%</p>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-slate-500">DR001</p>
                <p className="text-lg font-bold text-slate-800">{bd.liquidityTools.dr001}%</p>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-slate-500">DR007</p>
                <p className="text-lg font-bold text-slate-800">{bd.liquidityTools.dr007}%</p>
              </div>
              <div className="bg-emerald-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-emerald-600">7月净投放</p>
                <p className="text-lg font-bold text-emerald-700">+{bd.liquidityTools.monthlyNet}亿</p>
              </div>
            </div>

            {/* 操作明细表格 */}
            <div className="max-h-40 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-1 text-slate-500">日期</th>
                    <th className="text-left py-1 text-slate-500">工具</th>
                    <th className="text-right py-1 text-slate-500">投放(亿)</th>
                    <th className="text-right py-1 text-slate-500">到期(亿)</th>
                    <th className="text-right py-1 text-slate-500">净投放</th>
                  </tr>
                </thead>
                <tbody>
                  {bd.liquidityTools.operations.map((op: any, i: number) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-1 text-slate-600">{op.date.slice(5)}</td>
                      <td className="py-1">
                        <span className={`text-[10px] px-1 py-0.5 rounded ${
                          op.tool.includes('买断') ? 'bg-amber-100 text-amber-700' : 'bg-sky-100 text-sky-700'
                        }`}>
                          {op.tool}
                        </span>
                      </td>
                      <td className="py-1 text-right font-medium">{op.amount.toLocaleString()}</td>
                      <td className="py-1 text-right text-slate-500">{op.matured.toLocaleString()}</td>
                      <td className="py-1 text-right font-bold">
                        <span className={op.net >= 0 ? 'text-emerald-600' : 'text-red-500'}>
                          {op.net >= 0 ? '+' : ''}{op.net.toLocaleString()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 点评 */}
            <div className="bg-slate-50 p-2.5 rounded-lg">
              <p className="text-xs text-slate-700 leading-relaxed">
                <strong className="text-slate-800">点评：</strong>
                {bd.liquidityTools.comment}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 7. 融资融券 ====== */}
      {bd.marginTrading && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Scale className="w-4 h-4 text-indigo-500" />
                全市场融资融券
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge className={`text-[10px] h-5 ${
                  bd.marginTrading.trend === '下降' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
                }`}>
                  {bd.marginTrading.trend}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {bd.marginTrading.updateTime}
                </Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 关键指标 */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-indigo-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-indigo-600">融资融券余额</p>
                <p className="text-xl font-bold text-indigo-800">{bd.marginTrading.totalBalance.toLocaleString()}</p>
                <p className="text-[10px] text-indigo-500">亿元</p>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-slate-500">融资余额</p>
                <p className="text-xl font-bold text-slate-800">{bd.marginTrading.finBalance.toLocaleString()}</p>
                <p className="text-[10px] text-slate-500">亿元</p>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg text-center">
                <p className="text-[10px] text-slate-500">融券余额</p>
                <p className="text-xl font-bold text-slate-800">{bd.marginTrading.secBalance}</p>
                <p className="text-[10px] text-slate-500">亿元</p>
              </div>
            </div>

            {/* 融资融券余额走势图 + 每日变化 */}
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">融资融券余额走势（5月中-7月中）</p>
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart
                  data={(() => {
                    const d = bd.marginTrading.daily;
                    return d.map((item: any, i: number) => ({
                      ...item,
                      change: i > 0 ? item.total - d[i - 1].total : 0,
                    }));
                  })()}
                  margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 8 }}
                    tickFormatter={(v) => v.slice(5)}
                    interval={6}
                  />
                  <YAxis
                    yAxisId="left"
                    tick={{ fontSize: 9 }}
                    domain={['dataMin - 300', 'dataMax + 100']}
                    tickFormatter={(v) => `${(v / 10000).toFixed(1)}万亿`}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 8 }}
                    domain={['dataMin - 200', 'dataMax + 200']}
                    tickFormatter={(v) => `${v >= 0 ? '+' : ''}${v}亿`}
                  />
                  <Tooltip
                    contentStyle={{ fontSize: 11 }}
                    formatter={(value: any, name: string) => {
                      if (name === '余额') return [`${value.toLocaleString()}亿`, name];
                      if (name === '日变动') return [`${value >= 0 ? '+' : ''}${value}亿`, name];
                      return [value, name];
                    }}
                    labelFormatter={(l) => l}
                  />
                  <Bar
                    yAxisId="right"
                    dataKey="change"
                    name="日变动"
                    barSize={6}
                    fill="#94a3b8"
                    opacity={0.6}
                  />
                  <Line
                    yAxisId="left"
                    type="linear"
                    dataKey="total"
                    name="余额"
                    stroke="#dc2626"
                    strokeWidth={2}
                    dot={{ r: 2, fill: '#dc2626' }}
                    activeDot={{ r: 4 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="flex items-center justify-center gap-4 mt-1">
                <span className="flex items-center gap-1 text-[10px] text-slate-500">
                  <span className="w-3 h-0.5 bg-red-600" /> 融资融券余额
                </span>
                <span className="flex items-center gap-1 text-[10px] text-slate-500">
                  <span className="w-2 h-2 bg-slate-400 opacity-60" /> 日变动
                </span>
              </div>
            </div>

            {/* 点评 */}
            <div className="bg-slate-50 p-2.5 rounded-lg">
              <p className="text-xs text-slate-700 leading-relaxed">
                <strong className="text-slate-800">点评：</strong>
                {bd.marginTrading.comment}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 8. 中美国债对比 ====== */}
      {us && us.latest && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold">中美国债收益率对比</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <p className="text-sm font-bold text-red-600 mb-2">中国 {latest.date}</p>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={[{t:'2Y',v:latest.y2},{t:'5Y',v:latest.y5},{t:'10Y',v:latest.y10},{t:'30Y',v:latest.y30}]} layout="vertical" margin={{ top: 5, right: 30, left: 25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis type="number" domain={[0, 3]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                    <YAxis type="category" dataKey="t" tick={{ fontSize: 12, fontWeight: 'bold' }} width={30} />
                    <Tooltip formatter={(v: number) => [`${v}%`, '']} />
                    <Bar dataKey="v" fill="#ef4444" barSize={18} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div>
                <p className="text-sm font-bold text-blue-600 mb-2">美国 {us.latest.date}</p>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={[{t:'2Y',v:us.latest.y2},{t:'5Y',v:us.latest.y5},{t:'10Y',v:us.latest.y10},{t:'30Y',v:us.latest.y30}]} layout="vertical" margin={{ top: 5, right: 30, left: 25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis type="number" domain={[0, 6]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                    <YAxis type="category" dataKey="t" tick={{ fontSize: 12, fontWeight: 'bold' }} width={30} />
                    <Tooltip formatter={(v: number) => [`${v}%`, '']} />
                    <Bar dataKey="v" fill="#3b82f6" barSize={18} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="mt-3 p-3 bg-slate-50 rounded-lg text-xs text-slate-600">
              <span className="font-semibold">中美利差(10Y):</span> {(us.latest.y10 - latest.y10).toFixed(2)}%
              （美{us.latest.y10}% - 中{latest.y10}%）
              {us.latest.y10 > latest.y10 ? ' → 美元资产吸引力更高' : ' → 人民币资产吸引力更高'}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 7. 债券新闻 ====== */}
      {news.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Newspaper className="w-5 h-5 text-slate-600" />
              债券市场要闻
              <Badge variant="outline" className="text-xs bg-slate-50 text-slate-600">东方财富</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {news.map((item, idx) => (
                <div key={idx} className="flex items-start gap-3 py-2 border-b border-slate-100 last:border-0">
                  <span className="text-[10px] text-slate-400 flex-shrink-0 mt-0.5 w-16">{item.date}</span>
                  <p className="text-xs text-slate-700 leading-relaxed">{item.title}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 8. 债券 → A+H股市影响分析 ====== */}
      <BondToStockImpact latest={latest} us={us} chg1m={chg1m} daily={daily} />
    </div>
  );
}

/* ==================== 债券→A+H股市影响分析组件 ==================== */
function BondToStockImpact({
  latest,
  us,
  chg1m,
  daily,
}: {
  latest: Record<string, any>;
  us: { latest: Record<string, any> } | null;
  chg1m: Record<string, number>;
  daily: Array<Record<string, any>>;
}) {
  // 计算关键指标
  const cn10y = latest.y10 || 0;
  const spread = latest.spread || 0;
  const us10y = us?.latest?.y10 || 4.5;
  const usCnSpread = +(us10y - cn10y).toFixed(2);
  const y10chg1m = chg1m.y10 || 0;

  // 历史分位（10Y近一年）
  const all10y = daily.map(d => d.y10);
  const histMin = Math.min(...all10y);
  const histMax = Math.max(...all10y);
  const percentile10y = histMax > histMin ? Math.round(((cn10y - histMin) / (histMax - histMin)) * 100) : 50;

  // 各指标评分（-2~+2）
  const scores = {
    riskFree: cn10y < 2.0 ? +2 : cn10y < 2.5 ? +1 : cn10y < 3.0 ? 0 : -1, // 越低越利好
    spread: spread > 0.3 ? +1 : spread > 0 ? 0 : -2, // 倒挂=大利空
    usCn: usCnSpread > 2.5 ? -2 : usCnSpread > 1.5 ? -1 : usCnSpread > 0.5 ? 0 : +1, // 越大越利空
    trend10y: y10chg1m > 10 ? -2 : y10chg1m > 5 ? -1 : y10chg1m > 0 ? 0 : y10chg1m > -5 ? +1 : +2, // 上行=利空
  };

  // A股综合得分（国内因素权重高）
  const aScore = scores.riskFree * 0.35 + scores.spread * 0.20 + scores.usCn * 0.25 + scores.trend10y * 0.20;
  // H股综合得分（外资因素权重高）
  const hScore = scores.riskFree * 0.20 + scores.spread * 0.15 + scores.usCn * 0.45 + scores.trend10y * 0.20;

  const getVerdict = (s: number) => {
    if (s >= 1.0) return { text: '偏多', color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200' };
    if (s >= 0.3) return { text: '轻微偏多', color: 'text-emerald-600', bg: 'bg-emerald-50/60', border: 'border-emerald-100' };
    if (s > -0.3) return { text: '震荡', color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200' };
    if (s > -1.0) return { text: '轻微偏空', color: 'text-orange-600', bg: 'bg-orange-50/60', border: 'border-orange-100' };
    return { text: '偏空', color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' };
  };

  const aV = getVerdict(aScore);
  const hV = getVerdict(hScore);

  // 传导链数据
  const chainData = [
    { step: 1, label: '无风险利率', value: `${cn10y}%`, status: scores.riskFree >= 1 ? '利好' : scores.riskFree <= -1 ? '利空' : '中性', desc: `历史${percentile10y}%分位 · ${cn10y < 2 ? '低位' : '偏高'}` },
    { step: 2, label: '期限利差', value: `${spread}%`, status: spread > 0.3 ? '正常' : spread > 0 ? '收窄' : '倒挂', desc: spread > 0 ? '经济未衰退' : '⚠️ 衰退预警' },
    { step: 3, label: '中美利差', value: `${usCnSpread}%`, status: usCnSpread > 2 ? '高压' : usCnSpread > 1 ? '偏紧' : '正常', desc: `美${us10y}% - 中${cn10y}%` },
    { step: 4, label: '近1月趋势', value: `${y10chg1m >= 0 ? '+' : ''}${y10chg1m}bp`, status: y10chg1m > 5 ? '上行' : y10chg1m < -5 ? '下行' : '平稳', desc: '10Y国债月度变化' },
  ];

  // 行业影响
  const sectorImpacts = [
    { sector: '高股息/红利', aImpact: '受益', hImpact: '受益', reason: '低利率环境提升股息吸引力' },
    { sector: '科技/成长', aImpact: '受益', hImpact: '承压', reason: 'A股流动性宽松支撑估值，H股受外资流出压制' },
    { sector: '银行/金融', aImpact: '中性', hImpact: '承压', reason: '利差收窄压缩净息差，H股外资减持' },
    { sector: '地产链', aImpact: '受益', hImpact: '承压', reason: '低利率利好融资，但H股国际资金避险' },
    { sector: '消费', aImpact: '中性', hImpact: '承压', reason: '国内复苏预期，但汇率因素不利港股消费' },
    { sector: '资源/周期', aImpact: '承压', hImpact: '承压', reason: '期限利差正常=经济不热，商品价格受限' },
  ];

  return (
    <Card className="border-indigo-200">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-bold flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          债市信号 → A+H股市一个月影响推演
          <Badge variant="outline" className="text-xs bg-indigo-50 text-indigo-600">基于当前债券参数</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">

        {/* 传导链 */}
        <div className="bg-slate-50 rounded-xl p-4">
          <p className="text-xs font-bold text-slate-600 mb-3">债市 → 股市传导链</p>
          <div className="flex items-center gap-2 overflow-x-auto pb-2">
            {chainData.map((item, idx) => (
              <div key={idx} className="flex items-center gap-2 flex-shrink-0">
                <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 min-w-[120px]">
                  <p className="text-[10px] text-slate-400">{item.label}</p>
                  <p className="text-sm font-bold text-slate-800">{item.value}</p>
                  <Badge className={`text-[9px] mt-0.5 ${
                    item.status === '利好' ? 'bg-emerald-100 text-emerald-700' :
                    item.status === '利空' || item.status === '倒挂' || item.status === '高压' ? 'bg-red-100 text-red-700' :
                    item.status === '上行' || item.status === '偏紧' ? 'bg-orange-100 text-orange-700' :
                    item.status === '下行' ? 'bg-emerald-100 text-emerald-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>{item.status}</Badge>
                  <p className="text-[9px] text-slate-400 mt-0.5">{item.desc}</p>
                </div>
                {idx < chainData.length - 1 && (
                  <div className="flex flex-col items-center flex-shrink-0">
                    <ArrowUpDown className="w-3 h-3 text-slate-300 rotate-90" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* A股 vs H股 预测 */}
        <div className="grid grid-cols-2 gap-4">
          {/* A股 */}
          <div className={`${aV.bg} ${aV.border} border rounded-xl p-4`}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-bold text-slate-700">A股一个月展望</p>
              <Badge className={`text-xs ${aV.bg} ${aV.color} border-0`}>{aV.text}</Badge>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">无风险利率(35%)</span>
                <span className={`font-bold ${scores.riskFree > 0 ? 'text-emerald-600' : scores.riskFree < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.riskFree > 0 ? '+' : ''}{scores.riskFree}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">期限利差(20%)</span>
                <span className={`font-bold ${scores.spread > 0 ? 'text-emerald-600' : scores.spread < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.spread > 0 ? '+' : ''}{scores.spread}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">中美利差(25%)</span>
                <span className={`font-bold ${scores.usCn > 0 ? 'text-emerald-600' : scores.usCn < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.usCn > 0 ? '+' : ''}{scores.usCn}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">趋势(20%)</span>
                <span className={`font-bold ${scores.trend10y > 0 ? 'text-emerald-600' : scores.trend10y < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.trend10y > 0 ? '+' : ''}{scores.trend10y}
                </span>
              </div>
              <div className="border-t border-slate-200 pt-1.5 flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700">综合得分</span>
                <span className={`text-lg font-bold ${aV.color}`}>{aScore >= 0 ? '+' : ''}{aScore.toFixed(2)}</span>
              </div>
            </div>
            <div className="mt-3 text-[11px] text-slate-600 leading-relaxed">
              <span className="font-semibold">逻辑：</span>
              {cn10y < 2 ? '无风险利率处历史低位，流动性宽松支撑估值。' : '利率偏高压制估值。'}
              {spread > 0 ? '期限结构正常，经济未衰退。' : '⚠️ 曲线倒挂，警惕衰退。'}
              {usCnSpread > 2 ? '但中美利差过大，北向资金有流出压力。' : '中美利差收窄，外资回流可期。'}
              预计<span className={`font-bold ${aV.color}`}>{aV.text}</span>，结构分化为主。
            </div>
          </div>

          {/* H股 */}
          <div className={`${hV.bg} ${hV.border} border rounded-xl p-4`}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-bold text-slate-700">港股一个月展望</p>
              <Badge className={`text-xs ${hV.bg} ${hV.color} border-0`}>{hV.text}</Badge>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">无风险利率(20%)</span>
                <span className={`font-bold ${scores.riskFree > 0 ? 'text-emerald-600' : scores.riskFree < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.riskFree > 0 ? '+' : ''}{scores.riskFree}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">期限利差(15%)</span>
                <span className={`font-bold ${scores.spread > 0 ? 'text-emerald-600' : scores.spread < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.spread > 0 ? '+' : ''}{scores.spread}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">中美利差(45%)</span>
                <span className={`font-bold ${scores.usCn > 0 ? 'text-emerald-600' : scores.usCn < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.usCn > 0 ? '+' : ''}{scores.usCn}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">趋势(20%)</span>
                <span className={`font-bold ${scores.trend10y > 0 ? 'text-emerald-600' : scores.trend10y < 0 ? 'text-red-600' : 'text-slate-500'}`}>
                  {scores.trend10y > 0 ? '+' : ''}{scores.trend10y}
                </span>
              </div>
              <div className="border-t border-slate-200 pt-1.5 flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700">综合得分</span>
                <span className={`text-lg font-bold ${hV.color}`}>{hScore >= 0 ? '+' : ''}{hScore.toFixed(2)}</span>
              </div>
            </div>
            <div className="mt-3 text-[11px] text-slate-600 leading-relaxed">
              <span className="font-semibold">逻辑：</span>
              H股对中美利差更敏感（权重45%）。{usCnSpread > 2 ? `当前利差${usCnSpread}%，国际资金偏好美元资产，南向资金虽有承接但外资流出压力大。` : '利差收窄有利于国际资金回流。'}
              {usCnSpread > 2 ? '高股息防御板块相对抗跌，科技成长承压。' : '港股整体受益外资回流。'}
              预计<span className={`font-bold ${hV.color}`}>{hV.text}</span>。
            </div>
          </div>
        </div>

        {/* 行业分化 */}
        <div>
          <p className="text-xs font-bold text-slate-700 mb-2">行业分化（一个月内）</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500">
                  <th className="text-left py-2 px-3 font-medium">板块</th>
                  <th className="text-center py-2 px-3 font-medium">A股</th>
                  <th className="text-center py-2 px-3 font-medium">港股</th>
                  <th className="text-left py-2 px-3 font-medium">逻辑</th>
                </tr>
              </thead>
              <tbody>
                {sectorImpacts.map((s, i) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                    <td className="py-2 px-3 font-semibold text-slate-700">{s.sector}</td>
                    <td className="py-2 px-3 text-center">
                      <Badge className={`text-[9px] ${
                        s.aImpact === '受益' ? 'bg-emerald-100 text-emerald-700' :
                        s.aImpact === '承压' ? 'bg-red-100 text-red-700' :
                        'bg-slate-100 text-slate-600'
                      }`}>{s.aImpact}</Badge>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <Badge className={`text-[9px] ${
                        s.hImpact === '受益' ? 'bg-emerald-100 text-emerald-700' :
                        s.hImpact === '承压' ? 'bg-red-100 text-red-700' :
                        'bg-slate-100 text-slate-600'
                      }`}>{s.hImpact}</Badge>
                    </td>
                    <td className="py-2 px-3 text-slate-500">{s.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 免责声明 */}
        <div className="bg-slate-50 rounded-lg p-3 text-[10px] text-slate-400">
          <span className="font-semibold">说明：</span>
          以上推演基于当前国债收益率、期限利差、中美利差等债券参数，通过量化评分模型得出。
          实际股市走势还受政策、地缘、企业盈利等多重因素影响，仅供参考不构成投资建议。
          模型权重：A股侧重国内流动性(35%)，H股侧重中美利差(45%)。
        </div>
      </CardContent>
    </Card>
  );
}

