import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Landmark, Shield, Activity, ChevronRight, TrendingUp, TrendingDown,
  LandmarkIcon, Eye
} from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

// ====== 中央汇金 2025Q1 数据 ======
const huijinSummary = {
  totalStocks: 152,
  totalValue: '3.02万亿',
  bankValue: '2.68万亿',
  nonBankValue: '2442亿',
  etfValue: '超1万亿',
};

const huijinBanks = [
  { name: '中国银行', code: '601988', shares: '1425.9亿股', pct: '64.13%', change: '不变', note: '第一大重仓' },
  { name: '农业银行', code: '601288', shares: '1300.0亿股', pct: '40.14%', change: '不变', note: '长期持有' },
  { name: '工商银行', code: '601398', shares: '1237.2亿股', pct: '34.71%', change: '不变', note: '长期持有' },
  { name: '建设银行', code: '601939', shares: '1425.9亿股', pct: '57.11%', change: '不变', note: '长期持有' },
  { name: '交通银行', code: '601328', shares: '178.9亿股', pct: '24.08%', change: '不变', note: '长期持有' },
  { name: '邮储银行', code: '601658', shares: '450.7亿股', pct: '45.36%', change: '不变', note: '长期持有' },
  { name: '光大银行', code: '601818', shares: '77.0亿股', pct: '14.63%', change: '不变', note: '长期持有' },
  { name: '中信银行', code: '601998', shares: '31.9亿股', pct: '6.53%', change: '不变', note: '长期持有' },
];

const huijinSecurities = [
  { name: '申万宏源', code: '000166', shares: '149.0亿股', pct: '59.56%', change: '不变' },
  { name: '中国银河', code: '601881', shares: '86.7亿股', pct: '79.40%', change: '不变' },
  { name: '中金公司', code: '601995', shares: '19.4亿股', pct: '40.11%', change: '不变' },
  { name: '中信建投', code: '601066', shares: '23.9亿股', pct: '30.76%', change: '不变' },
  { name: '华泰证券', code: '601688', shares: '9614万股', pct: '1.32%', change: '新进', note: '2025Q1新进' },
  { name: '光大证券', code: '601788', shares: '12.3亿股', pct: '26.67%', change: '不变' },
  { name: '新华保险', code: '601336', shares: '9.8亿股', pct: '31.34%', change: '不变' },
];

// 动态ETF数据从 fund_data.json 读取（每日更新）
const etfBaseInfo: Record<string, string> = {
  '510300': '1434.49亿',
  '510310': '1057.12亿',
  '510330': '800+亿',
  '159919': '700+亿',
  '510050': '500+亿',
  '510500': '300+亿',
  '512100': '200+亿',
};

const huijinOther = [
  { name: '贵州茅台', code: '600519', shares: '1039万股', pct: '0.83%', change: '不变', note: '持有市值约200亿' },
  { name: '万华化学', code: '600309', shares: '持续持有', pct: '-', change: '不变', note: '汇金资管持有' },
  { name: '紫金矿业', code: '601899', shares: '6.91亿股', pct: '-', change: '不变', note: '证金持有超125亿' },
  { name: '川投能源', code: '600674', shares: '持续持有', pct: '-', change: '不变', note: '持有超10年' },
  { name: '金融街', code: '000402', shares: '5178万股', pct: '1.73%', change: '不变', note: '汇金资管' },
];

// ====== 社保基金 2025Q1 数据 ======
const shebaoSummary = {
  totalStocks: 15,
  totalValue: '52.15亿',
  increase: 5,
  decrease: 3,
  newEntry: 5,
  hold: 2,
};

