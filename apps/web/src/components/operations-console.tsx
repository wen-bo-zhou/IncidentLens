"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  KeyRound,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { api } from "@/lib/api";

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
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("");
  const [action, setAction] = useState("");
  const [investigationOffset, setInvestigationOffset] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);

  const investigations = useQuery({
    queryKey: ["operations", "investigations", token, status, investigationOffset],
    queryFn: () =>
      api.investigationHistory(token, {
        status: status || undefined,
        limit: PAGE_SIZE,
        offset: investigationOffset,
      }),
    enabled: Boolean(token),
  });
  const audits = useQuery({
    queryKey: ["operations", "audits", token, action, auditOffset],
    queryFn: () =>
      api.auditEvents(token, {
        action: action || undefined,
        limit: PAGE_SIZE,
        offset: auditOffset,
      }),
    enabled: Boolean(token),
  });

  useEffect(() => {
    if (!token) queryClient.removeQueries({ queryKey: ["operations"] });
  }, [queryClient, token]);

  function authenticate(event: FormEvent) {
    event.preventDefault();
    const nextToken = tokenInput.trim();
    if (nextToken) setToken(nextToken);
  }

  if (!token) {
    return (
      <main className="operations-page operations-gate">
        <Link className="operations-back" href="/">
          <ArrowLeft size={15} /> 返回调查台
        </Link>
        <form className="operations-login" onSubmit={authenticate}>
          <span className="operations-lock"><KeyRound /></span>
          <span className="eyebrow">Operations clearance</span>
          <h1>打开运营中心</h1>
          <p>
            调查历史和审计记录只向管理员开放。令牌仅保存在当前页面内存中，
            关闭或刷新页面后自动清除。
          </p>
          <label htmlFor="operations-admin-token">管理员令牌</label>
          <input
            id="operations-admin-token"
            type="password"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            placeholder="admin-demo-token"
            autoComplete="current-password"
          />
          <button disabled={!tokenInput.trim()}>
            <ShieldCheck size={16} /> 打开运营中心
          </button>
        </form>
      </main>
    );
  }

  const failed = investigations.error ?? audits.error;
  const investigationPage = investigations.data;
  const auditPage = audits.data;
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
          <h1>运行与审计</h1>
          <p>从持久化记录中追踪每次调查、失败状态和管理员动作。</p>
        </div>
        <button
          className="operations-logout"
          onClick={() => {
            setToken("");
            setTokenInput("");
          }}
        >
          <LogOut size={15} /> 清除令牌
        </button>
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
        <div>
          <ClipboardList size={18} />
          <span><small>审计事件</small><strong>{auditPage?.total ?? "—"}</strong></span>
        </div>
        <div className="operations-durable">
          <span className="operations-pulse" />
          DATABASE-BACKED · FILTERABLE · AUDITED
        </div>
      </section>

      {failed && (
        <section className="operations-error" role="alert">
          <strong>无法读取运营数据</strong>
          <span>{failed.message}</span>
          <button onClick={() => {
            void investigations.refetch();
            void audits.refetch();
          }}>
            <RefreshCw size={14} /> 重试
          </button>
        </section>
      )}

      <div className="operations-grid">
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
      </div>
    </main>
  );
}
