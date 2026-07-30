"use client";

import { LogIn, LogOut, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-context";
import { api } from "@/lib/api";

export function SessionControl({ returnTo }: { returnTo: string }) {
  const { session, isLoading, error, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  if (isLoading) {
    return (
      <div className="session-control session-loading" aria-label="正在读取身份">
        <span />
        IDENTITY CHECK
      </div>
    );
  }

  if (session.authenticated) {
    return (
      <div className="session-control session-authenticated">
        <ShieldCheck size={15} />
        <span>
          <strong>{session.role.toUpperCase()}</strong>
          <small title={session.actor ?? undefined}>{session.actor}</small>
        </span>
        <button
          type="button"
          aria-label="退出企业会话"
          disabled={loggingOut}
          onClick={async () => {
            setLoggingOut(true);
            try {
              await logout();
            } finally {
              setLoggingOut(false);
            }
          }}
        >
          <LogOut size={13} />
        </button>
      </div>
    );
  }

  if (session.sso_enabled) {
    return (
      <a className="session-control session-login" href={api.loginUrl(returnTo)}>
        <LogIn size={14} />
        企业 SSO 登录
      </a>
    );
  }

  return (
    <div
      className={`session-control session-static${error ? " session-error" : ""}`}
      title={error?.message}
    >
      <span />
      STATIC ACCESS
    </div>
  );
}
