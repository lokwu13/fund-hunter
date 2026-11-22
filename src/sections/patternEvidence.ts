export interface PatternEvidence {
  type?: string;
  days?: number;
  weeks?: number;
  amplitude?: number;
  drift?: number;
  volRatio?: number;
  trendSlopePct?: number;
  ma20?: number;
  ma20Previous?: number;
  ma60?: number;
  intervalNetInflow?: number | null;
  moneyflowCoveragePct?: number;
  moneyflowCoveredDays?: number;
  moneyflowDays?: number;
  moneyflowPass?: boolean;
  valuationPass?: boolean;
  valuationBasis?: 'dual' | 'single' | 'insufficient';
  valuationScorePct?: number | null;
  weeklyStructureLabel?: string;
  valuationMetrics?: Array<{
    metric: 'peTtm' | 'pb';
    percentile: number | null;
    samples: number;
    sufficient: boolean;
  }>;
  patternReasons?: string[];
  displayEligible?: boolean;
  bottomShape?: boolean;
  bottomPattern?: '底部整理';
  shapeRecognized?: boolean;
  formalAdmission?: boolean;
  qualificationStatus?: 'eligible' | 'pending' | 'excluded';
  qualificationLabel?: string;
}

const FORMAL_PATTERNS = new Set(['平台整理', '长平台整理', '底部整理']);

export interface VcpDailyTrendEvidence {
  close: number | null;
  ma50: number | null;
  ma150: number | null;
  ma200: number | null;
  samples: number;
  closeAboveMA50: boolean;
  bullish: boolean;
  bullishStatus: 'strict_bullish' | 'not_strict_bullish' | 'insufficient_samples';
  pass: boolean;
  reasons: string[];
  asOf: string | null;
  source: 'daily';
}

export interface VcpGestationEvidence {
  pass: boolean;
  status: 'pass' | 'premature_new_high' | 'insufficient_samples';
  startDate: string;
  endDate: string;
  referenceHigh: number | null;
  referenceDate: string | null;
  referenceSamples: number;
  referenceDays: number;
  anchorHigh?: number | null;
  prematureNewHighs?: Array<{ date: string; high: number; close: number; referenceHigh: number; finalBreakout: boolean }>;
  finalBreakout?: { date: string; high: number; close: number; referenceHigh: number; finalBreakout: true } | null;
  nearHighAllowed: true;
  sidewaysPreferred: boolean;
  sidewaysPreferenceOnly: true;
  sidewaysDriftPct: number | null;
  sidewaysScore: number;
  sidewaysLabel: string;
  rejectReasons: string[];
}

export interface PatternEpisode {
  episodeId: string;
  code: string;
  name: string;
  patternType: string;
  structurePath?: string | null;
  gestationStart: string;
  gestationEnd: string;
  pivot: number;
  breakoutPoint: number;
  referenceHigh: number;
  referenceDate?: string | null;
  breakoutDate: string;
  breakoutHigh: number;
  breakoutClose: number;
  breakoutVolume?: number;
  breakoutDefinition?: string;
  exitAfterTradingDays: 10;
  originFormalAdmission: boolean;
  originQualificationNote: string;
  sidewaysLabel?: string | null;
  sidewaysScore?: number | null;
  dailyTrend?: VcpDailyTrendEvidence | null;
  vcpGestation?: VcpGestationEvidence | null;
}

export interface PatternHistoryCoverage {
  kind: string;
  fullMarketComplete: false;
  note: string;
  sourceFile?: string;
  sourceSha256?: string;
  sampleEnd?: string;
  originFormalAdmission?: boolean;
}

export function vcpDailyTrendText(evidence?: VcpDailyTrendEvidence | null) {
  if (!evidence) return 'VCP日线趋势证据缺失';
  const state = evidence.pass ? '通过' : '未通过';
  return `VCP日线趋势${state}（${evidence.asOf ?? '—'}·${evidence.source ?? 'daily'}）：收盘${evidence.close ?? '—'} > MA50 ${evidence.ma50 ?? '—'}；MA50 ${evidence.ma50 ?? '—'} > MA150 ${evidence.ma150 ?? '—'} > MA200 ${evidence.ma200 ?? '—'}；样本${evidence.samples}根；严格多头=${evidence.bullish ? '是' : '否'}；原因=${evidence.reasons?.join('、') || '无'}。日线收盘>MA50且MA50>MA150>MA200；VCP不限制接近新高（即接近新高允许），但孕育期内不得先于最终突破创出新高；横盘仅为优选，非完全横盘不硬排除`;
}

