import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Eye, EyeOff, Loader2, Lock, User } from 'lucide-react';
import { Navigate, useNavigate } from 'react-router-dom';
import Button from '../components/ui/Button';
import AuthField from '../components/auth/AuthField';
import { apiFetch, getAuthSession, saveAuthSession } from '../services/api';

const MAX_ATTEMPTS = 5;
const LOCK_SECONDS = 30;

function sanitizeInput(value) {
  return String(value || '')
    .replace(/[\u0000-\u001F\u007F]/g, '')
    .trim();
}

function LoginPage() {
  const navigate = useNavigate();
  const existingSession = getAuthSession();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | loading | success
  const [error, setError] = useState(null);
  const [attempts, setAttempts] = useState(0);
  const [lockUntil, setLockUntil] = useState(0);
  const [nowTick, setNowTick] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const isLocked = useMemo(() => lockUntil > nowTick, [lockUntil, nowTick]);
  const lockSecondsLeft = useMemo(() => Math.max(0, Math.ceil((lockUntil - nowTick) / 1000)), [lockUntil, nowTick]);

  if (existingSession?.authenticated || existingSession?.access_token) {
    return <Navigate to="/dashboard" replace />;
  }

  const isUsernameValid = /^[a-zA-Z0-9._@-]{3,80}$/.test(sanitizeInput(username));
  const isPasswordValid = password.length >= 8 && password.length <= 120;
  const canSubmit = !isLocked && isUsernameValid && isPasswordValid && status !== 'loading';
  const forgotPasswordHref = useMemo(() => {
    const normalizedUser = sanitizeInput(username);
    const subject = encodeURIComponent('Recuperação de senha - Recrutamento Carris');
    const body = encodeURIComponent(
      [
        'Olá, equipe de TI da Carris.',
        '',
        'Solicito a recuperação/redefinição da minha senha de acesso ao sistema Recrutamento Carris.',
        '',
        `Usuário informado: ${normalizedUser || '(não informado)'}`,
        '',
        'Obrigado(a).',
      ].join('\n'),
    );
    return `mailto:grupoinformatica@carris.com.br?subject=${subject}&body=${body}`;
  }, [username]);

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setStatus('loading');
    setError(null);
    try {
      const payload = {
        username: sanitizeInput(username),
        password,
      };
      const result = await apiFetch('/auth/login', {
        method: 'POST',
        body: payload,
      });
      setStatus('success');
      saveAuthSession({
        authenticated: true,
        expires_at: result?.expires_at,
        user: result?.user || null,
      });
      setPassword('');
      setTimeout(() => navigate('/dashboard', { replace: true }), 350);
    } catch {
      const nextAttempts = attempts + 1;
      setAttempts(nextAttempts);
      setPassword('');
      setStatus('idle');
      setError('Não foi possível autenticar. Verifique suas credenciais e tente novamente.');
      if (nextAttempts >= MAX_ATTEMPTS) {
        setLockUntil(Date.now() + LOCK_SECONDS * 1000);
        setAttempts(0);
      }
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-slatewarm-900">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-20 -left-20 h-72 w-72 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute top-1/3 -right-16 h-80 w-80 rounded-full bg-cyan-500/15 blur-3xl" />
        <div className="absolute -bottom-24 left-1/3 h-80 w-80 rounded-full bg-emerald-500/15 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:28px_28px] opacity-20" />
      </div>

      <div className="relative z-10 flex min-h-screen items-center justify-center p-4">
        <div className="w-full max-w-md rounded-xl2 border border-slatewarm-700/80 bg-slatewarm-900/75 p-6 shadow-soft backdrop-blur-xl md:p-7">
          <div className="mb-6 flex items-center gap-3">
            <img src="/logo.png" alt="Logo Carris" className="h-12 w-12 rounded-full border border-slatewarm-700 bg-slatewarm-950 p-0.5 ring-1 ring-brand-400/25" />
            <div>
              <h1 className="text-lg font-bold tracking-[0.02em] text-slatewarm-50">Recrutamento Carris</h1>
              <p className="text-xs leading-relaxed tracking-[0.01em] text-slatewarm-300">Acesso ao painel corporativo</p>
            </div>
          </div>

          {error ? (
            <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {isLocked ? (
            <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              Muitas tentativas em sequência. Aguarde {lockSecondsLeft}s para tentar novamente.
            </div>
          ) : null}

          <form className="space-y-3" onSubmit={submit} noValidate>
            <AuthField
              icon={User}
              value={username}
              onChange={(e) => setUsername(sanitizeInput(e.target.value))}
              placeholder="Usuário corporativo"
              autoComplete="username"
              disabled={status === 'loading' || isLocked}
              invalid={Boolean(username) && !isUsernameValid}
            />

            <AuthField
              icon={Lock}
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value.replace(/[\u0000-\u001F\u007F]/g, ''))}
              placeholder="Senha"
              autoComplete="current-password"
              disabled={status === 'loading' || isLocked}
              invalid={Boolean(password) && !isPasswordValid}
              rightAction={
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="text-slatewarm-300 transition hover:text-slatewarm-100"
                  aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              }
            />

            <div className="flex items-center justify-between pt-1">
              <a
                href={forgotPasswordHref}
                className="text-xs text-brand-200 transition hover:text-brand-100 hover:underline"
              >
                Esqueci minha senha
              </a>
              <span className="text-[11px] text-slatewarm-400">Sessão segura</span>
            </div>

            <Button type="submit" disabled={!canSubmit} className="w-full">
              {status === 'loading' ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  Validando acesso...
                </span>
              ) : status === 'success' ? (
                'Acesso autorizado'
              ) : (
                'Entrar'
              )}
            </Button>
          </form>

        </div>
      </div>
    </div>
  );
}

export default LoginPage;
