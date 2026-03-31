import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Mail, Phone } from 'lucide-react';
import SectionCard from '../components/ui/SectionCard';
import Button from '../components/ui/Button';
import StatusBadge from '../components/ui/StatusBadge';
import { apiFetch } from '../services/api';
import { avatarDataUri } from '../utils/avatar';
import { formatDate } from '../utils/format';
import { STAGE_OPTIONS } from '../utils/stages';

function CandidateDetailsPage() {
  const { candidateId } = useParams();
  const navigate = useNavigate();

  const [candidate, setCandidate] = useState(null);
  const [latestResume, setLatestResume] = useState(null);
  const [apps, setApps] = useState([]);
  const [error, setError] = useState(null);
  const [busyAppId, setBusyAppId] = useState(null);
  const [stageDraft, setStageDraft] = useState({});
  const [selectedCommAppId, setSelectedCommAppId] = useState(null);
  const [commHistory, setCommHistory] = useState([]);
  const [commChannel, setCommChannel] = useState('whatsapp');
  const [commTemplate, setCommTemplate] = useState('atualizacao_etapa');
  const [commBody, setCommBody] = useState('');
  const [interviewAt, setInterviewAt] = useState('');
  const [interviewLocation, setInterviewLocation] = useState('Sede Carris');
  const [busyCommunication, setBusyCommunication] = useState(false);

  const loadCandidateData = async () => {
    if (!candidateId) return;
    setError(null);
    try {
      const [c, r, a] = await Promise.all([
        apiFetch(`/candidates/${candidateId}`),
        apiFetch(`/resumes?candidate_id=${candidateId}&limit=1`),
        apiFetch(`/applications?candidate_id=${candidateId}`),
      ]);
      setCandidate(c);
      setApps(a);
      setStageDraft(
        (a ?? []).reduce((acc, item) => {
          acc[item.id] = item.stage;
          return acc;
        }, {})
      );
      const hasCurrentCommSelection = (a ?? []).some((item) => item.id === selectedCommAppId);
      if (!hasCurrentCommSelection) {
        setSelectedCommAppId(a?.[0]?.id ?? null);
      }
      const resume = (r ?? [])[0];
      if (resume?.id) {
        const detail = await apiFetch(`/resumes/${resume.id}`);
        setLatestResume(detail);
      } else {
        setLatestResume(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    loadCandidateData();
  }, [candidateId]);

  useEffect(() => {
    if (!selectedCommAppId) return;
    apiFetch(`/communications/application/${selectedCommAppId}`)
      .then((rows) => setCommHistory(rows ?? []))
      .catch(() => setCommHistory([]));
  }, [selectedCommAppId]);

  const topApp = useMemo(() => {
    return apps.slice().sort((x, y) => (y.score ?? 0) - (x.score ?? 0))[0] ?? null;
  }, [apps]);

  const runAction = async (appId, endpoint) => {
    setBusyAppId(appId);
    setError(null);
    try {
      await apiFetch(`/applications/${appId}/${endpoint}`, { method: 'POST' });
      await loadCandidateData();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyAppId(null);
    }
  };

  const changeStage = async (appId) => {
    const toStage = stageDraft[appId];
    if (!toStage) return;
    setBusyAppId(appId);
    setError(null);
    try {
      await apiFetch(`/applications/${appId}/stage`, {
        method: 'PATCH',
        body: {
          to_stage: toStage,
          note: 'Atualizado manualmente na tela de detalhes',
        },
      });
      await loadCandidateData();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyAppId(null);
    }
  };

  const sendCommunication = async () => {
    if (!selectedCommAppId) return;
    setBusyCommunication(true);
    setError(null);
    try {
      await apiFetch(`/communications/application/${selectedCommAppId}/send-template`, {
        method: 'POST',
        body: {
          channel: commChannel,
          template_name: commTemplate,
          body: commBody || undefined,
          created_by: 'RH',
        },
      });
      const rows = await apiFetch(`/communications/application/${selectedCommAppId}`);
      setCommHistory(rows ?? []);
      setCommBody('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyCommunication(false);
    }
  };

  const scheduleInterview = async () => {
    if (!selectedCommAppId || !interviewAt) return;
    setBusyCommunication(true);
    setError(null);
    try {
      await apiFetch(`/communications/application/${selectedCommAppId}/schedule-interview`, {
        method: 'POST',
        body: {
          channel: commChannel,
          template_name: 'convite_entrevista',
          interview_at: new Date(interviewAt).toISOString(),
          location: interviewLocation,
          auto_reminders: true,
          created_by: 'RH',
        },
      });
      const rows = await apiFetch(`/communications/application/${selectedCommAppId}`);
      setCommHistory(rows ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyCommunication(false);
    }
  };

  if (error) {
    return (
      <SectionCard title="Erro" subtitle={error}>
        <Button onClick={() => navigate('/candidatos')}>Voltar</Button>
      </SectionCard>
    );
  }

  if (!candidate) {
    return <div className="card-surface p-4 text-sm text-slatewarm-300">Carregando…</div>;
  }

  return (
    <div className="space-y-5">
      <section className="card-surface p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <img
              src={avatarDataUri(candidate.full_name)}
              alt={candidate.full_name}
              className="h-16 w-16 rounded-full border border-slatewarm-700"
            />
            <div>
              <p className="text-2xl font-bold text-slatewarm-50">{candidate.full_name}</p>
              <p className="text-sm text-slatewarm-300">
                {topApp?.job_title ?? '—'} • {topApp?.stage ?? '—'} • Score {Math.round(topApp?.score ?? 0)}%
              </p>
              {topApp?.stage ? (
                <div className="mt-3">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slatewarm-300">Etapa atual</span>
                  <StatusBadge stage={topApp.stage} />
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => navigate('/pipeline')}>
              Ver pipeline
            </Button>
            <Button variant="outline" onClick={() => navigate('/candidatos')}>
              Voltar
            </Button>
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
            <p className="text-xs font-semibold text-slatewarm-300">Email</p>
            <p className="mt-1 flex items-center gap-2 text-sm font-semibold text-slatewarm-50">
              <Mail size={14} /> {latestResume?.candidate_email ?? candidate.email ?? 'Não informado'}
            </p>
          </div>
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
            <p className="text-xs font-semibold text-slatewarm-300">Telefone</p>
            <p className="mt-1 flex items-center gap-2 text-sm font-semibold text-slatewarm-50">
              <Phone size={14} /> {latestResume?.candidate_phone ?? candidate.phone ?? 'Não informado'}
            </p>
          </div>
          <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
            <p className="text-xs font-semibold text-slatewarm-300">Cadastro</p>
            <p className="mt-1 text-sm font-semibold text-slatewarm-50">{formatDate(candidate.created_at)}</p>
          </div>
        </div>
      </section>

      <SectionCard title="Resumo profissional" subtitle="Extraído automaticamente do currículo mais recente">
        <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
          <div className="whitespace-pre-wrap text-sm text-slatewarm-200">
            {latestResume?.professional_summary ?? 'Não informado'}
          </div>
          {latestResume?.warnings?.length ? (
            <div className="mt-3 text-xs text-amber-200">{latestResume.warnings.join('\n')}</div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="Candidaturas" subtitle="Vagas vinculadas a este candidato">
        <div className="space-y-3">
          {apps.map((a) => (
            <div key={a.id} className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slatewarm-50">{a.job_title}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge stage={a.stage} />
                    <span className="text-xs text-slatewarm-300">
                      {a.seniority} • Exp {a.experience_years ?? '-'}a
                    </span>
                  </div>
                </div>
                <div className="rounded-full bg-brand-900/30 px-3 py-1 text-xs font-semibold text-brand-100">
                  {Math.round(a.score ?? 0)}%
                </div>
              </div>
              {a.score_justification ? (
                <div className="mt-3 text-xs text-slatewarm-200">{a.score_justification}</div>
              ) : null}
              <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto]">
                <select
                  value={stageDraft[a.id] ?? a.stage}
                  onChange={(e) => setStageDraft((prev) => ({ ...prev, [a.id]: e.target.value }))}
                  className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
                >
                  {STAGE_OPTIONS.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage}
                    </option>
                  ))}
                </select>
                <Button variant="secondary" disabled={busyAppId === a.id} onClick={() => changeStage(a.id)}>
                  Salvar etapa
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="secondary" disabled={busyAppId === a.id} onClick={() => runAction(a.id, 'advance')}>
                  Próxima etapa
                </Button>
                <Button variant="secondary" disabled={busyAppId === a.id} onClick={() => runAction(a.id, 'approve')}>
                  Aprovar
                </Button>
                <Button variant="danger" disabled={busyAppId === a.id} onClick={() => runAction(a.id, 'dismiss')}>
                  Dispensar
                </Button>
                <Button variant="outline" disabled={busyAppId === a.id} onClick={() => runAction(a.id, 'talent-pool')}>
                  Banco de talentos
                </Button>
              </div>
            </div>
          ))}
          {!apps.length && <div className="text-sm text-slatewarm-300">Nenhuma candidatura encontrada.</div>}
        </div>
      </SectionCard>

      <SectionCard title="Comunicação e agendamento" subtitle="Automação de mensagens e entrevistas por candidatura">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slatewarm-300">Candidatura</label>
            <select
              value={selectedCommAppId ?? ''}
              onChange={(e) => setSelectedCommAppId(Number(e.target.value))}
              className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
            >
              {apps.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.job_title} - {a.stage}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slatewarm-300">Canal</label>
            <select
              value={commChannel}
              onChange={(e) => setCommChannel(e.target.value)}
              className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
            >
              <option value="whatsapp">WhatsApp</option>
            </select>
          </div>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-[220px_1fr]">
          <select
            value={commTemplate}
            onChange={(e) => setCommTemplate(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          >
            <option value="atualizacao_etapa">Atualização de etapa</option>
            <option value="convite_entrevista">Convite de entrevista</option>
            <option value="feedback_reprovacao">Feedback de reprovação</option>
          </select>
          <input
            value={commBody}
            onChange={(e) => setCommBody(e.target.value)}
            placeholder="Mensagem personalizada (opcional)"
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={busyCommunication || !selectedCommAppId} onClick={sendCommunication}>
            Enviar mensagem
          </Button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <input
            type="datetime-local"
            value={interviewAt}
            onChange={(e) => setInterviewAt(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
          />
          <input
            value={interviewLocation}
            onChange={(e) => setInterviewLocation(e.target.value)}
            className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50"
            placeholder="Local da entrevista"
          />
          <Button variant="outline" disabled={busyCommunication || !selectedCommAppId || !interviewAt} onClick={scheduleInterview}>
            Agendar entrevista
          </Button>
        </div>

        <div className="mt-5 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slatewarm-300">Histórico de comunicações</div>
          {commHistory.map((item) => (
            <div key={item.id} className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slatewarm-50">
                  {item.event_type} • {item.channel}
                </div>
                <div className="text-xs text-slatewarm-300">{item.status} • {formatDate(item.scheduled_for ?? item.created_at)}</div>
              </div>
              {item.subject ? <div className="mt-1 text-xs text-brand-200">{item.subject}</div> : null}
              <div className="mt-1 text-xs text-slatewarm-200">{item.body}</div>
            </div>
          ))}
          {!commHistory.length && <div className="text-sm text-slatewarm-300">Sem comunicações registradas para esta candidatura.</div>}
        </div>
      </SectionCard>
    </div>
  );
}

export default CandidateDetailsPage;
