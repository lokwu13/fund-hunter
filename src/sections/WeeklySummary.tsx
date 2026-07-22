import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { TrendingUp, TrendingDown, Activity, Zap, FileText, Newspaper, BarChart3 } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

export default function WeeklySummary() {
  const { data } = useFundData();
  const indices = data.indices;

  const signalColors: Record<string, string> = {
    danger: 'bg-red-50 border-red-200 text-red-700',
    warning: 'bg-amber-50 border-amber-200 text-amber-700',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    info: 'bg-blue-50 border-blue-200 text-blue-700',
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

      {/* Key Signals */}
      <div className="grid grid-cols-2 gap-3">
        {data.keySignals.map((signal, i) => (
          <div key={i} className={`${signalColors[signal.type]} border rounded-lg px-4 py-3 flex items-center gap-2`}>
            <Zap className="w-4 h-4 flex-shrink-0" />
            <span className="text-sm font-medium">{signal.text}</span>
          </div>
        ))}
      </div>

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
            <TabsList className="grid grid-cols-4 h-9 bg-slate-100">
              {data.holdingsNews.map((h) => (
                <TabsTrigger key={h.stockCode} value={h.stockCode} className="text-xs font-medium">
                  {h.stockName}
                </TabsTrigger>
              ))}
            </TabsList>
            {data.holdingsNews.map((h) => (
              <TabsContent key={h.stockCode} value={h.stockCode} className="mt-2">
                <ScrollArea className="h-48 rounded-lg border border-slate-200 bg-white">
                  <div className="p-3 space-y-2">
                    {h.items.map((item, i) => (
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
                    ))}
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
