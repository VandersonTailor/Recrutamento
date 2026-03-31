import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import SectionCard from '../components/ui/SectionCard';
import Button from '../components/ui/Button';
import { apiFetch } from '../services/api';
import { avatarDataUri } from '../utils/avatar';
import { formatDate, stageColorMap } from '../utils/format';
import { STAGE_OPTIONS } from '../utils/stages';

const columns = STAGE_OPTIONS;

function PipelinePage() {
  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState('');
  const [apps, setApps] = useState([]);
  const [sla, setSla] = useState(null);
  const [error, setError] = useState(null);
  const [busyAppId, setBusyAppId] = useState(null);
  const [stageDraft, setStageDraft] = useState({});
  const [department, setDepartment] = useState('');
  const [seniority, setSeniority] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    apiFetch('/jobs')
      .then((j) => {
        setJobs(j);
        if (j.length && !jobId) setJobId(String(j[0].id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const load = () => {
    if (!jobId) return;
    setError(null);
    const params = new URLSearchParams();
    params.set('job_id', jobId);
    if (department.trim()) params.set('department', department.trim());
    if (seniority.trim()) params.set('seniority', seniority.trim());
    if (dateFrom.trim()) params.set('date_from', dateFrom.trim());
    if (dateTo.trim()) params.set('date_to', dateTo.trim());
    Promise.all([
      apiFetch(`/applications?${params.toString()}`),
      apiFetch(`/applications/sla-alerts?job_id=${jobId}`),
    ])
      .then(([a, s]) => {
        setApps(a);
        setSla(s);
        setStageDraft(
          (a ?? []).reduce((acc, item) => {
            acc[item.id] = item.stage;
            return acc;
          }, {})
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(() => {
    load();
  }, [jobId]);

  const grouped = useMemo(() => {
    const out = {};
    for (const c of columns) out[c] = [];
    for (const a of apps) {
      const key = out[a.stage] ? a.stage : 'Recebido';
      out[key].push(a);
    }
    for (const c of columns) out[c].sort((x, y) => (y.score ?? 0) - (x.score ?? 0));
    return out;
  }, [apps]);

  const saveStage = async (appId) => {
    const toStage = stageDraft[appId];
    if (!toStage) return;
    setBusyAppId(appId);
    setError(null);
    try {
      await apiFetch(`/applications/${appId}/stage`, {
        method: 'PATCH',
        body: {
          to_stage: toStage,
          note: 'Atualizado manualmente no pipeline kanban',
        },
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyAppId(null);
    }
  };

  return (
    <div className="space-y-5">
      <SectionCard title="Pipeline Kanban" subtitle="Acompanhe a jornada de cada candidato com visão clara por etapa">
        <div className="mb-4 flex flex-wrap gap-2">
          <select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          >
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>
          <input
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            placeholder="Departamento"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
          <input
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
            placeholder="Senioridade"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
          <input
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            placeholder="De (YYYY-MM-DD)"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
          <input
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            placeholder="Até (YYYY-MM-DD)"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
          <button
            onClick={load}
            className="rounded-xl bg-brand-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600"
          >
            Filtrar
          </button>
        </div>
        {error && <div className="mb-4 text-sm text-red-200">{error}</div>}
        {sla ? (
          <div className="mb-4 grid gap-2 md:grid-cols-3">
            <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3 text-xs text-slatewarm-200">
              Em escopo SLA: <span className="font-semibold text-slatewarm-50">{sla.total_in_scope ?? 0}</span>
            </div>
            <div className="rounded-xl border border-rose-700/40 bg-rose-900/20 p-3 text-xs text-rose-100">
              Atrasados: <span className="font-semibold">{sla.overdue_count ?? 0}</span>
            </div>
            <div className="rounded-xl border border-amber-700/40 bg-amber-900/20 p-3 text-xs text-amber-100">
              Vencendo em até 8h: <span className="font-semibold">{sla.due_soon_count ?? 0}</span>
            </div>
          </div>
        ) : null}
        <div className="flex gap-4 overflow-x-auto pb-2">
          {columns.map((column) => {
            const items = grouped[column] ?? [];
            return (
              <div key={column} className="min-h-[520px] min-w-[260px] max-w-[260px] rounded-xl border border-slatewarm-700 bg-slatewarm-900/40 p-3">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slatewarm-50">{column}</h3>
                  <span className="rounded-full bg-slatewarm-900 px-2 py-1 text-xs font-semibold text-slatewarm-200">{items.length}</span>
                </div>

                <div className="space-y-3">
                  {items.map((a) => (
                    <article
                      key={a.id}
                      className={[
                        'rounded-xl border bg-slatewarm-900 p-3 transition hover:border-brand-400',
                        a.stage_overdue ? 'border-rose-500/70' : 'border-slatewarm-700',
                      ].join(' ')}
                    >
                      <div className="flex items-center gap-2">
                        <img src={avatarDataUri(a.candidate_name)} alt={a.candidate_name} className="h-9 w-9 rounded-full border border-slatewarm-700" />
                        <div>
                          <p className="text-sm font-semibold text-slatewarm-50">{a.candidate_name ?? `Candidato #${a.candidate_id}`}</p>
                          <p className="text-xs text-slatewarm-300">{a.job_title}</p>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2 text-xs">
                        <span className="rounded-full bg-brand-900/30 px-2 py-1 font-semibold text-brand-100">Score {Math.round(a.score ?? 0)}%</span>
                        <span className={`rounded-full px-2 py-1 font-semibold ${stageColorMap[a.stage]}`}>{a.seniority}</span>
                      </div>

                      <div className="mt-3 flex items-center justify-between text-xs text-slatewarm-300">
                        <span>{formatDate(a.created_at)}</span>
                        <Link to={`/candidatos/${a.candidate_id}`} className="font-semibold text-brand-200 hover:text-brand-100">
                          Detalhes
                        </Link>
                      </div>
                      {a.stage_sla_hours ? (
                        <div className={`mt-2 text-[11px] ${a.stage_overdue ? 'text-rose-200' : 'text-slatewarm-300'}`}>
                          SLA: {a.stage_elapsed_hours ?? 0}h / {a.stage_sla_hours}h
                          {a.stage_overdue ? ` • atraso ${a.stage_overdue_hours ?? 0}h` : ''}
                        </div>
                      ) : null}
                      <div className="mt-2 grid gap-2">
                        <select
                          value={stageDraft[a.id] ?? a.stage}
                          onChange={(e) => setStageDraft((prev) => ({ ...prev, [a.id]: e.target.value }))}
                          className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
                        >
                          {STAGE_OPTIONS.map((stage) => (
                            <option key={stage} value={stage}>
                              {stage}
                            </option>
                          ))}
                        </select>
                        <Button variant="secondary" className="w-full" disabled={busyAppId === a.id} onClick={() => saveStage(a.id)}>
                          Salvar etapa
                        </Button>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}

export default PipelinePage;
