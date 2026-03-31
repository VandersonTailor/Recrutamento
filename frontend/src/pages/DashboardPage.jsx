import { useEffect, useMemo, useState } from 'react';
import { BriefcaseBusiness, CircleCheck, Clock3, UserCheck, UserRoundX, Users } from 'lucide-react';
import MetricCard from '../components/ui/MetricCard';
import SectionCard from '../components/ui/SectionCard';
import AreaResumeChart from '../components/charts/AreaResumeChart';
import BarJobsChart from '../components/charts/BarJobsChart';
import CandidateMiniCard from '../components/candidates/CandidateMiniCard';
import { apiFetch } from '../services/api';
import { avatarDataUri } from '../utils/avatar';

function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [apps, setApps] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    Promise.all([apiFetch('/dashboard'), apiFetch('/dashboard/diagnostics'), apiFetch('/applications')])
      .then(([d, diag, a]) => {
        setStats(d);
        setDiagnostics(diag);
        setApps(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const byStage = useMemo(() => {
    const out = {};
    for (const row of stats?.applications_by_stage ?? []) out[row.stage] = row.count;
    return out;
  }, [stats]);

  const topCandidates = useMemo(() => {
    return apps
      .slice()
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, 5)
      .map((a) => ({
        id: a.candidate_id,
        name: a.candidate_name,
        job: a.job_title,
        level: a.seniority ?? 'Indefinido',
        score: Math.round(a.score ?? 0),
        avatar: avatarDataUri(a.candidate_name),
      }));
  }, [apps]);

  const latestEntries = useMemo(() => {
    return apps
      .slice()
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 5)
      .map((a) => ({
        id: a.candidate_id,
        name: a.candidate_name,
        job: a.job_title,
        level: a.seniority ?? 'Indefinido',
        score: Math.round(a.score ?? 0),
        avatar: avatarDataUri(a.candidate_name),
      }));
  }, [apps]);

  const metrics = useMemo(
    () => [
      { label: 'Currículos válidos', value: stats?.total_resumes ?? 0, delta: 0, icon: Users },
      { label: 'Em análise', value: byStage['Em análise'] || byStage['Em análise'.toLowerCase()] || 0, delta: 0, icon: Clock3 },
      { label: 'Entrevista', value: byStage['Entrevista'] || 0, delta: 0, icon: UserCheck },
      { label: 'Aprovados', value: byStage['Aprovado'] || 0, delta: 0, icon: CircleCheck },
      { label: 'Reprovados', value: byStage['Reprovado'] || 0, delta: 0, icon: UserRoundX },
      { label: 'Vagas ativas', value: stats?.total_open_jobs ?? 0, delta: 0, icon: BriefcaseBusiness },
    ],
    [byStage, stats]
  );

  return (
    <div className="space-y-5">
      {error && <div className="card-surface p-4 text-sm text-red-200">Erro: {error}</div>}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        <SectionCard title="Entradas por período" subtitle="Evolução semanal de recebimento de currículos">
          <AreaResumeChart data={(stats?.monthly_performance ?? []).map((m) => ({ name: m.month, total: m.approved }))} />
        </SectionCard>

        <SectionCard title="Origem dos candidatos" subtitle="Distribuição por canal de captação">
          <div className="space-y-3">
            {(stats?.resumes_by_channel ?? []).map((row) => (
              <div key={row.channel} className="rounded-lg bg-slatewarm-800 p-3">
                <p className="text-sm font-semibold text-slatewarm-50">{row.channel}</p>
                <p className="text-xs text-slatewarm-300">{row.count} candidatos</p>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Ranking rápido" subtitle="Top perfis por aderência">
          <div className="space-y-3">
            {topCandidates.map((candidate) => (
              <CandidateMiniCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </SectionCard>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
        <SectionCard title="Volume por vaga" subtitle="Comparativo entre vagas em aberto">
          <BarJobsChart data={(stats?.resumes_by_job ?? []).map((r) => ({ job: r.job_title, total: r.count }))} />
        </SectionCard>

        <SectionCard title="Últimas entradas" subtitle="Perfis recebidos recentemente">
          <div className="space-y-3">
            {latestEntries.map((candidate) => (
              <CandidateMiniCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </SectionCard>
      </section>

      <SectionCard title="SLA de revisão manual" subtitle="Indicadores operacionais da fila de revisão de currículos">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
            <div className="text-xs text-slatewarm-300">Pendentes revisão</div>
            <div className="text-lg font-semibold text-slatewarm-50">{diagnostics?.resumes_requires_manual_review ?? 0}</div>
          </div>
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
            <div className="text-xs text-slatewarm-300">SLA estourado &gt; 24h</div>
            <div className="text-lg font-semibold text-amber-200">{diagnostics?.review_pending_over_24h ?? 0}</div>
          </div>
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
            <div className="text-xs text-slatewarm-300">SLA crítico &gt; 72h</div>
            <div className="text-lg font-semibold text-red-200">{diagnostics?.review_pending_over_72h ?? 0}</div>
          </div>
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
            <div className="text-xs text-slatewarm-300">Tempo médio de resolução</div>
            <div className="text-lg font-semibold text-slatewarm-50">
              {typeof diagnostics?.avg_review_resolution_hours === 'number' ? `${diagnostics.avg_review_resolution_hours}h` : '—'}
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Funil por etapa" subtitle="Conversão real entre etapas do processo seletivo">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slatewarm-300">
              <tr>
                <th className="py-2 pr-3">Etapa</th>
                <th className="py-2 pr-3">Entradas</th>
                <th className="py-2 pr-3">Avanços</th>
                <th className="py-2 pr-3">Conversão</th>
                <th className="py-2 pr-3">Drop-off</th>
                <th className="py-2 pr-3">Banco talentos</th>
                <th className="py-2 pr-3">Tempo médio</th>
              </tr>
            </thead>
            <tbody>
              {(stats?.funnel_by_stage ?? []).map((row) => (
                <tr key={row.stage} className="border-t border-slatewarm-800 text-slatewarm-100">
                  <td className="py-2 pr-3 font-semibold">{row.stage}</td>
                  <td className="py-2 pr-3">{row.entered}</td>
                  <td className="py-2 pr-3">{row.advanced}</td>
                  <td className="py-2 pr-3">{row.conversion_rate}%</td>
                  <td className="py-2 pr-3 text-red-200">{row.dropoff_rate}%</td>
                  <td className="py-2 pr-3 text-amber-200">{row.talent_pool_rate}%</td>
                  <td className="py-2 pr-3">{typeof row.avg_time_to_next_hours === 'number' ? `${row.avg_time_to_next_hours}h` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

export default DashboardPage;
