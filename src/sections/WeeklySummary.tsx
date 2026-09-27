import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Layers, FileText, Newspaper, BarChart3, Briefcase, Eye, PieChart } from 'lucide-react';
import { useFundData } from '@/hooks/useFundData';

const GROWTH_SECTORS = new Set(['中证信息', '中证电信', '中证工业', '中证可选']);
const DEFENSIVE_SECTORS = new Set(['中证医药', '中证消费', '中证公用', '中证能源']);

interface WeeklySummaryProps {
  onNavigate?: (tab: string, anchor?: string, highlight?: string) => void;
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

  // 个股逆行日流水徽标：近120日逆行天数（2026-09-26 改版④口径）
  const rsMap = new Map((data.stockRS?.items || []).map((r) => [r.code, r]));
  const rsBadge = (code?: string) => {
    const rs = code ? rsMap.get(code) : undefined;
    if (!rs) return null;
    const n = rs.reverseCount ?? 0;
    const flow = (rs.reverseDays || []).map((dd: any) =>
      `${dd.date} ${dd.pct >= 0 ? '+' : ''}${dd.pct}%（${dd.idxPct !== undefined && dd.secPct !== undefined ? `大盘${dd.idxPct}%/板块${dd.secPct}%` : `${dd.base}${dd.basePct}%`}）${dd.big ? `⭐放量${dd.volX}倍` : ''}${dd.ann ? '*' : ''}`
    ).join('｜');
    const cls = n >= 8 ? 'bg-emerald-500' : n >= 4 ? 'bg-teal-500' : n > 0 ? 'bg-slate-400' : 'bg-slate-300';
    return (
      <div className="mt-1">
        <Badge
          className={`text-[9px] h-4 px-1.5 ${cls} text-white border-0`}
          title={`近120日逆行${n}天（上证跌+板块跌+个股收红/平手，三条件缺一不可，收绿不算）：${flow || '无逆行日'}；⭐=大涨≥3%且放量≥2倍20日均量，*=公告日备注不剔除`}
        >
          ⚔逆行{n}天
        </Badge>
      </div>
    );
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

  // 五路资金态度条（fundSources）已于 2026-09-27 按用户指令删除

  // ====== 五步漏斗（2026-09-27 重构：速览/双轴/VCP/排雷四卡已并入漏斗；此处仅保留漏斗仍用的变量） ======
  const mw = data.mineWatch;
  const axes = data.dualAxes;
  const shortSectors = axes?.short?.sectors ?? [];
  const shortConcepts = axes?.short?.concepts ?? [];

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

      {/* ====== 五步漏斗（2026-09-27 用户正式指令重构：0窗口→1宽基→2板块→3个股→4排雷） ====== */}
      {(() => {
        const fn = data.funnel;
        const lampColor = (l?: string) =>
          l === '🟢' ? 'bg-emerald-500' : l === '🔴' ? 'bg-red-500' : 'bg-amber-400';
        const lampBorder = (l?: string) =>
          l === '🟢' ? 'border-emerald-300' : l === '🔴' ? 'border-red-300' : 'border-amber-300';
        const winClosed = fn?.window === 'closed';
        if (!fn || !fn.steps) {
          return (
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-4">
                <p className="text-xs text-slate-400">五步漏斗数据积累中（等待晚间数据任务生成 funnel 块）</p>
              </CardContent>
            </Card>
          );
        }
        const navFor = (key: string) =>
          key === 'window' ? () => onNavigate?.('bonds', 'bond-margin')
          : key === 'broad' ? () => onNavigate?.('national')
          : key === 'sector' ? () => onNavigate?.('tools', 'bottom-watch')
          : key === 'vcp' ? () => onNavigate?.('tools')
          : undefined;
        return (
          <div>
            {/* 当日路径总结（点击跳对应步骤） */}
            <div className="mb-3 rounded-lg border border-indigo-200 bg-gradient-to-r from-indigo-50/70 via-white to-emerald-50/60 px-3 py-2 shadow-sm">
              <p className="text-[10px] text-slate-400 mb-1">当日路径 · 点击跳步骤 · {fn.trade_date}</p>
              <div className="flex items-center gap-1 flex-wrap">
                {fn.steps.map((st, i) => (
                  <span key={st.key} className="flex items-center gap-1">
                    {i > 0 && <span className="text-slate-300 text-xs">→</span>}
                    <button
                      className={`text-[11px] font-semibold rounded-full px-2 py-0.5 border ${lampBorder(st.lamp)} bg-white hover:bg-indigo-50 transition-colors`}
                      onClick={() => document.getElementById(`funnel-step-${st.n}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                    >
                      {st.lamp} {st.title}
                    </button>
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-slate-600 mt-1 font-medium">{fn.path}</p>
            </div>

            {/* 五步卡片（编号圆点+竖线串联） */}
            <div className="space-y-3">
              {fn.steps.map((st) => (
                <div key={st.key} id={`funnel-step-${st.n}`} className="relative pl-10 scroll-mt-20">
                  {st.n < 4 && <div className="absolute left-[19px] top-9 -bottom-3 w-0.5 bg-slate-200" />}
                  <div className={`absolute left-2 top-3 w-6 h-6 rounded-full flex items-center justify-center text-[12px] font-bold text-white shadow-sm ${lampColor(st.lamp)}`}>
                    {st.n}
                  </div>
                  <Card
                    className={`${lampBorder(st.lamp)} shadow-sm ${winClosed && st.n > 0 ? 'opacity-60 grayscale' : ''} ${navFor(st.key) ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`}
                    onClick={navFor(st.key)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <span className="text-base leading-none">{st.lamp}</span>
                        <Badge className={`text-[10px] h-[18px] px-1.5 border-0 text-white ${lampColor(st.lamp)}`}>第{st.n}步</Badge>
                        <h3 className="text-sm font-bold text-slate-800">{st.title}</h3>
                        <span className="text-xs font-semibold text-slate-600">{st.conclusion}</span>
                        {winClosed && st.n > 0 && (
                          <Badge className="text-[9px] h-4 px-1.5 border-0 bg-slate-400 text-white">窗口未开·信号仅观察</Badge>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 mb-2">{st.guide}</p>

                      {/* 第0步：窗口判定依据 */}
                      {st.key === 'window' && (
                        <p className="text-[11px] text-slate-500 bg-slate-50 rounded-lg px-2.5 py-1.5">{st.reason}</p>
                      )}

                      {/* 第1步：宽基四态 + ETF 买点 */}
                      {st.key === 'broad' && (
                        <div className="space-y-1">
                          {(st.rows || []).map((r) => (
                            <div key={r.indexCode} className="flex items-center gap-2 flex-wrap rounded-lg px-2 py-1 hover:bg-indigo-50/50">
                              <span className="text-xs font-semibold text-slate-800 flex-shrink-0">{r.indexName}</span>
                              <span className="text-[10px] text-slate-400 flex-shrink-0">{(r.etfCode || '').split('.')[0]}</span>
                              <Badge className={`text-[9px] h-4 px-1 border-0 flex-shrink-0 ${
                                r.label4 === '阶段底部' ? 'bg-emerald-500 text-white' :
                                r.label4 === '多头排列' ? 'bg-red-500 text-white' :
                                r.label4 === '窄幅波动' ? 'bg-sky-500 text-white' :
                                r.label4 === '高位' ? 'bg-slate-500 text-white' : 'bg-slate-300 text-white'
                              }`}>{r.label4}</Badge>
                              <Badge variant="outline" className="text-[9px] h-4 px-1 border-indigo-200 text-indigo-600 flex-shrink-0">{r.state}</Badge>
                              <span className="text-[10px] text-slate-500">
                                {r.pct1y != null ? `一年分位${r.pct1y}%` : ''}{r.maAlign ? ` · ${r.maAlign}` : ''}
                                {r.pivot != null ? ` · 枢轴${r.pivot} · 距${r.distPct}% · 失效${r.invalidation}` : ''}
                              </span>
                            </div>
                          ))}
                          {(!st.rows || st.rows.length === 0) && (
                            <p className="text-xs text-slate-400 px-2">今日无合乎要求的入围</p>
                          )}
                        </div>
                      )}

                      {/* 第2步：板块生命周期分级（默认只展开积聚期+启动期） */}
                      {st.key === 'sector' && (
                        <div className="space-y-1">
                          {(st.rows || []).map((r) => (
                            <div key={r.sector} className="flex items-center gap-2 flex-wrap rounded-lg px-2 py-1 hover:bg-orange-50/60">
                              <button
                                className="text-xs font-semibold text-orange-700 flex-shrink-0 underline decoration-dotted underline-offset-2 hover:text-orange-900"
                                title="跳工具栏对应卡片并高亮该板块"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onNavigate?.('tools', r.lifecycle === '积聚期' ? 'bottom-watch' : 'sector-scan', r.sector);
                                }}
                              >{r.sector}</button>
                              <Badge className={`text-[9px] h-4 px-1 border-0 flex-shrink-0 ${
                                r.lifecycle === '积聚期' ? 'bg-teal-500 text-white' : 'bg-orange-500 text-white'
                              }`}>{r.lifecycle}</Badge>
                              {r.dual && <Badge className="text-[9px] h-4 px-1 border-0 bg-red-500 text-white flex-shrink-0">🔥双档共振</Badge>}
                              {r.pattern && (
                                <Badge className="text-[9px] h-4 px-1 border-0 bg-indigo-500 text-white flex-shrink-0" title={r.patternEvidence}>
                                  {r.pattern}·缩量{(r.volRatio ?? 0).toFixed(2)}
                                </Badge>
                              )}
                              <span className="text-[11px] text-slate-500 flex-1 min-w-[120px]">{r.reason}</span>
                              <span className="text-[11px] text-slate-600 flex-shrink-0">
                                双龙头：{(r.leaders || []).length > 0
                                  ? r.leaders.map((l: any) => `${l.mine ? '⛔' : ''}${l.name}${(l.pctChg ?? 0) >= 0 ? '+' : ''}${l.pctChg}%`).join('、')
                                  : '暂无（待数据）'}
                              </span>
                            </div>
                          ))}
                          {(!st.rows || st.rows.length === 0) && (
                            <p className="text-xs text-slate-400 px-2">今日无入选（资金流入且板块形态双达标的板块为空）</p>
                          )}
                          {(st.dropped || []).length > 0 && (
                            <p className="text-[10px] text-amber-600 px-2">
                              ⚠ 资金流入但形态卡掉：{(st.dropped || []).map((d: any) => `${d.sector}（${d.why}）`).join('；')}
                            </p>
                          )}
                          {st.collapsed && Object.keys(st.collapsed).length > 0 && (
                            <p className="text-[10px] text-slate-400 px-2 pt-1 border-t border-slate-100">
                              其余板块（折叠）：{Object.entries(st.collapsed).map(([k, v]) => `${k}${v}`).join(' · ')}（生命周期：积聚/启动/主升/高潮/退潮/半路，仅展开积聚+启动）
                            </p>
                          )}
                          {/* 短线题材轴（保留自原并联双轴短线轴，与主线独立） */}
                          {(shortSectors.length > 0 || shortConcepts.length > 0) && (
                            <div className="mt-2 pt-2 border-t border-rose-100">
                              <p className="text-[10px] font-semibold text-rose-600 px-2 mb-1">短线题材（与主线独立，需自行甄别）</p>
                              {shortSectors.map((s) => (
                                <div key={s.sector} className="flex items-center gap-2 flex-wrap rounded-lg px-2 py-1 hover:bg-rose-50/60">
                                  <span className="text-xs font-semibold text-slate-800 flex-shrink-0">{s.sector}</span>
                                  <Badge variant="outline" className="text-[9px] h-4 px-1 border-rose-200 text-rose-600 flex-shrink-0">{s.status}</Badge>
                                  <span className="text-[11px] text-slate-500">
                                    {(s.leaders || []).map((l) => `${l.mine ? '⛔' : ''}${l.name}${l.pctChg >= 0 ? '+' : ''}${l.pctChg}%`).join('、')}
                                  </span>
                                </div>
                              ))}
                              {shortConcepts.map((c) => (
                                <div key={c.name} className="flex items-center gap-2 flex-wrap rounded-lg px-2 py-1 hover:bg-rose-50/60">
                                  <span className="text-xs font-semibold text-rose-800 flex-shrink-0">{c.name}</span>
                                  <span className="text-[11px] font-bold text-red-500 flex-shrink-0">+{c.pctChange}%</span>
                                  <span className="text-[10px] text-slate-400 flex-shrink-0">市值{c.totalMvY}亿·{c.upNum}家涨</span>
                                  <span className="text-[11px] text-slate-500">
                                    {(c.leaders || []).map((l) => `${l.mine ? '⛔' : ''}${l.name}${l.pctChg >= 0 ? '+' : ''}${l.pctChg}%`).join('、')}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* 第3步：个股形态双轨（🔗共振优先 / ⭐优中选优；两轨不沾不进榜） */}
                      {st.key === 'vcp' && (() => {
                        const rows = st.rows || [];
                        const reson = rows.filter((r: any) => r.track === 'reson');
                        const cherry = rows.filter((r: any) => r.track === 'cherry');
                        const renderRow = (r: any) => (
                          <div key={r.code} className={`flex items-center gap-2 flex-wrap rounded-lg px-2 py-1 ${r.track === 'reson' ? 'bg-violet-50/70 border border-violet-200' : 'hover:bg-amber-50/50'}`}>
                            <span className="text-xs font-semibold text-slate-800 flex-shrink-0">
                              {r.star && <span className="text-pink-500 mr-0.5">★</span>}
                              {r.mine && '⛔'}
                              {r.name}
                            </span>
                            <Badge className={`text-[10px] h-[18px] px-1.5 border-0 flex-shrink-0 ${
                              r.pattern === '杯柄型' ? 'bg-violet-500 text-white' :
                              r.pattern === 'VCP收缩型' ? 'bg-orange-500 text-white' : 'bg-slate-500 text-white'
                            }`}>{r.pattern}</Badge>
                            {r.track === 'reson' ? (
                              <Badge className="text-[9px] h-4 px-1 border-0 bg-violet-600 text-white flex-shrink-0">🔗共振·{r.sector}</Badge>
                            ) : (
                              <Badge className="text-[9px] h-4 px-1 border-0 bg-amber-500 text-white flex-shrink-0"
                                     title="池内（上证50/沪深300/中证500/科创50/创业板50）+形态达标（VCP/杯柄）+聪明钱持续流入">
                                ⭐精选·主力流入{r.smartMoneyPosDays}/10日
                              </Badge>
                            )}
                            <span className={`text-xs font-bold flex-shrink-0 ${(r.distPct ?? 99) <= 3 ? 'text-red-500' : 'text-amber-600'}`}>距枢轴{r.distPct}%</span>
                            <span className="text-[10px] text-slate-500">枢轴{r.pivot} · 失效{r.invalidation}</span>
                          </div>
                        );
                        return (
                          <div className="space-y-2">
                            <div className="space-y-1">
                              <p className="text-[10px] font-semibold text-violet-700 px-2">🔗 板块共振轨（第2步入选板块的个股，赢面优先）</p>
                              {reson.length > 0 ? reson.map(renderRow) : (
                                <p className="text-xs text-slate-400 px-2">今日无共振个股（入选板块内个股形态未成型）</p>
                              )}
                            </div>
                            <div className="space-y-1 pt-1.5 border-t border-amber-100">
                              <p className="text-[10px] font-semibold text-amber-700 px-2">⭐ 优中选优轨（板块不同步但池内+形态达标+聪明钱流入，缺一不入）</p>
                              {cherry.length > 0 ? cherry.map(renderRow) : (
                                <p className="text-xs text-slate-400 px-2">今日无精选个股</p>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {/* 第4步：排雷 */}
                      {st.key === 'mine' && (
                        <div className="space-y-1.5">
                          {(st.rows || []).length > 0 ? (
                            (st.rows || []).map((m) => (
                              <div key={m.code} className="flex items-start gap-2 rounded-lg border border-red-200 bg-white/80 px-2.5 py-1.5">
                                <span className="text-xs font-bold text-red-700 flex-shrink-0 mt-0.5">⛔{m.name}</span>
                                <span className="flex gap-1 flex-shrink-0 mt-0.5">
                                  {(m.types || []).map((t: any) => (
                                    <Badge key={t} className={`text-[9px] h-4 px-1 border-0 ${
                                      t === '资金' ? 'bg-orange-500 text-white' :
                                      t === '消息' ? 'bg-rose-500 text-white' : 'bg-purple-500 text-white'
                                    }`}>{t}</Badge>
                                  ))}
                                </span>
                                <span className="text-[11px] text-slate-600 leading-snug flex-1">
                                  {(m.details || []).map((dd: any) => `${dd.detail}${dd.date ? `（${dd.date}）` : ''}`).join('；')}
                                </span>
                                <span className="text-[9px] text-slate-400 flex-shrink-0 mt-0.5">{m.src}</span>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-emerald-600 font-medium px-2">✅ 入围标的今日无雷（命中才上榜，不凑数）</p>
                          )}
                          {mw?.thresholds && <p className="text-[10px] text-slate-400">{mw.thresholds}</p>}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              ))}
            </div>
            {fn.note && <p className="text-[10px] text-slate-400 mt-2 pl-10">{fn.note}</p>}
          </div>
        );
      })()}

      {/* 细分指数点评 */}

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
                    {rsBadge(s.code)}
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
                    {rsBadge(s.code)}
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

      {/* Fund Source Cards（五路资金态度条）已于 2026-09-27 按用户指令删除；底层数据块 nationalETFWatch/northbound/southbound 等继续取数，其他栏目仍在用 */}

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
