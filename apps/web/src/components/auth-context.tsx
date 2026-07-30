"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
} from "react";

import { api } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

const guestSession: AuthSession = {
  authenticated: false,
  sso_enabled: false,
  role: "guest",
  actor: null,
};

interface AuthContextValue {
  session: AuthSession;
  isLoading: boolean;
  error: Error | null;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  session: guestSession,
  isLoading: false,
  error: null,
  logout: async () => undefined,
});

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: api.session,
    staleTime: 30_000,
  });
  const session = sessionQuery.data ?? guestSession;

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isLoading: sessionQuery.isLoading,
      error:
        sessionQuery.error instanceof Error ? sessionQuery.error : null,
      logout: async () => {
        await api.logout();
        queryClient.setQueryData<AuthSession>(
          ["auth", "session"],
          {
            authenticated: false,
            sso_enabled: session.sso_enabled,
            role: "guest",
            actor: null,
          },
        );
        queryClient.removeQueries({ queryKey: ["operations"] });
        queryClient.removeQueries({ queryKey: ["incidents"] });
      },
    }),
    [
      queryClient,
      session,
      sessionQuery.error,
      sessionQuery.isLoading,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