const shebaoIncrease = [
  { name: '万华化学', code: '600309', combo: '103组合', change: '增持', value: '14.26亿', note: '化工龙头,持仓市值领先', pctChange: '+' },
  { name: '小商品城', code: '600415', combo: '110+116组合', change: '增持', value: '合计6126万股', note: '持股量翻倍', pctChange: '+100%+' },
  { name: '广联达', code: '002410', combo: '102组合', change: '增持', value: '5亿+', note: 'TMT个股', pctChange: '+' },
  { name: '千禾味业', code: '603027', combo: '-', change: '增持', value: '-', note: '调味品', pctChange: '+' },
  { name: '中国西电', code: '601179', combo: '-', change: '增持', value: '-', note: '电力设备', pctChange: '+' },
];

const shebaoNew = [
  { name: '钧达股份', code: '002865', combo: '118组合', change: '新进', value: '5亿+', note: '新能源', sector: '光伏' },
  { name: '三维化学', code: '002469', combo: '-', change: '新进', value: '-', note: '化工', sector: '化工' },
  { name: '绝味食品', code: '603517', combo: '-', change: '新进', value: '-', note: '食品', sector: '消费' },
  { name: '萤石网络', code: '688475', combo: '-', change: '新进', value: '-', note: '智能家居', sector: '科技' },
  { name: '奥来德', code: '688378', combo: '-', change: '新进', value: '-', note: '光电材料', sector: '材料' },
];

const shebaoDecrease = [
  { name: '九洲药业', code: '603456', combo: '17052+418组合', change: '减持', note: 'CXO', sector: '医药' },
  { name: '圣泉集团', code: '605589', combo: '-', change: '减持', note: '化工材料', sector: '化工' },
  { name: '中原传媒', code: '000719', combo: '-', change: '减持', note: '出版传媒, Q1净利+235%', sector: '传媒' },
];

// ====== 证金公司 2025Q1 数据 ======
const zhengjinSummary = {
  totalIncrease: 26,
  totalDecrease: 0,
  newEntry: 3,
};

const zhengjinIncrease = [
  { name: '中国平安', code: '601318', change: '增持', note: '保险龙头' },
  { name: '华泰证券', code: '601688', change: '增持', note: '券商' },
  { name: '国泰海通', code: '601211', change: '增持', note: '券商' },
  { name: '包钢股份', code: '600010', change: '增持', note: '钢铁' },
  { name: '浙能电力', code: '600023', change: '增持', note: '电力' },
  { name: '海螺水泥', code: '600585', change: '增持', note: '水泥建材' },
  { name: '东方电气', code: '600875', change: '增持', note: '电力设备' },
  { name: '新华保险', code: '601336', change: '增持', note: '保险' },
  { name: '许继电气', code: '000400', change: '增持', note: '电力设备,3家资管计划' },
  { name: '光大证券', code: '601788', change: '增持', note: '券商' },
  { name: '金螳螂', code: '002081', change: '增持', note: '装饰' },
  { name: '金隅集团', code: '601992', change: '增持', note: '建材' },
  { name: '安徽合力', code: '600761', change: '增持', note: '机械' },
  { name: '宝新能源', code: '000690', change: '增持', note: '电力' },
];

const zhengjinNew = [
  { name: '中信特钢', code: '000708', change: '新进', value: '1.21亿', note: '特钢制造,全球品种最多', sector: '钢铁' },
  { name: '中船防务', code: '600685', change: '新进', value: '1.05亿', note: 'Q1净利+1099%', sector: '军工' },
  { name: '天富能源', code: '600509', change: '新进', value: '-', note: '电力', sector: '电力' },
];

