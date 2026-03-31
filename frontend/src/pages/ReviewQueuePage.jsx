import { useEffect, useState } from 'react';
import SectionCard from '../components/ui/SectionCard';
import Button from '../components/ui/Button';
import { apiFetch } from '../services/api';

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

function ReviewQueuePage() {
  const [items, setItems] = useState([]);
  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [structuredDraft, setStructuredDraft] = useState('{}');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const loadQueue = async () => {
    const list = await apiFetch('/resumes/review-queue?limit=200');
    setItems(list ?? []);
  };

  useEffect(() => {
    loadQueue().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const save = async (approveReview) => {
    if (!detailId) return;
    setBusy(true);
    setError(null);
    try {
      const payload = JSON.parse(structuredDraft || '{}');
      const updated = await apiFetch(`/resumes/${detailId}/structured`, {
        method: 'PATCH',
        body: {
          structured_json: payload,
          approve_review: approveReview,
          extraction_confidence: detail?.extraction_confidence ?? null,
          review_reason: approveReview ? 'Revisado na fila manual' : (detail?.review_reason ?? 'Revisão pendente'),
        },
      });
      setDetail(updated);
      setStructuredDraft(JSON.stringify(parseStructuredJson(updated?.structured_json) ?? {}, null, 2));
      await loadQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reanalyzeStructured = async () => {
    if (!detailId) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/resumes/${detailId}/reanalyze`, { method: 'POST' });
      const refreshed = await apiFetch(`/resumes/${detailId}`);
      setDetail(refreshed);
      setStructuredDraft(JSON.stringify(parseStructuredJson(refreshed?.structured_json) ?? {}, null, 2));
      await loadQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      {error && <div className="card-surface p-4 text-sm text-red-200">Erro: {error}</div>}

      <SectionCard title="Fila de revisão manual" subtitle="Currículos com baixa confiança de extração">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm text-slatewarm-300">{items.length} pendentes</div>
          <Button variant="secondary" onClick={() => loadQueue()}>
            Atualizar fila
          </Button>
        </div>
        <div className="space-y-2">
          {items.map((r) => (
            <button key={r.id} onClick={() => openDetail(r.id)} className="w-full rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3 text-left transition hover:border-brand-400">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slatewarm-50">{r.candidate_name ?? `#${r.candidate_id}`}</div>
                  <div className="text-xs text-slatewarm-300">{r.department ?? '—'} • {r.original_filename ?? '—'}</div>
                  <div className="text-[11px] text-amber-200">{r.review_reason ?? 'Revisão pendente'}</div>
                </div>
                <div className="text-xs text-slatewarm-300">
                  {typeof r.extraction_confidence === 'number' ? `${Math.round(r.extraction_confidence * 100)}%` : '—'}
                </div>
              </div>
            </button>
          ))}
          {!items.length && <div className="text-sm text-slatewarm-300">Nenhum currículo pendente.</div>}
        </div>
      </SectionCard>

      {detailId !== null && (
        <div className="detailOverlay" onClick={() => { setDetailId(null); setDetail(null); }}>
          <div className="detailPanel" onClick={(e) => e.stopPropagation()}>
            <div className="detailHeader">
              <div>
                <div className="detailTitle">{detail?.candidate_name ?? `Currículo #${detailId}`}</div>
                <div className="detailSub">
                  Confiança: {typeof detail?.extraction_confidence === 'number' ? `${Math.round(detail.extraction_confidence * 100)}%` : '—'} •
                  Revisão: {detail?.requires_manual_review ? 'Pendente' : 'Concluída'}
                </div>
              </div>
              <Button variant="outline" onClick={() => { setDetailId(null); setDetail(null); }}>
                Fechar
              </Button>
            </div>

            {!detail && <div className="text-sm text-slatewarm-300">Carregando…</div>}
            {detail && (
              <div className="space-y-3">
                <div className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 p-3 text-sm text-slatewarm-100">
                  <div className="text-xs text-slatewarm-300">Resumo profissional</div>
                  <div className="whitespace-pre-wrap">{detail.professional_summary ?? 'Não informado'}</div>
                </div>
                <textarea
                  value={structuredDraft}
                  onChange={(e) => setStructuredDraft(e.target.value)}
                  className="min-h-[260px] w-full rounded-xl border border-slatewarm-700 bg-slatewarm-950 px-3 py-2 text-xs text-slatewarm-100"
                />
                <div className="flex gap-2">
                  <Button variant="outline" disabled={busy} onClick={reanalyzeStructured}>
                    Reprocessar JSON
                  </Button>
                  <Button variant="secondary" disabled={busy} onClick={() => save(false)}>
                    Enviar para revisão manual
                  </Button>
                  <Button disabled={busy} onClick={() => save(true)}>
                    Aprovar revisão
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ReviewQueuePage;
