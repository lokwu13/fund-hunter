import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  TrendingUp, TrendingDown, Zap, Activity, TrendingDown as TrendingDownIcon, Info
} from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

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

export default function SectorHeatmap({ detailed = false }: SectorHeatmapProps) {
  const { data } = useFundData();
  const sectors = data.sectors || [];
  const period = data.sectorPeriod || '近4周主力累计';

  // 分离流入/流出
  const inflowSectors = sectors.filter(s => (s.mainFlow || 0) > 0);
  const outflowSectors = sectors.filter(s => (s.mainFlow || 0) < 0);

  const totalInflow = inflowSectors.reduce((a, s) => a + (s.mainFlow || 0), 0);
  const totalOutflow = outflowSectors.reduce((a, s) => a + (s.mainFlow || 0), 0);
  const anomalyCount = sectors.filter(s => s.isAnomaly).length;

  return (
    <div className="space-y-6">
      {/* Summary Bar */}
      <div className="flex items-center justify-between bg-white rounded-lg border border-slate-200 px-4 py-3 flex-wrap gap-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-orange-400" />
            <span className="text-xs text-slate-600">流入TOP10 <b className="text-orange-600">+{totalInflow.toFixed(0)}亿</b></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-sky-400" />
            <span className="text-xs text-slate-600">流出TOP10 <b className="text-sky-600">{totalOutflow.toFixed(0)}亿</b></span>
          </div>
          {anomalyCount > 0 && (
            <div className="flex items-center gap-1">
              <Zap className="w-3 h-3 text-amber-500" />
              <span className="text-xs text-amber-600"><b>{anomalyCount}</b>个板块单周突增</span>
            </div>
          )}
        </div>
        <Badge variant="outline" className="text-xs bg-slate-50">{period}</Badge>
      </div>

      {/* ====== INFLOW HEATMAP (TOP 10) ====== */}
      <Card className="shadow-sm border-orange-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-orange-600" />
            主力净流入 TOP10 行业
            <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600">4周累计</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 grid-cols-5">
            {inflowSectors.map((sector) => {
              const flow = sector.mainFlow || 0;
              const level = getFlowLevel(flow);
              const colors = flowColors[level];
              return (
                <div
                  key={sector.name}
                  className={`${colors.bg} ${colors.text} rounded-lg p-3 border ${colors.border} transition-all hover:scale-105 hover:shadow-md cursor-pointer relative`}
                >
                  {sector.isAnomaly && (
                    <div className="absolute -top-1.5 -right-1.5 z-10" title={`单周最大+${sector.maxWeeklyFlow}亿`}>
                      <Zap className="w-5 h-5 text-amber-500 fill-amber-500 drop-shadow" />
                    </div>
                  )}
                  <p className="text-sm font-bold truncate pr-2">{sector.name}</p>
                  <p className="text-lg font-bold mt-1">+{flow}亿</p>
                  {sector.isAnomaly && (
                    <p className="text-[10px] mt-0.5 opacity-90 font-semibold">
                      单周+{sector.maxWeeklyFlow}亿
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* ====== OUTFLOW HEATMAP (TOP 10) ====== */}
      <Card className="shadow-sm border-sky-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <TrendingDown className="w-5 h-5 text-sky-600" />
            主力净流出 TOP10 行业
            <Badge variant="outline" className="text-xs bg-sky-50 text-sky-600">4周累计</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 grid-cols-5">
            {outflowSectors.map((sector) => {
              const flow = sector.mainFlow || 0;
              const level = getFlowLevel(flow);
              const colors = flowColors[level];
              return (
                <div
                  key={sector.name}
                  className={`${colors.bg} ${colors.text} rounded-lg p-3 border ${colors.border} transition-all hover:scale-105 hover:shadow-md cursor-pointer relative`}
                >
                  {sector.isAnomaly && (
                    <div className="absolute -top-1.5 -right-1.5 z-10" title={`单周最大${sector.maxWeeklyFlow}亿`}>
                      <Zap className="w-5 h-5 text-amber-500 fill-amber-500 drop-shadow" />
                    </div>
                  )}
                  <p className="text-sm font-bold truncate pr-2">{sector.name}</p>
                  <p className="text-lg font-bold mt-1">{flow}亿</p>
                  {sector.isAnomaly && (
                    <p className="text-[10px] mt-0.5 opacity-90 font-semibold">
                      单周{sector.maxWeeklyFlow}亿
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

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

      {/* ====== TABLE VIEW (板块页) ====== */}
      {detailed && (
        <Card>
          <CardContent className="p-3">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="text-xs">排名</TableHead>
                  <TableHead className="text-xs">行业板块</TableHead>
                  <TableHead className="text-xs text-right">4周累计净流入</TableHead>
                  <TableHead className="text-xs text-right">单周最大</TableHead>
                  <TableHead className="text-xs">异常标记</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sectors.map((sector, idx) => (
                  <TableRow key={sector.name} className="hover:bg-slate-50">
                    <TableCell className="text-xs font-bold">{idx + 1}</TableCell>
                    <TableCell className="text-xs font-semibold">{sector.name}</TableCell>
                    <TableCell className={`text-xs text-right font-bold ${(sector.mainFlow || 0) >= 0 ? 'text-orange-600' : 'text-sky-600'}`}>
                      {(sector.mainFlow || 0) >= 0 ? '+' : ''}{sector.mainFlow}亿
                    </TableCell>
                    <TableCell className="text-xs text-right">
                      {(sector.maxWeeklyFlow || 0) >= 0 ? '+' : ''}{sector.maxWeeklyFlow}亿
                    </TableCell>
                    <TableCell>
                      {sector.isAnomaly && (
                        <Badge className="text-[10px] bg-amber-100 text-amber-700">
                          <Zap className="w-3 h-3 mr-0.5" />
                          单周突增
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ====== 以下为板块页专属内容 ====== */}
      {detailed && (
        <>
          {/* 大医疗板块 */}
          <Card className="border-amber-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Activity className="w-5 h-5 text-amber-600" />
                大医疗板块 — 五路资金流向TOP5
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {['publicFund', 'privateFund', 'nationalTeam', 'foreignCapital', 'nonMainforce'].map((key) => {
                const labels: Record<string, { title: string; color: string; dot: string }> = {
                  publicFund: { title: '公募基金', color: 'text-blue-700', dot: 'bg-blue-500' },
                  privateFund: { title: '私募基金', color: 'text-violet-700', dot: 'bg-violet-500' },
                  nationalTeam: { title: '国家队（汇金/证金/社保）', color: 'text-red-700', dot: 'bg-red-500' },
                  foreignCapital: { title: '外资（北向资金）', color: 'text-indigo-700', dot: 'bg-indigo-500' },
                  nonMainforce: { title: '非主力资金（融资盘/散户）', color: 'text-amber-700', dot: 'bg-amber-500' },
                };
                const label = labels[key];
                const fundData = data.medicalSectorFunds?.[key as keyof typeof data.medicalSectorFunds];
                if (!fundData) return null;
                return (
                  <div key={key}>
                    <h4 className={`text-sm font-bold ${label.color} mb-1 flex items-center gap-2`}>
                      <span className={`w-2 h-2 rounded-full ${label.dot}`} />
                      {label.title}
                    </h4>
                    <p className="text-[10px] text-slate-400 mb-2 ml-4">{(fundData as any).period || ''}</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <p className="text-xs font-semibold text-emerald-600 mb-1">▲ 加仓/买入</p>
                        {(fundData as any).inflow?.map((item: any) => (
                          <div key={item.code} className="flex items-center justify-between text-xs py-1 border-b border-slate-100">
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold">{item.name}</span>
                              <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-600 px-1">{item.concept}</Badge>
                            </div>
                            <span className="text-emerald-600 font-bold">{item.amount}</span>
                          </div>
                        ))}
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-semibold text-red-600 mb-1">▼ 减仓/卖出</p>
                        {(fundData as any).outflow?.map((item: any) => (
                          <div key={item.code} className="flex items-center justify-between text-xs py-1 border-b border-slate-100">
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold">{item.name}</span>
                              <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-600 px-1">{item.concept}</Badge>
                            </div>
                            <span className="text-red-600 font-bold">{item.amount}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* 减持TOP10 + 杠杆资金TOP10 */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                  <TrendingDownIcon className="w-4 h-4 text-red-600" />
                  最近一周资金减持最多TOP10（国家队+公募+外资合并）
                </h3>
                <Badge variant="outline" className="text-xs">2025.06.16-06.20</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">排名</TableHead>
                    <TableHead className="text-xs">个股</TableHead>
                    <TableHead className="text-xs">资金来源</TableHead>
                    <TableHead className="text-xs text-right">减持规模</TableHead>
                    <TableHead className="text-xs">概念</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.combined_sell_top10?.map((item: any) => (
                    <TableRow key={item.code} className="hover:bg-slate-50">
                      <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                      <TableCell>
                        <p className="text-sm font-semibold">{item.name}</p>
                        <p className="text-xs text-slate-400">{item.code}</p>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {item.sources.map((s: string) => (
                            <Badge key={s} variant="outline" className={`text-xs ${
                              s === '国家队' ? 'bg-red-50 text-red-600' :
                              s === '公募' ? 'bg-blue-50 text-blue-600' :
                              s === '外资' ? 'bg-violet-50 text-violet-600' :
                              'bg-orange-50 text-orange-600'
                            }`}>{s}</Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-right text-red-600 font-bold text-sm">{item.amount}</TableCell>
                      <TableCell><Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-orange-600" />
                  杠杆资金控盘集中度TOP10
                </h3>
                <Badge variant="outline" className="text-xs">2025.06.23</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="bg-orange-50">
                    <TableHead className="text-xs">排名</TableHead>
                    <TableHead className="text-xs">个股</TableHead>
                    <TableHead className="text-xs text-right">融资余额占比</TableHead>
                    <TableHead className="text-xs">概念</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.leverage_concentration_top10?.map((item: any, idx: number) => (
                    <TableRow key={item.code} className="hover:bg-slate-50">
                      <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                      <TableCell>
                        <p className="text-sm font-semibold">{item.name}</p>
                        <p className="text-xs text-slate-400">{item.code}</p>
                      </TableCell>
                      <TableCell className="text-right text-orange-600 font-bold">{item.ratio}</TableCell>
                      <TableCell><Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="mt-3 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 flex items-start gap-2">
                <Info className="w-3.5 h-3.5 text-slate-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-slate-500">
                  <span className="font-semibold">什么是"非主力资金"？</span>
                  指通过融资融券加杠杆的散户、大户、游资等资金。融资余额占流通市值比例越高，说明该股被杠杆资金控盘程度越深。
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
