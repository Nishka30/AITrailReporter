import { useState } from 'react';
import { Navigate } from 'react-router-dom';

import { verifyAdminTokenExplicit } from '../api/admin';
import { useAdminAuth } from '../auth/AdminAuthContext';

export default function LoginPage() {
  const { auth, login } = useAdminAuth();
  const [token, setToken] = useState('');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (auth) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Verify against the backend BEFORE storing anything -- login() is
      // only called on success, so a wrong token never reaches localStorage.
      const result = await verifyAdminTokenExplicit(token, name.trim() || 'admin');
      login({ token, name: result.name });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not verify token');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-border bg-paper-elevated p-8 shadow-card"
      >
        <div className="font-heading text-xl font-extrabold text-ink">Trail Reporter</div>
        <div className="mb-6 text-sm font-bold uppercase tracking-wide text-marigold-deep">
          Content Console
        </div>

        <label className="text-sm font-bold text-ink-soft" htmlFor="admin-token">
          Admin token
        </label>
        <input
          id="admin-token"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
          className="mb-4 mt-1 w-full rounded-lg border border-border bg-paper p-2.5 text-sm"
          placeholder="Provided by your team"
        />

        <label className="text-sm font-bold text-ink-soft" htmlFor="admin-name">
          Your name
        </label>
        <input
          id="admin-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-1 mt-1 w-full rounded-lg border border-border bg-paper p-2.5 text-sm"
          placeholder="Shown on decisions you make"
        />
        <p className="mb-4 text-xs text-ink-faint">
          Used only to label the decisions you make -- not a verified identity.
        </p>

        {error ? <div className="mb-4 text-sm text-fix">{error}</div> : null}

        <button
          type="submit"
          disabled={submitting || !token}
          className="w-full rounded-full bg-ink py-2.5 text-sm font-bold text-marigold-soft disabled:opacity-50"
        >
          {submitting ? 'Checking…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
