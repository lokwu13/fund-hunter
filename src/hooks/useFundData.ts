import { useState, useEffect, useCallback } from 'react';
import fundDataFallback from '../data/fund_data.json';

export interface WeeklyFlowItem {
  week: string;
  mainFlow: number;
  foreignFlow: number;
}

export interface ForeignHolding {
  institution: string;
  action: string;
  shares: string;
  price: string;
  date: string;
  holdingAfter: string;
}

export interface RatingChange {
  from: string;
  to: string;
  date: string;
  institution: string;
}

export interface StockItem {
  name: string;
  code: string;
  market: string;
  sector: string;
  concept: string;
  ratingChange: RatingChange | null;
  foreignHoldings: ForeignHolding[];
  weeklyFlow: WeeklyFlowItem[];
  /** 用户个股扩展字段（由 update_data.py 每日生成） */
  group?: 'hold' | 'watch';
  industry?: string;
  close?: number;
  pctChg?: number;
  vol?: number;
  watchPrice?: number;
}

export interface MyETFItem {
  ticker: string;
  name: string;
  close?: number;
  changePct?: number;
  preClose?: number;
}

export interface DivergenceItem {
  name: string;
  code: string;
  southInflow: string;
  foreignOutflow: string;
  netDivergence: string;
  concept: string;
  sector: string;
  note: string;
}

export interface Top5Item {
  name: string;
  code: string;
  inflow: string;
  concept: string;
  sector: string;
  note: string;
  holder?: string;
}

export interface ForeignInstitutionItem {
  rank: number;
  name: string;
  code: string;
  market: string;
  institution: string;
  amount: string;
  date: string;
  concept: string;
  sector: string;
  holdingChange: string;
  note: string;
}

export interface ForeignInstitutionTop10 {
  buys: ForeignInstitutionItem[];
  sells: ForeignInstitutionItem[];
}

export interface PrivateFundItem {
  rank: number;
  name: string;
  code: string;
  market: string;
  fund: string;
  amount: string;
  concept: string;
  sector: string;
  note: string;
}

export interface ConcentrationItem {
  rank: number;
  name: string;
  code: string;
  concentration: string;
  concept: string;
  sector: string;
  fundCount: string;
  note: string;
}

export interface MedicalFundItem {
  rank: number;
  name: string;
  code: string;
  amount: string;
  concept: string;
  sector: string;
  fundCount?: string;
  fund?: string;
  holder?: string;
  institution?: string;
  ratio?: string;
  note: string;
}

export interface MedicalSectorFundCategory {
  inflow: MedicalFundItem[];
  outflow: MedicalFundItem[];
}

export interface MedicalSectorFunds {
  publicFund: MedicalSectorFundCategory;
  privateFund: MedicalSectorFundCategory;
  nationalTeam: MedicalSectorFundCategory;
  foreignCapital: MedicalSectorFundCategory;
  nonMainforce: MedicalSectorFundCategory;
}

