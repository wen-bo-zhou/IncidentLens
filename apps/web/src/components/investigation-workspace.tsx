"use client";

import {
  ArrowRight,
  BookOpenText,
  Braces,
  CheckCircle2,
  Clock3,
  Download,
  FileSearch,
  Gauge,
  GitCommitHorizontal,
  Radio,
  RotateCcw,
  ShieldCheck,
  Square,
  TimerReset,
  X,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { MetricEvidenceChart, TraceWaterfall } from "@/components/evidence-visuals";
import type {
  AuthSession,
  EvidenceRef,
  IncidentCase,
  InvestigationReport,
  InvestigationWindow,
  RemediationProposal,
} from "@/lib/types";

interface InvestigationWorkspaceProps {
  incident: IncidentCase;
  report?: InvestigationReport;
  loading: boolean;
  onRun: () => void;
  onRunLive?: (runnerToken: string, window: InvestigationWindow) => Promise<void>;
  onCancelLive?: () => Promise<void>;
  liveStatus?: string;
  liveEventCount?: number;
  remediationProposals?: RemediationProposal[];
  onApproveRemediation?: (proposalId: string, adminToken: string) => Promise<void>;
  sessionRole?: AuthSession["role"];
}

const kindLabels = { log: "LOG", metric: "METRIC", trace: "TRACE", runbook: "RUNBOOK" };

function formatClock(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

function EvidenceDialog({ evidence, onClose }: { evidence: EvidenceRef; onClose: () => void }) {
  return (
    <div className="dialog-scrim" onMouseDown={onClose}>
      <section
        className="evidence-dialog"
        role="dialog"
        aria-label="证据详情"
        aria-modal="true"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className={`kind-tag ${evidence.kind}`}>{kindLabels[evidence.kind]}</span>
            <h3>{evidence.service}</h3>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭证据详情"><X size={18} /></button>
        </header>
        <div className="evidence-meta">
          <span>{formatClock(evidence.timestamp)}</span>
          <span>{evidence.locator}</span>
          <span>{evidence.content_hash.slice(0, 10)}</span>
        </div>
        <pre>{evidence.excerpt}</pre>
        {evidence.kind === "metric" && <MetricEvidenceChart attributes={evidence.attributes} />}
        {evidence.kind === "trace" && <TraceWaterfall attributes={evidence.attributes} />}
        <dl className="attribute-grid">
          {Object.entries(evidence.attributes).map(([key, value]) => (
            <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
          ))}
        </dl>
        <p className="untrusted-note"><ShieldCheck size={15} /> 此内容以不可信证据处理，不会被解释为系统指令。</p>
      </section>
    </div>
  );
}

function LiveRunDialog({
  incident,
  onClose,
  onRun,
  useSession,
}: {
  incident: IncidentCase;
  onClose: () => void;
  onRun: (runnerToken: string, window: InvestigationWindow) => Promise<void>;
  useSession: boolean;
}) {
  const [token, setToken] = useState("");
  const [startAt, setStartAt] = useState(
    new Date(incident.starts_at).toISOString().slice(0, 16),
  );
  const [endAt, setEndAt] = useState(
    new Date(incident.ends_at).toISOString().slice(0, 16),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      const start = new Date(`${startAt}:00Z`);
      const end = new Date(`${endAt}:00Z`);
      if (start >= end) {
        throw new Error("开始时间必须早于结束时间");
      }
      await onRun(token, {
        startAt: start.toISOString().replace(".000Z", "Z"),
        endAt: end.toISOString().replace(".000Z", "Z"),
      });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法启动实时调查");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-scrim" onMouseDown={onClose}>
      <form
        className="live-dialog"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div><span className="eyebrow">Bounded live run</span><h2>启动实时调查</h2></div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭实时调查"><X size={18} /></button>
        </header>
        <p>
          实时模式会调用受限调查 Worker，并受每日额度和审计策略约束。
        </p>
        {useSession ? (
          <p className="session-assurance">
            <ShieldCheck size={15} /> 企业 Runner 会话已验证
          </p>
        ) : (
          <>
            <label htmlFor="runner-token">Runner 令牌</label>
            <input
              id="runner-token"
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="runner-demo-token"
              autoFocus
            />
          </>
        )}
        <div className="time-window-fields">
          <div>
            <label htmlFor="investigation-start">开始时间（UTC）</label>
            <input
              id="investigation-start"
              type="datetime-local"
              value={startAt}
              onChange={(event) => setStartAt(event.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="investigation-end">结束时间（UTC）</label>
            <input
              id="investigation-end"
              type="datetime-local"
              value={endAt}
              onChange={(event) => setEndAt(event.target.value)}
              required
            />
          </div>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button
          className="run-button"
          disabled={(!useSession && !token) || submitting}
        >
          {submitting ? "正在排队" : "确认启动"}
        </button>
      </form>
    </div>
  );
}

function EmptyReport({ loading }: { loading: boolean }) {
  return (
    <div className="report-empty">
      <div className="scanner" aria-hidden="true"><span /></div>
      <span className="eyebrow">Evidence pipeline</span>
      <h2>{loading ? "正在重建事故链路" : "选择事故，开始证据调查"}</h2>
      <p>{loading ? "正在关联日志、指标、Trace 与 Runbook…" : "系统会回放受约束的调查过程，并给出可验证的根因结论。"}</p>
    </div>
  );
}

function ApprovalDialog({
  proposal,
  onClose,
  onApprove,
  useSession,
}: {
  proposal: RemediationProposal;
  onClose: () => void;
  onApprove: (proposalId: string, adminToken: string) => Promise<void>;
  useSession: boolean;
}) {
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      await onApprove(proposal.id, token);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "处置审批失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-scrim" onMouseDown={onClose}>
      <form className="live-dialog approval-dialog" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span className="eyebrow">Human approval</span><h2>批准沙箱模拟</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="关闭处置审批"><X size={18} /></button></header>
        <p><strong>{proposal.title}</strong><br />审批只会触发预定义虚拟动作，不会生成或执行 Shell、SQL。</p>
        {useSession ? (
          <p className="session-assurance">
            <ShieldCheck size={15} /> 企业 Admin 会话已验证
          </p>
        ) : (
          <>
            <label htmlFor="admin-approval-token">管理员令牌</label>
            <input id="admin-approval-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="admin-demo-token" autoFocus />
          </>
        )}
        {error && <p className="form-error">{error}</p>}
        <button className="run-button" disabled={(!useSession && !token) || submitting}>{submitting ? "模拟执行中" : "批准并模拟"}</button>
      </form>
    </div>
  );
}

export function InvestigationWorkspace({
  incident,
  report,
  loading,
  onRun,
  onRunLive,
  onCancelLive,
  liveStatus,
  liveEventCount = 0,
  remediationProposals = [],
  onApproveRemediation,
  sessionRole = "guest",
}: InvestigationWorkspaceProps) {
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [showLiveDialog, setShowLiveDialog] = useState(false);
  const [approvalProposal, setApprovalProposal] = useState<RemediationProposal>();
  const evidenceById = useMemo(
    () => new Map(report?.evidence_index.map((item) => [item.id, item]) ?? []),
    [report],
  );
  const selectedEvidence = selectedEvidenceId ? evidenceById.get(selectedEvidenceId) : undefined;
  const top = report?.ranked_hypotheses[0];

  function exportMarkdown() {
    if (!report) return;
    const markdown = [
      `# ${incident.title}`,
      "",
      report.summary,
      "",
      "## 已确认事实",
      ...report.confirmed_facts.map((fact) => `- ${fact}`),
      "",
      "## 候选根因",
      ...report.ranked_hypotheses.map(
        (hypothesis, index) =>
          `${index + 1}. ${hypothesis.title} (${Math.round(hypothesis.score * 100)}%) — evidence: ${hypothesis.supporting_evidence_ids.join(", ") || "none"}`,
      ),
      "",
      "## 未解决问题",
      ...report.uncertainties.map((item) => `- ${item}`),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${incident.id}-report.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="workspace">
      <section className="incident-header">
        <div className="incident-identity">
          <div className="severity-block"><span>{incident.severity}</span><small>演练事故</small></div>
          <div>
            <span className="eyebrow">Case / {incident.id}</span>
            <h1>{incident.title}</h1>
            <p>{incident.summary}</p>
          </div>
        </div>
        <div className="header-actions">
          <div className="service-stack">
            {incident.services.map((service) => <span key={service}>{service}</span>)}
          </div>
          <div className="run-actions">
            <button
              className="replay-button"
              onClick={onRun}
              disabled={loading}
              aria-label="重新调查"
            >
              <RotateCcw size={16} className={loading ? "spin" : ""} />缓存回放
            </button>
            {onRunLive && (
              <button
                className="run-button"
                onClick={() => setShowLiveDialog(true)}
                disabled={loading}
              >
                <Radio size={17} />实时调查
              </button>
            )}
            {onCancelLive && (
              <button
                className="replay-button cancel-button"
                onClick={() => void onCancelLive()}
                aria-label="取消调查"
              >
                <Square size={14} />取消调查
              </button>
            )}
          </div>
        </div>
      </section>

      {liveStatus && (
        <section className="live-progress" aria-live="polite">
          <span className="live-pulse" />
          <strong>{liveStatus}</strong>
          <span>{liveEventCount} events</span>
        </section>
      )}

      <section className="metric-tape" aria-label="调查运行指标">
        <div><FileSearch /><span><small>证据</small><strong>{incident.evidence_count}</strong></span></div>
        <div><TimerReset /><span><small>调查耗时</small><strong>{report ? `${report.total_latency_ms} ms` : "—"}</strong></span></div>
        <div><Braces /><span><small>工具调用</small><strong>{report?.model_usage.tool_calls ?? "—"}</strong></span></div>
        <div><Gauge /><span><small>模型成本</small><strong>{report ? `¥${report.total_cost_cny.toFixed(3)}` : "—"}</strong></span></div>
        <div className="model-stamp"><small>RUNNER</small><strong>{report?.model_usage.model ?? "等待运行"}</strong></div>
      </section>

      {!report ? <EmptyReport loading={loading} /> : (
        <div className="investigation-grid">
          <section className="causal-panel">
            <header className="panel-heading">
              <div><span className="eyebrow">Causal spine</span><h2>事故因果时间线</h2></div>
              <span className="evidence-total">{report.timeline.length} 个关键节点</span>
            </header>
            <div className="causal-spine">
              {report.timeline.length === 0 && (
                <div className="timeline-empty">
                  <FileSearch size={24} />
                  <strong>所选时间窗内没有可用于因果排序的事件</strong>
                  <span>调整调查时间窗，或导入包含时间戳的日志、指标和 Trace。</span>
                </div>
              )}
              {report.timeline.map((item, index) => (
                <article className="timeline-node" key={`${item.timestamp}-${index}`}>
                  <div className="time-cell"><strong>{formatClock(item.timestamp)}</strong><small>UTC</small></div>
                  <div className={`spine-marker ${item.category}`}><span>{index + 1}</span></div>
                  <div className="timeline-copy">
                    <span className="timeline-category">{item.category}</span>
                    <p>{item.description}</p>
                    <div className="evidence-links">
                      {item.evidence_ids.map((id) => (
                        <button key={id} onClick={() => setSelectedEvidenceId(id)} aria-label={`查看证据 ${id}`}>
                          <GitCommitHorizontal size={14} /> {id.split(":").at(-1)}
                        </button>
                      ))}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <aside className="verdict-panel">
            <header className="panel-heading"><div><span className="eyebrow">Verdict</span><h2>根因判定</h2></div></header>
            {top && (
              <section className="top-hypothesis">
                <div className="score-orbit" style={{ "--score": `${top.score * 360}deg` } as React.CSSProperties}>
                  <span>{Math.round(top.score * 100)}%</span><small>{top.confidence}</small>
                </div>
                <span className="status-line"><CheckCircle2 size={15} /> 证据支持</span>
                <h3>{top.title}</h3>
                <ol className="causal-chain">
                  {top.causal_chain.map((step, index) => (
                    <li key={step}><span>{index + 1}</span><p>{step}</p>{index < top.causal_chain.length - 1 && <ArrowRight size={13} />}</li>
                  ))}
                </ol>
              </section>
            )}
            {!top && (
              <section className="inconclusive-verdict">
                <span className="status-line">Inconclusive</span>
                <h3>证据不足，无法判定根因</h3>
                <p>{report.summary}</p>
                {report.uncertainties.length > 0 && (
                  <>
                    <strong>继续调查需要</strong>
                    <ul>
                      {report.uncertainties.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </>
                )}
              </section>
            )}

            {report.ranked_hypotheses.length > 1 && (
              <section className="hypothesis-compare">
                <span className="eyebrow">Alternatives</span>
                {report.ranked_hypotheses.slice(1).map((hypothesis) => (
                  <article key={hypothesis.id}>
                    <div>
                      <strong>{Math.round(hypothesis.score * 100)}%</strong>
                      <span>{hypothesis.status}</span>
                    </div>
                    <h3>{hypothesis.title}</h3>
                    <p>
                      {hypothesis.contradicting_evidence_ids.length} 条反证 · {hypothesis.missing_evidence.length} 个缺失信号
                    </p>
                  </article>
                ))}
              </section>
            )}

            {report.confirmed_facts.length > 0 && (
              <section className="fact-box">
                <h3><CheckCircle2 size={16} /> 已确认事实</h3>
                <ul>{report.confirmed_facts.slice(0, 3).map((fact) => <li key={fact}>{fact}</li>)}</ul>
              </section>
            )}

            {report.recommended_actions.map((action) => {
              const proposal = remediationProposals.find(
                (item) => item.action_type === action.action_type,
              );
              const canApprove = proposal?.status === "proposed" && onApproveRemediation;
              return (
                <section className="action-box" key={action.action_type}>
                  <div><span className="eyebrow">Sandbox action</span><span className={`risk ${action.risk}`}>{action.risk}</span></div>
                  <h3>{action.title}</h3>
                  <p>{action.rationale}</p>
                  <button
                    disabled={!canApprove}
                    onClick={() => proposal && setApprovalProposal(proposal)}
                  >
                    <ShieldCheck size={16} />
                    {proposal?.status === "simulated" ? "沙箱模拟已完成" : "需要管理员审批"}
                  </button>
                </section>
              );
            })}

            <section className="runtime-box">
              <span><Clock3 size={15} /> {report.total_latency_ms} ms</span>
              <span><BookOpenText size={15} /> {report.evidence_index.length} refs</span>
              <span><ShieldCheck size={15} /> audited</span>
            </section>
            <button className="export-report" onClick={exportMarkdown}><Download size={14} />导出 Markdown 报告</button>
          </aside>
        </div>
      )}

      {selectedEvidence && <EvidenceDialog evidence={selectedEvidence} onClose={() => setSelectedEvidenceId(null)} />}
      {showLiveDialog && onRunLive && (
        <LiveRunDialog
          incident={incident}
          onClose={() => setShowLiveDialog(false)}
          onRun={onRunLive}
          useSession={sessionRole === "runner" || sessionRole === "admin"}
        />
      )}
      {approvalProposal && onApproveRemediation && (
        <ApprovalDialog
          proposal={approvalProposal}
          onClose={() => setApprovalProposal(undefined)}
          onApprove={onApproveRemediation}
          useSession={sessionRole === "admin"}
        />
      )}
    </main>
  );
}
