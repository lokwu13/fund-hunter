import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { TrendingUp, TrendingDown, Activity, Layers, FileText, Newspaper, BarChart3, Briefcase, Eye, PieChart } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

const GROWTH_SECTORS = new Set(['中证信息', '中证电信', '中证工业', '中证可选']);
const DEFENSIVE_SECTORS = new Set(['中证医药', '中证消费', '中证公用', '中证能源']);

export default function WeeklySummary() {
  const { data } = useFundData();
  const indices = data.indices;

  const myStocks = data.stocks || [];
  const holdStocks = myStocks.filter((s) => s.group === 'hold');
  const watchStocks = myStocks.filter((s) => s.group === 'watch');
  const myETFs = data.myETF || [];
  const sectors = data.sectorCommentary || [];

  const pctClass = (v?: number) =>
    (v ?? 0) >= 0 ? 'text-red-500' : 'text-green-500';
  const fmtPct = (v?: number) => `${(v ?? 0) >= 0 ? '+' : ''}${(v ?? 0).toFixed(2)}%`;

  // 细分指数总评：领涨/领跌 + 市场风格
  let sectorSummary = '';
  if (sectors.length > 0) {
    const ranked = [...sectors].sort((a, b) => b.pctChg - a.pctChg);
    const leader = ranked[0];
    const laggard = ranked[ranked.length - 1];
    let style = '均衡';
    if (GROWTH_SECTORS.has(leader.name)) style = '偏成长';
    else if (DEFENSIVE_SECTORS.has(leader.name)) style = '偏防御';
    sectorSummary = `今日${leader.name}领涨 ${fmtPct(leader.pctChg)}，${laggard.name}领跌 ${fmtPct(laggard.pctChg)}，市场风格${style}`;
  }

  const sectorToneClass: Record<string, string> = {
    up: 'bg-red-50 border-red-100',
    down: 'bg-green-50 border-green-100',
    flat: 'bg-slate-50 border-slate-200',
  };

  const fundSources = [
    { name: '国家队', status: '稳健', trend: '持平', color: 'red' },
    { name: '公募基金', status: '加仓医药', trend: '回暖', color: 'blue' },
    { name: '北向资金', status: data.northbound.week > 0 ? '净流入' : '净流出', trend: data.northbound.week > 0 ? '流入' : '流出', color: 'violet' },
    { name: '南下资金', status: data.southbound.week > 0 ? '净流入' : '净流出', trend: data.southbound.week > 0 ? '流入' : '放缓', color: 'teal' },
    { name: '融资融券', status: '增加', trend: '活跃', color: 'orange' },
  ];

  return (
    <div className="space-y-4">
      {/* Week Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-800">本周资金监测 ({data.week})</h2>
          <p className="text-sm text-slate-500">大盘: {data.marketStatus}</p>
        </div>
        <div className="flex gap-2">
          {Object.entries(indices).map(([key, idx]) => (
            <div key={key} className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-center shadow-sm">
              <p className="text-xs text-slate-400">{idx.name}</p>
              <p className="text-sm font-bold text-slate-700">{idx.value.toFixed(2)}</p>
              <p className={`text-xs font-medium ${idx.change >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                {idx.change >= 0 ? '+' : ''}{idx.change}%
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* 细分指数点评 */}
      {sectors.length > 0 && (
        <div>
          <h3 className="text-base font-bold text-slate-800 mb-2 flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-500" />
            细分指数点评
          </h3>
          <p className="text-xs text-slate-500 mb-3 bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-sm">
            {sectorSummary}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {sectors.map((s) => (
              <div key={s.code} className={`border rounded-lg px-3 py-2 ${sectorToneClass[s.tone] || sectorToneClass.flat}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-800">{s.name}</span>
                  <span className={`text-sm font-bold ${pctClass(s.pctChg)}`}>{fmtPct(s.pctChg)}</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">{s.comment}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 我的个股（持股 + 观察股） */}
      {(holdStocks.length > 0 || watchStocks.length > 0) && (
        <div>
          <h3 className="text-base font-bold text-slate-800 mb-3 flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-rose-500" />
            我的个股
          </h3>
          {holdStocks.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                持股 ({holdStocks.length})
              </p>
              <div className="grid grid-cols-2 gap-2">
                {holdStocks.map((s) => (
                  <div key={s.code} className="bg-white border border-rose-100 rounded-lg px-3 py-2 shadow-sm">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-sm font-semibold text-slate-800 truncate">{s.name}</span>
                      {s.industry && (
                        <Badge variant="outline" className="text-[10px] h-4 px-1 border-slate-200 text-slate-500 flex-shrink-0">
                          {s.industry}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-end justify-between mt-0.5">
                      <span className="text-[10px] text-slate-400">{s.code}</span>
                      <div className="text-right leading-tight">
                        <span className="text-sm font-bold text-slate-700 mr-1.5">{s.close?.toFixed(2) ?? '-'}</span>
                        <span className={`text-xs font-semibold ${pctClass(s.pctChg)}`}>{fmtPct(s.pctChg)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {watchStocks.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
                <Eye className="w-3 h-3 text-slate-400" />
                观察股 ({watchStocks.length})
              </p>
              <div className="grid grid-cols-2 gap-2">
                {watchStocks.map((s) => (
                  <div key={s.code} className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-sm">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-sm font-semibold text-slate-800 truncate">{s.name}</span>
                      {s.industry && (
                        <Badge variant="outline" className="text-[10px] h-4 px-1 border-slate-200 text-slate-500 flex-shrink-0">
                          {s.industry}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-end justify-between mt-0.5">
                      <span className="text-[10px] text-slate-400">{s.code}</span>
                      <div className="text-right leading-tight">
                        <span className="text-sm font-bold text-slate-700 mr-1.5">{s.close?.toFixed(2) ?? '-'}</span>
                        <span className={`text-xs font-semibold ${pctClass(s.pctChg)}`}>{fmtPct(s.pctChg)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 我的ETF账户 */}
      {myETFs.length > 0 && (
        <div>
          <h3 className="text-base font-bold text-slate-800 mb-3 flex items-center gap-2">
            <PieChart className="w-4 h-4 text-teal-500" />
            我的ETF账户
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {myETFs.map((e) => (
              <div key={e.ticker} className="bg-white border border-teal-100 rounded-lg px-3 py-2 shadow-sm">
                <p className="text-xs font-semibold text-slate-800 truncate" title={e.name}>{e.name}</p>
                <div className="flex items-end justify-between mt-0.5">
                  <span className="text-[10px] text-slate-400">{e.ticker}</span>
                  <div className="text-right leading-tight">
                    <span className="text-sm font-bold text-slate-700 mr-1.5">{e.close?.toFixed(3) ?? '-'}</span>
                    <span className={`text-xs font-semibold ${pctClass(e.changePct)}`}>{fmtPct(e.changePct)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fund Source Cards */}
      <div className="grid grid-cols-5 gap-3">
        {fundSources.map((fund) => {
          const statusColors: Record<string, string> = {
            red: 'from-red-500 to-red-600',
            blue: 'from-blue-500 to-blue-600',
            violet: 'from-violet-500 to-violet-600',
            teal: 'from-teal-500 to-teal-600',
            orange: 'from-orange-500 to-orange-600',
          };
          const bgColors: Record<string, string> = {
            red: 'bg-red-50 border-red-100',
            blue: 'bg-blue-50 border-blue-100',
            violet: 'bg-violet-50 border-violet-100',
            teal: 'bg-teal-50 border-teal-100',
            orange: 'bg-orange-50 border-orange-100',
          };
          return (
            <Card key={fund.name} className={`${bgColors[fund.color]} border`}>
              <CardContent className="p-3">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full bg-gradient-to-r ${statusColors[fund.color]}`} />
                  <p className="text-xs font-semibold text-slate-600">{fund.name}</p>
                </div>
                <p className="text-sm font-bold text-slate-800">{fund.status}</p>
                <Badge variant="outline" className="text-xs mt-1">
                  {fund.trend === '回暖' || fund.trend === '活跃' || fund.trend === '流入' ? (
                    <TrendingUp className="w-3 h-3 mr-0.5" />
                  ) : fund.trend === '流出' || fund.trend === '放缓' ? (
                    <TrendingDown className="w-3 h-3 mr-0.5" />
                  ) : (
                    <Activity className="w-3 h-3 mr-0.5" />
                  )}
                  {fund.trend}
                </Badge>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* 持仓表现 - 公告/新闻/关联信息 */}
      {data.holdingsNews && data.holdingsNews.length > 0 && (
        <div className="mt-6">
          <h3 className="text-base font-bold text-slate-800 mb-3 flex items-center gap-2">
            <FileText className="w-4 h-4 text-indigo-500" />
            持仓表现 · 公告与动态
          </h3>
          <Tabs defaultValue={data.holdingsNews[0].stockCode} className="w-full">
            <div className="overflow-x-auto -mx-1 px-1">
              <TabsList className="inline-flex h-9 bg-slate-100 w-auto">
                {data.holdingsNews.map((h) => (
                  <TabsTrigger key={h.stockCode} value={h.stockCode} className="text-xs font-medium flex-shrink-0 px-3">
                    {h.group === 'hold' && <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mr-1 inline-block" />}
                    {h.stockName}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            {data.holdingsNews.map((h) => (
              <TabsContent key={h.stockCode} value={h.stockCode} className="mt-2">
                <div className="flex items-center gap-2 mb-2 px-1">
                  <span className="text-sm font-bold text-slate-800">{h.stockName}</span>
                  <span className="text-[10px] text-slate-400">{h.stockCode}</span>
                  {h.industry && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1 border-indigo-200 text-indigo-600 bg-indigo-50">
                      {h.industry}
                    </Badge>
                  )}
                  {h.group && (
                    <Badge variant="outline" className={`text-[10px] h-4 px-1 ${
                      h.group === 'hold'
                        ? 'border-rose-200 text-rose-600 bg-rose-50'
                        : 'border-slate-200 text-slate-500 bg-slate-50'
                    }`}>
                      {h.group === 'hold' ? '持股' : '观察'}
                    </Badge>
                  )}
                </div>
                <ScrollArea className="h-48 rounded-lg border border-slate-200 bg-white">
                  <div className="p-3 space-y-2">
                    {h.items.length === 0 ? (
                      <p className="text-xs text-slate-400 text-center py-8">近 3 个交易日暂无公告</p>
                    ) : (
                      h.items.map((item, i) => (
                        <div key={i} className="flex gap-2 items-start p-2 rounded-md hover:bg-slate-50 transition-colors">
                          <div className="mt-0.5 flex-shrink-0">
                            {item.type === '公告' ? (
                              <FileText className="w-3.5 h-3.5 text-blue-500" />
                            ) : item.type === '财报' ? (
                              <BarChart3 className="w-3.5 h-3.5 text-emerald-500" />
                            ) : (
                              <Newspaper className="w-3.5 h-3.5 text-amber-500" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-0.5">
                              <Badge variant="outline" className={`text-[10px] h-4 px-1 ${
                                item.type === '公告' ? 'border-blue-200 text-blue-600 bg-blue-50' :
                                item.type === '财报' ? 'border-emerald-200 text-emerald-600 bg-emerald-50' :
                                'border-amber-200 text-amber-600 bg-amber-50'
                              }`}>
                                {item.type}
                              </Badge>
                              <span className="text-[10px] text-slate-400">{item.date}</span>
                            </div>
                            <p className="text-xs font-semibold text-slate-700 truncate">{item.title}</p>
                            <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-2">{item.content}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </TabsContent>
            ))}
          </Tabs>
        </div>
      )}

    </div>
  );
}
