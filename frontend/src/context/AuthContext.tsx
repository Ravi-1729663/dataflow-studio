import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { tokenStorage } from "../lib/api";
import { auth } from "../lib/resources";
import type { User } from "../lib/types";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    if (!tokenStorage.getAccess()) {
      setLoading(false);
      return;
    }
    try {
      const response = await auth.me();
      setUser(response.data);
    } catch {
      tokenStorage.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, [loadCurrentUser]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await auth.login(username, password);
    tokenStorage.set(response.data.access, response.data.refresh);
    const me = await auth.me();
    setUser(me.data);
  }, []);

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      await auth.register({ username, email, password });
      await login(username, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
