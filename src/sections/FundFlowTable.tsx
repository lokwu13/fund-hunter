import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell
} from 'recharts';
import {
  TrendingUp, TrendingDown, Star, Globe,
  ChevronDown, ChevronUp, Award, Filter
} from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

interface FundFlowTableProps {
  detailed?: boolean;
}

type FilterType = 'all' | 'buy' | 'sell' | 'rating' | 'ashare' | 'hkshare';

function MiniTrendChart({ data }: { data: Array<{ week: string; mainFlow: number; foreignFlow: number }> }) {
  return (
    <ResponsiveContainer width="100%" height={70}>
      <BarChart data={data} barSize={10} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <XAxis dataKey="week" tick={{ fontSize: 8 }} interval={0} axisLine={false} tickLine={false} />
        <YAxis hide />
        <Tooltip
          contentStyle={{ fontSize: 10, padding: '3px 6px', borderRadius: 4 }}
          formatter={(value: number) => [`${value}亿`, '']}
        />
        <Bar dataKey="foreignFlow" name="外资" radius={[2, 2, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.foreignFlow >= 0 ? '#8b5cf6' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function RatingBadge({ change }: { change: { from: string; to: string; institution: string } | null }) {
  if (!change) return <span className="text-xs text-slate-300">-</span>;
  const isUpgrade =
    (change.from === '中性' && (change.to === '增持' || change.to === '买入')) ||
    (change.from === '减持' && (change.to === '中性' || change.to === '增持' || change.to === '买入')) ||
    (change.from === '观望' && (change.to === '增持' || change.to === '买入')) ||
    (change.from === '买入' && change.to === '强烈买入');
  return (
    <div className="flex flex-col gap-0.5">
      <Badge className={`text-xs w-fit ${isUpgrade ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
        <Award className="w-3 h-3 mr-0.5" />
        {change.institution}
      </Badge>
      <span className={`text-[10px] ${isUpgrade ? 'text-emerald-600' : 'text-red-600'}`}>
        {change.from}→{change.to}
      </span>
    </div>
  );
}

function HoldingRecord({ record }: { record: { institution: string; action: string; shares: string; date: string; holdingAfter: string } }) {
  const isBuy = record.action === '增持';
  return (
    <div className="flex items-center gap-1 text-xs flex-wrap">
      <span className={`w-1.5 h-1.5 rounded-full ${isBuy ? 'bg-emerald-500' : 'bg-red-500'}`} />
      <span className="font-medium text-slate-700">{record.institution}</span>
      <span className={isBuy ? 'text-emerald-600 font-semibold' : 'text-red-600 font-semibold'}>
        {record.action}
      </span>
      <span className="text-slate-500">{record.shares}</span>
      <span className="text-slate-400">{record.date.slice(5)}</span>
    </div>
  );
}

const filterLabels: Record<FilterType, string> = {
  all: '全部',
  buy: '外资增持',
  sell: '外资减持',
  rating: '评级变化',
  ashare: 'A股',
  hkshare: '港股',
};

export default function FundFlowTable({ detailed = false }: FundFlowTableProps) {
  const { data } = useFundData();
  const stocks = data.stocks || [];
  const summary = data.foreignSummary;
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');

  // Filter stocks
  const filteredStocks = useMemo(() => {
    let result = stocks;
    switch (activeFilter) {
      case 'buy':
        result = stocks.filter(s => (s.foreignHoldings || []).some((h: {action: string}) => h.action === '增持'));
        break;
      case 'sell':
        result = stocks.filter(s => (s.foreignHoldings || []).some((h: {action: string}) => h.action === '减持'));
        break;
      case 'rating':
        result = stocks.filter(s => s.ratingChange !== null);
        break;
      case 'ashare':
        result = stocks.filter(s => s.market === 'A股');
        break;
      case 'hkshare':
        result = stocks.filter(s => s.market === '港股');
        break;
      default:
        result = stocks;
    }
    // Non-detailed: show only stocks with meaningful foreign activity (holdings or rating change)
    if (!detailed) {
      result = result.filter(s =>
        (s.foreignHoldings && s.foreignHoldings.length > 0) || s.ratingChange !== null
      );
      return result.slice(0, 12);
    }
    return result;
  }, [stocks, activeFilter, detailed]);

  // Compute net foreign flow for each stock
  const getNetForeign = (stock: typeof stocks[0]) => {
    return (stock.weeklyFlow || []).reduce((sum: number, w: {foreignFlow: number}) => sum + w.foreignFlow, 0);
  };

  const filters: FilterType[] = detailed
    ? ['all', 'buy', 'sell', 'rating', 'ashare', 'hkshare']
    : ['all', 'buy', 'sell', 'rating'];

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-5 gap-3">
          <Card className="bg-gradient-to-br from-emerald-50 to-emerald-100 border-emerald-200">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <TrendingUp className="w-4 h-4 text-emerald-600" />
                <span className="text-xs text-emerald-600 font-medium">外资增持</span>
              </div>
              <p className="text-2xl font-bold text-emerald-800">{summary.totalBuys}<span className="text-sm font-normal">笔</span></p>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-red-50 to-red-100 border-red-200">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <TrendingDown className="w-4 h-4 text-red-600" />
                <span className="text-xs text-red-600 font-medium">外资减持</span>
              </div>
              <p className="text-2xl font-bold text-red-800">{summary.totalSells}<span className="text-sm font-normal">笔</span></p>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-amber-50 to-amber-100 border-amber-200">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <Star className="w-4 h-4 text-amber-600" />
                <span className="text-xs text-amber-600 font-medium">评级上调</span>
              </div>
              <p className="text-2xl font-bold text-amber-800">{summary.ratingUpgrades}<span className="text-sm font-normal">次</span></p>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <TrendingDown className="w-4 h-4 text-orange-600" />
                <span className="text-xs text-orange-600 font-medium">评级下调</span>
              </div>
              <p className="text-2xl font-bold text-orange-800">{summary.ratingDowngrades}<span className="text-sm font-normal">次</span></p>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <Globe className="w-4 h-4 text-blue-600" />
                <span className="text-xs text-blue-600 font-medium">最活跃机构</span>
              </div>
              <p className="text-lg font-bold text-blue-800 truncate">{summary.topInstitution}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Table */}
      <Card className="shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Globe className="w-5 h-5 text-indigo-600" />
                近三个月外资变动 / 评级变化个股
              </CardTitle>
              <p className="text-xs text-slate-400 mt-1">
                覆盖A+H全市场 · 近三个月有外资(北向/南下)持股变动或投行评级调整个股 · 机构增减持+评级变化即入列
              </p>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-1.5 mt-3 flex-wrap">
            <Filter className="w-3.5 h-3.5 text-slate-400 mr-1" />
            {filters.map((f) => (
              <button
                key={f}
                onClick={() => setActiveFilter(f)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                  activeFilter === f
                    ? 'bg-indigo-500 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {filterLabels[f]}
              </button>
            ))}
            <span className="text-xs text-slate-400 ml-2">
              共 {filteredStocks.length} 只
            </span>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50">
                <TableHead className="text-xs w-32">个股</TableHead>
                <TableHead className="text-xs w-16">市场</TableHead>
                <TableHead className="text-xs w-28">评级变化</TableHead>
                <TableHead className="text-xs">最近外资操作</TableHead>
                <TableHead className="text-xs w-20 text-right">近一月外资净流向</TableHead>
                <TableHead className="text-xs w-40">近四周流向</TableHead>
                <TableHead className="text-xs w-8"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredStocks.map((stock) => {
                const netForeign = getNetForeign(stock);
                const hasActivity = (stock.foreignHoldings || []).length > 0 || stock.ratingChange;
                return (
                  <>
                    <TableRow
                      key={stock.code}
                      className={`hover:bg-slate-50 cursor-pointer ${!hasActivity ? 'opacity-60' : ''}`}
                      onClick={() => setExpandedRow(expandedRow === stock.code ? null : stock.code)}
                    >
                      <TableCell>
                        <div>
                          <p className="text-sm font-bold text-slate-800">{stock.name}</p>
                          <p className="text-xs text-slate-400">{stock.code}</p>
                          <div className="flex gap-1 mt-0.5">
                            <span className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">{stock.sector}</span>
                            <Badge variant="outline" className="text-[10px] px-1 py-0 bg-blue-50 text-blue-600">{stock.concept}</Badge>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-xs ${
                          stock.market === '港股' ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-600'
                        }`}>
                          {stock.market}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <RatingBadge change={stock.ratingChange} />
                      </TableCell>
                      <TableCell>
                        <div className="space-y-0.5">
                          {(stock.foreignHoldings || []).slice(0, 2).map((h, i) => (
                            <HoldingRecord key={i} record={h} />
                          ))}
                          {(stock.foreignHoldings || []).length > 2 && (
                            <span className="text-xs text-slate-400">+{(stock.foreignHoldings || []).length - 2}笔更多</span>
                          )}
                          {(stock.foreignHoldings || []).length === 0 && !stock.ratingChange && (
                            <span className="text-xs text-slate-300">近三月无显著变动</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={`text-sm font-bold ${netForeign >= 0 ? 'text-violet-600' : 'text-red-500'}`}>
                          {netForeign >= 0 ? '+' : ''}{netForeign >= 10000 ? `${(netForeign/10000).toFixed(1)}亿` : `${netForeign}万`}
                        </span>
                      </TableCell>
                      <TableCell>
                        <MiniTrendChart data={stock.weeklyFlow || []} />
                      </TableCell>
                      <TableCell>
                        {expandedRow === stock.code ? (
                          <ChevronUp className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        )}
                      </TableCell>
                    </TableRow>

                    {/* Expanded Detail Row */}
                    {expandedRow === stock.code && (
                      <TableRow className="bg-slate-50/80">
                        <TableCell colSpan={7} className="py-4">
                          <div className="grid grid-cols-2 gap-6">
                            {/* Left: All foreign holdings */}
                            <div>
                              <h4 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                                <Globe className="w-4 h-4 text-indigo-500" />
                                近三个月外资操作记录
                              </h4>
                              {(stock.foreignHoldings || []).length > 0 ? (
                                <div className="space-y-2">
                                  {(stock.foreignHoldings || []).map((h, i) => (
                                    <div key={i} className="bg-white rounded-lg p-3 border border-slate-200">
                                      <div className="flex items-center justify-between mb-1">
                                        <span className="font-semibold text-sm text-slate-800">{h.institution}</span>
                                        <Badge className={h.action === '增持' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}>
                                          {h.action}
                                        </Badge>
                                      </div>
                                      <div className="grid grid-cols-2 gap-2 text-xs text-slate-500">
                                        <span>股数: <span className="font-medium text-slate-700">{h.shares}</span></span>
                                        <span>日期: <span className="font-medium text-slate-700">{h.date}</span></span>
                                        {h.price !== '-' && <span>均价: <span className="font-medium text-slate-700">{h.price}</span></span>}
                                        {h.holdingAfter !== '-' && <span>持股: <span className="font-medium text-slate-700">{h.holdingAfter}</span></span>}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-sm text-slate-400">近三个月无外资持股变动记录</p>
                              )}
                            </div>

                            {/* Right: Weekly bar chart */}
                            <div>
                              <h4 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                                <TrendingUp className="w-4 h-4 text-indigo-500" />
                                近四周资金流向详情 (万元)
                              </h4>
                              <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={stock.weeklyFlow || []} margin={{ top: 10, right: 10, bottom: 20, left: 0 }}>
                                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                                  <XAxis dataKey="week" tick={{ fontSize: 10 }} />
                                  <YAxis tick={{ fontSize: 10 }} />
                                  <Tooltip
                                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                                    formatter={(value: number, name: string) => [`${value}万`, name === 'mainFlow' ? '主力资金' : '外资']}
                                  />
                                  <Legend wrapperStyle={{ fontSize: 12 }} />
                                  <Bar dataKey="mainFlow" name="主力资金" fill="#10b981" radius={[4, 4, 0, 0]} />
                                  <Bar dataKey="foreignFlow" name="外资" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                );
              })}
            </TableBody>
          </Table>

          {filteredStocks.length === 0 && (
            <div className="text-center py-8 text-sm text-slate-400">
              当前筛选条件下无数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data Source Note */}
      <div className="text-xs text-slate-400 text-center">
        数据来源: 港交所权益披露(Disclosure of Interests) · 沪深港通持股数据 · 投行评级报告 · 点击行可查看详细记录
      </div>
    </div>
  );
}
