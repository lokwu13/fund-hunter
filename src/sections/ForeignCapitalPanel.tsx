import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Globe, ArrowUpRight, ArrowDownRight, ChevronRight, Activity, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';



// 分歧数据 - 南向流入 vs 外资流出
const divergenceData = [
  { name: '腾讯控股', code: '00700', southInflow: 48.5, foreignOutflow: 205.6, concept: '互联网/游戏', sector: '港股科技' },
  { name: '小米集团', code: '01810', southInflow: 35.2, foreignOutflow: 156.3, concept: '智能手机/IoT', sector: '消费电子' },
  { name: '阿里巴巴', code: '09988', southInflow: 28.8, foreignOutflow: 86.6, concept: '电商/云计算', sector: '互联网' },
  { name: '泡泡玛特', code: '09992', southInflow: 42.3, foreignOutflow: 25.4, concept: '潮玩/IP', sector: '新消费' },
  { name: '快手-W', code: '01024', southInflow: 15.6, foreignOutflow: 52.8, concept: '短视频', sector: '互联网' },
  { name: '中芯国际', code: '00981', southInflow: 38.5, foreignOutflow: 18.2, concept: '晶圆代工', sector: '半导体' },
  { name: '康方生物', code: '09926', southInflow: 22.1, foreignOutflow: 13.3, concept: '创新药', sector: '生物科技' },
  { name: '美团-W', code: '03690', southInflow: 116.2, foreignOutflow: 8.5, concept: '本地生活', sector: '互联网' },
];

