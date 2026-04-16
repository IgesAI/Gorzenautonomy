import { useEffect, useState } from 'react';
import { AlertTriangle, Lock, Server, WifiOff, X } from 'lucide-react';
import { clsx } from 'clsx';
import { api, onApiError, tokenStore, type ApiError } from '../../api/client';

/**
 * Global backend health banner. Subscribes to `onApiError` so every API
 * failure (network, 401, 429, 503) surfaces as a single dismissible
 * notification in the upper right. Also runs a lightweight `/health`
 * poll so the banner can tell the operator when the backend is
 * unreachable *before* they click anything.
 */
export function BackendStatus() {
  const [banner, setBanner] = useState<ApiError | null>(null);
  const [dismissedAt, setDismissedAt] = useState<number>(0);
  const [probeFailed, setProbeFailed] = useState(false);
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    return onApiError((err) => {
      // Ignore the health probe itself — it already drives `probeFailed`.
      if (err.path === '/health') return;
      // Ignore stale errors the user already dismissed.
      if (err.at < dismissedAt) return;
      setBanner(err);
      if (err.kind === 'unauthorized') setShowLogin(true);
    });
  }, [dismissedAt]);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        await api.health.api();
        if (!cancelled) setProbeFailed(false);
      } catch {
        if (!cancelled) setProbeFailed(true);
      }
    };
    probe();
    const id = window.setInterval(probe, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (!banner && !probeFailed) return null;

  if (probeFailed && (!banner || banner.at < Date.now() - 30_000)) {
    return (
      <BannerShell
        icon={<WifiOff size={14} />}
        tone="danger"
        title="Backend unreachable"
        detail="The API at /api is not responding. Start the backend with `uvicorn gorzen.api.app:create_app --factory` and confirm port 8000."
        onDismiss={() => setProbeFailed(false)}
      />
    );
  }

  if (!banner) return null;

  const { kind, status, message, hint, path } = banner;
  const tone: 'warning' | 'danger' | 'info' =
    kind === 'unauthorized' ? 'warning' : kind === 'rate_limited' ? 'info' : 'danger';
  const icon =
    kind === 'unauthorized' ? (
      <Lock size={14} />
    ) : kind === 'database_unavailable' ? (
      <Server size={14} />
    ) : kind === 'rate_limited' ? (
      <AlertTriangle size={14} />
    ) : (
      <AlertTriangle size={14} />
    );
  const title =
    kind === 'unauthorized'
      ? 'Authentication required'
      : kind === 'database_unavailable'
      ? 'Database unavailable'
      : kind === 'rate_limited'
      ? 'Rate limited'
      : kind === 'network'
      ? 'Network error'
      : `Backend error ${status ?? ''}`.trim();

  return (
    <>
      <BannerShell
        icon={icon}
        tone={tone}
        title={title}
        detail={`${path} — ${message.slice(0, 200)}${hint ? ' · ' + hint : ''}`}
        onDismiss={() => {
          setBanner(null);
          setDismissedAt(Date.now());
        }}
        action={
          kind === 'unauthorized' ? (
            <button
              onClick={() => setShowLogin(true)}
              className="text-[10px] font-mono uppercase tracking-widest underline text-amber-400 hover:text-amber-200"
            >
              Sign in
            </button>
          ) : null
        }
      />
      {showLogin && (
        <LoginDialog
          onClose={() => setShowLogin(false)}
          onDone={() => {
            setShowLogin(false);
            setBanner(null);
          }}
        />
      )}
    </>
  );
}

