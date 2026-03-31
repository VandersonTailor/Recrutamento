import { mockApiFetch } from '../data/mockApi';

const AUTH_STORAGE_KEY = 'recruitflow_auth';

function getPrimaryStorage() {
  if (typeof window === 'undefined') return null;
  return window.sessionStorage;
}

function getLegacyStorage() {
  if (typeof window === 'undefined') return null;
  return window.localStorage;
}

export function getApiBaseUrl() {
  const fromEnv = String(import.meta.env.VITE_API_URL ?? '').trim();
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8091/api/v1`;
  }
  return 'http://127.0.0.1:8091/api/v1';
}

export function getApiKey() {
  return import.meta.env.VITE_API_KEY;
}

export function getApiRole() {
  const role = String(import.meta.env.VITE_USER_ROLE ?? '').trim().toLowerCase();
  if (['viewer', 'recruiter', 'manager', 'admin'].includes(role)) return role;
  // Default operacional para ambiente local MVP
  return 'admin';
}

export function getAuthSession() {
  try {
    const storage = getPrimaryStorage();
    const legacy = getLegacyStorage();
    const raw = storage?.getItem(AUTH_STORAGE_KEY) || legacy?.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed;
  } catch {
    return null;
  }
}

export function getAuthToken() {
  const session = getAuthSession();
  return session?.access_token || null;
}

export function saveAuthSession(session) {
  if (!session) return;
  const storage = getPrimaryStorage();
  const legacy = getLegacyStorage();
  storage?.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  legacy?.removeItem(AUTH_STORAGE_KEY);
}

export function clearAuthSession() {
  const storage = getPrimaryStorage();
  const legacy = getLegacyStorage();
  storage?.removeItem(AUTH_STORAGE_KEY);
  legacy?.removeItem(AUTH_STORAGE_KEY);
}

export function isUsingMockApi() {
  const forceMock = String(import.meta.env.VITE_USE_MOCK ?? '').toLowerCase();
  if (forceMock === 'true') return true;
  if (forceMock === 'false') return false;
  return false;
}

function parseErrorMessage(status, rawText) {
  let payload = null;
  try {
    payload = JSON.parse(rawText);
  } catch {
    payload = null;
  }

  if (payload && Array.isArray(payload.detail) && payload.detail.length) {
    const first = payload.detail[0];
    if (first?.type === 'missing' && Array.isArray(first.loc) && first.loc.length >= 2) {
      const source = String(first.loc[0] || '');
      const field = String(first.loc[first.loc.length - 1] || '');
      if (source === 'query') return `Campo obrigatório ausente na URL: ${field}.`;
      if (source === 'body') return `Campo obrigatório ausente no formulário: ${field}.`;
      return `Campo obrigatório ausente: ${field}.`;
    }
    if (first?.msg) return String(first.msg);
  }

  if (payload && typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail;
  }

  if (status === 404) return 'Recurso não encontrado.';
  if (status === 403) return 'Acesso negado para esta ação.';
  if (status === 422) return 'Dados inválidos para esta operação.';
  if (status >= 500) return 'Erro interno no servidor.';
  return rawText || `Erro na requisição (${status}).`;
}

export async function apiFetch(path, options = {}) {
  if (isUsingMockApi()) {
    return mockApiFetch(path, options);
  }

  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new Error('VITE_API_URL não configurada para API real.');
  }

  const base = baseUrl.replace(/\/$/, '');
  const url = `${base}/${String(path).replace(/^\//, '')}`;

  const headers = {};
  const apiKey = getApiKey();
  if (apiKey) headers['X-API-Key'] = apiKey;
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  headers['X-User-Role'] = getApiRole();
  if (options.body) headers['Content-Type'] = 'application/json';

  let res;
  try {
    res = await fetch(url, {
      method: options.method ?? 'GET',
      headers: Object.keys(headers).length ? headers : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: 'include',
    });
  } catch (error) {
    const fallbackOnFailure = String(import.meta.env.VITE_FALLBACK_TO_MOCK ?? 'false').toLowerCase() !== 'false';
    if (fallbackOnFailure) {
      return mockApiFetch(path, options);
    }
    throw error;
  }

  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) {
      clearAuthSession();
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    const msg = parseErrorMessage(res.status, text);
    throw new Error(`API ${res.status}: ${msg}`);
  }

  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return res.json();
  return res.text();
}
