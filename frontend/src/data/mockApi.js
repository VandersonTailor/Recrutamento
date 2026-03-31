import { candidates, entriesByPeriod, jobVolume } from './mockData';

const createdJobs = [];
const createdCommunicationEvents = [];

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase();
}

function unique(values) {
  return [...new Set(values)];
}

function serializeCsv(items) {
  const header = 'candidate_id,candidate_name,job,score,level,origin,stage,received_at';
  const lines = items.map((item) =>
    [
      item.candidate_id,
      `"${String(item.candidate_name ?? '').replaceAll('"', '""')}"`,
      `"${String(item.job_title ?? '').replaceAll('"', '""')}"`,
      item.match_percent ?? item.score ?? 0,
      `"${String(item.seniority ?? '').replaceAll('"', '""')}"`,
      `"${String(item.department ?? '').replaceAll('"', '""')}"`,
      `"${String(item.stage ?? '').replaceAll('"', '""')}"`,
      item.created_at ?? '',
    ].join(',')
  );
  return [header, ...lines].join('\n');
}

function buildJobs() {
  const inferred = unique(candidates.map((candidate) => candidate.job)).map((jobTitle, index) => ({
    id: index + 1,
    title: jobTitle,
    department: 'Talent',
    is_active: true,
  }));
  return [...inferred, ...createdJobs];
}

function buildApplications() {
  const jobs = buildJobs();
  return candidates.map((candidate, index) => {
    const job = jobs.find((item) => item.title === candidate.job);
    const createdAt = `${candidate.receivedAt}T09:00:00.000Z`;
    const updatedAt = `${candidate.receivedAt}T14:00:00.000Z`;
    return {
      id: index + 1,
      candidate_id: candidate.id,
      candidate_name: candidate.name,
      job_id: job?.id ?? 1,
      job_title: candidate.job,
      seniority: candidate.level,
      score: candidate.score,
      department: candidate.origin,
      stage: candidate.stage,
      created_at: createdAt,
      updated_at: updatedAt,
      experience_years: candidate.level === 'Sênior' ? 8 : candidate.level === 'Pleno' ? 5 : 2,
      strengths: candidate.strengths,
      score_justification: candidate.scoreReason,
    };
  });
}

function buildResumes() {
  return candidates.map((candidate, index) => ({
    id: index + 100,
    candidate_id: candidate.id,
    candidate_name: candidate.name,
    department: candidate.origin,
    original_filename: `${candidate.name.toLowerCase().replaceAll(' ', '_')}.pdf`,
    received_at: `${candidate.receivedAt}T09:00:00.000Z`,
    candidate_email: candidate.email,
    candidate_phone: candidate.phone,
    candidate_address: 'São Paulo, Brasil',
    professional_summary: candidate.summary,
    warnings: candidate.attentionPoints ?? [],
    strengths: candidate.strengths ?? [],
    linkedin: `https://linkedin.com/in/${candidate.name.toLowerCase().replaceAll(' ', '-')}`,
    extraction_confidence: 0.72,
    requires_manual_review: index % 4 === 0,
    review_reason: index % 4 === 0 ? 'contato_ausente;experiencia_nao_detectada' : null,
    structured_json: JSON.stringify({
      fields: {
        nome: candidate.name,
        contato: { email: candidate.email, telefone: candidate.phone },
        classificacao_cargo: { primary_role: candidate.job, confidence: 0.72, secondary_roles: [] },
      },
      quality: {
        confidence: 0.72,
        field_confidence: { contato: 0.9, classificacao_cargo: 0.72 },
        requires_manual_review: index % 4 === 0,
        review_reason: index % 4 === 0 ? 'contato_ausente;experiencia_nao_detectada' : null,
      },
    }),
  }));
}

