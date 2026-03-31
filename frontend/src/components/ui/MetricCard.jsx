import { ArrowDown, ArrowUp } from 'lucide-react';

function MetricCard({ label, value, delta, icon: Icon }) {
  const showDelta = typeof delta === 'number' && delta !== 0;
  const positive = typeof delta === 'number' ? delta >= 0 : true;
  return (
    <article className="card-surface p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slatewarm-300">{label}</p>
          <p className="mt-2 text-2xl font-bold text-slatewarm-50">{value}</p>
          {showDelta ? (
            <p className={`mt-2 inline-flex items-center gap-1 text-xs font-semibold ${positive ? 'text-emerald-300' : 'text-rose-300'}`}>
              {positive ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {Math.abs(delta)}% vs período anterior
            </p>
          ) : null}
        </div>
        {Icon && (
          <div className="rounded-xl bg-brand-900/20 p-2 text-brand-100">
            <Icon size={20} />
          </div>
        )}
      </div>
    </article>
  );
}

export default MetricCard;