function BannerShell({
  icon,
  tone,
  title,
  detail,
  onDismiss,
  action,
}: {
  icon: React.ReactNode;
  tone: 'warning' | 'danger' | 'info';
  title: string;
  detail: string;
  onDismiss: () => void;
  action?: React.ReactNode;
}) {
  const toneStyles = {
    danger: 'bg-red-500/10 border-red-500/30 text-red-300',
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
    info: 'bg-sky-500/10 border-sky-500/30 text-sky-300',
  }[tone];
  return (
    <div
      className={clsx(
        'fixed top-3 right-3 z-50 max-w-sm px-3 py-2 rounded-xl border backdrop-blur-md shadow-xl',
        toneStyles,
      )}
      role="alert"
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5">{icon}</div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-widest">{title}</div>
          <div className="text-[10px] font-mono text-white/70 mt-0.5 break-words">{detail}</div>
          {action && <div className="mt-1.5">{action}</div>}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-white/40 hover:text-white/80 -mr-1 -mt-0.5"
          aria-label="Dismiss"
          title="Dismiss"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

// ─── Minimal login dialog (JWT or dev-token) ─────────────────────────────────

function LoginDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<'password' | 'dev_token'>('password');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [devToken, setDevToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'password') {
        await api.auth.login(username, password);
      } else {
        tokenStore.set(devToken.trim());
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign in failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[360px] glass-panel-elevated p-5"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-semibold uppercase tracking-widest text-white/60">
            Backend authentication
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/40 hover:text-white/80"
            aria-label="Close"
            title="Close"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex gap-1 mb-4 p-1 rounded-lg bg-white/[0.03] border border-white/[0.05]">
          {(['password', 'dev_token'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={clsx(
                'flex-1 px-2 py-1 rounded text-[10px] font-mono tracking-wider transition-colors',
                mode === m
                  ? 'bg-white/10 text-white/90'
                  : 'text-white/40 hover:text-white/70',
              )}
            >
              {m === 'password' ? 'USER + PASS' : 'DEV TOKEN'}
            </button>
          ))}
        </div>

        {mode === 'password' ? (
          <div className="space-y-2.5">
            <div>
              <label
                htmlFor="gorzen-login-username"
                className="text-[9px] font-mono uppercase tracking-widest text-white/40"
              >
                Username
              </label>
              <input
                id="gorzen-login-username"
                name="username"
                placeholder="admin"
                autoComplete="username"
                className="glass-input text-xs font-mono mt-1"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
              />
            </div>
            <div>
              <label
                htmlFor="gorzen-login-password"
                className="text-[9px] font-mono uppercase tracking-widest text-white/40"
              >
                Password
              </label>
              <input
                id="gorzen-login-password"
                name="password"
                placeholder="••••••••"
                type="password"
                autoComplete="current-password"
                className="glass-input text-xs font-mono mt-1"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-2.5">
            <div>
              <label
                htmlFor="gorzen-dev-token"
                className="text-[9px] font-mono uppercase tracking-widest text-white/40"
              >
                Dev WebSocket token
              </label>
              <input
                id="gorzen-dev-token"
                name="dev_token"
                className="glass-input text-xs font-mono mt-1"
                placeholder="GORZEN_DEV_WS_TOKEN value"
                value={devToken}
                onChange={(e) => setDevToken(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                autoFocus
              />
              <p className="text-[9px] text-white/35 mt-1.5 leading-relaxed">
                Pass-through when the backend runs with auth disabled; matches
                the <code>GORZEN_DEV_WS_TOKEN</code> env var.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-3 text-[10px] font-mono text-red-400 p-2 rounded bg-red-500/10 border border-red-500/20">
            {error}
          </div>
        )}

        <div className="mt-4 flex gap-2">
          <button
            onClick={submit}
            disabled={submitting}
            className="flex-1 glass-button text-[11px] py-2 font-mono tracking-widest disabled:opacity-40"
          >
            {submitting ? 'SIGNING IN…' : 'SIGN IN'}
          </button>
          <button
            onClick={() => {
              tokenStore.set(null);
              onDone();
            }}
            className="glass-button text-[10px] py-2 px-3 font-mono tracking-widest text-white/50"
            title="Clear the stored token"
          >
            CLEAR
          </button>
        </div>
      </div>
    </div>
  );
}
