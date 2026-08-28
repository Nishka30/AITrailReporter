import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

/**
 * Holds the admin token + display name entered at the login screen. This is
 * a MINIMAL, development-safe boundary (see backend/app/core/admin_auth.py)
 * -- not a verified identity, just a shared secret plus a self-reported
 * attribution label. Both live only in this browser's localStorage, never in
 * the built JS bundle, and are sent as request headers rather than a URL or
 * query param so they don't end up in server access logs.
 */
const STORAGE_KEY = 'aitrailreporter-admin-auth';

export type AdminAuth = {
  token: string;
  name: string;
};

type AdminAuthContextValue = {
  auth: AdminAuth | null;
  login: (auth: AdminAuth) => void;
  logout: () => void;
};

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

/** Exported so api/client.ts can attach the current token/name to every
 * request without needing to be inside a React component. */
export function readStoredAuth(): AdminAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.token === 'string' && typeof parsed?.name === 'string') {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AdminAuth | null>(() => readStoredAuth());

  const value = useMemo<AdminAuthContextValue>(
    () => ({
      auth,
      login: (next) => {
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // localStorage can be unavailable (private browsing, quota) --
          // auth still works for this tab session via in-memory state.
        }
        setAuth(next);
      },
      logout: () => {
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch {
          // see above
        }
        setAuth(null);
      },
    }),
    [auth]
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error('useAdminAuth must be used within AdminAuthProvider');
  return ctx;
}