function buildDashboard(applications) {
  const jobs = buildJobs();
  const stageFlow = ['Recebido', 'Em análise', 'Pré-selecionado', 'Entrevista', 'Teste técnico', 'Aprovado'];
  const applicationsByStage = unique(applications.map((app) => app.stage)).map((stage) => ({
    stage,
    count: applications.filter((app) => app.stage === stage).length,
  }));
  const resumesByChannel = unique(applications.map((app) => app.department)).map((channel) => ({
    channel,
    count: applications.filter((app) => app.department === channel).length,
  }));
  const resumesByJob = unique(applications.map((app) => app.job_title)).map((jobTitle) => ({
    job_title: jobTitle,
    count: applications.filter((app) => app.job_title === jobTitle).length,
  }));
  const funnelByStage = stageFlow.map((stage, idx) => {
    const entered = applicationsByStage.find((row) => row.stage === stage)?.count ?? 0;
    const nextStage = stageFlow[idx + 1];
    const advanced = nextStage ? Math.min(entered, applicationsByStage.find((row) => row.stage === nextStage)?.count ?? 0) : 0;
    const conversionRate = entered ? Number(((advanced / entered) * 100).toFixed(2)) : 0;
    const dropoffRate = entered ? Number((Math.max(0, (entered - advanced) / entered) * 28).toFixed(2)) : 0;
    const talentPoolRate = entered ? Number((Math.max(0, (entered - advanced) / entered) * 18).toFixed(2)) : 0;
    const avgHours = entered ? Number((10 + idx * 7.5).toFixed(1)) : null;
    return {
      stage,
      next_stage: nextStage ?? null,
      entered,
      advanced,
      conversion_rate: conversionRate,
      dropoff_rate: dropoffRate,
      talent_pool_rate: talentPoolRate,
      avg_time_to_next_hours: avgHours,
    };
  });

  return {
    total_resumes: applications.length,
    total_open_jobs: jobs.filter((job) => job.is_active).length,
    applications_by_stage: applicationsByStage,
    conversion_by_stage: applicationsByStage.map((row) => ({
      stage: row.stage,
      count: row.count,
      rate: Number(((row.count / Math.max(1, applications.length)) * 100).toFixed(2)),
    })),
    funnel_by_stage: funnelByStage,
    resumes_by_channel: resumesByChannel,
    resumes_by_job: resumesByJob.length ? resumesByJob : jobVolume.map((item) => ({ job_title: item.job, count: item.total })),
    monthly_performance: entriesByPeriod.map((row) => ({ month: row.name, approved: row.total })),
  };
}

function buildDiagnostics(resumes) {
  const pending = resumes.filter((r) => r.requires_manual_review).length;
  const over24 = Math.floor(pending * 0.6);
  const over72 = Math.floor(pending * 0.25);
  return {
    total_processing_logs: 240,
    processing_success_rate: 93.4,
    processing_avg_duration_ms: 1840,
    processing_p95_duration_ms: 4200,
    resumes_missing_in_storage: 0,
    resumes_with_extracted_text: resumes.length,
    extraction_coverage_rate: 97.8,
    resumes_requires_manual_review: pending,
    manual_review_rate: Number(((pending / Math.max(1, resumes.length)) * 100).toFixed(2)),
    review_pending_over_24h: over24,
    review_pending_over_72h: over72,
    avg_review_resolution_hours: 18.7,
    candidates_with_email: resumes.filter((r) => r.candidate_email).length,
    candidates_with_phone: resumes.filter((r) => r.candidate_phone).length,
    candidates_with_contact_rate: 95.2,
  };
}

