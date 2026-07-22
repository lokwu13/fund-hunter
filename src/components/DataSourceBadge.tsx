import { Badge } from '@/components/ui/badge';
import { useFundData } from '@/hooks/useFundData';

interface DataSourceBadgeProps {
  dataKey: string;
  showDetail?: boolean;
}

const freqColors: Record<string, string> = {
  '实时': 'bg-red-100 text-red-700',
  '日更': 'bg-emerald-100 text-emerald-700',
  '周更': 'bg-blue-100 text-blue-700',
  '季更': 'bg-amber-100 text-amber-700',
  '季更+周更': 'bg-orange-100 text-orange-700',
  '事件驱动': 'bg-purple-100 text-purple-700',
};

export function DataSourceBadge({ dataKey, showDetail = false }: DataSourceBadgeProps) {
  const { data } = useFundData();
  const ds = data.dataSources?.[dataKey];

  if (!ds) return null;

  const colorClass = freqColors[ds.freq] || 'bg-slate-100 text-slate-600';

  if (showDetail) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <Badge className={`text-[10px] ${colorClass}`}>
          {ds.freq}
        </Badge>
        <span className="text-[10px] text-slate-400">
          {ds.source} · 更新于 {ds.lastUpdate}
        </span>
      </div>
    );
  }

  return (
    <Badge variant="outline" className={`text-[10px] ${colorClass}`}>
      {ds.freq}
    </Badge>
  );
}

export function DataSourceFooter({ dataKey }: { dataKey: string }) {
  const { data } = useFundData();
  const ds = data.dataSources?.[dataKey];

  if (!ds) return null;

  return (
    <p className="text-[10px] text-slate-400 mt-2">
      数据来源: {ds.source} · 更新频率: {ds.freq} · 最后更新: {ds.lastUpdate}
      {ds.note ? ` · ${ds.note}` : ''}
    </p>
  );
}
