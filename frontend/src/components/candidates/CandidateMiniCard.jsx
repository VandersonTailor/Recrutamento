import { Link } from 'react-router-dom';

function CandidateMiniCard({ candidate }) {
  return (
    <article className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3 transition hover:border-brand-400">
      <div className="flex items-center gap-3">
        <img src={candidate.avatar} alt={candidate.name} className="h-10 w-10 rounded-full border border-slatewarm-700" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slatewarm-50">{candidate.name}</p>
          <p className="truncate text-xs text-slatewarm-300">{candidate.job}</p>
        </div>
        <span className="ml-auto rounded-full bg-brand-900/30 px-2 py-1 text-xs font-semibold text-brand-100">{candidate.score}%</span>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-slatewarm-300">
        <span>{candidate.level}</span>
        <Link to={`/candidatos/${candidate.id}`} className="font-semibold text-brand-100 hover:text-brand-50">Abrir</Link>
      </div>
    </article>
  );
}

export default CandidateMiniCard;