function queryList(items, query) {
  return items
    .filter((item) => {
      if (query.get('candidate_id') && String(item.candidate_id) !== query.get('candidate_id')) return false;
      if (query.get('job_id') && String(item.job_id) !== query.get('job_id')) return false;
      if (query.get('department') && normalizeText(item.department) !== normalizeText(query.get('department'))) return false;
      if (query.get('seniority') && normalizeText(item.seniority) !== normalizeText(query.get('seniority'))) return false;
      if (query.get('min_score') && Number(item.score ?? 0) < Number(query.get('min_score'))) return false;
      if (query.get('q') && !normalizeText(item.candidate_name).includes(normalizeText(query.get('q')))) return false;
      if (query.get('cargo') && !normalizeText(item.job_title).includes(normalizeText(query.get('cargo')))) return false;
      if (query.get('date_from') && new Date(item.created_at) < new Date(query.get('date_from'))) return false;
      if (query.get('date_to') && new Date(item.created_at) > new Date(query.get('date_to'))) return false;
      return true;
    })
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

const STAGE_SLA_HOURS = {
  Recebido: 24,
  'Em análise': 48,
  'Pré-selecionado': 72,
  Entrevista: 120,
  'Teste técnico': 96,
};

function withStageSla(item) {
  const sla = STAGE_SLA_HOURS[item.stage];
  if (!sla) {
    return { ...item, stage_sla_hours: null, stage_elapsed_hours: null, stage_overdue: null, stage_overdue_hours: null };
  }
  const enteredAt = item.updated_at ?? item.created_at;
  const elapsed = Math.max(0, Math.floor((Date.now() - new Date(enteredAt).getTime()) / 3600000));
  const overdue = elapsed > sla;
  return {
    ...item,
    stage_entered_at: enteredAt,
    stage_sla_hours: sla,
    stage_elapsed_hours: elapsed,
    stage_overdue: overdue,
    stage_overdue_hours: Math.max(0, elapsed - sla),
  };
}

function buildMockAudit(jobId, query) {
  const applications = buildApplications().filter((app) => app.job_id === jobId);
  const resumes = buildResumes();

  const decisions = ['approved', 'rejected', 'promoted'];
  let feedbackEvents = applications.slice(0, 6).map((app, index) => {
    const decision = decisions[index % decisions.length];
    const createdAt = new Date(new Date(app.updated_at).getTime() - index * 3600_000).toISOString();
    const beforeProfile = {
      weights: { cargo: 0.3, formacao: 0.2, cursos: 0.25, experiencia: 0.25 },
      porto_alegre_bonus: 8,
      minimum_signal_floor: 12,
    };
    const afterProfile = {
      weights: {
        cargo: decision === 'approved' ? 0.33 : decision === 'rejected' ? 0.28 : 0.31,
        formacao: decision === 'rejected' ? 0.22 : 0.19,
        cursos: decision === 'promoted' ? 0.27 : 0.24,
        experiencia: decision === 'approved' ? 0.26 : 0.25,
      },
      porto_alegre_bonus: decision === 'approved' ? 9 : 8,
      minimum_signal_floor: decision === 'rejected' ? 13 : 12,
    };
    return {
      id: index + 1,
      created_at: createdAt,
      actor: 'rh@carris.com.br',
      application_id: app.id,
      decision,
      note: `Feedback simulado para ${app.candidate_name}`,
      before_profile: beforeProfile,
      after_profile: afterProfile,
    };
  });

  const decisionFilter = normalizeText(query.get('decision'));
  if (decisionFilter) {
    feedbackEvents = feedbackEvents.filter((event) => normalizeText(event.decision) === decisionFilter);
  }
  if (query.get('application_id')) {
    feedbackEvents = feedbackEvents.filter((event) => String(event.application_id) === String(query.get('application_id')));
  }
  if (query.get('date_from')) {
    const from = new Date(query.get('date_from')).getTime();
    feedbackEvents = feedbackEvents.filter((event) => new Date(event.created_at).getTime() >= from);
  }
  if (query.get('date_to')) {
    const to = new Date(query.get('date_to')).getTime();
    feedbackEvents = feedbackEvents.filter((event) => new Date(event.created_at).getTime() <= to);
  }

  const rankingRows = queryList(
    applications.map((app) => ({
      ...app,
      job_title: app.job_title,
      candidate_name: app.candidate_name,
      score: app.score,
    })),
    query
  );

  const rankingSnapshot = rankingRows.slice(0, Number(query.get('snapshot_limit') ?? 50)).map((app, index) => {
    const resume = resumes.find((item) => item.candidate_id === app.candidate_id);
    return {
      application_id: app.id,
      candidate_id: app.candidate_id,
      candidate_name: app.candidate_name,
      match_percent: app.score,
      rank_position: index + 1,
      rank_reason: index === 0 ? 'Maior aderência geral da vaga' : 'Posição calculada pelo desempate empresarial',
      role_confidence: 0.7,
      role_needs_review: false,
      primary_role: app.job_title,
      email: resume?.candidate_email ?? '',
      phone: resume?.candidate_phone ?? '',
    };
  });

  return {
    job_id: jobId,
    current_profile: {
      role_hint: 'Motorista',
      weights: { cargo: 0.33, formacao: 0.18, cursos: 0.22, experiencia: 0.27 },
      porto_alegre_bonus: 8,
      minimum_signal_floor: 12,
    },
    feedback_events: feedbackEvents.slice(0, Number(query.get('limit_events') ?? 50)),
    ranking_snapshot: rankingSnapshot,
  };
}

function serializeAuditCsv(payload) {
  const header = 'record_type,job_id,event_id,created_at,application_id,decision,note,candidate_id,candidate_name,rank_position,match_percent,rank_reason';
  const eventLines = (payload.feedback_events ?? []).map((event) =>
    [
      'feedback_event',
      payload.job_id,
      event.id,
      event.created_at,
      event.application_id ?? '',
      event.decision ?? '',
      `"${String(event.note ?? '').replaceAll('"', '""')}"`,
      '',
      '',
      '',
      '',
      '',
    ].join(',')
  );
  const rankLines = (payload.ranking_snapshot ?? []).map((item) =>
    [
      'ranking_snapshot',
      payload.job_id,
      '',
      '',
      item.application_id ?? '',
      '',
      '',
      item.candidate_id ?? '',
      `"${String(item.candidate_name ?? '').replaceAll('"', '""')}"`,
      item.rank_position ?? '',
      item.match_percent ?? '',
      `"${String(item.rank_reason ?? '').replaceAll('"', '""')}"`,
    ].join(',')
  );
  return [header, ...eventLines, ...rankLines].join('\n');
}

function nextCommunicationId() {
  const maxPersisted = createdCommunicationEvents.reduce((acc, item) => Math.max(acc, Number(item.id ?? 0)), 0);
  return maxPersisted + 1;
}

function findApplicationContext(applications, resumes, applicationId) {
  const app = applications.find((item) => Number(item.id) === Number(applicationId));
  if (!app) return null;
  const resume = resumes.find((item) => item.candidate_id === app.candidate_id);
  return { app, resume };
}

export async function mockApiFetch(path, options = {}) {
  const [rawPath, rawQuery = ''] = String(path).split('?');
  const routePath = `/${rawPath.replace(/^\/+/, '')}`;
  const query = new URLSearchParams(rawQuery);
  const method = String(options.method ?? 'GET').toUpperCase();

  const applications = buildApplications();
  const resumes = buildResumes();

  if (routePath === '/dashboard' && method === 'GET') return buildDashboard(applications);
  if (routePath === '/dashboard/diagnostics' && method === 'GET') return buildDiagnostics(resumes);
  if (routePath === '/applications' && method === 'GET') return queryList(applications, query).map(withStageSla);
  if (routePath === '/applications/sla-alerts' && method === 'GET') {
    const scoped = queryList(applications, query).map(withStageSla);
    const overdueCount = scoped.filter((item) => item.stage_overdue).length;
    const dueSoonCount = scoped.filter((item) => !item.stage_overdue && typeof item.stage_sla_hours === 'number' && (item.stage_sla_hours - item.stage_elapsed_hours) <= 8).length;
    const onlyOverdue = query.get('only_overdue') === 'true';
    return {
      total_in_scope: scoped.length,
      overdue_count: overdueCount,
      due_soon_count: dueSoonCount,
      items: onlyOverdue ? scoped.filter((item) => item.stage_overdue) : scoped,
    };
  }
  if (/^\/communications\/application\/\d+$/.test(routePath) && method === 'GET') {
    const applicationId = Number(routePath.split('/')[3]);
    return createdCommunicationEvents
      .filter((item) => Number(item.application_id) === applicationId)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }
  if (/^\/communications\/application\/\d+\/send-template$/.test(routePath) && method === 'POST') {
    const applicationId = Number(routePath.split('/')[3]);
    const context = findApplicationContext(applications, resumes, applicationId);
    if (!context) throw new Error(`API 404: Application ${applicationId} não encontrada`);
    const nowIso = new Date().toISOString();
    const event = {
      id: nextCommunicationId(),
      application_id: applicationId,
      channel: options.body?.channel ?? 'email',
      event_type: 'message',
      status: options.body?.send_at ? 'planned' : 'sent',
      template_name: options.body?.template_name ?? null,
      subject: options.body?.subject ?? `Atualização de etapa - ${context.app.job_title}`,
      body:
        options.body?.body ??
        `Olá ${context.app.candidate_name}, sua candidatura para ${context.app.job_title} está na etapa ${context.app.stage}.`,
      payload_json: JSON.stringify({ variables: options.body?.variables ?? {} }),
      scheduled_for: options.body?.send_at ?? nowIso,
      sent_at: options.body?.send_at ? null : nowIso,
      created_by: options.body?.created_by ?? 'RH',
      created_at: nowIso,
    };
    createdCommunicationEvents.push(event);
    return event;
  }
  if (/^\/communications\/application\/\d+\/schedule-interview$/.test(routePath) && method === 'POST') {
    const applicationId = Number(routePath.split('/')[3]);
    const context = findApplicationContext(applications, resumes, applicationId);
    if (!context) throw new Error(`API 404: Application ${applicationId} não encontrada`);
    const nowIso = new Date().toISOString();
    const interviewAt = options.body?.interview_at ?? nowIso;
    const location = options.body?.location ?? 'Sede Carris';
    const channel = options.body?.channel ?? 'whatsapp';

    const invite = {
      id: nextCommunicationId(),
      application_id: applicationId,
      channel,
      event_type: 'interview_invite',
      status: 'sent',
      template_name: options.body?.template_name ?? 'convite_entrevista',
      subject: `Entrevista agendada - ${context.app.job_title}`,
      body: `Olá ${context.app.candidate_name}, sua entrevista para ${context.app.job_title} foi agendada para ${interviewAt} em ${location}.`,
      payload_json: JSON.stringify({ interview_at: interviewAt, location }),
      scheduled_for: nowIso,
      sent_at: nowIso,
      created_by: options.body?.created_by ?? 'RH',
      created_at: nowIso,
    };
    createdCommunicationEvents.push(invite);

    const out = [invite];
    if (options.body?.auto_reminders !== false) {
      const reminder = {
        id: nextCommunicationId(),
        application_id: applicationId,
        channel,
        event_type: 'interview_reminder',
        status: 'planned',
        template_name: options.body?.template_name ?? 'convite_entrevista',
        subject: `Lembrete de entrevista - ${context.app.job_title}`,
        body: `Lembrete: entrevista para ${context.app.job_title} em ${interviewAt}.`,
        payload_json: JSON.stringify({ interview_at: interviewAt, location, type: 'reminder' }),
        scheduled_for: interviewAt,
        sent_at: null,
        created_by: options.body?.created_by ?? 'RH',
        created_at: nowIso,
      };
      createdCommunicationEvents.push(reminder);
      out.push(reminder);
    }
    return out;
  }
  if (routePath === '/communications/pending' && method === 'GET') {
    const dueInHours = Number(query.get('due_in_hours') ?? 24);
    const until = Date.now() + dueInHours * 3600 * 1000;
    const items = createdCommunicationEvents.filter((item) => item.status === 'planned' && new Date(item.scheduled_for).getTime() <= until);
    return { total: items.length, items };
  }
  if (routePath === '/communications/dispatch/stats' && method === 'GET') {
    const planned = createdCommunicationEvents.filter((item) => item.status === 'planned').length;
    const sent = createdCommunicationEvents.filter((item) => item.status === 'sent').length;
    const failed = createdCommunicationEvents.filter((item) => item.status === 'failed').length;
    const oldest = createdCommunicationEvents
      .filter((item) => item.status === 'planned')
      .sort((a, b) => new Date(a.scheduled_for).getTime() - new Date(b.scheduled_for).getTime())[0];
    return { planned, sent, failed, oldest_due_at: oldest?.scheduled_for ?? null };
  }
  if (routePath === '/communications/dispatch/run' && method === 'POST') {
    const limit = Number(query.get('limit') ?? 50);
    const now = Date.now();
    let processed = 0;
    let sent = 0;
    const items = [];
    for (const item of createdCommunicationEvents) {
      if (processed >= limit) break;
      if (item.status === 'planned' && new Date(item.scheduled_for).getTime() <= now) {
        item.status = 'sent';
        item.sent_at = new Date().toISOString();
        processed += 1;
        sent += 1;
        items.push({ id: item.id, status: 'sent', channel: item.channel, event_type: item.event_type });
      }
    }
    return { processed, sent, failed: 0, items };
  }
  if (routePath === '/jobs' && method === 'GET') return buildJobs();
  if (routePath === '/jobs' && method === 'POST') {
    const nextId = buildJobs().length + 1;
    createdJobs.push({
      id: nextId,
      title: options.body?.title ?? `Nova vaga ${nextId}`,
      department: options.body?.department ?? 'Talent',
      is_active: options.body?.is_active ?? true,
    });
    return createdJobs[createdJobs.length - 1];
  }
  if (routePath === '/departments' && method === 'GET') {
    return { items: unique(candidates.map((candidate) => candidate.origin)).map((department) => ({ department })) };
  }
  if (routePath === '/resumes' && method === 'GET') {
    let filtered = queryList(
      resumes.map((resume) => ({
        ...resume,
        job_title: candidates.find((candidate) => candidate.id === resume.candidate_id)?.job ?? '',
        score: candidates.find((candidate) => candidate.id === resume.candidate_id)?.score ?? 0,
        created_at: resume.received_at,
      })),
      query
    ).map((resume) => ({
      id: resume.id,
      candidate_id: resume.candidate_id,
      candidate_name: resume.candidate_name,
      department: resume.department,
      original_filename: resume.original_filename,
      received_at: resume.received_at,
      extraction_confidence: resume.extraction_confidence,
      requires_manual_review: resume.requires_manual_review,
      review_reason: resume.review_reason,
    }));
    if (query.get('requires_review') === 'true') {
      filtered = filtered.filter((r) => r.requires_manual_review);
    }
    const limit = Number(query.get('limit') ?? filtered.length);
    const offset = Number(query.get('offset') ?? 0);
    return filtered.slice(offset, offset + limit);
  }
  if (routePath === '/resumes/review-queue' && method === 'GET') {
    const rows = buildResumes().filter((r) => r.requires_manual_review);
    return rows.map((r) => ({
      id: r.id,
      candidate_id: r.candidate_id,
      candidate_name: r.candidate_name,
      department: r.department,
      original_filename: r.original_filename,
      received_at: r.received_at,
      extraction_confidence: r.extraction_confidence,
      requires_manual_review: r.requires_manual_review,
      review_reason: r.review_reason,
    }));
  }
  if (/^\/resumes\/\d+$/.test(routePath) && method === 'GET') {
    const resumeId = Number(routePath.split('/')[2]);
    const found = resumes.find((resume) => resume.id === resumeId);
    if (!found) throw new Error(`API 404: Resume ${resumeId} não encontrado`);
    return found;
  }
  if (/^\/resumes\/\d+\/structured$/.test(routePath) && method === 'PATCH') {
    const resumeId = Number(routePath.split('/')[2]);
    const found = resumes.find((resume) => resume.id === resumeId);
    if (!found) throw new Error(`API 404: Resume ${resumeId} não encontrado`);
    return {
      ...found,
      structured_json: JSON.stringify(options.body?.structured_json ?? {}),
      requires_manual_review: !options.body?.approve_review,
      review_reason: options.body?.review_reason ?? null,
      extraction_confidence: options.body?.extraction_confidence ?? found.extraction_confidence ?? 0.7,
    };
  }
  if (/^\/candidates\/[^/]+$/.test(routePath) && method === 'GET') {
    const candidateId = routePath.split('/')[2];
    const found = candidates.find((candidate) => String(candidate.id) === candidateId);
    if (!found) throw new Error(`API 404: Candidate ${candidateId} não encontrado`);
    return {
      id: found.id,
      full_name: found.name,
      email: found.email,
      phone: found.phone,
      created_at: `${found.receivedAt}T09:00:00.000Z`,
    };
  }
  if (/^\/jobs\/\d+\/ranking$/.test(routePath) && method === 'GET') {
    const jobId = Number(routePath.split('/')[2]);
    const apps = queryList(applications.filter((app) => app.job_id === jobId), query).slice(0, Number(query.get('limit') ?? 50));
    return {
      items: apps.map((app) => {
        const resume = resumes.find((item) => item.candidate_id === app.candidate_id);
        return {
          candidate_id: app.candidate_id,
          candidate_name: app.candidate_name,
          match_percent: app.score,
          match_breakdown: {
            cargo: Math.max(45, Math.min(100, app.score - 3)),
            formacao: Math.max(40, Math.min(100, app.score - 8)),
          },
          professional_summary: resume?.professional_summary ?? '',
          strengths: resume?.strengths ?? [],
          email: resume?.candidate_email ?? '',
          phone: resume?.candidate_phone ?? '',
          linkedin: resume?.linkedin ?? '',
          stage: app.stage,
          primary_role: app.job_title,
          secondary_roles: [],
          role_confidence: 0.74,
          role_needs_review: false,
          scoring_profile: {
            role_hint: app.job_title,
            weights: { cargo: 0.3, formacao: 0.2, cursos: 0.25, experiencia: 0.25 },
            porto_alegre_bonus: 8,
            minimum_signal_floor: 12,
          },
          job_title: app.job_title,
          seniority: app.seniority,
          department: app.department,
          created_at: app.created_at,
        };
      }),
    };
  }
  if (/^\/jobs\/\d+\/ranking\/export$/.test(routePath) && method === 'GET') {
    const jobId = Number(routePath.split('/')[2]);
    const apps = applications.filter((app) => app.job_id === jobId);
    return serializeCsv(apps);
  }
  if (/^\/jobs\/\d+\/ranking\/audit$/.test(routePath) && method === 'GET') {
    const jobId = Number(routePath.split('/')[2]);
    return buildMockAudit(jobId, query);
  }
  if (/^\/jobs\/\d+\/ranking\/audit\/export$/.test(routePath) && method === 'GET') {
    const jobId = Number(routePath.split('/')[2]);
    const payload = buildMockAudit(jobId, query);
    if (normalizeText(query.get('format')) === 'json') return payload;
    return serializeAuditCsv(payload);
  }
  if (
    routePath.startsWith('/jobs/') ||
    routePath === '/ingestion/scan' ||
    routePath === '/resumes/actions/cleanup_missing' ||
    routePath === '/ingestion/reconcile'
  ) {
    if (/^\/jobs\/\d+\/ranking-feedback$/.test(routePath) && method === 'POST') {
      return {
        job_id: Number(routePath.split('/')[2]),
        application_id: options.body?.application_id,
        decision: options.body?.decision,
        updated_profile: {
          role_hint: 'Motorista',
          weights: { cargo: 0.33, formacao: 0.18, cursos: 0.22, experiencia: 0.27 },
          porto_alegre_bonus: 8,
          minimum_signal_floor: 12,
          feedback_stats: { approved: 1, promoted: 0, rejected: 0 },
        },
      };
    }
    return { ok: true };
  }

  throw new Error(`API 404: Endpoint mock não implementado para ${routePath}`);
}
