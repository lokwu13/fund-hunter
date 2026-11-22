import type { PatternEpisode, PatternHistoryCoverage } from './patternEvidence';

interface PatternHistoryLabelProps {
  records?: PatternEpisode[] | null;
  coverage?: PatternHistoryCoverage | null;
}

/** 仅在再次入选且确有此前不同episode时出现；当前首次突破不伪装成历史。 */
export default function PatternHistoryLabel({ records, coverage }: PatternHistoryLabelProps) {
  if (!records?.length) return null;
  return (
    <details className="mt-1 rounded border border-slate-200 bg-slate-50/80 px-2 py-1 text-[9px] leading-relaxed text-slate-500">
      <summary className="cursor-pointer font-semibold text-slate-600">
        历史入选记录 {records.length} 条（小字证据；含明确标注的结构回放）
      </summary>
      <div className="mt-1 space-y-1.5">
        {records.map((record) => (
          <div key={record.episodeId} className="border-l-2 border-slate-200 pl-2">
            <p className="font-medium text-slate-600">
              {record.originFormalAdmission ? '当时正式入选' : '结构回放·非当时正式入选'} · {record.patternType}
            </p>
            <p>
              孕育{record.gestationStart}～{record.gestationEnd}；形态类型{record.patternType}；
              突破日{record.breakoutDate}；突破点/枢轴价{record.breakoutPoint ?? record.pivot}；
              参考高{record.referenceHigh}（{record.referenceDate || '日期未记录'}）；
              突破最高/收盘{record.breakoutHigh}/{record.breakoutClose}；满{record.exitAfterTradingDays}个交易日后退出。
            </p>
            <p className={record.originFormalAdmission ? 'text-slate-400' : 'font-semibold text-amber-700'}>
              资格边界：{record.originQualificationNote || '原资格说明缺失，不补造正式入选结论'}
            </p>
          </div>
        ))}
        <p className="border-t border-slate-200 pt-1 text-slate-400">
          覆盖边界：{coverage?.note || '历史覆盖说明缺失；未覆盖区间不伪造历史。'}
          {coverage?.sampleEnd ? ` 首批样本截止${coverage.sampleEnd}。` : ''}
          统一生命周期：突破日age=0，满10个交易日后退出。
        </p>
      </div>
    </details>
  );
}
