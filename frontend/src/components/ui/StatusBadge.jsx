import { stageColorMap } from '../../utils/format';

function StatusBadge({ stage }) {
  const style = stageColorMap[stage] || 'bg-slatewarm-100 text-slatewarm-700';
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}>{stage}</span>;
}

export default StatusBadge;