export function vcpGestationText(evidence?: VcpGestationEvidence | null) {
  if (!evidence) return 'VCP孕育期新高证据缺失';
  return `孕育${evidence.startDate}～${evidence.endDate}·参考高${evidence.referenceHigh ?? '—'}(${evidence.referenceDate ?? '—'})·参考样本${evidence.referenceSamples}根·${evidence.pass ? '通过' : '未通过'}·${evidence.sidewaysLabel}·提前新高${evidence.prematureNewHighs?.length ?? 0}次·原因=${evidence.rejectReasons?.join('、') || '无'}`;
}

export function completeMoneyflow(evidence?: PatternEvidence | null) {
  return !!evidence && evidence.moneyflowPass === true
    && evidence.moneyflowCoveragePct === 100
    && (evidence.intervalNetInflow ?? 0) > 0;
}

export function completeBottomEvidence(evidence?: PatternEvidence | null) {
  return completeMoneyflow(evidence) && evidence?.displayEligible === true
    && evidence.valuationPass === true && (evidence.valuationScorePct ?? 101) <= 40;
}

/** 旧缓存或缺证据对象不得在前端继续伪装成正式VCP/平台/底部；旧标签仅作快照兼容。 */
export function formalPatternDisplayable(item: {
  pattern?: string;
  patternEvidence?: PatternEvidence | null;
  vcpDailyTrend?: VcpDailyTrendEvidence | null;
  dailyTrendPass?: boolean | null;
  vcpGestation?: VcpGestationEvidence | null;
  gestationPass?: boolean | null;
}) {
  if (item.pattern === 'VCP收缩型') {
    const dailyPassed = item.vcpDailyTrend?.pass === true && item.dailyTrendPass === true;
    return dailyPassed && item.vcpGestation?.pass === true && item.gestationPass === true;
  }
  if (!item.pattern || !FORMAL_PATTERNS.has(item.pattern)) return true;
  if (!item.patternEvidence || item.patternEvidence.displayEligible !== true) return false;
  return item.pattern === '底部整理'
    ? completeBottomEvidence(item.patternEvidence)
    : completeMoneyflow(item.patternEvidence);
}

export function patternEvidenceText(evidence?: PatternEvidence | null) {
  if (!evidence) return '正式形态证据缺失，不展示平台/底部标签';
  const flow = `区间净流入${evidence.intervalNetInflow ?? '—'}亿元·覆盖${evidence.moneyflowCoveragePct ?? 0}%（${evidence.moneyflowCoveredDays ?? 0}/${evidence.moneyflowDays ?? 0}日）`;
  if (evidence.type === '底部整理') {
    const basis = evidence.valuationBasis === 'dual' ? 'PE/PB双指标均值'
      : evidence.valuationBasis === 'single' ? '单指标（另一指标不足）' : '样本不足';
    const metrics = (evidence.valuationMetrics || []).map((m) =>
      `${m.metric === 'peTtm' ? 'PE_TTM' : 'PB'}分位${m.percentile ?? '—'}%·样本${m.samples}个${m.sufficient ? '' : '（不足）'}`
    ).join('；');
    return `底部${evidence.weeks ?? '—'}周（最少12周）·${evidence.weeklyStructureLabel ?? '结构缺失'}·回归${evidence.trendSlopePct ?? '—'}%·振幅${evidence.amplitude ?? '—'}%·${flow}·估值${basis}${evidence.valuationScorePct ?? '—'}%（≤40%）·${metrics || 'PE/PB明细缺失'}`;
  }
  const platformLabel = evidence.type === '长平台整理' ? '平台整理（旧快照）' : '平台整理';
  return `${platformLabel}${evidence.days ?? '—'}日·统一振幅≤15%·平台前40日斜率${evidence.trendSlopePct ?? '—'}%·MA20 ${evidence.ma20 ?? '—'}（前窗${evidence.ma20Previous ?? '—'}）>MA60 ${evidence.ma60 ?? '—'}·振幅${evidence.amplitude ?? '—'}%·漂移${evidence.drift ?? '—'}%·平台/前20日总体量比${evidence.volRatio ?? '—'}·${flow}`;
}
