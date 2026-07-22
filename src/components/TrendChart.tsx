import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Area, ComposedChart
} from 'recharts';

interface TrendChartProps {
  data: Array<Record<string, string | number>>;
  lines: Array<{
    key: string;
    name: string;
    color: string;
    strokeWidth?: number;
  }>;
  height?: number;
  showArea?: boolean;
  showGrid?: boolean;
  yAxisFormatter?: (value: number) => string;
  tooltipFormatter?: (value: number, name: string) => [string, string];
  title?: string;
}

export default function TrendChart({
  data,
  lines,
  height = 220,
  showArea = false,
  showGrid = true,
  yAxisFormatter,
  tooltipFormatter,
  title,
}: TrendChartProps) {
  // Pick every Nth point to avoid overcrowding
  const sampled = data.length > 30
    ? data.filter((_, i) => i % Math.ceil(data.length / 30) === 0 || i === data.length - 1)
    : data;

  return (
    <div>
      {title && <p className="text-xs text-slate-500 mb-1">{title}</p>}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={sampled} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />}
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            interval="preserveStartEnd"
            axisLine={{ stroke: '#e2e8f0' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={yAxisFormatter}
            width={50}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
            formatter={tooltipFormatter as any}
            labelStyle={{ fontSize: 10, color: '#64748b' }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
            iconType="line"
            iconSize={10}
          />
          {lines.map((line) => (
            showArea ? (
              <Area
                key={line.key}
                type="monotone"
                dataKey={line.key}
                name={line.name}
                stroke={line.color}
                fill={line.color}
                fillOpacity={0.08}
                strokeWidth={line.strokeWidth || 2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            ) : (
              <Line
                key={line.key}
                type="monotone"
                dataKey={line.key}
                name={line.name}
                stroke={line.color}
                strokeWidth={line.strokeWidth || 2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            )
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