export default function NationalTeamPanel() {
  const [activeHuijinTab, setActiveHuijinTab] = useState('banks');
  const { data } = useFundData();

  return (
    <div className="space-y-5">
      {/* ====== SUMMARY CARDS ====== */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-gradient-to-br from-red-50 to-red-100 border-red-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-5 h-5 text-red-600" />
              <h3 className="font-bold text-red-800">中央汇金</h3>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-red-600">持仓公司</span>
                <span className="font-bold text-red-800">{huijinSummary.totalStocks}家</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-600">总市值</span>
                <span className="font-bold text-red-800">{huijinSummary.totalValue}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-600">银行板块</span>
                <span className="font-bold text-red-800">{huijinSummary.bankValue}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-600">非银金融</span>
                <span className="font-bold text-red-800">{huijinSummary.nonBankValue}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-600">ETF持仓</span>
                <span className="font-bold text-red-800">{huijinSummary.etfValue}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-5 h-5 text-blue-600" />
              <h3 className="font-bold text-blue-800">社保基金</h3>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-blue-600">重仓个股</span>
                <span className="font-bold text-blue-800">{shebaoSummary.totalStocks}只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-blue-600">合计市值</span>
                <span className="font-bold text-blue-800">{shebaoSummary.totalValue}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-blue-600">增持</span>
                <span className="font-bold text-emerald-600">{shebaoSummary.increase}只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-blue-600">新进</span>
                <span className="font-bold text-amber-600">{shebaoSummary.newEntry}只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-blue-600">减持</span>
                <span className="font-bold text-red-600">{shebaoSummary.decrease}只</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Landmark className="w-5 h-5 text-orange-600" />
              <h3 className="font-bold text-orange-800">证金公司</h3>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-orange-600">增持个股</span>
                <span className="font-bold text-orange-800">{zhengjinSummary.totalIncrease}只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-orange-600">新进个股</span>
                <span className="font-bold text-amber-600">{zhengjinSummary.newEntry}只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-orange-600">减持个股</span>
                <span className="font-bold text-slate-500">{zhengjinSummary.totalDecrease}只</span>
              </div>
              <div className="mt-2 pt-2 border-t border-orange-200">
                <p className="text-xs text-orange-700">风格：加仓低估值蓝筹+高景气赛道</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ====== DETAIL TABS ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <LandmarkIcon className="w-5 h-5 text-slate-600" />
            国家队资金调仓明细
          </CardTitle>
          <CardDescription>数据来源：Wind · 上市公司2025年一季报十大流通股东披露</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="huijin">
            <TabsList className="grid grid-cols-3 w-full max-w-md mb-4">
              <TabsTrigger value="huijin">中央汇金</TabsTrigger>
              <TabsTrigger value="shebao">社保基金</TabsTrigger>
              <TabsTrigger value="zhengjin">证金公司</TabsTrigger>
            </TabsList>

            {/* === 中央汇金 === */}
            <TabsContent value="huijin" className="space-y-4">
              <Tabs value={activeHuijinTab} onValueChange={setActiveHuijinTab}>
                <TabsList className="grid grid-cols-4 w-full max-w-lg">
                  <TabsTrigger value="banks">银行股(8家)</TabsTrigger>
                  <TabsTrigger value="securities">券商(7家)</TabsTrigger>
                  <TabsTrigger value="etf">ETF(7只)</TabsTrigger>
                  <TabsTrigger value="other">其他持股</TabsTrigger>
                </TabsList>

                <TabsContent value="banks" className="mt-4">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-red-50">
                        <TableHead>银行</TableHead>
                        <TableHead>持股数</TableHead>
                        <TableHead>持股比例</TableHead>
                        <TableHead>变动</TableHead>
                        <TableHead>备注</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {huijinBanks.map((b) => (
                        <TableRow key={b.code}>
                          <TableCell>
                            <p className="font-semibold">{b.name}</p>
                            <p className="text-xs text-slate-400">{b.code}</p>
                          </TableCell>
                          <TableCell className="font-medium">{b.shares}</TableCell>
                          <TableCell><Badge variant="outline" className="text-xs bg-red-50">{b.pct}</Badge></TableCell>
                          <TableCell><Badge className="bg-slate-100 text-slate-600 text-xs">{b.change}</Badge></TableCell>
                          <TableCell className="text-xs text-slate-500">{b.note}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TabsContent>

                <TabsContent value="securities" className="mt-4">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-red-50">
                        <TableHead>券商/保险</TableHead>
                        <TableHead>持股数</TableHead>
                        <TableHead>持股比例</TableHead>
                        <TableHead>变动</TableHead>
                        <TableHead>备注</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {huijinSecurities.map((s) => (
                        <TableRow key={s.code}>
                          <TableCell>
                            <p className="font-semibold">{s.name}</p>
                            <p className="text-xs text-slate-400">{s.code}</p>
                          </TableCell>
                          <TableCell className="font-medium">{s.shares}</TableCell>
                          <TableCell><Badge variant="outline" className="text-xs bg-red-50">{s.pct}</Badge></TableCell>
                          <TableCell>
                            <Badge className={s.change === '新进' ? 'bg-emerald-100 text-emerald-700 text-xs' : 'bg-slate-100 text-slate-600 text-xs'}>
                              {s.change}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-slate-500">{s.note || '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <p className="text-xs text-slate-500 mt-2">汇金旗下共8家券商：中国银河、中金公司、申万宏源、中信建投、光大证券、信达证券、东兴证券、长城国瑞</p>
                </TabsContent>

                <TabsContent value="etf" className="mt-4 space-y-4">
                  {/* 汇金宽基ETF */}
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-red-50">
                        <TableHead>ETF名称</TableHead>
                        <TableHead>代码</TableHead>
                        <TableHead>持仓市值</TableHead>
                        <TableHead>当日涨跌</TableHead>
                        <TableHead>收盘价</TableHead>
                        <TableHead>备注</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.nationalETF?.map((e: any) => (
                        <TableRow key={e.ticker}>
                          <TableCell className="font-semibold">{e.name}</TableCell>
                          <TableCell className="text-xs text-slate-400">{e.ticker}</TableCell>
                          <TableCell className="font-medium">{etfBaseInfo[e.ticker] || '--'}</TableCell>
                          <TableCell>
                            <Badge className={e.changePct >= 0 ? 'bg-emerald-100 text-emerald-700 text-xs' : 'bg-red-100 text-red-700 text-xs'}>
                              {e.changePct >= 0 ? '+' : ''}{e.changePct}%
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium">{e.close?.toFixed(3) || '--'}</TableCell>
                          <TableCell className="text-xs text-slate-500">{e.q1Note}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <p className="text-xs text-slate-500">汇金+汇金资管合计持有ETF市值超1万亿元，2025Q1大举增持4只沪深300ETF+华夏上证50ETF。ETF数据每日更新。</p>

                  {/* 三家国家队动态 - 从数据读取 */}
                  {data.nationalTeamNews && (
                    <div className="mt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-bold text-slate-800">三家国家队最新动向</h4>
                        <span className="text-[10px] text-slate-400">更新: {data.nationalTeamNews.updateTime}</span>
                      </div>
                      {data.nationalTeamNews.teams.map((team: any) => (
                        <div key={team.name} className={`p-3 rounded-lg border ${
                          team.name === '中央汇金' ? 'bg-red-50 border-red-200' :
                          team.name === '中国诚通' ? 'bg-blue-50 border-blue-200' :
                          'bg-amber-50 border-amber-200'
                        }`}>
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <div className={`w-2 h-2 rounded-full ${
                                team.name === '中央汇金' ? 'bg-red-500' :
                                team.name === '中国诚通' ? 'bg-blue-500' :
                                'bg-amber-500'
                              }`} />
                              <span className="text-sm font-bold text-slate-800">{team.name}</span>
                              <span className="text-[10px] text-slate-500">({team.role})</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge className={`text-[10px] h-4 ${
                                team.trend.includes('增持') ? 'bg-emerald-100 text-emerald-700' :
                                team.trend.includes('减持') ? 'bg-red-100 text-red-700' :
                                'bg-slate-100 text-slate-700'
                              }`}>
                                {team.trend}
                              </Badge>
                            </div>
                          </div>
                          <p className="text-xs text-slate-700 mb-1"><strong>持仓规模:</strong> {team.totalValue}</p>
                          <p className="text-xs text-slate-600 mb-2">{team.latestAction}</p>
                          {/* 时间线 */}
                          <div className="space-y-1">
                            {team.details.map((d: any, i: number) => (
                              <div key={i} className="flex gap-2 text-[11px]">
                                <span className="text-slate-400 flex-shrink-0 w-[70px]">{d.date}</span>
                                <span className="text-slate-600">{d.event}</span>
                                <span className="text-slate-400 flex-shrink-0">[{d.source}]</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="other" className="mt-4">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-red-50">
                        <TableHead>个股</TableHead>
                        <TableHead>持股数</TableHead>
                        <TableHead>持股比例</TableHead>
                        <TableHead>变动</TableHead>
                        <TableHead>备注</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {huijinOther.map((o) => (
                        <TableRow key={o.code}>
                          <TableCell>
                            <p className="font-semibold">{o.name}</p>
                            <p className="text-xs text-slate-400">{o.code}</p>
                          </TableCell>
                          <TableCell className="font-medium">{o.shares}</TableCell>
                          <TableCell><Badge variant="outline" className="text-xs">{o.pct}</Badge></TableCell>
                          <TableCell><Badge className="bg-slate-100 text-slate-600 text-xs">{o.change}</Badge></TableCell>
                          <TableCell className="text-xs text-slate-500">{o.note}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TabsContent>
              </Tabs>
            </TabsContent>

            {/* === 社保基金 === */}
            <TabsContent value="shebao" className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <Card className="bg-emerald-50 border-emerald-200">
                  <CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-emerald-700 flex items-center gap-2"><TrendingUp className="w-4 h-4" />增持5只</CardTitle></CardHeader>
                  <CardContent className="pt-0">
                    {shebaoIncrease.map((s) => (
                      <div key={s.code} className="py-1.5 border-b border-emerald-100 last:border-0">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">{s.name}</span>
                          <Badge className="bg-emerald-100 text-emerald-700 text-xs">{s.change}</Badge>
                        </div>
                        <p className="text-xs text-slate-500">{s.combo} · {s.value}</p>
                        <p className="text-xs text-slate-400">{s.note}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="bg-amber-50 border-amber-200">
                  <CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-amber-700 flex items-center gap-2"><Eye className="w-4 h-4" />新进5只</CardTitle></CardHeader>
                  <CardContent className="pt-0">
                    {shebaoNew.map((s) => (
                      <div key={s.code} className="py-1.5 border-b border-amber-100 last:border-0">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">{s.name}</span>
                          <Badge className="bg-amber-100 text-amber-700 text-xs">{s.change}</Badge>
                        </div>
                        <p className="text-xs text-slate-500">{s.combo} · {s.sector}</p>
                        <p className="text-xs text-slate-400">{s.note}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="bg-red-50 border-red-200">
                  <CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-red-700 flex items-center gap-2"><TrendingDown className="w-4 h-4" />减持3只</CardTitle></CardHeader>
                  <CardContent className="pt-0">
                    {shebaoDecrease.map((s) => (
                      <div key={s.code} className="py-1.5 border-b border-red-100 last:border-0">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">{s.name}</span>
                          <Badge className="bg-red-100 text-red-700 text-xs">{s.change}</Badge>
                        </div>
                        <p className="text-xs text-slate-500">{s.combo} · {s.sector}</p>
                        <p className="text-xs text-slate-400">{s.note}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <h4 className="text-sm font-bold text-blue-800 mb-2">持仓特征</h4>
                <ul className="text-xs text-blue-700 space-y-1">
                  <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />主板12只，科创板2只，创业板1只</li>
                  <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />"科技+消费"双核驱动，7只Q1净利同比增长</li>
                  <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />小商品城、九洲药业、绝味食品各有2家社保同时重仓</li>
                </ul>
              </div>
            </TabsContent>

            {/* === 证金公司 === */}
            <TabsContent value="zhengjin" className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-bold text-emerald-700">增持26只个股（部分）</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                      {zhengjinIncrease.map((z) => (
                        <div key={z.code} className="flex items-center justify-between py-1 border-b border-slate-50">
                          <div>
                            <p className="text-sm font-medium">{z.name}</p>
                            <p className="text-xs text-slate-400">{z.code} · {z.note}</p>
                          </div>
                          <Badge className="bg-emerald-100 text-emerald-700 text-xs">{z.change}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <div className="space-y-4">
                  <Card className="bg-amber-50 border-amber-200">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-bold text-amber-700">新进3只个股</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0 space-y-2">
                      {zhengjinNew.map((z) => (
                        <div key={z.code} className="bg-white rounded-lg p-3 border border-amber-200">
                          <div className="flex justify-between items-center mb-1">
                            <span className="font-bold text-sm">{z.name}</span>
                            <Badge className="bg-amber-100 text-amber-700 text-xs">{z.change}</Badge>
                          </div>
                          <p className="text-xs text-slate-500">{z.code} · {z.sector}</p>
                          <p className="text-xs text-slate-500">新增持仓: <span className="font-semibold">{z.value}</span></p>
                          <p className="text-xs text-slate-400 mt-0.5">{z.note}</p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  <Card className="bg-slate-50 border-slate-200">
                    <CardContent className="p-4">
                      <h4 className="text-sm font-bold text-slate-800 mb-2">证金持仓特征</h4>
                      <ul className="text-xs text-slate-600 space-y-1.5">
                        <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />坚守金融蓝筹+加码周期、制造</li>
                        <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />新进中信特钢、中船防务、天富能源</li>
                        <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />小商品城、许继电气有3家以上证金资管计划同时持股</li>
                        <li className="flex items-start gap-2"><ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />自2015年以来持有紫金矿业、川投能源等超10年</li>
                      </ul>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* ====== TOP5 National Team Inflow ====== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-red-600" />
            国家队近三个月增持最多TOP5
          </CardTitle>
          <CardDescription>社保基金 2026Q1 一季报口径 · Q2 持仓随中报 8 月披露</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="bg-red-50">
                <TableHead className="text-xs">排名</TableHead>
                <TableHead className="text-xs">个股</TableHead>
                <TableHead className="text-xs">增持金额</TableHead>
                <TableHead className="text-xs">概念</TableHead>
                <TableHead className="text-xs">二级板块</TableHead>
                <TableHead className="text-xs">持股方</TableHead>
                <TableHead className="text-xs">备注</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.top5_national?.map((item, idx) => (
                <TableRow key={item.code} className="hover:bg-slate-50">
                  <TableCell className="font-bold text-sm">{idx + 1}</TableCell>
                  <TableCell>
                    <p className="font-semibold text-sm">{item.name}</p>
                    <p className="text-xs text-slate-400">{item.code}</p>
                  </TableCell>
                  <TableCell className="text-red-600 font-bold">{item.inflow}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs bg-blue-50 text-blue-600">{item.concept}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{item.sector}</span>
                  </TableCell>
                  <TableCell className="text-xs font-medium">{item.holder}</TableCell>
                  <TableCell className="text-xs text-slate-500">{item.note}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ====== UPDATE SCHEDULE ====== */}
      <Card className="bg-slate-50 border-slate-200">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-slate-600" />
            <h4 className="font-bold text-slate-800">数据更新说明</h4>
          </div>
          <div className="grid grid-cols-3 gap-4 text-xs text-slate-600">
            <div>
              <p className="font-semibold mb-1">中央汇金</p>
              <p>季报/年报披露（1月、4月、7月、10月），ETF数据随基金季报更新</p>
            </div>
            <div>
              <p className="font-semibold mb-1">社保基金</p>
              <p>上市公司十大流通股东季报披露，调仓较活跃</p>
            </div>
            <div>
              <p className="font-semibold mb-1">证金公司</p>
              <p>上市公司十大流通股东季报披露，持仓高度稳定</p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-3">当前数据基于2025年一季报（截至4月30日披露完毕） · 数据来源：Wind · Choice</p>
        </CardContent>
      </Card>
    </div>
  );
}
