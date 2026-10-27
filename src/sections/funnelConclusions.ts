// 五步漏斗结论全部由既有数据块派生；不新增取数，不硬配不确定的行业 ETF。
export const SECTOR_ETF_MAP: Record<string, { code: string; name: string }> = {
  煤炭: { code: '515220', name: '煤炭ETF' },
  券商: { code: '512000', name: '券商ETF' },
  证券: { code: '512000', name: '券商ETF' },
  医药: { code: '512010', name: '医药ETF' },
  医药生物: { code: '512010', name: '医药ETF' },
  军工: { code: '512660', name: '军工ETF' },
  国防军工: { code: '512660', name: '军工ETF' },
  银行: { code: '512800', name: '银行ETF' },
  酒: { code: '512690', name: '酒ETF' },
  白酒: { code: '512690', name: '酒ETF' },
  半导体: { code: '512480', name: '半导体ETF' },
};

const shortNames = (names: string[], max = 3) =>
  names.length > max ? `${names.slice(0, max).join('、')}等${names.length}项` : names.join('、');

const oversoldWait = (items: any[]) => {
  const pending = [
    items.some((r) => (r.rsi ?? 100) < 20) ? 'RSI回20上方' : '',
    items.some((r) => (r.distLower ?? 0) < 0) ? '收回下轨' : '',
    items.some((r) => !r.lowVol) ? '地量' : '',
  ].filter(Boolean);
  return pending.length > 0 ? `待${pending.join('+')}` : '待日线确认';
};

export const sectorEtfFor = (sector: string) => SECTOR_ETF_MAP[sector];

const sectorRef = (sector: string) => {
  const etf = sectorEtfFor(sector);
  return `${sector}${etf ? `→${etf.code}` : ''}`;
};

export const broadOscFor = (data: any, indexCode: string) =>
  (data.broadOsc?.items || []).find((r: any) => r.indexCode === indexCode);

function windowConclusion(data: any) {
  const lw = data.longWindow || {};
  const windowLabel = lw.windowType === 'extreme_rebound'
    ? `极端修复临时窗（最长5日·剩余${lw.remainingDays ?? '—'}日）`
    : lw.window === 'open' ? '开窗' : lw.window === 'closed' ? '关窗' : '半窗';
  const water = [
    lw.temp ? `水温${lw.temp}` : '',
    lw.verdict ? String(lw.verdict).replace(/[（）]/g, '') : '',
    typeof lw.bondY10_1m === 'number' ? `10Y ${lw.bondY10_1m >= 0 ? '+' : ''}${lw.bondY10_1m}bp` : '',
  ].filter(Boolean).join('·');
  const osc = data.broadOsc || {};
  const items = osc.items || [];
  const signals: string[] = [];
  if ((osc.sellAlerts || []).length > 0) {
    signals.push(`强硬减仓：${osc.sellAlerts.join('、')}`);
  } else {
    const topRisks = items.filter((r: any) => r.state === '顶部风险');
    if (topRisks.length > 0) {
      signals.push(`顶部风险：${topRisks.map((r: any) => r.indexName).join('、')}（不能做多）`);
    }
    if ((osc.buyWindows || []).length > 0) signals.push(`完整抄底窗口：${osc.buyWindows.join('、')}`);
    if ((osc.reboundWatch || []).length > 0) signals.push(`反弹观察：${osc.reboundWatch.join('、')}（不升档）`);
    const oversold = items.filter((r: any) => String(r.state).includes('超卖观察'));
    if (oversold.length > 0) {
      const rsis = oversold.map((r: any) => r.rsi ?? '—').join('/');
      signals.push(`${oversold.map((r: any) => r.indexName).join('、')}超卖观察（RSI${rsis}，${oversoldWait(oversold)}）`);
    }
  }
  if (lw.extremeRebound?.pendingConfirmation) {
    signals.push(`极端修复待确认：近20日超卖${(lw.extremeEvidence || []).length}个宽基，核心完整抄底未确认，不开窗`);
  }
  if (signals.length === 0) signals.push('宽基无超买超卖触发');
  const bulls = items.filter((r: any) => r.weeklyMaBull).map((r: any) => r.indexName);
  const ma = items.length > 0
    ? bulls.length === items.length ? '周线MA全多头' : bulls.length > 0 ? `周MA多头：${bulls.join('、')}` : '周线MA未多头'
    : '';
  return [windowLabel, water, ...signals, ma].filter(Boolean).join('｜');
}

