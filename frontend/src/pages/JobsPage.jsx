import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import SectionCard from '../components/ui/SectionCard';
import Button from '../components/ui/Button';
import { apiFetch, getApiBaseUrl, isUsingMockApi } from '../services/api';
import { avatarDataUri } from '../utils/avatar';
import { STAGE_OPTIONS } from '../utils/stages';

function splitCsv(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function clamp(value, min, max) {
  const n = Number(value);
  if (Number.isNaN(n)) return min;
  return Math.min(max, Math.max(min, n));
}

function weightsToPoints(weights) {
  const safe = {
    cargo: Number(weights?.cargo ?? 0.3),
    formacao: Number(weights?.formacao ?? 0.2),
    cursos: Number(weights?.cursos ?? 0.25),
    experiencia: Number(weights?.experiencia ?? 0.25),
  };
  return {
    cargo: Number((safe.cargo * 10).toFixed(1)),
    formacao: Number((safe.formacao * 10).toFixed(1)),
    cursos: Number((safe.cursos * 10).toFixed(1)),
    experiencia: Number((safe.experiencia * 10).toFixed(1)),
  };
}

function pointsToWeights(points) {
  const safe = {
    cargo: clamp(points?.cargo ?? 3, 0, 10),
    formacao: clamp(points?.formacao ?? 2, 0, 10),
    cursos: clamp(points?.cursos ?? 2.5, 0, 10),
    experiencia: clamp(points?.experiencia ?? 2.5, 0, 10),
  };
  const total = safe.cargo + safe.formacao + safe.cursos + safe.experiencia;
  if (total <= 0) return { cargo: 0.3, formacao: 0.2, cursos: 0.25, experiencia: 0.25 };
  return {
    cargo: Number((safe.cargo / total).toFixed(6)),
    formacao: Number((safe.formacao / total).toFixed(6)),
    cursos: Number((safe.cursos / total).toFixed(6)),
    experiencia: Number((safe.experiencia / total).toFixed(6)),
  };
}

function prettyJson(value) {
  if (!value) return '{}';
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value;
    return JSON.stringify(parsed, null, 2);
  } catch {
    return String(value);
  }
}