export interface FundData {
  updateTime: string;
  week: string;
  marketStatus: string;
  sectorPeriod?: string;
  indices: Record<string, { name: string; value: number; change: number }>;
  sectors: Array<{
    name: string;
    mainFlow: number;
    change?: number;
    color?: string;
    leadStock?: string;
    companyNum?: number;
    maxWeeklyFlow?: number;
    isAnomaly?: boolean;
  }>;
  stocks: StockItem[];
  northbound: { today: number; week: number; medical: number };
  southbound: { today: number; week: number; month: number };
  keySignals: Array<{ type: string; text: string }>;
  foreignSummary?: {
    totalBuys: number;
    totalSells: number;
    ratingUpgrades: number;
    ratingDowngrades: number;
    topInstitution: string;
    topSector: string;
    recentHighlight: string;
  };
  divergence_top10?: DivergenceItem[];
  top5_national?: Top5Item[];
  top5_publicfund?: Top5Item[];
  top5_foreign?: Top5Item[];
  top5_sector?: Top5Item[];
  foreignInstitution_top10?: ForeignInstitutionTop10;
  privateFund_inflow?: PrivateFundItem[];
  privateFund_outflow?: PrivateFundItem[];
  concentration_top10?: ConcentrationItem[];
  mainforce_inflow_top10?: Array<{name: string; code: string; concept: string; sector: string}>;
  mainforce_outflow_top10?: Array<{name: string; code: string; concept: string; sector: string}>;
  combined_sell_top10?: Array<{rank: number; name: string; code: string; sources: string[]; amount: string; concept: string; sector: string}>;
  auction_rebound_weekly?: {
    week: string;
    updateDate: string;
    summary: string;
    dataSourceNote: string;
    stocks: Array<{date: string; name: string; code: string; openChange: string; volumeRatio: string; amplitude: string; isST: boolean; concept: string; sector: string; note: string}>;
  };
  wash_trade_weekly?: {
    week: string;
    updateDate: string;
    summary: string;
    method: string;
    stocks: Array<{date: string; name: string; code: string; auctionLow: string; open: string; rebound: string; volumeBefore: string; volumeAfter: string; concept: string; sector: string; signal: string}>;
    pattern_analysis?: {
      total: number;
      avg_rebound: string;
      avg_volume_expand: string;
      common_sectors: string[];
      common_features: string;
    };
  };
  leverage_concentration_top10?: Array<{name: string; code: string; ratio: string; finBalance: string; concept: string; sector: string}>;
  southbound_concentration_top10?: Array<{name: string; code: string; ratio: string; concept: string; sector: string}>;
  foreign_concentration_top10?: Array<{name: string; code: string; ratio: string; institution: string; concept: string; sector: string}>;
  top10_publicfund?: Array<{rank: number; name: string; code: string; amount: string; concept: string; sector: string; note: string}>;
  publicFund_outflow_top10?: Array<{rank: number; name: string; code: string; amount: string; concept: string; sector: string; note: string}>;
  top10_foreign?: Array<{name: string; code: string; inflow: string; concept: string; sector: string; note: string}>;
  medicalSectorFunds?: MedicalSectorFunds;
  conceptSectors?: Array<{
    name: string;
    mainFlow: number;
    change?: number;
    maxWeeklyFlow?: number;
    isAnomaly?: boolean;
  }>;
  dataSources?: Record<string, {
    source: string;
    freq: string;
    lastUpdate: string;
    note: string;
  }>;
  bondData?: {
    daily: Array<{
      date: string; y2: number; y5: number; y10: number; y30: number;
      y2_chg: number; y5_chg: number; y10_chg: number; y30_chg: number;
    }>;
    curveCompare: Record<string, { date: string; y2: number; y5: number; y10: number; y30: number }>;
    stats: {
      latest: { date: string; y2: number; y5: number; y10: number; y30: number; spread: number };
      '1m_change': Record<string, number>;
      range: Record<string, { min: number; max: number }>;
    };
    us?: {
      latest: { date: string; y2: number; y5: number; y10: number; y30: number; spread: number };
      history: Array<{ date: string; y2: number; y5: number; y10: number; y30: number }>;
    };
    news?: Array<{ date: string; time?: string; title: string; source?: string }>;
    liquidityTools?: {
      updateTime: string;
      policyRate: number;
      dr001: number;
      dr007: number;
      monthlyNet: number;
      monthlyNetUnit: string;
      comment: string;
      operations: Array<{
        date: string;
        tool: string;
        amount: number;
        rate: number | null;
        matured: number;
        net: number;
      }>;
    };
    marginTrading?: {
      updateTime: string;
      totalBalance: number;
      totalBalanceUnit: string;
      finBalance: number;
      secBalance: number;
      comment: string;
      trend: string;
      daily: Array<{
        date: string;
        total: number;
        fin: number;
        sec: number;
      }>;
    };
  };
  eciData?: {
    updateTime: string;
    period: string;
    sectors: Array<{
      sector: string;
      eci: number;
      volConvergence: number;
      fundConcentration: number;
      trendSync: number;
      consistencyMomentum: number;
      activity: number;
      policy: number;
      currentCorr: number;
      predictedCorr: number;
      trend: string;
      stocks: number;
      advice: string;
      sampleStocks?: string[];
      leaders?: {
        mvLeader: { name: string; code: string; mv: string };
        gainLeader: { name: string; code: string; return: string };
        lossLeader: { name: string; code: string; return: string };
      };
    }>;
    indicators: Record<string, { name: string; weight: string; desc: string }>;
    totalIndustries?: number;
    divergentCount?: number;
  };
  nationalETF?: Array<{
    ticker: string;
    name: string;
    market: string;
    q1Note: string;
    close?: number;
    changePct?: number;
    preClose?: number;
  }>;
  myETF?: MyETFItem[];
  holdingsNews?: Array<{
    stockCode: string;
    stockName: string;
    group?: 'hold' | 'watch';
    industry?: string;
    items: Array<{
      type: string;
      date: string;
      title: string;
      content: string;
      url?: string;
    }>;
  }>;
  nationalTeamNews?: {
    updateTime: string;
    sources: string[];
    teams: Array<{
      name: string;
      role: string;
      totalValue: string;
      latestAction: string;
      trend: string;
      details: Array<{
        date: string;
        event: string;
        source: string;
      }>;
    }>;
  };
}

interface UseFundDataResult {
  data: FundData;
  isLoading: boolean;
  error: string | null;
  lastUpdate: string;
  refresh: () => void;
}

export function useFundData(): UseFundDataResult {
  const [data, setData] = useState<FundData>(fundDataFallback as unknown as FundData);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState('');

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const cacheBuster = `?t=${Date.now()}`;
      const response = await fetch(`./fund_data.json${cacheBuster}`, {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const freshData = await response.json();
      setData(freshData as FundData);
      setLastUpdate(freshData.updateTime || new Date().toLocaleString('zh-CN'));

      try {
        localStorage.setItem('fund_data_cache', JSON.stringify(freshData));
        localStorage.setItem('fund_data_cache_time', Date.now().toString());
      } catch {
        // localStorage may be unavailable
      }
    } catch (err) {
      console.warn('Failed to fetch fresh data, using fallback:', err);
      try {
        const cached = localStorage.getItem('fund_data_cache');
        if (cached) {
          const parsed = JSON.parse(cached);
          setData(parsed as FundData);
          setLastUpdate(parsed.updateTime + ' (缓存)');
          setError('已加载缓存数据，联网后自动更新');
          return;
        }
      } catch {
        // localStorage unavailable
      }
      setData(fundDataFallback as unknown as FundData);
      setLastUpdate((fundDataFallback as unknown as FundData).updateTime);
      setError('当前使用默认数据，联网后自动更新');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadData();
      }
    };
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        loadData();
      }
    }, 5 * 60 * 1000);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      clearInterval(interval);
    };
  }, [loadData]);

  return {
    data,
    isLoading,
    error,
    lastUpdate,
    refresh: loadData,
  };
}