export default function ForeignCapitalPanel() {
  const { data } = useFundData();
  const nb = data.northbound;
  const sb = data.southbound;

  // 计算最大比例用于条形图
  const maxFlow = Math.max(
    ...divergenceData.map(d => d.foreignOutflow),
    ...divergenceData.map(d => d.southInflow)
  );

  return (
    <div className="space-y-6">
      {/* Northbound & Southbound Summary */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="bg-gradient-to-br from-violet-50 to-violet-100 border-violet-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <ArrowUpRight className="w-5 h-5 text-violet-600" />
              <h3 className="font-bold text-violet-800">北向资金 (本周)</h3>
            </div>
            <p className="text-2xl font-bold text-violet-900">{nb.week > 0 ? '+' : ''}{nb.week}亿</p>
            <p className="text-sm text-violet-600">{nb.week > 0 ? '净流入' : '净流出'}</p>
            <div className="mt-3 p-2 bg-white/60 rounded-lg">
              <p className="text-xs text-violet-700">
                医疗板块: {nb.medical > 0 ? '+' : ''}{nb.medical}亿
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-teal-50 to-teal-100 border-teal-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <ArrowDownRight className="w-5 h-5 text-teal-600" />
              <h3 className="font-bold text-teal-800">南下资金 (本周)</h3>
            </div>
            <p className="text-2xl font-bold text-teal-900">{sb.week > 0 ? '+' : ''}{sb.week}亿港元</p>
            <p className="text-sm text-teal-600">{sb.week > 0 ? '净流入' : '净流出'}</p>
            <div className="mt-3 flex gap-2">
              <Badge className={sb.week < 0 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}>
                本周: {sb.week > 0 ? '+' : ''}{sb.week}亿
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ====== 内外资分歧个股双向对比图 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                内外资分歧 — 个股双向流向对比
              </CardTitle>
              <CardDescription>同一标的上：南向资金买入 vs 国际中介卖出 · 单位：亿港元</CardDescription>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-emerald-400 rounded" />南向买入</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-400 rounded" />外资卖出</span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {divergenceData.map((item) => {
              const southPct = (item.southInflow / maxFlow) * 100;
              const foreignPct = (item.foreignOutflow / maxFlow) * 100;
              const divergenceTotal = item.southInflow + item.foreignOutflow;
              return (
                <div key={item.code} className="group">
                  {/* 个股名称行 */}
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-slate-800">{item.name}</span>
                      <span className="text-xs text-slate-400">{item.code}</span>
                      <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                    </div>
                    <span className="text-xs font-bold text-amber-700">
                      分歧 {divergenceTotal.toFixed(1)}亿
                    </span>
                  </div>
                  {/* 双向条形图 */}
                  <div className="flex items-center gap-2 h-6">
                    {/* 左侧：外资流出（红色，从右往左） */}
                    <div className="flex-1 flex justify-end">
                      <div className="flex items-center gap-1" style={{ width: `${foreignPct}%`, minWidth: '20px' }}>
                        <span className="text-xs text-red-600 font-medium whitespace-nowrap">-{item.foreignOutflow}</span>
                        <div className="h-3.5 bg-red-400 rounded-l-md w-full" />
                      </div>
                    </div>
                    {/* 中线 */}
                    <div className="w-px h-5 bg-slate-300 flex-shrink-0" />
                    {/* 右侧：南向流入（绿色，从左往右） */}
                    <div className="flex-1 flex justify-start">
                      <div className="flex items-center gap-1" style={{ width: `${southPct}%`, minWidth: '20px' }}>
                        <div className="h-3.5 bg-emerald-400 rounded-r-md w-full" />
                        <span className="text-xs text-emerald-600 font-medium whitespace-nowrap">+{item.southInflow}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-slate-400 mt-3 text-center">
            左右两端长度代表金额大小 · 中间竖线为分界 · 两侧同时存在=激烈分歧
          </p>
        </CardContent>
      </Card>

      {/* ====== 分歧TOP10详细表格 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <Activity className="w-5 h-5 text-amber-600" />
            内外资分歧最大十大标的
          </CardTitle>
          <CardDescription>南向资金净买入 vs 国际中介净卖出 · 2025年6月</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="bg-amber-50">
                <TableHead className="text-xs">排名</TableHead>
                <TableHead className="text-xs">个股</TableHead>
                <TableHead className="text-xs text-right">南向流入</TableHead>
                <TableHead className="text-xs text-right">外资流出</TableHead>
                <TableHead className="text-xs text-right">分歧金额</TableHead>
                <TableHead className="text-xs">概念</TableHead>
                <TableHead className="text-xs">二级板块</TableHead>
                <TableHead className="text-xs">分歧特征</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.divergence_top10?.map((item, idx) => (
                <TableRow key={item.code} className="hover:bg-slate-50">
                  <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                  <TableCell>
                    <p className="font-semibold text-sm">{item.name}</p>
                    <p className="text-xs text-slate-400">{item.code}</p>
                  </TableCell>
                  <TableCell className="text-right text-emerald-600 font-medium">{item.southInflow}</TableCell>
                  <TableCell className="text-right text-red-600 font-medium">{item.foreignOutflow}</TableCell>
                  <TableCell className="text-right font-bold text-amber-700">{item.netDivergence}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                  </TableCell>
                  <TableCell className="text-xs text-slate-500">{item.note}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ====== 南下资金 vs 外资 集中度对比 ====== */}
      <div className="grid grid-cols-2 gap-4">
        {/* 南下资金（国内资金）集中度TOP10 */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-teal-600" />
                  南下资金（国内资金）持股集中度TOP10
                </h3>
                <p className="text-xs text-slate-400">港股通持股占港股总股本比例</p>
              </div>
              <Badge variant="outline" className="text-xs">港股</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-teal-50">
                  <TableHead className="text-xs">排名</TableHead>
                  <TableHead className="text-xs">个股</TableHead>
                  <TableHead className="text-xs text-right">持股比例</TableHead>
                  <TableHead className="text-xs">概念</TableHead>
                  <TableHead className="text-xs">二级板块</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.southbound_concentration_top10?.map((item, idx) => (
                  <TableRow key={item.code} className="hover:bg-slate-50">
                    <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                    <TableCell>
                      <p className="text-sm font-semibold">{item.name}</p>
                      <p className="text-xs text-slate-400">{item.code}</p>
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="text-sm font-bold text-teal-600">{item.ratio}</span>
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

        {/* 外资（非国内资金）集中度TOP10 */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                  <Globe className="w-4 h-4 text-indigo-600" />
                  外资（非国内资金）持股集中度TOP10
                </h3>
                <p className="text-xs text-slate-400">国际机构持股占港股总股本比例</p>
              </div>
              <Badge variant="outline" className="text-xs">港股</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-indigo-50">
                  <TableHead className="text-xs">排名</TableHead>
                  <TableHead className="text-xs">个股</TableHead>
                  <TableHead className="text-xs text-right">持股比例</TableHead>
                  <TableHead className="text-xs">概念</TableHead>
                  <TableHead className="text-xs">二级板块</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.foreign_concentration_top10?.map((item, idx) => (
                  <TableRow key={item.code} className="hover:bg-slate-50">
                    <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                    <TableCell>
                      <p className="text-sm font-semibold">{item.name}</p>
                      <p className="text-xs text-slate-400">{item.code}</p>
                      <p className="text-xs text-slate-400">{item.institution}</p>
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="text-sm font-bold text-indigo-600">{item.ratio}</span>
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

      {/* ====== 北向资金净流入TOP10 ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-violet-600" />
            北向资金近三个月净流入最多TOP10
          </CardTitle>
          <CardDescription>沪深港通持股变动 · 2025Q2</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="bg-violet-50">
                <TableHead className="text-xs">排名</TableHead>
                <TableHead className="text-xs">个股</TableHead>
                <TableHead className="text-xs">净流入</TableHead>
                <TableHead className="text-xs">概念</TableHead>
                <TableHead className="text-xs">二级板块</TableHead>
                <TableHead className="text-xs">备注</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.top10_foreign?.map((item, idx) => (
                <TableRow key={item.code} className="hover:bg-slate-50">
                  <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                  <TableCell>
                    <p className="font-semibold text-sm">{item.name}</p>
                    <p className="text-xs text-slate-400">{item.code}</p>
                  </TableCell>
                  <TableCell className="text-violet-600 font-bold">{item.inflow}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                  </TableCell>
                  <TableCell className="text-xs text-slate-500">{item.note}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ====== 外资机构买入/卖出TOP10 左右对照 ====== */}
      <div className="grid grid-cols-2 gap-4">
        {/* 买入TOP10 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold flex items-center gap-2 text-emerald-700">
              <TrendingUp className="w-4 h-4" />
              外资机构买入TOP10（A+H股）
            </CardTitle>
            <CardDescription className="text-xs">
              港交所权益披露 + 沪深港通北向持仓 · 覆盖全市场
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-emerald-50">
                  <TableHead className="text-xs">排名</TableHead>
                  <TableHead className="text-xs">个股</TableHead>
                  <TableHead className="text-xs">市场</TableHead>
                  <TableHead className="text-xs text-right">买入金额</TableHead>
                  <TableHead className="text-xs">机构</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.foreignInstitution_top10?.buys?.map((stock) => (
                  <TableRow key={stock.code} className="hover:bg-slate-50">
                    <TableCell className="font-bold text-sm">{stock.rank}</TableCell>
                    <TableCell>
                      <p className="text-sm font-semibold">{stock.name}</p>
                      <p className="text-xs text-slate-400">{stock.code}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-xs ${
                        stock.market === '港股' ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-600'
                      }`}>
                        {stock.market}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-emerald-600 font-bold text-sm">{stock.amount}</TableCell>
                    <TableCell className="text-xs font-medium">{stock.institution}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* 卖出TOP10 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold flex items-center gap-2 text-red-700">
              <TrendingDown className="w-4 h-4" />
              外资机构卖出TOP10（A+H股）
            </CardTitle>
            <CardDescription className="text-xs">
              港交所权益披露 + 沪深港通北向持仓 · 覆盖全市场
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-red-50">
                  <TableHead className="text-xs">排名</TableHead>
                  <TableHead className="text-xs">个股</TableHead>
                  <TableHead className="text-xs">市场</TableHead>
                  <TableHead className="text-xs text-right">卖出金额</TableHead>
                  <TableHead className="text-xs">机构</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.foreignInstitution_top10?.sells?.map((stock) => (
                  <TableRow key={stock.code} className="hover:bg-slate-50">
                    <TableCell className="font-bold text-sm">{stock.rank}</TableCell>
                    <TableCell>
                      <p className="text-sm font-semibold">{stock.name}</p>
                      <p className="text-xs text-slate-400">{stock.code}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-xs ${
                        stock.market === '港股' ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-600'
                      }`}>
                        {stock.market}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-red-600 font-bold text-sm">{stock.amount}</TableCell>
                    <TableCell className="text-xs font-medium">{stock.institution}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* 详细表格 - 买入 */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Globe className="w-5 h-5 text-indigo-600" />
                外资机构买入TOP10详细（A+H股全市场）
              </CardTitle>
              <CardDescription>
                覆盖南向资金/北向资金/BlackRock/JPMorgan/Vanguard/State Street/Fidelity等
              </CardDescription>
            </div>
            <Badge className="bg-emerald-100 text-emerald-700 text-xs">每周更新</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="bg-indigo-50">
                <TableHead className="text-xs">排名</TableHead>
                <TableHead className="text-xs">个股</TableHead>
                <TableHead className="text-xs">市场</TableHead>
                <TableHead className="text-xs">机构</TableHead>
                <TableHead className="text-xs text-right">金额</TableHead>
                <TableHead className="text-xs">日期</TableHead>
                <TableHead className="text-xs">概念</TableHead>
                <TableHead className="text-xs">板块</TableHead>
                <TableHead className="text-xs">持股变动</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.foreignInstitution_top10?.buys?.map((stock) => (
                <TableRow key={stock.code} className="hover:bg-slate-50">
                  <TableCell className="font-bold text-sm">{stock.rank}</TableCell>
                  <TableCell>
                    <p className="font-semibold text-sm">{stock.name}</p>
                    <p className="text-xs text-slate-400">{stock.code}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-xs ${
                      stock.market === '港股' ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-600'
                    }`}>
                      {stock.market}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs font-medium">{stock.institution}</TableCell>
                  <TableCell className="text-right text-emerald-600 font-bold">{stock.amount}</TableCell>
                  <TableCell className="text-xs">{stock.date}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{stock.concept}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{stock.sector}</span>
                  </TableCell>
                  <TableCell className="text-xs text-slate-500">{stock.holdingChange}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-slate-400 mt-3">
            注：数据来源港交所"披露权益"系统 + 沪深港通北向持仓统计。A股包含通过港股通买入的标的。
            每周五收盘后更新，反映前一周机构最新买卖动作。
          </p>
        </CardContent>
      </Card>

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
