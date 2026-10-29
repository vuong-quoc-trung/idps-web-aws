/**
 * AuthContext — provides current user state + login/logout helpers
 * to the entire app.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { clearAuthTokens, fetchMe, login as apiLogin, logout as apiLogout } from '../api/authApi';
import { apiGet } from '../api/client';
import type { CurrentUser } from '../types/auth';

async function enrichedUser() {
  const user = await fetchMe();
  if (user?.role === 'STUDENT') {
    try {
      const profile = await apiGet<{ fullName: string; studentCode: string; avatarUrl?: string }>('/me/profile');
      return { ...user, fullName: profile.fullName, studentCode: profile.studentCode, avatarUrl: profile.avatarUrl };
    } catch { return user; }
  }
  return user;
}

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  clearSession: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const me = await enrichedUser();
    setUser(me);
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password);
    const me = await enrichedUser();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const clearSession = useCallback(() => { clearAuthTokens(); setUser(null); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
