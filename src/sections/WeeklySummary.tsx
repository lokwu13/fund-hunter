import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { TrendingUp, TrendingDown, Activity, Layers, FileText, Newspaper, BarChart3, Briefcase, Eye, PieChart, ChevronRight, Crosshair } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

const GROWTH_SECTORS = new Set(['中证信息', '中证电信', '中证工业', '中证可选']);
const DEFENSIVE_SECTORS = new Set(['中证医药', '中证消费', '中证公用', '中证能源']);

interface WeeklySummaryProps {
  onNavigate?: (tab: string, anchor?: string) => void;
}

export default function WeeklySummary({ onNavigate }: WeeklySummaryProps) {
  const { data } = useFundData();
  const indices = data.indices;

  const myStocks = data.stocks || [];
  const holdStocks = myStocks.filter((s) => s.group === 'hold');
  const watchStocks = myStocks.filter((s) => s.group === 'watch');
  const myETFs = data.myETF || [];
  const sectors = data.sectorCommentary || [];

  // 融资余额分级预警：红灯=3日增量÷流通市值≥3%（脉冲）；黄灯=连续5日增持且5日增量占比≥0.5%（Tushare 融资融券口径，T+1 披露）
  const marginMap = new Map((data.marginWatch?.items || []).map((m) => [m.code, m]));
  const hasMarginAlert = (data.marginWatch?.items || []).some((m) => m.level || m.triggered);
  const marginBadge = (code?: string) => {
    const mw = code ? marginMap.get(code) : undefined;
    if (!mw) return null;
    const isAlert = mw.level ? mw.level === 'alert' : mw.triggered;
    if (isAlert) {
      return (
        <div className="mt-1">
          <Badge
            className="text-[9px] h-4 px-1.5 bg-red-500 text-white border-0 animate-pulse"
            title="红灯：3 日融资余额增量 ÷ 流通市值 ≥3%（Tushare 融资融券口径，T+1 披露）"
          >
            🔥融资3日{mw.inc3d >= 0 ? '+' : ''}{mw.inc3d}亿·占流通{mw.incPct}%
          </Badge>
        </div>
      );
    }
    if (mw.level === 'watch') {
      return (
        <div className="mt-1">
          <Badge
            className="text-[9px] h-4 px-1.5 bg-amber-400 text-white border-0"
            title={`黄灯·温和增持：连续${mw.consecutiveUpDays}个交易日增持，5日累计${(mw.inc5d ?? 0) >= 0 ? '+' : ''}${mw.inc5d ?? 0}亿（占流通市值${mw.inc5dPct}%）；连续5日增持且占比≥0.5%触发（Tushare 融资融券口径，T+1 披露）`}
          >
            ⚠融资增持{mw.consecutiveUpDays}日·{mw.inc5dPct}%
          </Badge>
        </div>
      );
    }
    return null;
  };

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
    { name: '北向资金', status: '成交额口径', trend: '官方停披净买入', color: 'violet' },
    { name: '南下资金', status: data.southbound.week > 0 ? '净流入' : '净流出', trend: data.southbound.week > 0 ? '流入' : '放缓', color: 'teal' },
    { name: '融资融券', status: '增加', trend: '活跃', color: 'orange' },
  ];

  // ====== 每日评语速览：聚合四大栏目结论 ======
  const mt = data.bondData?.marginTrading;
  const mtComment = mt?.comment || '';
  const mtTail = mtComment.includes('水温')
    ? mtComment.slice(mtComment.lastIndexOf('水温'))
    : '';
  const ntText = (data.nationalTeamComment || '').split('。').filter(Boolean)[0];
  const dualNote = data.bottomWatch?.dualConfirmNote || '';
  const act = data.actionableSectors;
  const lowVolText = data.lowVolDigest || '';
  const hasDigest = mtTail || ntText || sectors.length > 0 || dualNote || lowVolText;

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

      {/* ====== 每日评语速览（聚合四大栏目结论，点击跳来源） ====== */}
      {hasDigest && (
        <Card className="border-emerald-300 bg-gradient-to-r from-emerald-50/60 via-white to-teal-50/60 shadow-sm">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2.5">
              <Crosshair className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-800">每日评语速览</h3>
              <Badge variant="outline" className="text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200">点击跳转来源栏目</Badge>
            </div>
            <div className="space-y-1.5">
              {mtTail && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-emerald-50 transition-colors"
                  onClick={() => onNavigate?.('bonds', 'bond-margin')}
                >
                  <Badge className={`text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 ${
                    mt?.temp?.includes('暖') ? 'bg-red-500 text-white' :
                    mt?.temp?.includes('冷') ? 'bg-blue-500 text-white' : 'bg-amber-400 text-white'
                  }`}>债券水温{mt?.temp ? ` ${mt.temp}` : ''}</Badge>
                  <span className="text-xs text-slate-600 leading-snug flex-1">{mtTail}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
              {ntText && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-red-50 transition-colors"
                  onClick={() => onNavigate?.('national', 'nt-comment')}
                >
                  <Badge className="text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 bg-red-600 text-white">国家队</Badge>
                  <span className="text-xs text-slate-600 leading-snug flex-1">{ntText}。</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
              {sectors.length > 0 && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-indigo-50 transition-colors"
                  onClick={() => onNavigate?.('sectors', 'sector-commentary')}
                >
                  <Badge className="text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 bg-indigo-500 text-white">板块短评</Badge>
                  <span className="text-xs text-slate-600 leading-snug flex-1">
                    {sectors.slice(0, 3).map(s => `${s.name}：${s.comment}`).join('；')}
                    {sectors.length > 3 ? ` 等${sectors.length}条` : ''}
                  </span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
              {dualNote && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-teal-50 transition-colors"
                  onClick={() => onNavigate?.('tools', 'bottom-watch')}
                >
                  <Badge className="text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 bg-teal-500 text-white">双确认</Badge>
                  <span className="text-xs text-slate-600 leading-snug flex-1">{dualNote}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
              {lowVolText && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-cyan-50 transition-colors"
                  onClick={() => onNavigate?.('national', 'index-vol')}
                >
                  <Badge className="text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 bg-cyan-600 text-white">宽基低波</Badge>
                  <span className="text-xs text-slate-600 leading-snug flex-1">{lowVolText}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
              {act && (
                <button
                  className="w-full flex items-start gap-2 text-left rounded-lg px-2.5 py-1.5 hover:bg-orange-50 transition-colors"
                  onClick={() => onNavigate?.('tools', 'bottom-watch')}
                >
                  <Badge className="text-[10px] h-[18px] px-1.5 mt-0.5 flex-shrink-0 border-0 bg-orange-500 text-white">能投板块</Badge>
                  {act.items.length > 0 ? (
                    <span className="text-xs text-slate-600 leading-snug flex-1">
                      {act.items.slice(0, 5).map(it => `${it.sector}（${it.reasons[0] || ''}）`).join('；')}
                      {act.items.length > 5 ? ` 等${act.items.length}个` : ''}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400 leading-snug flex-1">今日无能投板块（名单为空或全部被否决）</span>
                  )}
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 mt-0.5 flex-shrink-0" />
                </button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== VCP 形态精扫（总览精简版，点击去工具栏看明细） ====== */}
      {data.vcpStocks && data.vcpStocks.items && data.vcpStocks.items.length > 0 && (
        <Card
          className="border-violet-300 shadow-sm cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => onNavigate?.('tools')}
        >
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <Activity className="w-4 h-4 text-violet-500" />
                VCP 形态精扫 · 杯柄/底部平台
              </h3>
              <Badge variant="outline" className="text-[10px] bg-violet-50 text-violet-700 border-violet-200">
                {data.vcpStocks.trade_date} · 池{data.vcpStocks.poolSize}只 · 点击看明细
              </Badge>
            </div>
            <div className="space-y-1">
              {data.vcpStocks.items.slice(0, 6).map((it) => (
                <div key={it.code} className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-violet-50/60">
                  <span className="text-xs font-semibold text-slate-800 flex-shrink-0">
                    {it.star && <span className="text-pink-500 mr-0.5">★</span>}
                    {it.name}
                  </span>
                  <Badge className={`text-[10px] h-[18px] px-1.5 border-0 flex-shrink-0 ${
                    it.pattern === '杯柄型' ? 'bg-violet-500 text-white' : 'bg-teal-500 text-white'
                  }`}>{it.pattern}</Badge>
                  <span className={`text-xs font-bold flex-shrink-0 ${
                    (it.distMain ?? 99) <= 3 ? 'text-red-500' : 'text-amber-600'
                  }`}>距枢轴{it.distMain}%</span>
                  <span className="text-[11px] text-slate-500 truncate flex-1">{it.advice}</span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-slate-400 mt-2">
              建议=水温×板块合适度，仅关注优先级参考，不构成操作建议 · 收缩型已降级不单独展示
            </p>
          </CardContent>
        </Card>
      )}

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
                    {marginBadge(s.code)}
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
                    {marginBadge(s.code)}
                  </div>
                ))}
              </div>
            </div>
          )}
          {hasMarginAlert && (
            <p className="text-[10px] text-slate-400 mt-2">预警口径：红灯=3 日融资余额增量 ÷ 流通市值 ≥3%；黄灯=连续 5 日增持且 5 日增量占比 ≥0.5%（Tushare 融资融券口径，T+1 披露）</p>
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
          {/* 备选池（纯展示，不进信号/预警） */}
          {(data.myETFAlt || []).length > 0 && (
            <div className="mt-2.5 rounded-lg border border-dashed border-amber-300 bg-amber-50/50 px-3 py-2">
              <div className="flex items-center gap-1.5 mb-1">
                <Eye className="w-3 h-3 text-amber-500" />
                <span className="text-[11px] font-semibold text-amber-700">ETF 备选（{(data.myETFAlt || []).length}）</span>
                <span className="text-[9px] text-slate-400">仅观察，不进信号</span>
              </div>
              <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
                {(data.myETFAlt || []).map((e) => (
                  <span key={e.ticker} className="text-xs text-slate-600 whitespace-nowrap" title={e.name}>
                    <span className="text-slate-400">{e.ticker}</span> {e.name}
                    <span className={`ml-1 font-semibold ${pctClass(e.changePct)}`}>{fmtPct(e.changePct)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
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
