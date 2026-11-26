import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useFundData } from '@/hooks/useFundData';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function PublicFundPanel() {
  const { data } = useFundData();

  return (
    <div className="space-y-6">
      {data.fundProfitBreadth && (
        <Card id="fund-profit-breadth" data-testid="fund-profit-breadth">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base font-bold">全市场公开净值基金盈利情况</CardTitle>
              <Badge variant="outline" className="text-xs">
                {data.fundProfitBreadth.status === 'stale' ? '沿用最近完整数据' : '日更'}
              </Badge>
            </div>
            <CardDescription className="text-xs leading-5">
              {data.fundProfitBreadth.source}覆盖 {data.fundProfitBreadth.total.toLocaleString('zh-CN')} 个代码/份额 ·
              最近披露 {data.fundProfitBreadth.asOf}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
              <div className="h-48 min-w-0" role="img" aria-label="公开净值基金盈利、亏损、平盘和未披露家数柱状图">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={Object.entries(data.fundProfitBreadth.counts).map(([key, value]) => ({
                    key, count: value.count,
                    name: { profit: '盈利', loss: '亏损', flat: '平盘', missing: '未披露' }[key] || key,
                    color: { profit: '#dc2626', loss: '#059669', flat: '#64748b', missing: '#94a3b8' }[key],
                  }))} margin={{ top: 12, right: 8, bottom: 0, left: 8 }}>
                    <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 12 }} />
                    <YAxis hide domain={[0, 'auto']} />
                    <Tooltip formatter={(value) => [`${Number(value).toLocaleString('zh-CN')} 家`, '家数']} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                      {Object.entries(data.fundProfitBreadth.counts).map(([key]) => (
                        <Cell key={key} fill={{ profit: '#dc2626', loss: '#059669', flat: '#64748b', missing: '#94a3b8' }[key]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">披露日表现</TableHead>
                    <TableHead className="text-xs text-right">家数</TableHead>
                    <TableHead className="text-xs text-right">占覆盖</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {([
                    ['profit', '盈利', 'text-red-600'],
                    ['loss', '亏损', 'text-emerald-600'],
                    ['flat', '平盘', 'text-slate-600'],
                    ['missing', '未披露', 'text-slate-400'],
                  ] as const).map(([key, label, color]) => (
                    <TableRow key={key} data-breadth-row={key}>
                      <TableCell className={`text-sm font-medium ${color}`}>{label}</TableCell>
                      <TableCell className="text-sm text-right font-semibold" data-breadth-count={key}>
                        {data.fundProfitBreadth!.counts[key].count.toLocaleString('zh-CN')}
                      </TableCell>
                      <TableCell className="text-sm text-right">{data.fundProfitBreadth!.counts[key].pct.toFixed(2)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="text-xs text-slate-500 leading-5 space-y-1">
              <p>有效日增长率 {data.fundProfitBreadth.validCount.toLocaleString('zh-CN')} 家（{data.fundProfitBreadth.validPct.toFixed(2)}%） · 主披露日 {data.fundProfitBreadth.primaryDate}：{data.fundProfitBreadth.primaryDateValidCount.toLocaleString('zh-CN')} 家，占有效样本 {data.fundProfitBreadth.primaryDateValidPct.toFixed(2)}%</p>
              <p>披露日范围 {data.fundProfitBreadth.earliestDisclosureDate} 至 {data.fundProfitBreadth.asOf}，共 {data.fundProfitBreadth.disclosureDateCount} 个日期</p>
              <p>家数按公开基金代码/份额计，A/C 分开；盈利仅指该披露日增长率 &gt; 0，不代表持有至今收益；缺失不补 0。非完整法定基金名录，各基金披露日可能不同。</p>
              {data.fundProfitBreadth.status === 'stale' && <p className="text-amber-600">本次数据源异常，展示最近一次通过完整性校验的数据。</p>}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
