import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  TrendingUp, TrendingDown, Lock, Activity
} from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

const fundOverview = {
  totalHolding: '8.87%',
  change: '+0.90',
  historicalLow: '7.97%',
  historicalAvg: '12.0%',
  recoverySpace: '+3.13',
};

const subSectorChanges = [
  { name: 'CXO', change: '+1.2%', trend: 'up' },
  { name: '创新药', change: '+0.8%', trend: 'up' },
  { name: '中药', change: '+0.3%', trend: 'up' },
  { name: '医疗器械', change: '-0.5%', trend: 'down' },
  { name: '医疗服务', change: '-0.3%', trend: 'down' },
];

// 公募数据从 fund_data.json 动态加载，覆盖全市场A+H股

export default function PublicFundPanel() {
  const { data } = useFundData();
  const [activeTab, setActiveTab] = useState('public');
  const [openSmart, setOpenSmart] = useState<string | null>(null);
  const sm = data.sectorSmartMoney;

  const smVerdictCls = (v: string) =>
    v === '✅有效' ? 'bg-emerald-600 text-white' :
    v === '❌无效' ? 'bg-rose-600 text-white' :
    v === '中性' ? 'bg-slate-400 text-white' : 'bg-slate-200 text-slate-500';
  const exTxt = (v: number | null) =>
    v == null ? <span className="text-slate-300">—</span> :
      <span className={`font-semibold ${v >= 0 ? 'text-red-500' : 'text-emerald-600'}`}>{v >= 0 ? '+' : ''}{v}%</span>;

  return (
    <div className="space-y-6">
      {/* ====== 板块聪明钱超额榜（45只主动基金×12板块，并入总览第2步验证） ====== */}
      {sm && (
        <Card id="smart-money" className="shadow-sm border-emerald-200">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-600" />
                板块聪明钱超额榜
                <span className="text-[10px] font-normal text-slate-400">
                  主动基金超额=YTD超额中位判定 · 净值 {sm.nav_date || sm.trade_date}（T+1口径）
                </span>
              </CardTitle>
              <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-200">
                {sm.sectors.filter(s => s.verdict === '✅有效').length}✅ / {sm.sectors.filter(s => s.verdict === '❌无效').length}❌ / {sm.sectors.filter(s => s.verdict === '中性').length}中性
              </Badge>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">
              判定：YTD超额中位&gt;0 且 跑赢占比≥60% → ✅有效；中位&lt;0 且 ≤40% → ❌无效；其余中性。基准东财板块指数优先、封禁降级等权合成（逐板块注明）。点击板块行展开基金明细。
            </p>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {sm.sectors.map((s) => (
              <div key={s.sector} className="rounded-lg border border-slate-100">
                <button type="button" onClick={() => setOpenSmart(openSmart === s.sector ? null : s.sector)}
                        className="w-full flex items-center gap-2 flex-wrap px-3 py-2 text-left hover:bg-emerald-50/40 rounded-lg">
                  <span className="text-xs font-bold text-slate-800 w-16 flex-shrink-0">{s.sector}</span>
                  <Badge className={`text-[10px] h-[18px] px-1.5 border-0 flex-shrink-0 ${smVerdictCls(s.verdict)}`}>{s.verdict}</Badge>
                  <span className="text-[10px] text-slate-400 flex-shrink-0">{s.nFunds}只</span>
                  <span className="text-[11px] flex-shrink-0">1月 {exTxt(s.ex1mMed)}</span>
                  <span className="text-[11px] flex-shrink-0">3月 {exTxt(s.ex3mMed)}</span>
                  <span className="text-[11px] flex-shrink-0">YTD {exTxt(s.exytdMed)}</span>
                  <span className="text-[10px] text-slate-500 flex-shrink-0">跑赢{s.winYtdPct ?? '—'}%</span>
                  <span className="text-[9px] text-slate-300 ml-auto flex-shrink-0">{s.benchSrc} {openSmart === s.sector ? '▲' : '▼'}</span>
                </button>
                {openSmart === s.sector && s.funds.length > 0 && (
                  <div className="px-3 pb-2 space-y-1">
                    {s.funds.map((f) => (
                      <div key={f.ts_code} className="flex items-center gap-2 flex-wrap text-[11px] border-t border-slate-50 pt-1">
                        <span className="text-slate-700 font-medium min-w-[180px]">{f.name}</span>
                        <span className="text-slate-400">{f.scale != null ? `${f.scale}亿` : ''}</span>
                        <span>1月 {exTxt(f.ex1m)}</span>
                        <span>3月 {exTxt(f.ex3m)}</span>
                        <span>YTD {exTxt(f.exytd)}</span>
                      </div>
                    ))}
                    {s.funds.length === 0 && <p className="text-[10px] text-slate-400 pt-1">该板块暂无合适主动基金样本（空档保留）</p>}
                  </div>
                )}
              </div>
            ))}
            {sm.note && <p className="text-[10px] text-slate-400 pt-1">{sm.note}</p>}
          </CardContent>
        </Card>
      )}

      {/* Overview */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <CardContent className="p-4">
            <p className="text-xs text-blue-600 mb-1">当前医药持仓</p>
            <p className="text-2xl font-bold text-blue-800">{fundOverview.totalHolding}</p>
            <p className="text-xs text-blue-500">{fundOverview.change}pp</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-slate-50 to-slate-100 border-slate-200">
          <CardContent className="p-4">
            <p className="text-xs text-slate-600 mb-1">历史最低</p>
            <p className="text-2xl font-bold text-slate-700">{fundOverview.historicalLow}</p>
            <p className="text-xs text-slate-500">2025年Q1</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-amber-50 to-amber-100 border-amber-200">
          <CardContent className="p-4">
            <p className="text-xs text-amber-600 mb-1">历史均值</p>
            <p className="text-2xl font-bold text-amber-800">{fundOverview.historicalAvg}</p>
            <p className="text-xs text-amber-500">2019-2024</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-emerald-50 to-emerald-100 border-emerald-200">
          <CardContent className="p-4">
            <p className="text-xs text-emerald-600 mb-1">回补空间</p>
            <p className="text-2xl font-bold text-emerald-800">{fundOverview.recoverySpace}pp</p>
            <p className="text-xs text-emerald-500">距历史均值</p>
          </CardContent>
        </Card>
      </div>

      {/* Sub Sector Changes */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold">医药子行业配置变动 (2025Q1→Q2)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {subSectorChanges.map((sector) => (
              <div key={sector.name} className="flex items-center justify-between">
                <span className="text-sm font-medium w-24">{sector.name}</span>
                <div className="flex-1 mx-4">
                  <Progress
                    value={Math.abs(parseFloat(sector.change)) * 20}
                    className={`h-2 ${sector.trend === 'up' ? 'bg-emerald-100' : 'bg-red-100'}`}
                  />
                </div>
                <span className={`text-sm font-bold ${sector.trend === 'up' ? 'text-emerald-600' : 'text-red-600'}`}>
                  {sector.trend === 'up' ? '+' : ''}{sector.change}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Tabs: Public Fund vs Private Fund */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-2 w-full max-w-md mb-4">
          <TabsTrigger value="public">公募基金加仓TOP5</TabsTrigger>
          <TabsTrigger value="private">私募基金流向TOP10</TabsTrigger>
        </TabsList>

        {/* ====== 公募 ====== */}
        <TabsContent value="public" className="space-y-4">
          {/* 左右对照：流入TOP10 vs 流出TOP10（全市场A+H） */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-emerald-700">
                  <TrendingUp className="w-4 h-4" />
                  公募加仓TOP10（A+H全市场）
                </CardTitle>
                <CardDescription className="text-xs">主动权益基金重仓股净流入 · 2026Q2 二季报(7月21日披露完毕)</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-emerald-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">概念</TableHead>
                      <TableHead className="text-xs text-right">加仓金额</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.top10_publicfund?.map((item) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                        </TableCell>
                        <TableCell className="text-right text-emerald-600 font-bold">{item.amount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-red-700">
                  <TrendingDown className="w-4 h-4" />
                  公募减仓TOP10（A+H全市场）
                </CardTitle>
                <CardDescription className="text-xs">主动权益基金重仓股净流出 · 2026Q2 二季报(7月21日披露完毕)</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-red-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">概念</TableHead>
                      <TableHead className="text-xs text-right">减仓金额</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.publicFund_outflow_top10?.map((item) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                        </TableCell>
                        <TableCell className="text-right text-red-600 font-bold">{item.amount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          {/* 机构持仓集中度最高TOP10 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Activity className="w-5 h-5 text-red-600" />
                机构持仓集中度最高TOP10
              </CardTitle>
              <CardDescription>公募重仓持股占自由流通市值比重 · 2026Q2 二季报(7月21日披露完毕)</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">排名</TableHead>
                    <TableHead className="text-xs">个股</TableHead>
                    <TableHead className="text-xs text-right">集中度</TableHead>
                    <TableHead className="text-xs">概念</TableHead>
                    <TableHead className="text-xs">二级板块</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.concentration_top10?.map((item) => (
                    <TableRow key={item.code} className="hover:bg-slate-50">
                      <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                      <TableCell>
                        <p className="font-semibold text-sm">{item.name}</p>
                        <p className="text-xs text-slate-400">{item.code}</p>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="text-sm font-bold text-red-600">{item.concentration}</span>
                        <p className="text-xs text-slate-400">{item.fundCount}</p>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ====== 私募 ====== */}
        <TabsContent value="private" className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* 主力资金净流入TOP10 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-emerald-700">
                  <TrendingUp className="w-4 h-4" />
                  主力资金净流入TOP10
                </CardTitle>
                <CardDescription>超大单+大单累计 · 近三个月</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-emerald-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">概念</TableHead>
                      <TableHead className="text-xs">二级板块</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.mainforce_inflow_top10?.map((item, idx) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* 主力资金净流出TOP10 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-red-700">
                  <TrendingDown className="w-4 h-4" />
                  主力资金净流出TOP10
                </CardTitle>
                <CardDescription>超大单+大单累计 · 近三个月</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-red-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">概念</TableHead>
                      <TableHead className="text-xs">二级板块</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.mainforce_outflow_top10?.map((item, idx) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          {/* 私募净流入/流出TOP5 */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <p className="text-xs text-amber-700">
              已更新至 2026Q2 中报十大流通股东口径（私募排排网统计+公开报道，截至 2026-08-27 披露）；景林为美股13F口径，仅供参考
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-emerald-700">
                  <TrendingUp className="w-4 h-4" />
                  私募净流入TOP5
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-emerald-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">私募</TableHead>
                      <TableHead className="text-xs text-right">金额</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.privateFund_inflow?.map((item) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell className="text-xs font-medium">{item.fund}</TableCell>
                        <TableCell className="text-right text-emerald-600 font-bold">{item.amount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold flex items-center gap-2 text-red-700">
                  <TrendingDown className="w-4 h-4" />
                  私募净流出TOP5
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-red-50">
                      <TableHead className="text-xs">排名</TableHead>
                      <TableHead className="text-xs">个股</TableHead>
                      <TableHead className="text-xs">私募</TableHead>
                      <TableHead className="text-xs text-right">金额</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.privateFund_outflow?.map((item) => (
                      <TableRow key={item.code} className="hover:bg-slate-50">
                        <TableCell className="font-bold text-sm">{item.rank}</TableCell>
                        <TableCell>
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-slate-400">{item.code}</p>
                        </TableCell>
                        <TableCell className="text-xs font-medium">{item.fund}</TableCell>
                        <TableCell className="text-right text-red-600 font-bold">{item.amount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          {/* 概念板块汇总 */}
          <Card className="bg-slate-50 border-slate-200">
            <CardContent className="p-4">
              <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                <Lock className="w-4 h-4" />
                私募调仓特征总结
              </h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="font-semibold text-emerald-700 mb-1">净流入方向</p>
                  <ul className="text-slate-600 space-y-1 text-xs">
                    <li>• 高毅/重阳：安防龙头分歧（冯柳减、重阳进）</li>
                    <li>• 鸿鹄基金：减持周期股，增配消费金融</li>
                    <li>• 玄元投资：重仓化工一体化龙头超3年</li>
                    <li>• 险资私募：偏好高股息+现金流稳定标的</li>
                  </ul>
                </div>
                <div>
                  <p className="font-semibold text-red-700 mb-1">净流出方向</p>
                  <ul className="text-slate-600 space-y-1 text-xs">
                    <li>• 高毅邓晓峰：减持紫金矿业（此前连续加仓）</li>
                    <li>• 冯柳：减仓海康威视/中炬高新</li>
                    <li>• 鸿鹄基金：大幅减持陕西煤业</li>
                    <li>• 整体：从能源/周期向消费/金融切换</li>
                  </ul>
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-3">
                数据来源：上市公司季报十大流通股东披露 · 覆盖高毅资产、重阳投资、玄元投资、鸿鹄基金、迎水投资等百亿级私募
                · 每周五收盘后更新
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
