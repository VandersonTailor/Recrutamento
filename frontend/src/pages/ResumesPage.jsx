import { useEffect, useMemo, useState } from 'react';
import SectionCard from '../components/ui/SectionCard';
import Button from '../components/ui/Button';
import StatusBadge from '../components/ui/StatusBadge';
import { apiFetch, getApiBaseUrl } from '../services/api';
import { STAGE_OPTIONS } from '../utils/stages';

function parseStructuredJson(rawValue) {
  if (!rawValue) return null;
  try {
    const parsed = typeof rawValue === 'string' ? JSON.parse(rawValue) : rawValue;
    if (!parsed || typeof parsed !== 'object') return null;
    if (Object.keys(parsed).length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

function normalizeText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function isYoungApprenticeLabel(value) {
  const n = normalizeText(value);
  return n.includes('jovem aprendiz') || n.includes('menor aprendiz') || n.includes('aprendiz');
}

function hasSeniorExperienceSignals(detail) {
  const text = `${detail?.professional_summary || ''}\n${detail?.extracted_text || ''}`;
  const n = normalizeText(text);
  if (!n) return false;
  const internshipSignals = [
    'estagio',
    'estagiario',
    'estagiaria',
    'aprendizagem',
    'jovem aprendiz',
    'menor aprendiz',
  ];
  const hasInternshipProfile = internshipSignals.some((k) => n.includes(k));
  const strongRoleKeywords = [
    'chapeador',
    'pintor',
    'motorista',
    'mecanico',
    'eletricista',
    'almoxarife',
    'encarregado',
    'lider',
    'supervisor',
    'marcopolo',
    'restinga transportes',
  ];
  const hasStrongRole = strongRoleKeywords.some((k) => n.includes(k));
  if (hasStrongRole) return true;

  const yearMatches = (text.match(/\b(19|20)\d{2}\b/g) || []).length;
  const companySignals = (n.match(/\bempresa\b/g) || []).length;
  // Histórico de estágio sozinho não deve virar "perfil sênior".
  if (hasInternshipProfile && yearMatches < 6 && companySignals < 3) return false;

  if (yearMatches >= 4) return true;
  if (companySignals >= 2) return true;

  return false;
}

function hasYoungApprenticeSignals(detail) {
  const text = `${detail?.professional_summary || ''}\n${detail?.extracted_text || ''}`;
  const n = normalizeText(text);
  if (!n) return false;
  const signals = [
    'jovem aprendiz',
    'menor aprendiz',
    'primeiro emprego',
    'sem experiencia',
    'estudante',
    'estagio',
    'estagiario',
    'estagiaria',
    'ensino medio incompleto',
    'aprendizagem',
  ];
  return signals.some((s) => n.includes(s));
}

function resolveCandidateRole(detail) {
  const fromFilename = String(detail?.filename_cargo || '').trim();
  const normalizedFilename = normalizeText(fromFilename);
  const structured = parseStructuredJson(detail?.structured_json);
  const primaryRole = typeof structured?.fields?.classificacao_cargo?.primary_role === 'string'
    ? structured.fields.classificacao_cargo.primary_role
    : '';
  const seniorSignals = hasSeniorExperienceSignals(detail);
  const apprenticeSignals = hasYoungApprenticeSignals(detail);

  if (normalizedFilename && !['sem cargo', 'sem_cargo', 'outros'].includes(normalizedFilename)) {
    // Guardrail: se o arquivo vier como "jovem aprendiz" mas o conteúdo indica profissional experiente,
    // preferimos o cargo classificado pelo conteúdo.
    if (isYoungApprenticeLabel(normalizedFilename) && ((seniorSignals || !apprenticeSignals) && primaryRole)) {
      return primaryRole;
    }
    return fromFilename;
  }
  return primaryRole;
}

function findSuggestedJobByRole(jobs, roleLabel, detail) {
  const roleNorm = normalizeText(roleLabel);
  if (!roleNorm) return null;
  const seniorSignals = hasSeniorExperienceSignals(detail);
  const apprenticeSignals = hasYoungApprenticeSignals(detail);
  const wantsYoungApprentice = isYoungApprenticeLabel(roleNorm);

  if (wantsYoungApprentice && (seniorSignals || !apprenticeSignals)) {
    return null;
  }

  const candidates = (jobs || []).filter((job) => {
    const titleNorm = normalizeText(job?.title);
    if (!titleNorm) return false;
    if (wantsYoungApprentice) {
      return isYoungApprenticeLabel(titleNorm);
    }
    if (isYoungApprenticeLabel(titleNorm) && !wantsYoungApprentice) {
      return false;
    }
    return titleNorm === roleNorm || titleNorm.includes(roleNorm) || roleNorm.includes(titleNorm);
  });
  if (!candidates.length) return null;
  const exact = candidates.find((job) => normalizeText(job?.title) === roleNorm);
  return exact || candidates[0];
}

function ResumesPage({ mode = 'received' }) {
  const [jobs, setJobs] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [selectedDepartment, setSelectedDepartment] = useState('');
  const [q, setQ] = useState('');
  const [cargo, setCargo] = useState('');
  const [page, setPage] = useState(0);
  const [requiresReview, setRequiresReview] = useState(false);

  const [recent, setRecent] = useState([]);
  const [all, setAll] = useState([]);
  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [structuredDraft, setStructuredDraft] = useState('');
  const [structuredError, setStructuredError] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editDepartment, setEditDepartment] = useState('');
  const [editCargo, setEditCargo] = useState('');
  const [editCandidateName, setEditCandidateName] = useState('');
  const [editFilename, setEditFilename] = useState('');
  const [history, setHistory] = useState([]);
  const [candidateStageMap, setCandidateStageMap] = useState({});
  const [candidateApplications, setCandidateApplications] = useState([]);
  const [stageDraft, setStageDraft] = useState({});
  const [stageError, setStageError] = useState(null);
  const [stageBusyAppId, setStageBusyAppId] = useState(null);
  const [creatingApplication, setCreatingApplication] = useState(false);

  const limit = 50;

  const loadJobs = async () => {
    const j = await apiFetch('/jobs');
    setJobs(Array.isArray(j) ? j : []);
  };

  const loadDepartments = async () => {
    const d = await apiFetch('/departments');
    setDepartments(d.items ?? []);
  };

  const loadRecent = async () => {
    const params = new URLSearchParams();
    params.set('limit', '20');
    if (mode === 'talent') params.set('talent_pool_only', 'true');
    if (mode !== 'talent') params.set('include_talent_pool', 'false');
    if (selectedDepartment) params.set('department', selectedDepartment);
    if (q.trim()) params.set('q', q.trim());
    if (cargo.trim()) params.set('cargo', cargo.trim());
    if (requiresReview) params.set('requires_review', 'true');
    const r = await apiFetch(`/resumes?${params.toString()}`);
    setRecent(r);
  };

  const loadAll = async () => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    params.set('offset', String(page * limit));
    if (mode === 'talent') params.set('talent_pool_only', 'true');
    if (mode !== 'talent') params.set('include_talent_pool', 'false');
    if (selectedDepartment) params.set('department', selectedDepartment);
    if (q.trim()) params.set('q', q.trim());
    if (cargo.trim()) params.set('cargo', cargo.trim());
    if (requiresReview) params.set('requires_review', 'true');
    const r = await apiFetch(`/resumes?${params.toString()}`);
    setAll(r);
  };

  const reload = async () => {
    setError(null);
    await Promise.all([loadJobs(), loadDepartments(), loadRecent(), loadAll()]);
  };

  useEffect(() => {
    reload().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    loadRecent().catch((e) => setError(e instanceof Error ? e.message : String(e)));
    loadAll().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [selectedDepartment, page, requiresReview]);

  useEffect(() => {
    const items = [...recent, ...all];
    const ids = [...new Set(items.map((r) => r?.candidate_id).filter(Boolean))];
    if (!ids.length) {
      setCandidateStageMap({});
      return;
    }
    Promise.all(
      ids.map(async (candidateId) => {
        try {
          const resp = await apiFetch(`/applications?candidate_id=${candidateId}`);
          const app = Array.isArray(resp) ? resp[0] : resp;
          return [candidateId, app?.stage ?? 'Recebido'];
        } catch {
          return [candidateId, 'Recebido'];
        }
      }),
    ).then((pairs) => {
      const mapped = {};
      for (const [candidateId, stage] of pairs) {
        if (stage) mapped[candidateId] = stage;
      }
      setCandidateStageMap(mapped);
    });
  }, [recent, all]);

  const canNext = all.length === limit;
  const downloadBaseUrl = useMemo(() => getApiBaseUrl().replace(/\/api\/v1\/?$/, ''), []);

  const openDetail = async (id) => {
    setDetailId(id);
    setDetail(null);
    try {
      let d = await apiFetch(`/resumes/${id}`);
      let structured = parseStructuredJson(d?.structured_json);
      if (!structured) {
        await apiFetch(`/resumes/${id}/reanalyze`, { method: 'POST' });
        d = await apiFetch(`/resumes/${id}`);
        structured = parseStructuredJson(d?.structured_json);
      }
      setDetail(d);
      setStructuredDraft(JSON.stringify(structured ?? {}, null, 2));
      setEditDepartment(d?.department ?? '');
      setEditCargo(d?.filename_cargo ?? '');
      setEditCandidateName(d?.candidate_name ?? '');
      setEditFilename(d?.original_filename ?? '');
      const apps = d?.candidate_id
        ? await apiFetch(`/applications?candidate_id=${d.candidate_id}`).catch(() => [])
        : [];
      const appList = Array.isArray(apps) ? apps : [];
      const draft = appList.reduce((acc, app) => {
        if (app?.id) acc[app.id] = app.stage;
        return acc;
      }, {});
      setCandidateApplications(appList);
      setStageDraft(draft);
      setStageError(null);
      setCreatingApplication(false);
      const h = await apiFetch(`/resumes/${id}/history`).catch(() => []);
      setHistory(Array.isArray(h) ? h : []);
      setStructuredError(null);
      setFileError(null);
      setDeleteError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const saveStructured = async (approveReview = true) => {
    if (!detailId) return;
    setBusy(true);
    setStructuredError(null);
    try {
      const parsed = JSON.parse(structuredDraft || '{}');
      const updated = await apiFetch(`/resumes/${detailId}/structured`, {
        method: 'PATCH',
        body: {
          structured_json: parsed,
          approve_review: approveReview,
          extraction_confidence: detail?.extraction_confidence ?? null,
          review_reason: approveReview ? 'Revisado pelo RH' : (detail?.review_reason ?? 'Revisão pendente'),
        },
      });
      setDetail(updated);
      setStructuredDraft(JSON.stringify(parseStructuredJson(updated?.structured_json) ?? {}, null, 2));
      await loadRecent();
      await loadAll();
    } catch (e) {
      setStructuredError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reanalyzeStructured = async () => {
    if (!detailId) return;
    setBusy(true);
    setStructuredError(null);
    try {
      await apiFetch(`/resumes/${detailId}/reanalyze`, { method: 'POST' });
      const refreshed = await apiFetch(`/resumes/${detailId}`);
      setDetail(refreshed);
      setStructuredDraft(JSON.stringify(parseStructuredJson(refreshed?.structured_json) ?? {}, null, 2));
      await loadRecent();
      await loadAll();
    } catch (e) {
      setStructuredError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveFileChanges = async () => {
    if (!detailId) return;
    setBusy(true);
    setFileError(null);
    try {
      const updated = await apiFetch(`/resumes/${detailId}/file`, {
        method: 'PATCH',
        body: {
          new_department: editDepartment || null,
          new_cargo: editCargo || null,
          new_candidate_name: editCandidateName || null,
          new_filename: editFilename || null,
          reason: 'Ajuste manual pelo RH',
          apply_filename_pattern: !editFilename,
        },
      });
      setDetail(updated);
      setEditDepartment(updated?.department ?? '');
      setEditCargo(updated?.filename_cargo ?? '');
      setEditCandidateName(updated?.candidate_name ?? '');
      setEditFilename(updated?.original_filename ?? '');
      const h = await apiFetch(`/resumes/${detailId}/history`).catch(() => []);
      setHistory(Array.isArray(h) ? h : []);
      await loadRecent();
      await loadAll();
    } catch (e) {
      setFileError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sync = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/ingestion/scan', { method: 'POST', body: { job_id: null, force_reanalyze: false } });
      await apiFetch('/resumes/actions/cleanup_missing', { method: 'POST' });
      await apiFetch('/ingestion/reconcile', { method: 'POST' });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const deleteResume = async () => {
    if (!detailId) return;
    if (!window.confirm('Deseja excluir este currículo? Esta ação remove do banco e pode excluir o arquivo físico.')) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await apiFetch(`/resumes/${detailId}?delete_file=true`, { method: 'DELETE' });
      setDetailId(null);
      setDetail(null);
      setCandidateApplications([]);
      setStageDraft({});
      await loadRecent();
      await loadAll();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const updateApplicationState = (updated) => {
    if (!updated?.id) return;
    setCandidateApplications((prev) => prev.map((app) => (app.id === updated.id ? { ...app, ...updated } : app)));
    setStageDraft((prev) => ({ ...prev, [updated.id]: updated.stage }));
  };

  const runStageAction = async (appId, modeAction) => {
    if (!appId) return;
    const toStage = stageDraft[appId];
    if (modeAction === 'set' && !toStage) return;
    setStageBusyAppId(appId);
    setStageError(null);
    try {
      let updated = null;
      if (modeAction === 'set') {
        updated = await apiFetch(`/applications/${appId}/stage`, {
          method: 'PATCH',
          body: {
            to_stage: toStage,
            note: 'Mudança de etapa pela tela de currículos',
          },
        });
      } else if (modeAction === 'advance') {
        updated = await apiFetch(`/applications/${appId}/advance`, { method: 'POST' });
      } else if (modeAction === 'talent') {
        updated = await apiFetch(`/applications/${appId}/talent-pool`, { method: 'POST' });
      } else if (modeAction === 'approve') {
        updated = await apiFetch(`/applications/${appId}/approve`, { method: 'POST' });
      } else if (modeAction === 'reject') {
        updated = await apiFetch(`/applications/${appId}/dismiss`, { method: 'POST' });
      }
      updateApplicationState(updated);
      await loadRecent();
      await loadAll();
    } catch (e) {
      setStageError(e instanceof Error ? e.message : String(e));
    } finally {
      setStageBusyAppId(null);
    }
  };

  const candidateRoleLabel = useMemo(() => resolveCandidateRole(detail), [detail]);
  const suggestedJob = useMemo(
    () => findSuggestedJobByRole(jobs, candidateRoleLabel, detail),
    [jobs, candidateRoleLabel, detail],
  );

  const createApplicationForCandidate = async () => {
    if (!detail?.candidate_id) return;
    if (!suggestedJob?.id) {
      setStageError('Nenhuma vaga compatível encontrada para o cargo identificado. Crie a vaga primeiro.');
      return;
    }
    setCreatingApplication(true);
    setStageError(null);
    try {
      await apiFetch('/applications', {
        method: 'POST',
        body: {
          candidate_id: detail.candidate_id,
          job_id: Number(suggestedJob.id),
        },
      });
      const apps = await apiFetch(`/applications?candidate_id=${detail.candidate_id}`).catch(() => []);
      const appList = Array.isArray(apps) ? apps : [];
      const draft = appList.reduce((acc, app) => {
        if (app?.id) acc[app.id] = app.stage;
        return acc;
      }, {});
      setCandidateApplications(appList);
      setStageDraft(draft);
      setCandidateStageMap((prev) => ({ ...prev, [detail.candidate_id]: appList[0]?.stage || prev[detail.candidate_id] }));
      await loadRecent();
      await loadAll();
    } catch (e) {
      setStageError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreatingApplication(false);
    }
  };

  const titleRight = useMemo(() => {
    const base = mode === 'talent' ? 'Banco de talentos' : 'Currículos recebidos';
    return selectedDepartment ? `${base} (${selectedDepartment})` : base;
  }, [selectedDepartment, mode]);

  return (
    <div className="space-y-5">
      {error && <div className="card-surface p-4 text-sm text-red-200">Erro: {error}</div>}

      <SectionCard title="Filtros e sincronização" subtitle="Atualize a base e navegue por departamento">
        <div className="flex flex-wrap gap-2">
          <select
            value={selectedDepartment}
            onChange={(e) => {
              setPage(0);
              setSelectedDepartment(e.target.value);
            }}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          >
            <option value="">Todos</option>
            {departments.map((d) => (
              <option key={d.department} value={d.department}>
                {d.department}
              </option>
            ))}
          </select>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nome" className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50" />
          <input value={cargo} onChange={(e) => setCargo(e.target.value)} placeholder="Filtrar por cargo" className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50" />
          <Button variant="secondary" onClick={() => { setPage(0); loadRecent().then(loadAll); }}>
            Buscar
          </Button>
          <label className="inline-flex items-center gap-2 rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-100">
            <input type="checkbox" checked={requiresReview} onChange={(e) => { setPage(0); setRequiresReview(e.target.checked); }} />
            Somente revisão manual
          </label>
          {mode !== 'talent' ? (
            <Button onClick={sync} disabled={busy}>
              Sincronizar da pasta
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => reload()} disabled={busy}>
            Atualizar
          </Button>
        </div>
      </SectionCard>

      <div className="grid gap-5 xl:grid-cols-2">
        <SectionCard title="20 mais recentes" subtitle="Clique para ver detalhes">
          <div className="space-y-3">
            {recent.map((r) => (
              <button key={r.id} onClick={() => openDetail(r.id)} className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4 text-left transition hover:border-brand-400">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slatewarm-50">{r.candidate_name ?? `#${r.candidate_id}`}</div>
                    <div className="text-xs text-slatewarm-300">{r.department ?? '—'} • {r.original_filename ?? '—'}</div>
                    <div className="mt-1">
                      <StatusBadge stage={r.current_stage || candidateStageMap[r.candidate_id] || 'Recebido'} />
                    </div>
                  </div>
                  <div className="text-xs text-slatewarm-300">{new Date(r.received_at).toLocaleString()}</div>
                </div>
              </button>
            ))}
            {!recent.length && <div className="text-sm text-slatewarm-300">Sem itens.</div>}
          </div>
        </SectionCard>

        <SectionCard title={titleRight} subtitle="Paginação (50 por página)">
          <div className="mb-3 flex items-center justify-between">
            <Button variant="secondary" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
              Página anterior
            </Button>
            <div className="text-xs text-slatewarm-300">Página {page + 1}</div>
            <Button variant="secondary" disabled={!canNext} onClick={() => setPage((p) => p + 1)}>
              Próxima página
            </Button>
          </div>
          <div className="space-y-3">
            {all.map((r) => (
              <button key={r.id} onClick={() => openDetail(r.id)} className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4 text-left transition hover:border-brand-400">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slatewarm-50">{r.candidate_name ?? `#${r.candidate_id}`}</div>
                    <div className="text-xs text-slatewarm-300">{r.department ?? '—'} • {r.original_filename ?? '—'}</div>
                    <div className="mt-1">
                      <StatusBadge stage={r.current_stage || candidateStageMap[r.candidate_id] || 'Recebido'} />
                    </div>
                  </div>
                  <div className="text-xs text-slatewarm-300">{new Date(r.received_at).toLocaleString()}</div>
                </div>
              </button>
            ))}
            {!all.length && <div className="text-sm text-slatewarm-300">Sem itens.</div>}
          </div>
        </SectionCard>
      </div>

      {detailId !== null && (
        <div className="detailOverlay" onClick={() => { setDetailId(null); setDetail(null); setCandidateApplications([]); setStageDraft({}); }}>
          <div className="detailPanel" onClick={(e) => e.stopPropagation()}>
            <div className="detailHeader">
              <div>
                <div className="detailTitle">{detail?.candidate_name ?? `Currículo #${detailId}`}</div>
                <div className="detailSub">{detail?.department ?? '—'} • {detail?.original_filename ?? '—'}</div>
              </div>
              <Button variant="outline" onClick={() => { setDetailId(null); setDetail(null); setCandidateApplications([]); setStageDraft({}); }}>
                Fechar
              </Button>
            </div>

            {!detail && <div className="text-sm text-slatewarm-300">Carregando…</div>}
            {detail && (
              <div className="space-y-4">
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="text-xs text-slatewarm-300">Email</div>
                  <div className="text-sm font-semibold text-slatewarm-50">{detail.candidate_email ?? 'Não informado'}</div>
                </div>
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="text-xs text-slatewarm-300">Telefone</div>
                  <div className="text-sm font-semibold text-slatewarm-50">{detail.candidate_phone ?? 'Não informado'}</div>
                </div>
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="text-xs text-slatewarm-300">Endereço</div>
                  <div className="whitespace-pre-wrap text-sm font-semibold text-slatewarm-50">{detail.candidate_address ?? 'Não informado'}</div>
                </div>
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="text-xs text-slatewarm-300">Resumo profissional</div>
                  <div className="whitespace-pre-wrap text-sm text-slatewarm-200">{detail.professional_summary ?? 'Não informado'}</div>
                  {detail.warnings?.length ? (
                    <div className="mt-3 text-xs text-amber-200">{detail.warnings.join('\n')}</div>
                  ) : null}
                </div>

                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="mb-2 text-xs text-slatewarm-300">Etapas do candidato</div>
                  <div className="space-y-3">
                    {candidateApplications.map((app) => (
                      <div key={app.id} className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 p-3">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-semibold text-slatewarm-100">{app.job_title ?? `Aplicação #${app.id}`}</div>
                          <div className="flex items-center gap-2 text-xs text-slatewarm-300">
                            <span>Atual:</span>
                            <StatusBadge stage={app.stage ?? '—'} />
                          </div>
                        </div>
                        <div className="grid gap-2 md:grid-cols-2">
                          <div className="space-y-2">
                            <select
                              value={stageDraft[app.id] ?? app.stage ?? 'Recebido'}
                              onChange={(e) => setStageDraft((prev) => ({ ...prev, [app.id]: e.target.value }))}
                              className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-xs text-slatewarm-100"
                            >
                              {STAGE_OPTIONS.map((stage) => (
                                <option key={stage} value={stage}>
                                  {stage}
                                </option>
                              ))}
                            </select>
                            <div className="flex items-center gap-2 text-xs text-slatewarm-300">
                              <span>Selecionada:</span>
                              <StatusBadge stage={stageDraft[app.id] ?? app.stage ?? 'Recebido'} />
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button variant="secondary" disabled={stageBusyAppId === app.id} onClick={() => runStageAction(app.id, 'set')}>
                              Salvar etapa
                            </Button>
                            <Button variant="outline" disabled={stageBusyAppId === app.id} onClick={() => runStageAction(app.id, 'advance')}>
                              Avançar
                            </Button>
                            <Button variant="outline" disabled={stageBusyAppId === app.id} onClick={() => runStageAction(app.id, 'talent')}>
                              Banco talentos
                            </Button>
                            <Button variant="outline" disabled={stageBusyAppId === app.id} onClick={() => runStageAction(app.id, 'approve')}>
                              Aprovar
                            </Button>
                            <Button variant="outline" disabled={stageBusyAppId === app.id} onClick={() => runStageAction(app.id, 'reject')}>
                              Reprovar
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                    {!candidateApplications.length ? (
                      <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-950 p-3">
                        <div className="mb-2 flex items-center gap-2 text-xs text-slatewarm-300">
                          <span>Etapa atual:</span>
                          <StatusBadge stage="Recebido" />
                        </div>
                        <div className="text-xs text-slatewarm-300">Nenhuma aplicação vinculada a este candidato.</div>
                        <div className="mt-2 space-y-2">
                          <div className="text-xs text-slatewarm-300">
                            Cargo identificado: <span className="font-semibold text-slatewarm-100">{candidateRoleLabel || 'Não identificado'}</span>
                          </div>
                          <div className="text-xs text-slatewarm-300">
                            Vaga compatível: <span className="font-semibold text-slatewarm-100">{suggestedJob?.title || 'Nenhuma vaga compatível criada ainda'}</span>
                          </div>
                          <Button variant="secondary" disabled={creatingApplication || !suggestedJob} onClick={createApplicationForCandidate}>
                            Criar candidatura automática
                          </Button>
                        </div>
                      </div>
                    ) : null}
                    {stageError ? <div className="text-xs text-red-200">{stageError}</div> : null}
                  </div>
                </div>

                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="mb-2 text-xs text-slatewarm-300">Gestão do arquivo físico</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="space-y-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slatewarm-300">Departamento/Pasta</div>
                      <input value={editDepartment} onChange={(e) => setEditDepartment(e.target.value)} placeholder="Ex.: administrativo" className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100" />
                    </label>
                    <label className="space-y-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slatewarm-300">Cargo do arquivo</div>
                      <input value={editCargo} onChange={(e) => setEditCargo(e.target.value)} placeholder="Ex.: motorista" className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100" />
                    </label>
                    <label className="space-y-1 md:col-span-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slatewarm-300">Nome do candidato</div>
                      <input value={editCandidateName} onChange={(e) => setEditCandidateName(e.target.value)} placeholder="Ex.: Juliana Gulart" className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100" />
                    </label>
                    <label className="space-y-1 md:col-span-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slatewarm-300">Nome final do arquivo (opcional)</div>
                      <input value={editFilename} onChange={(e) => setEditFilename(e.target.value)} placeholder="Se vazio, o sistema gera no padrão automático" className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100" />
                    </label>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Button variant="secondary" disabled={busy} onClick={saveFileChanges}>Salvar arquivo/pasta</Button>
                    <a href={`${downloadBaseUrl}/api/v1/resumes/${detailId}/download`} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-xl border border-slatewarm-700 px-3 py-2 text-xs text-slatewarm-100 hover:border-brand-400">Download arquivo</a>
                  </div>
                  {fileError ? <div className="mt-2 text-xs text-red-200">{fileError}</div> : null}
                </div>

                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-xs text-slatewarm-300">Estrutura extraída (JSON)</div>
                      <div className="text-xs text-slatewarm-400">
                        Confiança: {typeof detail.extraction_confidence === 'number' ? `${Math.round(detail.extraction_confidence * 100)}%` : '—'} •
                        Revisão: {detail.requires_manual_review ? 'Pendente' : 'Concluída'}
                      </div>
                      {detail.review_reason ? <div className="text-xs text-amber-200">Motivo: {detail.review_reason}</div> : null}
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" disabled={busy} onClick={deleteResume}>Excluir currículo</Button>
                      <Button variant="outline" disabled={busy} onClick={reanalyzeStructured}>Reprocessar JSON</Button>
                      <Button disabled={busy} onClick={() => saveStructured(true)}>Aprovar revisão</Button>
                    </div>
                  </div>
                  <textarea
                    value={structuredDraft}
                    onChange={(e) => setStructuredDraft(e.target.value)}
                    className="min-h-[220px] w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100"
                  />
                  {structuredError ? <div className="mt-2 text-xs text-red-200">{structuredError}</div> : null}
                  {deleteError ? <div className="mt-2 text-xs text-red-200">{deleteError}</div> : null}
                </div>

                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
                  <div className="mb-2 text-xs text-slatewarm-300">Histórico de alterações</div>
                  <div className="space-y-2">
                    {history.map((h) => (
                      <div key={h.id} className="rounded-lg border border-slatewarm-700 bg-slatewarm-950 p-2 text-xs text-slatewarm-200">
                        <div className="font-semibold text-slatewarm-100">{h.action}</div>
                        <div>{new Date(h.created_at).toLocaleString()}</div>
                        {h.reason ? <div>Motivo: {h.reason}</div> : null}
                      </div>
                    ))}
                    {!history.length ? <div className="text-xs text-slatewarm-400">Sem histórico para este currículo.</div> : null}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ResumesPage;
