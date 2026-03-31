import { Link } from 'react-router-dom';
import StatusBadge from '../ui/StatusBadge';
import { formatDate } from '../../utils/format';

function CandidateTable({ candidates }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slatewarm-700 text-left text-xs uppercase tracking-wide text-slatewarm-300">
            <th className="py-3 pr-3 font-semibold">Candidato</th>
            <th className="py-3 pr-3 font-semibold">Vaga</th>
            <th className="py-3 pr-3 font-semibold">Score</th>
            <th className="py-3 pr-3 font-semibold">Nível</th>
            <th className="py-3 pr-3 font-semibold">Origem</th>
            <th className="py-3 pr-3 font-semibold">Recebido</th>
            <th className="py-3 pr-3 font-semibold">Etapa</th>
            <th className="py-3 font-semibold">Ações</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={candidate.id} className="border-b border-slatewarm-800 text-slatewarm-200">
              <td className="py-3 pr-3">
                <div className="flex items-center gap-3">
                  <img src={candidate.avatar} alt={candidate.name} className="h-9 w-9 rounded-full border border-slatewarm-700" />
                  <div>
                    <p className="font-semibold text-slatewarm-50">{candidate.name}</p>
                    <p className="text-xs text-slatewarm-300">{candidate.email || '—'}</p>
                  </div>
                </div>
              </td>
              <td className="py-3 pr-3">{candidate.job}</td>
              <td className="py-3 pr-3"><span className="font-semibold text-brand-100">{candidate.score}%</span></td>
              <td className="py-3 pr-3">{candidate.level}</td>
              <td className="py-3 pr-3">{candidate.origin}</td>
              <td className="py-3 pr-3 text-slatewarm-300">{formatDate(candidate.receivedAt)}</td>
              <td className="py-3 pr-3"><StatusBadge stage={candidate.stage} /></td>
              <td className="py-3">
                <Link to={`/candidatos/${candidate.candidateId ?? candidate.id}`} className="text-sm font-semibold text-brand-100 transition hover:text-brand-50">Ver detalhes</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default CandidateTable;
