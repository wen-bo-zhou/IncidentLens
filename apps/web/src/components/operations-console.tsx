"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  FileSearch,
  KeyRound,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-context";
import { HistoryReportDialog } from "@/components/history-report-dialog";
import { SessionControl } from "@/components/session-control";
import { api } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

const PAGE_SIZE = 20;
const terminalStatuses = new Set(["completed", "failed", "canceled", "inconclusive"]);

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function statusLabel(status: string): string {
  return {
    completed: "已完成",
    failed: "失败",
    canceled: "已取消",
    inconclusive: "证据不足",
    queued: "排队中",
  }[status] ?? status;
}

export function OperationsConsole() {
  const queryClient = useQueryClient();
  const { session, isLoading: authLoading } = useAuth();
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState("");
  const [tokenSession, setTokenSession] = useState<AuthSession>();
  const [credentialError, setCredentialError] = useState("");
  const [authenticating, setAuthenticating] = useState(false);
  const [status, setStatus] = useState("");
  const [action, setAction] = useState("");
  const [selectedInvestigationId, setSelectedInvestigationId] = useState("");
  const reportTrigger = useRef<HTMLButtonElement | null>(null);
  const [investigationOffset, setInvestigationOffset] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);
  const activeRole = tokenSession?.role ?? session.role;
  const sessionAuthenticated = session.role === "runner" || session.role === "admin";
  const hasOperatorAccess =
    activeRole === "runner" || activeRole === "admin";
  const hasAdminAccess = activeRole === "admin";
  const credentialKey = tokenSession
    ? `${tokenSession.role}:${tokenSession.actor ?? "static"}`
    : sessionAuthenticated
      ? `${session.role}:${session.actor ?? "session"}`
      : "";
  const requestToken = token || undefined;

  const investigations = useQuery({
    queryKey: [
      "operations",
      "investigations",
      credentialKey,
      status,
      investigationOffset,
    ],
    queryFn: () =>
      api.investigationHistory(requestToken, {
        status: status || undefined,
        limit: PAGE_SIZE,
        offset: investigationOffset,
      }),
    enabled: hasOperatorAccess,
  });
  const audits = useQuery({
    queryKey: [
      "operations",
      "audits",
      credentialKey,
      action,
      auditOffset,
    ],
    queryFn: () =>
      api.auditEvents(requestToken, {
        action: action || undefined,
        limit: PAGE_SIZE,
        offset: auditOffset,
      }),
    enabled: hasAdminAccess,
  });
  const selectedInvestigation = useQuery({
    queryKey: [
      "operations",
      "investigation",
      credentialKey,
      selectedInvestigationId,
    ],
    queryFn: () => api.investigation(selectedInvestigationId, requestToken),
    enabled: hasOperatorAccess && Boolean(selectedInvestigationId),
  });

  useEffect(() => {
    if (!hasOperatorAccess) {
      queryClient.removeQueries({ queryKey: ["operations"] });
    }
  }, [hasOperatorAccess, queryClient]);

  useEffect(
    () => () => {
      queryClient.removeQueries({ queryKey: ["operations"] });
    },
    [queryClient],
  );

  async function authenticate(event: FormEvent) {
    event.preventDefault();
    const nextToken = tokenInput.trim();
    if (!nextToken) return;
    setAuthenticating(true);
    setCredentialError("");
    try {
      const credentialSession = await api.credentialSession(nextToken);
      if (
        !credentialSession.authenticated ||
        credentialSession.role === "guest"
      ) {
        throw new Error("该令牌没有调查访问权限");
      }
      setTokenSession(credentialSession);
      setToken(nextToken);
    } catch (error) {
      setCredentialError(
        error instanceof Error ? error.message : "无法验证访问令牌",
      );
    } finally {
      setAuthenticating(false);
    }
  }

  if (authLoading) {
    return (
      <main className="operations-page operations-gate">
        <p className="ledger-empty">正在验证企业身份…</p>
      </main>
    );
  }

  if (!hasOperatorAccess) {
    return (
      <main className="operations-page operations-gate">
        <Link className="operations-back" href="/">
          <ArrowLeft size={15} /> 返回调查台
        </Link>
        <form className="operations-login" onSubmit={authenticate}>
          <span className="operations-lock"><KeyRound /></span>
          <span className="eyebrow">Operations clearance</span>
          <h1>查看调查历史</h1>
          <p>
            Runner 可以恢复自己创建的调查报告，Admin 还可以查看全局审计记录。
            {session.sso_enabled
              ? " 使用企业身份登录，或输入应急访问令牌。"
              : " 令牌仅保存在当前页面内存中，关闭或刷新页面后自动清除。"}
          </p>
          {session.sso_enabled && (
            <SessionControl returnTo="/operations" />
          )}
          <label htmlFor="operations-access-token">Runner 或 Admin 令牌</label>
          <input
            id="operations-access-token"
            type="password"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            placeholder="runner-demo-token"
            autoComplete="off"
          />
          {credentialError && (
            <span className="operations-login-error" role="alert">
              {credentialError}
            </span>
          )}
          <button disabled={!tokenInput.trim() || authenticating}>
            <ShieldCheck size={16} />
            {authenticating ? "正在验证…" : "查看调查历史"}
          </button>
        </form>
      </main>
    );
  }

  const failed =
    investigations.error ??
    (hasAdminAccess ? audits.error : null) ??
    selectedInvestigation.error;
  const investigationPage = investigations.data;
  const auditPage = audits.data;
  const investigationDetail = selectedInvestigation.data;
  const activeCount =
    investigationPage?.items.filter((item) => !terminalStatuses.has(item.status)).length ?? 0;

  return (
    <main className="operations-page">
      <header className="operations-header">
        <div>
          <Link className="operations-back" href="/">
            <ArrowLeft size={15} /> 返回调查台
          </Link>
          <span className="eyebrow">Durable operations ledger</span>
          <h1>{hasAdminAccess ? "运行与审计" : "调查历史"}</h1>
          <p>
            {hasAdminAccess
              ? "从持久化记录中追踪每次调查、失败状态和管理员动作。"
              : "恢复已完成的调查报告，或追踪仍在运行的任务。"}
          </p>
        </div>
        {sessionAuthenticated && !token ? (
          <SessionControl returnTo="/operations" />
        ) : (
          <button
            className="operations-logout"
            onClick={() => {
              setToken("");
              setTokenInput("");
              setTokenSession(undefined);
              setSelectedInvestigationId("");
            }}
          >
            <LogOut size={15} /> 清除令牌
          </button>
        )}
      </header>

      <section className="operations-tape" aria-label="运营摘要">
        <div>
          <Database size={18} />
          <span><small>调查总数</small><strong>{investigationPage?.total ?? "—"}</strong></span>
        </div>
        <div>
          <Activity size={18} />
          <span><small>当前页运行中</small><strong>{activeCount}</strong></span>
        </div>
        {hasAdminAccess ? (
          <div>
            <ClipboardList size={18} />
            <span><small>审计事件</small><strong>{auditPage?.total ?? "—"}</strong></span>
          </div>
        ) : (
          <div>
            <ShieldCheck size={18} />
            <span><small>访问范围</small><strong className="scope-label">仅显示你创建的调查</strong></span>
          </div>
        )}
        <div className="operations-durable">
          <span className="operations-pulse" />
          DATABASE-BACKED · FILTERABLE · RECOVERABLE
        </div>
      </section>

      {failed && (
        <section className="operations-error" role="alert">
          <strong>无法读取运营数据</strong>
          <span>{failed.message}</span>
          <button onClick={() => {
            void investigations.refetch();
            if (hasAdminAccess) void audits.refetch();
            if (selectedInvestigationId) void selectedInvestigation.refetch();
          }}>
            <RefreshCw size={14} /> 重试
          </button>
        </section>
      )}

      <div className={`operations-grid${hasAdminAccess ? "" : " runner-ledger"}`}>
        <section className="ledger-panel" aria-labelledby="investigation-ledger-title">
          <header className="ledger-header">
            <div>
              <span className="eyebrow">Investigation ledger</span>
              <h2 id="investigation-ledger-title">调查历史</h2>
            </div>
            <label>
              <span>运行状态</span>
              <select
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setInvestigationOffset(0);
                }}
              >
                <option value="">全部状态</option>
                <option value="completed">已完成</option>
                <option value="inconclusive">证据不足</option>
                <option value="failed">失败</option>
                <option value="canceled">已取消</option>
                <option value="queued">排队中</option>
              </select>
            </label>
          </header>

          <div className="ledger-list">
            {investigations.isLoading ? (
              <p className="ledger-empty">正在读取调查记录…</p>
            ) : investigationPage?.items.length ? (
              investigationPage.items.map((item) => (
                <article className="investigation-ledger-row" key={item.investigation_id}>
                  <span className={`ledger-status status-${item.status}`}>
                    {statusLabel(item.status)}
                  </span>
                  <div>
                    <small><span>{item.incident_case_id}</span> · {item.mode.toUpperCase()}</small>
                    <h3>{item.summary ?? "报告尚未生成"}</h3>
                    <code>{item.investigation_id}</code>
                  </div>
                  <time dateTime={item.updated_at}>{formatTime(item.updated_at)}</time>
                  <button
                    className="ledger-open-report"
                    aria-label={`打开报告 ${item.investigation_id}`}
                    onClick={(event) => {
                      reportTrigger.current = event.currentTarget;
                      setSelectedInvestigationId(item.investigation_id);
                    }}
                  >
                    <FileSearch size={15} />
                    查看
                  </button>
                </article>
              ))
            ) : (
              <p className="ledger-empty">当前筛选条件下没有调查记录。</p>
            )}
          </div>

          <footer className="ledger-pagination">
            <span>
              {investigationPage?.total
                ? `${investigationOffset + 1}–${Math.min(
                    investigationOffset + PAGE_SIZE,
                    investigationPage.total,
                  )} / ${investigationPage.total}`
                : "0 条记录"}
            </span>
            <div>
              <button
                aria-label="上一页调查记录"
                disabled={investigationOffset === 0}
                onClick={() =>
                  setInvestigationOffset(Math.max(0, investigationOffset - PAGE_SIZE))
                }
              >
                <ChevronLeft size={15} />
              </button>
              <button
                aria-label="下一页调查记录"
                disabled={
                  !investigationPage ||
                  investigationOffset + PAGE_SIZE >= investigationPage.total
                }
                onClick={() => setInvestigationOffset(investigationOffset + PAGE_SIZE)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </footer>
        </section>

        {hasAdminAccess && (
          <section className="ledger-panel audit-ledger" aria-labelledby="audit-ledger-title">
          <header className="ledger-header">
            <div>
              <span className="eyebrow">Governance trail</span>
              <h2 id="audit-ledger-title">审计轨迹</h2>
            </div>
            <label>
              <span>动作类型</span>
              <select
                value={action}
                onChange={(event) => {
                  setAction(event.target.value);
                  setAuditOffset(0);
                }}
              >
                <option value="">全部动作</option>
                <option value="investigation.created">创建调查</option>
                <option value="investigation.canceled">取消调查</option>
                <option value="incident.imported">导入事故</option>
                <option value="remediation.simulated">模拟处置</option>
                <option value="evaluation.completed">完成评测</option>
              </select>
            </label>
          </header>

          <div className="audit-list">
            {audits.isLoading ? (
              <p className="ledger-empty">正在读取审计记录…</p>
            ) : auditPage?.items.length ? (
              auditPage.items.map((item) => (
                <article className="audit-ledger-row" key={item.id}>
                  <span className="audit-sequence">{String(item.id).padStart(4, "0")}</span>
                  <div>
                    <strong>{item.action}</strong>
                    <code>{item.resource_id}</code>
                    <small>{item.actor} · {formatTime(item.created_at)}</small>
                  </div>
                </article>
              ))
            ) : (
              <p className="ledger-empty">当前筛选条件下没有审计记录。</p>
            )}
          </div>

          <footer className="ledger-pagination">
            <span>
              {auditPage?.total
                ? `${auditOffset + 1}–${Math.min(
                    auditOffset + PAGE_SIZE,
                    auditPage.total,
                  )} / ${auditPage.total}`
                : "0 条记录"}
            </span>
            <div>
              <button
                aria-label="上一页审计记录"
                disabled={auditOffset === 0}
                onClick={() => setAuditOffset(Math.max(0, auditOffset - PAGE_SIZE))}
              >
                <ChevronLeft size={15} />
              </button>
              <button
                aria-label="下一页审计记录"
                disabled={!auditPage || auditOffset + PAGE_SIZE >= auditPage.total}
                onClick={() => setAuditOffset(auditOffset + PAGE_SIZE)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </footer>
          </section>
        )}
      </div>

      {selectedInvestigationId && (
        <HistoryReportDialog
          detail={investigationDetail}
          error={
            selectedInvestigation.error instanceof Error
              ? selectedInvestigation.error
              : null
          }
          investigationId={selectedInvestigationId}
          loading={selectedInvestigation.isLoading}
          onClose={() => setSelectedInvestigationId("")}
          returnFocus={reportTrigger}
        />
      )}
    </main>
  );
}
