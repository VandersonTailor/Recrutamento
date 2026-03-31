import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowRight, RefreshCw } from 'lucide-react';
import SectionCard from '../components/ui/SectionCard';
import MetricCard from '../components/ui/MetricCard';
import Button from '../components/ui/Button';
import { apiFetch, getApiBaseUrl, isUsingMockApi } from '../services/api';
import { avatarDataUri } from '../utils/avatar';

function asNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatDateTime(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '-';
  return parsed.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatPercent(value, digits = 0) {
  const n = asNumber(value, 0);
  return `${n.toFixed(digits)}%`;
}

function toPoints(value) {
  return asNumber(value, 0) * 10;
}

function eventLabel(event) {
  const action = String(event?.action || '').toLowerCase();
  if (action === 'jobs.ranking_profile.update') return 'Perfil atualizado';
  const decision = String(event?.decision || '').toLowerCase();
  if (decision === 'approved') return 'Feedback aprovado';
  if (decision === 'rejected') return 'Feedback reprovado';
  if (decision === 'promoted') return 'Feedback promovido';
  return 'Ajuste de ranking';
}

function eventStyle(event) {
  const action = String(event?.action || '').toLowerCase();
  if (action === 'jobs.ranking_profile.update') return 'bg-brand-500/20 text-brand-100 border-brand-500/40';
  const decision = String(event?.decision || '').toLowerCase();
  if (decision === 'approved') return 'bg-emerald-500/20 text-emerald-200 border-emerald-500/40';
  if (decision === 'rejected') return 'bg-rose-500/20 text-rose-200 border-rose-500/40';
  if (decision === 'promoted') return 'bg-blue-500/20 text-blue-200 border-blue-500/40';
  return 'bg-slatewarm-800 text-slatewarm-200 border-slatewarm-600';
}

function buildChanges(beforeProfile, afterProfile) {
  if (!afterProfile) return [];
  if (!beforeProfile) {
    return ['Perfil de score definido/atualizado'];
  }
  const keys = ['cargo', 'formacao', 'cursos', 'experiencia'];
  const weightChanges = keys
    .map((key) => {
      const before = asNumber(beforeProfile?.weights?.[key], 0);
      const after = asNumber(afterProfile?.weights?.[key], 0);
      const delta = after - before;
      if (Math.abs(delta) < 0.0001) return null;
      return `${key}: ${toPoints(before).toFixed(1)} -> ${toPoints(after).toFixed(1)} pontos`;
    })
    .filter(Boolean);

  const bonusBefore = asNumber(beforeProfile?.porto_alegre_bonus, 0);
  const bonusAfter = asNumber(afterProfile?.porto_alegre_bonus, 0);
  if (Math.abs(bonusAfter - bonusBefore) > 0.0001) {
    weightChanges.push(`bônus residência: ${bonusBefore.toFixed(1)} -> ${bonusAfter.toFixed(1)}`);
  }

  const floorBefore = asNumber(beforeProfile?.minimum_signal_floor, 0);
  const floorAfter = asNumber(afterProfile?.minimum_signal_floor, 0);
  if (Math.abs(floorAfter - floorBefore) > 0.0001) {
    weightChanges.push(`piso: ${floorBefore.toFixed(1)} -> ${floorAfter.toFixed(1)}`);
  }

  return weightChanges;
}

function RankingAuditPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobIdFromUrl = searchParams.get('jobId') ?? '';

  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(jobIdFromUrl);
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState(null);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [candidateQuery, setCandidateQuery] = useState('');
  const [minScore, setMinScore] = useState('');

  const selectedJob = useMemo(
    () => jobs.find((job) => String(job.id) === String(selectedJobId)) ?? null,
    [jobs, selectedJobId]
  );

  const averageScore = useMemo(() => {
    const items = audit?.ranking_snapshot ?? [];
    if (!items.length) return 0;
    const total = items.reduce((sum, item) => sum + asNumber(item.match_percent, 0), 0);
    return total / items.length;
  }, [audit]);

  const averageRoleConfidence = useMemo(() => {
    const items = audit?.ranking_snapshot ?? [];
    const withConfidence = items.filter((item) => typeof item.role_confidence === 'number');
    if (!withConfidence.length) return 0;
    const total = withConfidence.reduce((sum, item) => sum + asNumber(item.role_confidence, 0), 0);
    return (total / withConfidence.length) * 100;
  }, [audit]);

  const loadJobs = async () => {
    setLoadingJobs(true);
    setError(null);
    try {
      const result = await apiFetch('/jobs');
      setJobs(result ?? []);
      if (!selectedJobId && result?.length) {
        const firstId = String(result[0].id);
        setSelectedJobId(firstId);
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.set('jobId', firstId);
          return next;
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingJobs(false);
    }
  };

  const buildAuditParams = () => {
    const params = new URLSearchParams();
    if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
    if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);
    if (candidateQuery.trim()) params.set('q', candidateQuery.trim());
    if (minScore.trim()) params.set('min_score', minScore.trim());
    params.set('limit_events', '200');
    params.set('snapshot_limit', '200');
    return params;
  };

  const loadAudit = async (jobId) => {
    if (!jobId) return;
    setLoadingAudit(true);
    setError(null);
    try {
      const params = buildAuditParams();
      const result = await apiFetch(`/jobs/${jobId}/ranking/audit?${params.toString()}`);
      setAudit(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setAudit(null);
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  useEffect(() => {
    if (!selectedJobId) return;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('jobId', String(selectedJobId));
      return next;
    });
    loadAudit(selectedJobId);
  }, [selectedJobId]);

  const exportBaseUrl = useMemo(() => {
    if (!selectedJobId) return null;
    if (isUsingMockApi()) return null;
    const apiBase = getApiBaseUrl();
    if (!apiBase) return null;
    const base = apiBase.replace(/\/$/, '');
    const params = buildAuditParams();
    return `${base}/jobs/${selectedJobId}/ranking/audit/export?${params.toString()}`;
  }, [selectedJobId, dateFrom, dateTo, candidateQuery, minScore]);

  return (
    <div className="space-y-5">
      {error ? <div className="card-surface p-4 text-sm text-rose-200">Erro: {error}</div> : null}

      <SectionCard title="Auditoria de Ranking" subtitle="Perfil de score vigente, histórico de ajustes e snapshot operacional da vaga">
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <select
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
            disabled={loadingJobs || !jobs.length}
          >
            {!jobs.length ? <option value="">{loadingJobs ? 'Carregando vagas...' : 'Sem vagas'}</option> : null}
            {jobs.map((job) => (
              <option key={job.id} value={String(job.id)}>
                #{job.id} - {job.title}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => loadAudit(selectedJobId)} disabled={!selectedJobId || loadingAudit}>
            <RefreshCw size={16} className="mr-2" />
            Atualizar
          </Button>
          <Button variant="outline" onClick={loadJobs} disabled={loadingJobs}>
            Recarregar vagas
          </Button>
        </div>
        {selectedJob ? (
          <p className="mt-3 text-xs text-slatewarm-300">
            Vaga selecionada: <span className="font-semibold text-slatewarm-100">{selectedJob.title}</span>
            {' • '}
            {selectedJob.department ?? 'Sem departamento'}
          </p>
        ) : null}
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <input
            value={candidateQuery}
            onChange={(e) => setCandidateQuery(e.target.value)}
            placeholder="Nome do candidato (snapshot)"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
          />
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
          />
          <input
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="Score mínimo (snapshot)"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => loadAudit(selectedJobId)} disabled={!selectedJobId || loadingAudit}>
            Aplicar filtros
          </Button>
          {selectedJobId ? (
            <>
              {exportBaseUrl ? (
                <>
                  <a
                    className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs font-semibold text-slatewarm-100 hover:border-brand-400"
                    href={`${exportBaseUrl}&format=csv`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Exportar CSV
                  </a>
                  <a
                    className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs font-semibold text-slatewarm-100 hover:border-brand-400"
                    href={`${exportBaseUrl}&format=json`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Exportar JSON
                  </a>
                </>
              ) : (
                <span className="text-xs text-slatewarm-400">Exportação disponível quando API real estiver ativa.</span>
              )}
            </>
          ) : null}
        </div>
      </SectionCard>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Eventos de auditoria" value={String(audit?.feedback_events?.length ?? 0)} />
        <MetricCard label="Candidatos no snapshot" value={String(audit?.ranking_snapshot?.length ?? 0)} />
        <MetricCard label="Score médio" value={formatPercent(averageScore, 1)} />
        <MetricCard label="Confiança média do cargo" value={formatPercent(averageRoleConfidence, 1)} />
      </div>

      <SectionCard title="Perfil Atual da Vaga" subtitle="Pontuação 0-10, bônus e filtros ativos do ranking">
        {!audit ? (
          <div className="text-sm text-slatewarm-300">{loadingAudit ? 'Carregando auditoria...' : 'Selecione uma vaga para visualizar.'}</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-3">
              {Object.entries(audit?.current_profile?.weights ?? {}).map(([key, value]) => (
                <div key={key}>
                  <div className="mb-1 flex items-center justify-between text-xs text-slatewarm-300">
                    <span className="capitalize">{key}</span>
                    <span className="font-semibold text-slatewarm-100">{toPoints(value).toFixed(1)} pontos</span>
                  </div>
                  <div className="h-2 rounded-full bg-slatewarm-800">
                    <div
                      className="h-2 rounded-full bg-brand-500"
                      style={{ width: `${Math.max(0, Math.min(100, toPoints(value) * 10))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="space-y-2 text-sm text-slatewarm-200">
              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                Bônus residência: <span className="font-semibold text-slatewarm-50">{asNumber(audit?.current_profile?.porto_alegre_bonus, 0).toFixed(1)}</span>
              </div>
              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                Piso mínimo de sinal: <span className="font-semibold text-slatewarm-50">{asNumber(audit?.current_profile?.minimum_signal_floor, 0).toFixed(1)}</span>
              </div>
              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3 text-xs text-slatewarm-200">
                <div className="font-semibold text-slatewarm-50">Filtros ativos</div>
                <div className="mt-1">Cursos obrigatórios: {(audit?.current_profile?.ranking_filters?.required_courses ?? []).join(', ') || 'Nenhum'}</div>
                <div>Cidades preferidas: {(audit?.current_profile?.ranking_filters?.preferred_cities ?? []).join(', ') || 'Nenhuma'}</div>
                <div>Experiência mínima: {asNumber(audit?.current_profile?.ranking_filters?.minimum_years_experience, 0).toFixed(1)} anos</div>
                <div>Residência obrigatória: {audit?.current_profile?.ranking_filters?.residence_required ? 'Sim' : 'Não'}</div>
              </div>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Histórico de Ajustes" subtitle="Registro dos ajustes de perfil/feedback que impactaram o ranking">
        {!audit?.feedback_events?.length ? (
          <div className="text-sm text-slatewarm-300">Ainda não há eventos de ajuste para esta vaga.</div>
        ) : (
          <div className="space-y-3">
            {audit.feedback_events.map((event) => {
              const changes = buildChanges(event.before_profile, event.after_profile);
              return (
                <div key={event.id} className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${eventStyle(event)}`}>
                        {eventLabel(event)}
                      </span>
                      <span className="text-xs text-slatewarm-300">
                        {event.application_id ? `Aplicação #${event.application_id}` : 'Ajuste da vaga'}
                      </span>
                    </div>
                    <span className="text-xs text-slatewarm-400">{formatDateTime(event.created_at)}</span>
                  </div>
                  {event.note ? <div className="mt-2 text-xs text-slatewarm-200">Observação: {event.note}</div> : null}
                  {changes.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {changes.map((change) => (
                        <span key={change} className="rounded-full border border-slatewarm-600 bg-slatewarm-800 px-2.5 py-1 text-[11px] text-slatewarm-200">
                          {change}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] text-slatewarm-400">Sem alteração numérica detectada no perfil.</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Snapshot Atual do Ranking" subtitle="Visão operacional de quem está no topo após os últimos ajustes">
        {!audit?.ranking_snapshot?.length ? (
          <div className="text-sm text-slatewarm-300">Sem candidatos no snapshot atual.</div>
        ) : (
          <div className="space-y-3">
            {audit.ranking_snapshot.map((item) => (
              <div key={item.application_id ?? item.candidate_id} className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <img src={avatarDataUri(item.candidate_name)} alt={item.candidate_name} className="h-10 w-10 rounded-full border border-slatewarm-700" />
                    <div>
                      <div className="text-sm font-semibold text-slatewarm-50">{item.candidate_name}</div>
                      <div className="text-xs text-slatewarm-300">
                        Rank #{item.rank_position ?? '-'} <ArrowRight size={12} className="mx-1 inline" /> {formatPercent(item.match_percent, 0)}
                        {typeof item.role_confidence === 'number' ? ` • conf. cargo ${formatPercent(item.role_confidence * 100, 0)}` : ''}
                      </div>
                      {item.rank_reason ? <div className="text-[11px] text-slatewarm-400">{item.rank_reason}</div> : null}
                    </div>
                  </div>
                  <div className="text-xs text-slatewarm-300">{item.primary_role ?? 'Cargo não inferido'}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}

export default RankingAuditPage;