function JobsPage() {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState('');
  const [department, setDepartment] = useState('');
  const [description, setDescription] = useState('');
  const [requirements, setRequirements] = useState('');
  const [requiredCourses, setRequiredCourses] = useState('');
  const [minExperienceYears, setMinExperienceYears] = useState('0');
  const [preferredCities, setPreferredCities] = useState('');
  const [residenceRequired, setResidenceRequired] = useState(false);
  const [customFilters, setCustomFilters] = useState([]);
  const [createProfilePoints, setCreateProfilePoints] = useState({ cargo: 3, formacao: 2, cursos: 2.5, experiencia: 2.5 });
  const [createPortoBonus, setCreatePortoBonus] = useState(8);
  const [createSignalFloor, setCreateSignalFloor] = useState(12);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const [selectedJob, setSelectedJob] = useState(null);
  const [rank, setRank] = useState(null);
  const [rankError, setRankError] = useState(null);
  const [q, setQ] = useState('');
  const [minScore, setMinScore] = useState('');
  const [reason, setReason] = useState('');
  const [stageDraft, setStageDraft] = useState({});
  const [detailResume, setDetailResume] = useState(null);
  const [detailResumeError, setDetailResumeError] = useState(null);
  const [profilePoints, setProfilePoints] = useState({ cargo: 3, formacao: 2, cursos: 2.5, experiencia: 2.5 });
  const [profile, setProfile] = useState({
    weights: { cargo: 0.3, formacao: 0.2, cursos: 0.25, experiencia: 0.25 },
    porto_alegre_bonus: 8,
    minimum_signal_floor: 12,
    ranking_filters: {
      required_courses: [],
      minimum_years_experience: 0,
      preferred_cities: [],
      residence_required: false,
      custom_filters: [],
    },
  });

  const load = () => {
    setError(null);
    return apiFetch('/jobs')
      .then((j) => setJobs(j))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const createJob = async () => {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/jobs', {
        method: 'POST',
        body: {
          title: title.trim(),
          department: department.trim() || null,
          description: description.trim() || null,
          requirements: requirements.trim() || null,
          ranking_profile: {
            weights: pointsToWeights(createProfilePoints),
            porto_alegre_bonus: Number(createPortoBonus || 0),
            minimum_signal_floor: Number(createSignalFloor || 0),
            ranking_filters: {
              required_courses: splitCsv(requiredCourses),
              minimum_years_experience: Number(minExperienceYears || 0),
              preferred_cities: splitCsv(preferredCities),
              residence_required: Boolean(residenceRequired),
              custom_filters: customFilters
                .map((filter) => ({
                  label: String(filter.label || '').trim(),
                  keywords: splitCsv(filter.keywords),
                  points: clamp(filter.points || 0, 0, 10),
                  mode: filter.mode === 'required' ? 'required' : 'bonus',
                }))
                .filter((filter) => filter.label && filter.keywords.length),
            },
          },
          is_active: true,
        },
      });
      setTitle('');
      setDepartment('');
      setDescription('');
      setRequirements('');
      setRequiredCourses('');
      setMinExperienceYears('0');
      setPreferredCities('');
      setResidenceRequired(false);
      setCustomFilters([]);
      setCreateProfilePoints({ cargo: 3, formacao: 2, cursos: 2.5, experiencia: 2.5 });
      setCreatePortoBonus(8);
      setCreateSignalFloor(12);
      setIsCreateModalOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const action = async (path) => {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(path, { method: 'POST' });
      await load();
      if (selectedJob) {
        const refreshed = jobs.find((j) => j.id === selectedJob.id);
        if (refreshed) setSelectedJob(refreshed);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openRanking = async (job) => {
    setSelectedJob(job);
    setRank(null);
    setRankError(null);
    if (selectedJob?.id !== job.id) {
      setQ('');
      setMinScore('');
    }
    try {
      const p = await apiFetch(`/jobs/${job.id}/ranking-profile`);
      setProfile(p);
      setProfilePoints(weightsToPoints(p?.weights));
      const params = new URLSearchParams();
      if (job.department) params.set('department', job.department);
      if (q.trim()) params.set('q', q.trim());
      if (minScore.trim()) params.set('min_score', minScore.trim());
      params.set('limit', '50');
      const res = await apiFetch(`/jobs/${job.id}/ranking?${params.toString()}`);
      setRank(res);
      const draft = {};
      (res?.items ?? []).forEach((item) => {
        if (item?.application_id) draft[item.application_id] = item.stage || 'Recebido';
      });
      setStageDraft(draft);
    } catch (e) {
      setRankError(e instanceof Error ? e.message : String(e));
    }
  };

  const saveProfile = async () => {
    if (!selectedJob) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/jobs/${selectedJob.id}/ranking-profile`, {
        method: 'PATCH',
        body: {
          ...profile,
          weights: pointsToWeights(profilePoints),
        },
      });
      await openRanking(selectedJob);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveStage = async (applicationId) => {
    if (!selectedJob || !applicationId) return;
    const toStage = stageDraft[applicationId];
    if (!toStage) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/applications/${applicationId}/stage`, {
        method: 'PATCH',
        body: {
          to_stage: toStage,
          note: 'Atualizado na tela de ranking da vaga',
        },
      });
      await openRanking(selectedJob);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const exportUrl = useMemo(() => {
    if (!selectedJob) return null;
    if (isUsingMockApi()) return null;
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return null;
    const base = baseUrl.replace(/\/$/, '');
    const params = new URLSearchParams();
    if (selectedJob.department) params.set('department', selectedJob.department);
    if (q.trim()) params.set('q', q.trim());
    if (minScore.trim()) params.set('min_score', minScore.trim());
    params.set('limit', '200');
    return `${base}/jobs/${selectedJob.id}/ranking/export?${params.toString()}`;
  }, [selectedJob, q, minScore]);

  const resumeDownloadUrl = (resumeId) => {
    if (!resumeId || isUsingMockApi()) return null;
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return null;
    const base = baseUrl.replace(/\/$/, '');
    return `${base}/resumes/${resumeId}/download`;
  };

  const openResumeInfo = async (resumeId) => {
    if (!resumeId) return;
    setDetailResume(null);
    setDetailResumeError(null);
    try {
      const data = await apiFetch(`/resumes/${resumeId}`);
      setDetailResume(data);
    } catch (e) {
      setDetailResumeError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-5">
      {error && <div className="card-surface p-4 text-sm text-red-200">Erro: {error}</div>}

      <SectionCard title="Criar vaga" subtitle="O departamento pode ser preenchido automaticamente com base na pasta">
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => setIsCreateModalOpen(true)} disabled={busy}>
            Nova vaga com critérios
          </Button>
          <div className="text-xs text-slatewarm-300">
            Defina filtros de ranking: cursos, experiência, residência e regras personalizadas.
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Vagas" subtitle="Clique em uma vaga para ver o ranking de candidatos">
        <div className="space-y-3">
          {jobs.map((j) => (
            <button
              key={j.id}
              onClick={() => openRanking(j)}
              className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4 text-left transition hover:border-brand-400"
            >
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-slatewarm-50">{j.title}</div>
                  <div className="text-xs text-slatewarm-300">{j.department ?? '—'} • {j.is_active ? 'Ativa' : 'Inativa'}</div>
                </div>
                <div className="text-xs text-slatewarm-300">ID {j.id}</div>
              </div>
            </button>
          ))}
          {!jobs.length && <div className="text-sm text-slatewarm-300">Nenhuma vaga cadastrada.</div>}
        </div>
      </SectionCard>

      {selectedJob && (
        <div className="detailOverlay" onClick={() => { setSelectedJob(null); setRank(null); setRankError(null); }}>
          <div className="detailPanel" onClick={(e) => e.stopPropagation()}>
            <div className="detailHeader">
              <div>
                <div className="detailTitle">{selectedJob.title}</div>
                <div className="detailSub">{selectedJob.department ?? '—'}</div>
              </div>
              <Button variant="outline" onClick={() => { setSelectedJob(null); setRank(null); setRankError(null); }}>
                Fechar
              </Button>
            </div>

            <div className="grid gap-2">
              <div className="grid gap-2 md:grid-cols-2">
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrar por nome" className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50" />
                <input value={minScore} onChange={(e) => setMinScore(e.target.value)} placeholder="Score mín." className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50" />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => openRanking(selectedJob)}>
                  Atualizar ranking
                </Button>
                <Link
                  className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm font-semibold text-slatewarm-100 hover:border-brand-400"
                  to={`/auditoria-ranking?jobId=${selectedJob.id}`}
                >
                  Abrir auditoria
                </Link>
                {exportUrl && (
                  <a className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm font-semibold text-slatewarm-100 hover:border-brand-400" href={exportUrl} target="_blank" rel="noreferrer">
                    Exportar CSV
                  </a>
                )}
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motivo (opcional)" className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50 md:col-span-3" />
                <Button variant="secondary" disabled={busy} onClick={() => action(`/jobs/${selectedJob.id}/close?reason=${encodeURIComponent(reason)}`)}>
                  Encerrar
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => action(`/jobs/${selectedJob.id}/reopen`)}>
                  Reabrir
                </Button>
                <Button variant="danger" disabled={busy} onClick={() => action(`/jobs/${selectedJob.id}/delete?reason=${encodeURIComponent(reason)}`)}>
                  Excluir
                </Button>
              </div>

              <div className="mt-2 rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                <div className="mb-2 text-xs font-semibold text-slatewarm-200">Perfil de score da vaga (0 a 10)</div>
                <div className="mb-3 text-xs text-slatewarm-300">
                  Defina a importância de cada critério para o ranking. Quanto maior o ponto, maior o impacto no score final.
                </div>
                <div className="grid gap-2 md:grid-cols-4">
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Cargo (aderência ao cargo da vaga)</div>
                    <input value={profilePoints?.cargo ?? ''} onChange={(e) => setProfilePoints((prev) => ({ ...prev, cargo: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Formação (escolaridade)</div>
                    <input value={profilePoints?.formacao ?? ''} onChange={(e) => setProfilePoints((prev) => ({ ...prev, formacao: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Cursos/Certificações</div>
                    <input value={profilePoints?.cursos ?? ''} onChange={(e) => setProfilePoints((prev) => ({ ...prev, cursos: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Experiência (tempo/atuação)</div>
                    <input value={profilePoints?.experiencia ?? ''} onChange={(e) => setProfilePoints((prev) => ({ ...prev, experiencia: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-3">
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Bônus por residência local</div>
                    <input value={profile?.porto_alegre_bonus ?? ''} onChange={(e) => setProfile((prev) => ({ ...prev, porto_alegre_bonus: Number(e.target.value || 0) }))} placeholder="0-10 sugerido" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Piso mínimo de score com evidências</div>
                    <input value={profile?.minimum_signal_floor ?? ''} onChange={(e) => setProfile((prev) => ({ ...prev, minimum_signal_floor: Number(e.target.value || 0) }))} placeholder="0-40" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <Button variant="secondary" disabled={busy} onClick={saveProfile}>Salvar perfil</Button>
                </div>
              </div>
            </div>

            {rankError && <div className="mt-3 text-sm text-red-200">{rankError}</div>}
            {!rankError && !rank && <div className="mt-3 text-sm text-slatewarm-300">Carregando…</div>}

            {rank && (
              <div className="mt-4 space-y-3">
                {(rank.items ?? []).map((it) => (
                  <div key={it.application_id ?? `${it.candidate_id}-${it.resume_id ?? 'na'}`} className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <img src={avatarDataUri(it.candidate_name)} alt={it.candidate_name} className="h-10 w-10 rounded-full border border-slatewarm-700" />
                        <div>
                          <div className="text-sm font-semibold text-slatewarm-50">{it.candidate_name}</div>
                          <div className="text-xs text-slatewarm-300">{it.match_breakdown ? `cargo ${it.match_breakdown.cargo?.toFixed?.(0) ?? ''}% • formação ${it.match_breakdown.formacao?.toFixed?.(0) ?? ''}%` : ''}</div>
                          {it.match_breakdown ? (
                            <div className="text-[11px] text-slatewarm-300">
                              exp {it.match_breakdown.experiencia?.toFixed?.(0) ?? ''}% •
                              cursos {it.match_breakdown.cursos?.toFixed?.(0) ?? ''}% •
                              penalidade {it.match_breakdown.stuffing_penalty?.toFixed?.(1) ?? '0.0'}
                            </div>
                          ) : null}
                          {it.primary_role ? (
                            <div className="text-[11px] text-brand-200">
                              Cargo IA: {it.primary_role}
                              {it.secondary_roles?.length ? ` • Alternativos: ${it.secondary_roles.join(', ')}` : ''}
                              {typeof it.role_confidence === 'number' ? ` • conf. ${Math.round(it.role_confidence * 100)}%` : ''}
                              {it.role_needs_review ? ' • revisar classificação' : ''}
                            </div>
                          ) : null}
                        </div>
                      </div>
                      <div className="rounded-full bg-brand-900/30 px-3 py-1 text-xs font-semibold text-brand-100">
                        #{it.rank_position ?? '—'} • {Math.round(it.match_percent)}%
                      </div>
                    </div>
                    {it.professional_summary ? <div className="mt-3 whitespace-pre-wrap text-xs text-slatewarm-200">{it.professional_summary}</div> : null}
                    {it.strengths?.length ? <div className="mt-3 text-xs text-slatewarm-300">Pontos fortes: {it.strengths.join(' • ')}</div> : null}
                    <div className="mt-3 text-xs text-slatewarm-300">Contato: {it.email ?? '—'} • {it.phone ?? '—'} • {it.linkedin ?? '—'}</div>
                    {it.rank_reason ? <div className="mt-1 text-[11px] text-slatewarm-400">Ranking: {it.rank_reason}</div> : null}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {it.resume_id ? (
                        <>
                          <Button variant="secondary" onClick={() => openResumeInfo(it.resume_id)}>
                            Ver informações
                          </Button>
                          {resumeDownloadUrl(it.resume_id) ? (
                            <a
                              className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs font-semibold text-slatewarm-100 hover:border-brand-400"
                              href={resumeDownloadUrl(it.resume_id)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Download PDF/Arquivo
                            </a>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                    {it.application_id ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto]">
                        <select
                          value={stageDraft[it.application_id] ?? it.stage ?? 'Recebido'}
                          onChange={(e) => setStageDraft((prev) => ({ ...prev, [it.application_id]: e.target.value }))}
                          className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-50"
                        >
                          {STAGE_OPTIONS.map((stage) => (
                            <option key={stage} value={stage}>
                              {stage}
                            </option>
                          ))}
                        </select>
                        <Button variant="secondary" disabled={busy} onClick={() => saveStage(it.application_id)}>
                          Salvar etapa
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
                {!rank.items?.length && <div className="text-sm text-slatewarm-300">Sem candidatos compatíveis.</div>}
              </div>
            )}
          </div>
        </div>
      )}

      {(detailResume || detailResumeError) && (
        <div className="detailOverlay" onClick={() => { setDetailResume(null); setDetailResumeError(null); }}>
          <div className="detailPanel" onClick={(e) => e.stopPropagation()}>
            <div className="detailHeader">
              <div>
                <div className="detailTitle">Informações do currículo</div>
                <div className="detailSub">Resumo e estrutura extraída</div>
              </div>
              <Button variant="outline" onClick={() => { setDetailResume(null); setDetailResumeError(null); }}>
                Fechar
              </Button>
            </div>
            {detailResumeError ? <div className="text-sm text-red-200">{detailResumeError}</div> : null}
            {detailResume ? (
              <div className="space-y-2 text-sm text-slatewarm-100">
                <div><span className="text-slatewarm-300">Nome:</span> {detailResume.candidate_name ?? '—'}</div>
                <div><span className="text-slatewarm-300">Email:</span> {detailResume.email ?? '—'}</div>
                <div><span className="text-slatewarm-300">Telefone:</span> {detailResume.phone ?? '—'}</div>
                <div><span className="text-slatewarm-300">Endereço:</span> {detailResume.address ?? '—'}</div>
                <div><span className="text-slatewarm-300">Resumo:</span></div>
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-2 text-xs whitespace-pre-wrap">
                  {detailResume.professional_summary || '—'}
                </div>
                <div><span className="text-slatewarm-300">JSON estruturado:</span></div>
                <pre className="max-h-72 overflow-auto rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-2 text-[11px] text-slatewarm-100">
                  {prettyJson(detailResume.structured_json)}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {isCreateModalOpen && (
        <div className="detailOverlay" onClick={() => setIsCreateModalOpen(false)}>
          <div className="detailPanel" onClick={(e) => e.stopPropagation()}>
            <div className="detailHeader">
              <div>
                <div className="detailTitle">Nova vaga</div>
                <div className="detailSub">Configure os critérios que serão usados no ranking</div>
              </div>
              <Button variant="outline" onClick={() => setIsCreateModalOpen(false)}>
                Fechar
              </Button>
            </div>

            <div className="space-y-3">
              <div className="grid gap-2 md:grid-cols-2">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Cargo / Vaga"
                  className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
                />
                <input
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="Departamento (opcional)"
                  className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
                />
              </div>
              <div className="text-xs text-slatewarm-300">
                `Cargo/Vaga`: nome exato da função. `Departamento`: pasta/setor onde a vaga será operada.
              </div>

              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descrição da vaga"
                rows={3}
                className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
              />
              <textarea
                value={requirements}
                onChange={(e) => setRequirements(e.target.value)}
                placeholder="Requisitos gerais"
                rows={3}
                className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
              />
              <div className="text-xs text-slatewarm-300">
                `Descrição`: contexto e atividades do cargo. `Requisitos`: critérios que o RH espera encontrar no currículo.
              </div>

              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                <div className="mb-2 text-xs font-semibold text-slatewarm-200">Perfil de score da vaga (0 a 10)</div>
                <div className="mb-2 text-xs text-slatewarm-300">
                  Cada campo define o peso no ranking final. Exemplo: se experiência é mais importante, use pontuação maior em experiência.
                </div>
                <div className="grid gap-2 md:grid-cols-4">
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Cargo</div>
                    <input value={createProfilePoints.cargo} onChange={(e) => setCreateProfilePoints((prev) => ({ ...prev, cargo: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Formação</div>
                    <input value={createProfilePoints.formacao} onChange={(e) => setCreateProfilePoints((prev) => ({ ...prev, formacao: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Cursos</div>
                    <input value={createProfilePoints.cursos} onChange={(e) => setCreateProfilePoints((prev) => ({ ...prev, cursos: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Experiência</div>
                    <input value={createProfilePoints.experiencia} onChange={(e) => setCreateProfilePoints((prev) => ({ ...prev, experiencia: clamp(e.target.value, 0, 10) }))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Bônus por residência local</div>
                    <input value={createPortoBonus} onChange={(e) => setCreatePortoBonus(clamp(e.target.value, 0, 10))} placeholder="0-10" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] text-slatewarm-300">Piso mínimo do score (quando há sinais)</div>
                    <input value={createSignalFloor} onChange={(e) => setCreateSignalFloor(clamp(e.target.value, 0, 40))} placeholder="0-40" className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50" />
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                <div className="mb-2 text-xs font-semibold text-slatewarm-200">Filtros principais para ranking</div>
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    value={requiredCourses}
                    onChange={(e) => setRequiredCourses(e.target.value)}
                    placeholder="Cursos obrigatórios (separados por vírgula)"
                    className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50"
                  />
                  <input
                    value={minExperienceYears}
                    onChange={(e) => setMinExperienceYears(e.target.value)}
                    placeholder="Anos mínimos de experiência"
                    className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50"
                  />
                  <input
                    value={preferredCities}
                    onChange={(e) => setPreferredCities(e.target.value)}
                    placeholder="Cidades de residência (vírgula)"
                    className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50 md:col-span-2"
                  />
                </div>
                <label className="mt-2 inline-flex items-center gap-2 text-xs text-slatewarm-200">
                  <input type="checkbox" checked={residenceRequired} onChange={(e) => setResidenceRequired(e.target.checked)} />
                  Residência obrigatória nas cidades informadas
                </label>
                <div className="mt-2 text-xs text-slatewarm-300">
                  `Cursos obrigatórios`: aumenta score se encontrado, penaliza se faltar.
                  `Anos mínimos`: exige experiência mínima.
                  `Cidades`: bônus por proximidade; se obrigatório, penaliza fora da região.
                </div>
              </div>

              <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-semibold text-slatewarm-200">Filtros personalizados</div>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setCustomFilters((prev) => [...prev, { label: '', keywords: '', points: 3, mode: 'bonus' }])
                    }
                  >
                    Adicionar filtro
                  </Button>
                </div>
                <div className="mb-2 text-xs text-slatewarm-300">
                  `Bônus`: soma pontos quando encontra palavras-chave. `Obrigatório`: desconta pontos quando não encontra.
                  Pontuação de cada filtro: `0 a 10`.
                </div>
                <div className="space-y-2">
                  {customFilters.map((filter, idx) => (
                    <div key={`filter-${idx}`} className="grid gap-2 md:grid-cols-12">
                      <input
                        value={filter.label}
                        onChange={(e) =>
                          setCustomFilters((prev) =>
                            prev.map((item, i) => (i === idx ? { ...item, label: e.target.value } : item))
                          )
                        }
                        placeholder="Nome do filtro"
                        className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50 md:col-span-3"
                      />
                      <input
                        value={filter.keywords}
                        onChange={(e) =>
                          setCustomFilters((prev) =>
                            prev.map((item, i) => (i === idx ? { ...item, keywords: e.target.value } : item))
                          )
                        }
                        placeholder="Palavras-chave (vírgula)"
                        className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50 md:col-span-5"
                      />
                      <input
                        value={filter.points}
                        onChange={(e) =>
                          setCustomFilters((prev) =>
                            prev.map((item, i) => (i === idx ? { ...item, points: clamp(e.target.value, 0, 10) } : item))
                          )
                        }
                        placeholder="0-10"
                        className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50 md:col-span-2"
                      />
                      <select
                        value={filter.mode}
                        onChange={(e) =>
                          setCustomFilters((prev) =>
                            prev.map((item, i) => (i === idx ? { ...item, mode: e.target.value } : item))
                          )
                        }
                        className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-50 md:col-span-1"
                      >
                        <option value="bonus">Bônus</option>
                        <option value="required">Obrigatório</option>
                      </select>
                      <Button
                        variant="danger"
                        onClick={() => setCustomFilters((prev) => prev.filter((_, i) => i !== idx))}
                      >
                        X
                      </Button>
                    </div>
                  ))}
                  {!customFilters.length && <div className="text-xs text-slatewarm-400">Sem filtros personalizados.</div>}
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setIsCreateModalOpen(false)}>
                  Cancelar
                </Button>
                <Button onClick={createJob} disabled={busy || !title.trim()}>
                  Criar vaga
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default JobsPage;
