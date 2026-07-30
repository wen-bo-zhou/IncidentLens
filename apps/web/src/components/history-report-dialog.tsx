"use client";

import { X } from "lucide-react";
import { type RefObject, useEffect, useRef } from "react";

import type { InvestigationDetail } from "@/lib/types";

interface HistoryReportDialogProps {
  detail?: InvestigationDetail;
  error: Error | null;
  investigationId: string;
  loading: boolean;
  onClose: () => void;
  returnFocus: RefObject<HTMLButtonElement | null>;
}

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

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element.getAttribute("aria-hidden") !== "true");
}

export function HistoryReportDialog({
  detail,
  error,
  investigationId,
  loading,
  onClose,
  returnFocus,
}: HistoryReportDialogProps) {
  const backdropRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const report = detail?.report;

  useEffect(() => {
    const focusTarget = returnFocus.current;
    const backdrop = backdropRef.current;
    const backgroundElements = backdrop?.parentElement
      ? Array.from(backdrop.parentElement.children).filter(
          (element): element is HTMLElement =>
            element instanceof HTMLElement && element !== backdrop,
        )
      : [];
    const previousAttributes = backgroundElements.map((element) => ({
      element,
      inert: element.getAttribute("inert"),
      ariaHidden: element.getAttribute("aria-hidden"),
    }));
    const previousBodyOverflow = document.body.style.overflow;

    backgroundElements.forEach((element) => {
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    });
    document.body.style.overflow = "hidden";
    headingRef.current?.focus();

    return () => {
      previousAttributes.forEach(({ element, inert, ariaHidden }) => {
        if (inert === null) element.removeAttribute("inert");
        else element.setAttribute("inert", inert);
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
      document.body.style.overflow = previousBodyOverflow;
      focusTarget?.focus();
    };
  }, [investigationId, returnFocus]);

  return (
    <div
      ref={backdropRef}
      className="history-report-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        ref={panelRef}
        className="history-report-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-report-title"
        aria-busy={loading}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
            return;
          }
          if (event.key !== "Tab" || !panelRef.current) return;

          const focusableElements = getFocusableElements(panelRef.current);
          if (!focusableElements.length) {
            event.preventDefault();
            headingRef.current?.focus();
            return;
          }

          const firstElement = focusableElements[0];
          const lastElement = focusableElements.at(-1);
          const activeElement = document.activeElement;
          if (
            event.shiftKey &&
            (activeElement === firstElement || activeElement === headingRef.current)
          ) {
            event.preventDefault();
            lastElement?.focus();
          } else if (
            !event.shiftKey &&
            (activeElement === lastElement || activeElement === headingRef.current)
          ) {
            event.preventDefault();
            firstElement.focus();
          }
        }}
      >
        <header>
          <div>
            <span className="eyebrow">Recovered investigation</span>
            <h2 id="history-report-title" ref={headingRef} tabIndex={-1}>
              {report?.summary ?? "调查报告"}
            </h2>
            <code>{investigationId}</code>
          </div>
          <button aria-label="关闭历史报告" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        <div className="history-report-content" aria-live="polite">
          {error ? (
            <div className="history-report-empty history-report-error" role="alert">
              <strong>无法恢复调查报告</strong>
              <span>{error.message}</span>
            </div>
          ) : loading ? (
            <p className="history-report-empty">正在恢复调查报告…</p>
          ) : report ? (
            <>
              <section className="history-report-summary">
                <div>
                  <span className="eyebrow">Report summary</span>
                  <p>{report.summary}</p>
                </div>
                <div className="history-report-metrics" aria-label="调查指标">
                  <span>
                    <small>证据</small>
                    <strong>{report.evidence_index.length}</strong>
                  </span>
                  <span>
                    <small>工具调用</small>
                    <strong>{report.model_usage.tool_calls}</strong>
                  </span>
                  <span>
                    <small>耗时</small>
                    <strong>{report.total_latency_ms} ms</strong>
                  </span>
                  <span>
                    <small>成本</small>
                    <strong>¥{report.total_cost_cny.toFixed(3)}</strong>
                  </span>
                </div>
              </section>

              <section className="history-report-section">
                <header>
                  <span className="eyebrow">Causal spine</span>
                  <h3>因果时间线</h3>
                </header>
                {report.timeline.length ? (
                  <ol className="history-timeline">
                    {report.timeline.map((item, index) => (
                      <li key={`${item.timestamp}-${item.category}-${index}`}>
                        <time dateTime={item.timestamp}>
                          {formatTime(item.timestamp)}
                        </time>
                        <div>
                          <small>{item.category}</small>
                          <p>{item.description}</p>
                          <code>{item.evidence_ids.join(" · ")}</code>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="history-section-empty">没有可用的时间线节点。</p>
                )}
              </section>

              <section className="history-report-section">
                <header>
                  <span className="eyebrow">Ranked hypotheses</span>
                  <h3>根因假设</h3>
                </header>
                {report.ranked_hypotheses.length ? (
                  <div className="history-hypotheses">
                    {report.ranked_hypotheses.map((hypothesis, index) => (
                      <article key={hypothesis.id}>
                        <div className="history-hypothesis-rank">
                          <span>#{index + 1}</span>
                          <strong>{Math.round(hypothesis.score * 100)}%</strong>
                        </div>
                        <div>
                          <small>
                            {hypothesis.status} · {hypothesis.confidence} confidence
                          </small>
                          <h4>{hypothesis.title}</h4>
                          <p>{hypothesis.causal_chain.join(" → ")}</p>
                          <dl>
                            <div>
                              <dt>支持证据</dt>
                              <dd>
                                {hypothesis.supporting_evidence_ids.join(" · ") || "—"}
                              </dd>
                            </div>
                            <div>
                              <dt>反证</dt>
                              <dd>
                                {hypothesis.contradicting_evidence_ids.join(" · ") || "—"}
                              </dd>
                            </div>
                            <div>
                              <dt>缺失证据</dt>
                              <dd>{hypothesis.missing_evidence.join(" · ") || "—"}</dd>
                            </div>
                          </dl>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="history-section-empty">没有可用的根因假设。</p>
                )}
              </section>

              <div className="history-report-columns">
                <section className="history-report-section">
                  <header>
                    <span className="eyebrow">Verified</span>
                    <h3>已确认事实</h3>
                  </header>
                  {report.confirmed_facts.length ? (
                    <ul>
                      {report.confirmed_facts.map((fact) => (
                        <li key={fact}>{fact}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="history-section-empty">没有已确认事实。</p>
                  )}
                </section>
                <section className="history-report-section">
                  <header>
                    <span className="eyebrow">Open questions</span>
                    <h3>不确定项</h3>
                  </header>
                  {report.uncertainties.length ? (
                    <ul>
                      {report.uncertainties.map((uncertainty) => (
                        <li key={uncertainty}>{uncertainty}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="history-section-empty">没有未解决的不确定项。</p>
                  )}
                </section>
              </div>

              <section className="history-report-section">
                <header>
                  <span className="eyebrow">Recommended actions</span>
                  <h3>建议处置</h3>
                </header>
                {report.recommended_actions.length ? (
                  <div className="history-actions">
                    {report.recommended_actions.map((action) => (
                      <article key={`${action.action_type}-${action.title}`}>
                        <small>
                          {action.risk} risk ·
                          {action.requires_approval ? " 需要审批" : " 无需审批"}
                        </small>
                        <h4>{action.title}</h4>
                        <p>{action.rationale}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="history-section-empty">没有建议处置。</p>
                )}
              </section>

              <section className="history-report-section">
                <header>
                  <span className="eyebrow">Evidence ledger</span>
                  <h3>证据索引</h3>
                </header>
                {report.evidence_index.length ? (
                  <div className="history-evidence">
                    {report.evidence_index.map((evidence) => (
                      <article key={evidence.id}>
                        <div>
                          <span>{evidence.kind}</span>
                          <code>{evidence.id}</code>
                        </div>
                        <strong>{evidence.service}</strong>
                        <p>{evidence.excerpt}</p>
                        <small>
                          {evidence.source} · {evidence.locator}
                        </small>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="history-section-empty">没有可用的证据。</p>
                )}
              </section>
            </>
          ) : (
            <p className="history-report-empty">
              当前调查状态为“{detail?.status ?? "未知"}”，报告尚未生成。
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}
