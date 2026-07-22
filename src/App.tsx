import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  Activity, Building2, Globe,
  Landmark, Clock, AlertCircle, RefreshCw,
  BarChart3, Target, Wifi, WifiOff,
  Banknote, Wrench
} from 'lucide-react';
import { useFundData } from './hooks/useFundData';

// Section imports
import WeeklySummary from './sections/WeeklySummary';
import SectorHeatmap from './sections/SectorHeatmap';
import NationalTeamPanel from './sections/NationalTeamPanel';
import PublicFundPanel from './sections/PublicFundPanel';
import ForeignCapitalPanel from './sections/ForeignCapitalPanel';
import FundFlowTable from './sections/FundFlowTable';
import BondsPanel from './sections/BondsPanel';
import ECIPanel from './sections/ECIPanel';
// import NationalTeamPanel from './sections/NationalTeamPanel';
// import PublicFundPanel from './sections/PublicFundPanel';
// import ForeignCapitalPanel from './sections/ForeignCapitalPanel';
// import FundFlowTable from './sections/FundFlowTable';
// import BondsPanel from './sections/BondsPanel';
// import ECIPanel from './sections/ECIPanel';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const { data, isLoading, error, lastUpdate, refresh } = useFundData();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center shadow-lg">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-700 to-teal-600 bg-clip-text text-transparent">
                资金猎人
              </h1>
              <p className="text-xs text-slate-500">A股 · 港股 · 板块资金监测 v25</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isLoading ? (
              <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200 animate-pulse">
                <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                更新中...
              </Badge>
            ) : error ? (
              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200 cursor-pointer" onClick={refresh}>
                <WifiOff className="w-3 h-3 mr-1" />
                {error}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-200">
                <Wifi className="w-3 h-3 mr-1" />
                每日更新
              </Badge>
            )}
            {lastUpdate && (
              <Badge variant="outline" className="text-xs bg-slate-50 text-slate-600 border-slate-200">
                <Clock className="w-3 h-3 mr-1" />
                数据截止: {lastUpdate}
              </Badge>
            )}
            <button onClick={refresh} disabled={isLoading} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50">
              <RefreshCw className={`w-4 h-4 text-slate-500 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
              <AlertCircle className="w-3 h-3 mr-1" />
              仅供参考
            </Badge>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid grid-cols-7 w-full max-w-5xl mx-auto bg-white shadow-sm border border-slate-200 p-1 rounded-xl">
            <TabsTrigger value="dashboard" className="rounded-lg data-[state=active]:bg-emerald-500 data-[state=active]:text-white text-xs">
              <BarChart3 className="w-3.5 h-3.5 mr-1" />总览
            </TabsTrigger>
            <TabsTrigger value="national" className="rounded-lg data-[state=active]:bg-red-600 data-[state=active]:text-white text-xs">
              <Landmark className="w-3.5 h-3.5 mr-1" />国家队
            </TabsTrigger>
            <TabsTrigger value="public" className="rounded-lg data-[state=active]:bg-blue-600 data-[state=active]:text-white text-xs">
              <Building2 className="w-3.5 h-3.5 mr-1" />基金
            </TabsTrigger>
            <TabsTrigger value="foreign" className="rounded-lg data-[state=active]:bg-violet-600 data-[state=active]:text-white text-xs">
              <Globe className="w-3.5 h-3.5 mr-1" />外资
            </TabsTrigger>
            <TabsTrigger value="sectors" className="rounded-lg data-[state=active]:bg-orange-600 data-[state=active]:text-white text-xs">
              <Target className="w-3.5 h-3.5 mr-1" />板块
            </TabsTrigger>
            <TabsTrigger value="bonds" className="rounded-lg data-[state=active]:bg-emerald-700 data-[state=active]:text-white text-xs">
              <Banknote className="w-3.5 h-3.5 mr-1" />债券
            </TabsTrigger>
            <TabsTrigger value="tools" className="rounded-lg data-[state=active]:bg-cyan-600 data-[state=active]:text-white text-xs">
              <Wrench className="w-3.5 h-3.5 mr-1" />工具
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard" className="space-y-6">
            <WeeklySummary />
            <SectorHeatmap />
          </TabsContent>

          <TabsContent value="national" className="space-y-6">
            <NationalTeamPanel />
          </TabsContent>

          <TabsContent value="public" className="space-y-6">
            <PublicFundPanel />
          </TabsContent>

          <TabsContent value="foreign" className="space-y-6">
            <ForeignCapitalPanel />
            <FundFlowTable detailed />
          </TabsContent>

          <TabsContent value="sectors" className="space-y-6">
            <SectorHeatmap detailed />
          </TabsContent>

          <TabsContent value="bonds" className="space-y-6">
            <BondsPanel />
          </TabsContent>

          <TabsContent value="tools" className="space-y-6">
            <ECIPanel data={data} />
          </TabsContent>
        </Tabs>
      </main>

      <footer className="border-t border-slate-200 bg-white mt-8">
        <div className="max-w-7xl mx-auto px-4 py-4 text-center text-xs text-slate-400">
          <p>数据来源: 东方财富 · 港交所权益披露 · Wind · 天天基金 | 仅供参考, 不构成投资建议</p>
          <p className="mt-1">数据每日更新 · 打开App自动同步最新数据 · 来源：Tushare Pro</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
