import { useState, Fragment } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Landmark, Shield, Activity, ChevronRight, TrendingUp, TrendingDown,
  LandmarkIcon, Eye, Quote, Radar, ArrowLeftRight, Gauge
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
      {/* ====== 国家队每日短评（置顶） ====== */}
      {data.nationalTeamComment && (
        <Card id="nt-comment" className="bg-gradient-to-r from-red-50 via-white to-red-50 border-red-300 shadow-sm">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="bg-red-100 rounded-full p-2 flex-shrink-0">
                <Quote className="w-4 h-4 text-red-600" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-bold text-red-800 text-sm">国家队资金每日短评</h3>
                  <Badge className="bg-red-100 text-red-700 text-[10px]">自动生成</Badge>
                </div>
                <p className="text-sm text-slate-700 leading-relaxed">{data.nationalTeamComment}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 国家队主体全景（披露口径说明卡） ====== */}
      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <Shield className="w-4 h-4 text-red-600" />
            国家队主体全景 · 五路资金与披露口径
          </CardTitle>
          <CardDescription className="text-[10px]">
            本栏目日度监测以 ETF 份额口径为主（汇金/国新/诚通）；证金、社保、外管局平台仅在季报十大股东中披露，按季度跟踪，无法日度监测
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {[
            {
              name: '中央汇金（2 账户）', daily: true,
              channel: '宽基 ETF（沪深300/上证50/中证500/中证1000 等）+ 国有大行等原始持股',
              disclosure: 'ETF 份额日度可监测 → 本页「份额雷达」「ETF 轮动」；个股持仓季报口径',
              note: '2024 年起托市主力，ETF 规模超万亿',
            },
            {
              name: '国新投资 / 中国诚通', daily: true,
              channel: '央企主题 ETF（央企科技/央企红利/港股通央企红利等）',
              disclosure: 'ETF 份额日度可监测 → 本页雷达「国新系 / 诚通系」分组',
              note: '多为发行人关联方，单边异动常为自身调仓，解读需谨慎',
            },
            {
              name: '证金公司（16 账户）', daily: false,
              channel: '中国证券金融直接账户 + 15 个中证金融资管计划，以个股为主',
              disclosure: '仅季报十大股东披露，无法日度监测',
              note: '2015 年救市主体；2025Q1 国家队合计持股约 4.3 万亿（占全 A 自由流通市值 9.4%）',
            },
            {
              name: '证金系 5 只救市基金（已清盘）', daily: false, defunct: true,
              channel: '华夏新经济 001683 / 嘉实新机遇 001620 / 南方消费活力 001772 / 易方达瑞惠 001769 / 招商丰庆A 001773',
              disclosure: '2015 年证金出资 2000 亿设立（各 400 亿）；2018Q3 已赎回 99%+ 并股债清仓，其后全部清盘，不再纳入跟踪',
              note: '历史主体，仅作背景参考',
            },
            {
              name: '社保基金（组合 10x/11x 等编号）', daily: false,
              channel: '通过社保基金组合委托公募管理，持有 A 股个股',
              disclosure: '仅季报十大股东披露，无法日度监测；露面时会在减持/增持榜单 holder 字段标注「社保 XX 组合」',
              note: '长线配置型资金，偏价值与高股息',
            },
          ].map((s) => (
            <div key={s.name} className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${
              s.defunct ? 'border-slate-100 bg-slate-50/60' :
              s.daily ? 'border-red-100 bg-red-50/40' : 'border-amber-100 bg-amber-50/40'
            }`}>
              <Badge className={`text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 ${
                s.defunct ? 'bg-slate-300 text-white' :
                s.daily ? 'bg-red-500 text-white' : 'bg-amber-400 text-white'
              }`}>
                {s.defunct ? '已清盘' : s.daily ? '日度监测' : '季报口径'}
              </Badge>
              <div className="min-w-0 flex-1">
                <p className={`text-xs font-bold ${s.defunct ? 'text-slate-400' : 'text-slate-800'}`}>{s.name}</p>
                <p className="text-[11px] text-slate-500 leading-snug mt-0.5">{s.channel}</p>
                <p className="text-[11px] text-slate-500 leading-snug">{s.disclosure}</p>
                <p className="text-[10px] text-slate-400 leading-snug">{s.note}</p>
              </div>
            </div>
          ))}
          <p className="text-[10px] text-slate-400 pt-1">
            另有外管局旗下 3 个投资平台（梧桐树/凤山/坤藤），规模较小、增减持幅度不大，同为季报口径。
            口径来源：华泰睿思《25Q1 长线资金持仓透视》（2025-06，国家队四来源划分、4.3 万亿规模与清盘结论）；5 只救市基金清盘进程见中证网/中国证券报 2018-10 报道。
          </p>
        </CardContent>
      </Card>

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

      {/* ====== 宽基ETF份额监控 ====== */}
      {data.nationalETFWatch && data.nationalETFWatch.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Activity className="w-5 h-5 text-red-600" />
              宽基ETF份额监控（截至 {data.nationalETFWatch.trade_date}）
            </CardTitle>
            <CardDescription>
              份额变动×成交均价估算，用于跟踪大资金（含国家队）宽基ETF申赎动向，仅供参考
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[760px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">名称</TableHead>
                    <TableHead className="text-xs">代码</TableHead>
                    <TableHead className="text-xs text-right">最新份额(亿)</TableHead>
                    <TableHead className="text-xs text-right">前一日份额(亿)</TableHead>
                    <TableHead className="text-xs text-right">份额变动(亿)</TableHead>
                    <TableHead className="text-xs text-right">均价(元)</TableHead>
                    <TableHead className="text-xs text-right">净流入(亿)</TableHead>
                    <TableHead className="text-xs text-right">5日份额变动(亿)</TableHead>
                    <TableHead className="text-xs text-right">5日净流入(亿)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.nationalETFWatch.items.map((e) => (
                    <TableRow key={e.code} className="hover:bg-slate-50">
                      <TableCell className="text-xs font-semibold whitespace-nowrap">{e.name}</TableCell>
                      <TableCell className="text-xs text-slate-400">{e.code.split('.')[0]}</TableCell>
                      <TableCell className="text-xs text-right">{e.share.toFixed(2)}</TableCell>
                      <TableCell className="text-xs text-right text-slate-500">{e.prevShare.toFixed(2)}</TableCell>
                      <TableCell className={`text-xs text-right font-semibold ${e.shareChg >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.shareChg >= 0 ? '+' : ''}{e.shareChg.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-xs text-right">{e.avgPrice.toFixed(3)}</TableCell>
                      <TableCell className={`text-xs text-right font-bold ${e.netFlow >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.netFlow >= 0 ? '+' : ''}{e.netFlow.toFixed(2)}
                      </TableCell>
                      <TableCell className={`text-xs text-right font-semibold ${e.shareChg5d >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.shareChg5d >= 0 ? '+' : ''}{e.shareChg5d.toFixed(2)}
                      </TableCell>
                      <TableCell className={`text-xs text-right font-bold ${e.netFlow5d >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {e.netFlow5d >= 0 ? '+' : ''}{e.netFlow5d.toFixed(2)}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="bg-slate-100 font-bold">
                    <TableCell className="text-xs" colSpan={4}>合计</TableCell>
                    <TableCell className={`text-xs text-right font-bold ${data.nationalETFWatch.total.shareChg >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {data.nationalETFWatch.total.shareChg >= 0 ? '+' : ''}{data.nationalETFWatch.total.shareChg.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-xs text-right">-</TableCell>
                    <TableCell className={`text-xs text-right font-bold ${data.nationalETFWatch.total.netFlow >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {data.nationalETFWatch.total.netFlow >= 0 ? '+' : ''}{data.nationalETFWatch.total.netFlow.toFixed(2)}
                    </TableCell>
                    <TableCell className={`text-xs text-right font-bold ${data.nationalETFWatch.total.shareChg5d >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {data.nationalETFWatch.total.shareChg5d >= 0 ? '+' : ''}{data.nationalETFWatch.total.shareChg5d.toFixed(2)}
                    </TableCell>
                    <TableCell className={`text-xs text-right font-bold ${data.nationalETFWatch.total.netFlow5d >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {data.nationalETFWatch.total.netFlow5d >= 0 ? '+' : ''}{data.nationalETFWatch.total.netFlow5d.toFixed(2)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== ETF 份额雷达（宽基监测） ====== */}
      {data.etfShareRadar && data.etfShareRadar.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Radar className="w-5 h-5 text-red-600" />
                ETF份额雷达（截至 {data.etfShareRadar.trade_date}）
              </CardTitle>
              {data.etfShareRadar.alertCount > 0 && (
                <Badge className="bg-red-600 text-white text-xs">{data.etfShareRadar.alertCount} 只异动</Badge>
              )}
            </div>
            <CardDescription>{data.etfShareRadar.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[860px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">名称</TableHead>
                    <TableHead className="text-xs text-right">份额(亿)</TableHead>
                    <TableHead className="text-xs text-right">1日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-right">折算金额(亿)</TableHead>
                    <TableHead className="text-xs text-right">5日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-right">20日变化(亿份)</TableHead>
                    <TableHead className="text-xs text-center">信号</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.etfShareRadar.items.map((e, idx) => (
                    <Fragment key={e.code}>
                      {(idx === 0 || e.group !== data.etfShareRadar!.items[idx - 1].group) && (
                        <TableRow className="bg-slate-100">
                          <TableCell colSpan={7} className="text-xs font-bold text-slate-600 py-1.5">
                            {e.group === 'soe' ? '央企主题组（国新/诚通系）' : '宽基组（汇金系）'}
                          </TableCell>
                        </TableRow>
                      )}
                      <TableRow className={e.alert ? 'bg-red-50/60' : 'hover:bg-slate-50'}>
                        <TableCell className="text-xs font-semibold whitespace-nowrap">
                          {e.name}
                          <span className="text-slate-400 ml-1">{e.code.split('.')[0]}</span>
                        </TableCell>
                        <TableCell className="text-xs text-right">{e.share.toFixed(2)}</TableCell>
                        <TableCell className={`text-xs text-right font-semibold ${(e.chg1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {e.chg1 != null ? `${e.chg1 >= 0 ? '+' : ''}${e.chg1.toFixed(2)}` : '--'}
                          {e.chg1Pct != null && <span className="text-slate-400 font-normal"> ({e.chg1Pct >= 0 ? '+' : ''}{e.chg1Pct.toFixed(1)}%)</span>}
                        </TableCell>
                        <TableCell className={`text-xs text-right font-bold ${(e.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {e.amt1 != null ? `${e.amt1 >= 0 ? '+' : ''}${e.amt1.toFixed(1)}` : '--'}
                        </TableCell>
                        <TableCell className={`text-xs text-right ${(e.chg5 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {e.chg5 != null ? `${e.chg5 >= 0 ? '+' : ''}${e.chg5.toFixed(2)}` : '--'}
                        </TableCell>
                        <TableCell className={`text-xs text-right ${(e.chg20 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {e.chg20 != null ? `${e.chg20 >= 0 ? '+' : ''}${e.chg20.toFixed(2)}` : '--'}
                        </TableCell>
                        <TableCell className="text-xs text-center">
                          {e.signal === '强信号'
                            ? <Badge className="bg-red-600 text-white text-[10px]">强信号</Badge>
                            : e.signal === '关注'
                              ? <Badge className="bg-amber-100 text-amber-700 text-[10px]">关注</Badge>
                              : <span className="text-slate-300">—</span>}
                          {e.trend3 && <div className="text-[10px] text-blue-600 mt-0.5">{e.trend3}</div>}
                        </TableCell>
                      </TableRow>
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 国家队持仓轮动（宽基组 + 央企主题组） ====== */}
      {data.ntRotation && data.ntRotation.groups.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <ArrowLeftRight className="w-5 h-5 text-red-600" />
                国家队持仓轮动（截至 {data.ntRotation.trade_date}）
              </CardTitle>
              {data.ntRotation.resonance.hit && (
                <Badge className="bg-amber-500 text-white text-xs">
                  共振·疑似国家队{data.ntRotation.resonance.direction}
                </Badge>
              )}
            </div>
            <CardDescription>{data.ntRotation.note}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.ntRotation.resonance.hit && (
              <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 text-xs text-amber-800">
                <span className="font-bold">⚠ 共振信号：</span>
                {data.ntRotation.resonance.count} 只核心宽基ETF（{data.ntRotation.resonance.names.slice(0, 4).join('、')}
                {data.ntRotation.resonance.names.length > 4 ? ' 等' : ''}）同日同向{data.ntRotation.resonance.direction}，
                符合国家队批量操作的典型特征，重点关注后续 1-2 日是否延续。
              </div>
            )}
            {data.ntRotation.groups.map((g) => (
              <div key={g.key}>
                <h4 className={`text-sm font-bold mb-2 ${g.key === 'broad' ? 'text-red-800' : 'text-blue-800'}`}>
                  {g.name}
                </h4>
                <div className="overflow-x-auto">
                  <Table className="min-w-[760px]">
                    <TableHeader>
                      <TableRow className={g.key === 'broad' ? 'bg-red-50' : 'bg-blue-50'}>
                        <TableHead className="text-xs">ETF</TableHead>
                        <TableHead className="text-xs text-right">最新份额(亿)</TableHead>
                        <TableHead className="text-xs text-right">日变化</TableHead>
                        <TableHead className="text-xs text-right">5日累计</TableHead>
                        <TableHead className="text-xs text-right">金额(亿)</TableHead>
                        <TableHead className="text-xs text-center">信号</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {g.series.map((s) => (
                        <Fragment key={s.name}>
                          <TableRow className="bg-slate-50">
                            <TableCell colSpan={6} className="text-[11px] font-bold text-slate-500 py-1">
                              {s.name}
                            </TableCell>
                          </TableRow>
                          {s.items.map((r) => (
                            <TableRow key={r.code} className={r.signal ? 'bg-red-50/50' : 'hover:bg-slate-50'}>
                              <TableCell className="text-xs font-semibold whitespace-nowrap">
                                {r.name}
                                <span className="text-slate-400 ml-1">{r.code.split('.')[0]}</span>
                                {r.owner && (
                                  <div className="text-[10px] text-slate-400 font-normal">
                                    {r.owner}{r.ratio != null ? ` 持有${(r.ratio * 100).toFixed(1)}%` : ''}
                                  </div>
                                )}
                              </TableCell>
                              <TableCell className="text-xs text-right">{r.share.toFixed(2)}</TableCell>
                              <TableCell className={`text-xs text-right font-semibold ${(r.chg1Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.chg1Pct != null ? `${r.chg1Pct >= 0 ? '+' : ''}${r.chg1Pct.toFixed(1)}%` : '--'}
                                {r.chg1 != null && <span className="text-slate-400 font-normal"> ({r.chg1 >= 0 ? '+' : ''}{r.chg1.toFixed(2)})</span>}
                              </TableCell>
                              <TableCell className={`text-xs text-right ${(r.chg5Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.chg5Pct != null ? `${r.chg5Pct >= 0 ? '+' : ''}${r.chg5Pct.toFixed(1)}%` : '--'}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(r.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {r.amt1 != null ? `${r.amt1 >= 0 ? '+' : ''}${r.amt1.toFixed(1)}` : '--'}
                              </TableCell>
                              <TableCell className="text-xs text-center">
                                {r.signal === '强信号'
                                  ? <Badge className="bg-red-600 text-white text-[10px]">强信号</Badge>
                                  : r.signal === '关注'
                                    ? <Badge className="bg-amber-100 text-amber-700 text-[10px]">关注</Badge>
                                    : <span className="text-slate-300">—</span>}
                                {r.trend3 && <div className="text-[10px] text-blue-600 mt-0.5">{r.trend3}</div>}
                              </TableCell>
                            </TableRow>
                          ))}
                          {s.total && (
                            <TableRow className="bg-slate-100 font-bold">
                              <TableCell className="text-xs">{s.name}合计</TableCell>
                              <TableCell className="text-xs text-right">{s.total.share?.toFixed(2) ?? '--'}</TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.chg1Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.chg1Pct != null ? `${s.total.chg1Pct >= 0 ? '+' : ''}${s.total.chg1Pct.toFixed(1)}%` : '--'}
                                {s.total.chg1 != null && <span className="text-slate-400 font-normal"> ({s.total.chg1 >= 0 ? '+' : ''}{s.total.chg1.toFixed(2)})</span>}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.chg5Pct ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.chg5Pct != null ? `${s.total.chg5Pct >= 0 ? '+' : ''}${s.total.chg5Pct.toFixed(1)}%` : '--'}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-bold ${(s.total.amt1 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                                {s.total.amt1 != null ? `${s.total.amt1 >= 0 ? '+' : ''}${s.total.amt1.toFixed(1)}` : '--'}
                              </TableCell>
                              <TableCell className="text-xs text-center text-slate-300">—</TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ))}
            <p className="text-[10px] text-slate-400">
              央企主题组占比为 2025 年报前十持有人披露口径（证券之星F10）· 金额=份额变化×当日收盘价 · 系列合计百分比按份额加权
            </p>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基波动率说明卡（浅色版） ====== */}
      {data.indexVol && data.indexVol.items.length > 0 && (
        <Card className="bg-slate-50 border-slate-200">
          <CardContent className="p-4 space-y-3">
            <div>
              <h4 className="text-sm font-bold text-slate-800 mb-1">🌡️ 这张表量的是什么？——市场的"颠簸程度"</h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                把大盘想象成一辆车：<b>HV20 是最近 1 个月的路面颠簸度，HV60 是最近 3 个月的</b>。数字越大路越烂，坐在车里（持仓）越难受。
              </p>
              <div className="bg-white border-l-2 border-blue-400 rounded-r-lg px-3 py-2 mt-2 text-xs text-slate-600 leading-relaxed">
                <b>"近一年分位"就是排名：</b>把过去一年每个交易日的颠簸度排个队，今天站在什么位置。
                比如 <b>94% 分位</b> = 今天比过去一年 94% 的日子都颠簸，属于一年里最烂的那 6% 路况。
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-red-50 border border-red-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-red-600 mb-1">🔴 高热（分位 &gt;80%）</b>
                路面最烂的一段。不加仓、不抄底、不追热点，安全带系紧（收紧止损），等路况变好再说。
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-amber-600 mb-1">🟡 升温 / 降温途中</b>
                HV20 明显高于 HV60 = 路在变坏（升温），反过来是在变好（降温）。升温期减减速，降温期可以开始看路边的上车点。
              </div>
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2.5 text-[11px] leading-relaxed text-slate-600">
                <b className="block text-xs text-emerald-600 mb-1">🟢 低位（分位 &lt;25%）</b>
                一年里最平静的路段。平静往往是大行情前的"憋劲"期——这时去翻 VCP 栏目，若有板块🟢收缩共振，就是高质量伏击区。
              </div>
            </div>
            <div className="bg-white border border-slate-200 rounded-lg p-3 text-xs text-slate-600 leading-relaxed">
              <b>📖 读法示范（示例日期 2026-08-06）：</b>当日沪深300 HV20=27.7%（94%分位）、科创50 HV20=71.2%（97%分位）、
              创业板指 HV20=61.9%（96%分位），三个指数全是红灯——一年里最颠簸的时候。这种路况下 VCP 栏目一个收缩信号都没有是
              <b>正常且正确</b>的（车都在颠簸，不可能有"窄幅整理"）。两个栏目互相印证：该做的是等，不是动手。
              什么时候这张表转绿（分位掉到 25% 以下），再去 VCP 栏目找目标。
              <div className="text-[10px] text-slate-400 mt-1">※ 示例数值为 2026-08-06 真实数据，仅作读法示范</div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 宽基波动率（ETF VIX） ====== */}
      {data.indexVol && data.indexVol.items.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Gauge className="w-5 h-5 text-red-600" />
              宽基波动率（截至 {data.indexVol.trade_date}）
            </CardTitle>
            <CardDescription>{data.indexVol.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[720px]">
                <TableHeader>
                  <TableRow className="bg-red-50">
                    <TableHead className="text-xs">指数</TableHead>
                    <TableHead className="text-xs text-right">HV20(%)</TableHead>
                    <TableHead className="text-xs text-right">HV60(%)</TableHead>
                    <TableHead className="text-xs text-right">5日变化</TableHead>
                    <TableHead className="text-xs text-right">年分位</TableHead>
                    <TableHead className="text-xs text-right">PE TTM</TableHead>
                    <TableHead className="text-xs text-right">PE 2年分位</TableHead>
                    <TableHead className="text-xs text-center">状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.indexVol.items.map((v) => (
                    <TableRow key={v.code} className="hover:bg-slate-50">
                      <TableCell className="text-xs font-semibold">{v.name}</TableCell>
                      <TableCell className="text-xs text-right font-semibold">{v.hv20 ?? '--'}</TableCell>
                      <TableCell className="text-xs text-right text-slate-500">{v.hv60 ?? '--'}</TableCell>
                      <TableCell className={`text-xs text-right ${(v.hv20Chg5 ?? 0) >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {v.hv20Chg5 != null ? `${v.hv20Chg5 >= 0 ? '+' : ''}${v.hv20Chg5.toFixed(1)}` : '--'}
                      </TableCell>
                      <TableCell className="text-xs text-right">{v.hvPct1y != null ? `${v.hvPct1y.toFixed(0)}%` : '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.peTtm ?? '--'}</TableCell>
                      <TableCell className="text-xs text-right">{v.pePct2y != null ? `${v.pePct2y.toFixed(0)}%` : '--'}</TableCell>
                      <TableCell className="text-xs text-center">
                        <Badge className={`text-[10px] ${
                          v.status === '升温' ? 'bg-red-100 text-red-700' :
                          v.status === '降温' ? 'bg-green-100 text-green-700' :
                          'bg-slate-100 text-slate-600'
                        }`}>
                          {v.status}{v.low ? '·低位' : ''}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

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