function broadConclusion(data: any, step: any) {
  const rows = step.rows || [];
  const oscTriggered = rows.filter((r: any) => {
    const state = broadOscFor(data, r.indexCode)?.state;
    return state && state !== '中性';
  });
  const patternTriggered = rows.filter((r: any) => r.state && r.state !== '无形态');
  const selected = oscTriggered.length > 0 ? oscTriggered : patternTriggered;
  if (selected.length === 0) return 'ETF参考｜宽基形态与超买超卖均未触发';
  const refs = selected.map((r: any) => {
    const code = String(r.etfCode || '').split('.')[0];
    const osc = broadOscFor(data, r.indexCode);
    if (osc && osc.state !== '中性') {
      const action = String(osc.state).includes('超卖观察') ? oversoldWait([osc])
        : osc.state === '超跌反弹观察' ? '反弹观察·不升档'
        : osc.state === '完整抄底窗口' ? '日线+周线已确认'
        : osc.state;
      return `${r.indexName}${osc.state}→${code} ${action}`;
    }
    const pivot = r.pivot != null ? ` 枢轴${r.pivot}·距${r.distPct}%` : '';
    return `${r.indexName}${r.state}→${code}${pivot}`;
  });
  return `ETF参考｜${shortNames(refs, 3)}`;
}

function sectorConclusion(data: any, step: any) {
  const rows = step.rows || [];
  const green = (data.vcpWatch?.items || []).filter((r: any) => r.signal === '🟢');
  const cups = data.vcpWatch?.cupItems || [];
  const parts = [
    `入选${rows.length}${rows.length > 0 ? `：${shortNames(rows.map((r: any) => sectorRef(r.sector)))}` : ''}`,
    green.length > 0 ? `VCP强共振：${shortNames(green.map((r: any) => sectorRef(r.name)))}` : '',
    cups.length > 0
      ? `杯柄：${shortNames(cups.map((r: any) => `${sectorRef(r.name)}距枢轴${r.distPct}%${r.breakout ? '已放量' : '待放量'}`))}`
      : '',
  ].filter(Boolean);
  if (green.length === 0 && cups.length === 0) parts.push('VCP强共振/杯柄均无');
  if (rows.length === 0 && (step.dropped || []).length > 0) {
    parts.push(`量门未过：${shortNames(step.dropped.map((r: any) => r.sector))}`);
  }
  return parts.join('｜');
}

const GUIDES: Record<string, string> = {
  window: '水温/债券与 broadOsc 合并判定',
  broad: '宽基形态＋超买超卖＋ETF，只点触发项',
  sector: '主线入选＋VCP强共振＋杯柄；ETF仅用可靠映射',
  vcp: '杯柄仅紧凑展示首次信号；高股息按行业/概念近4周RSI、缩量与首次量价催化独立开门',
  mine: '入围标的资金、消息与交易风险排查',
};

export interface FunnelStepView {
  n: number;
  key: string;
  title: string;
  lamp: string;
  conclusion: string;
  guide: string;
  reason?: string;
  rows?: any[];
  dropped?: any[];
  [key: string]: any;
}

export function buildFunnelStepViews(data: any): FunnelStepView[] {
  return (data.funnel?.steps || []).map((step: any) => {
    let conclusion = step.conclusion;
    if (step.key === 'window') conclusion = windowConclusion(data);
    else if (step.key === 'broad') conclusion = broadConclusion(data, step);
    else if (step.key === 'sector') conclusion = sectorConclusion(data, step);
    else if (step.key === 'vcp') {
      const rows = step.rows || [];
      const count = (track: string) => rows.filter((r: any) => r.track === track).length;
      const dw = data.dividendWatch;
      const dividendText = dw?.visible
        ? `高股息防御${dw.count || 0}只（${dw.catalystGroupCount || 0}个催化组）`
        : `高股息未展示（行业/概念首次催化${dw?.catalystGroupCount ?? 0}组）`;
      conclusion = `形态${rows.length}只｜共振${count('reson')}·精选${count('cherry')}·储备${count('reserve')}｜${dividendText}`;
    }
    return { ...step, conclusion, guide: GUIDES[step.key] || step.guide };
  });
}
