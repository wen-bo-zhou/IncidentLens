import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InvestigationWorkspace } from "@/components/investigation-workspace";
import type { IncidentCase, InvestigationReport } from "@/lib/types";

const incident: IncidentCase = {
  id: "deploy-timeout-showcase",
  title: "结算发布后支付超时",
  summary: "结算成功率在新版本发布后迅速下降。",
  scenario_family: "deployment_config",
  visibility: "showcase",
  starts_at: "2026-01-10T09:00:00Z",
  ends_at: "2026-01-10T10:00:00Z",
  services: ["checkout-service", "payment-service"],
  evidence_count: 6,
  replay_available: true,
  severity: "SEV-2",
};

const report: InvestigationReport = {
  investigation_id: "replay-deploy-timeout-showcase",
  summary: "最可能根因：发布配置将支付超时阈值错误降低。",
  timeline: [
    {
      timestamp: "2026-01-10T09:04:00Z",
      category: "deployment",
      description: "release v2.4 deployed",
      evidence_ids: ["ev-deploy"],
    },
  ],
  ranked_hypotheses: [
    {
      id: "hyp-1",
      title: "发布配置将支付超时阈值错误降低",
      root_cause_category: "deployment_config",
      causal_chain: ["发布新配置", "超时阈值降低", "支付调用提前取消"],
      supporting_evidence_ids: ["ev-deploy"],
      contradicting_evidence_ids: [],
      missing_evidence: [],
      score: 0.91,
      confidence: "high",
      status: "supported",
    },
  ],
  confirmed_facts: ["支付调用在 120ms 被取消"],
  uncertainties: ["真实生产处置前仍需人工复核"],
  recommended_actions: [
    {
      action_type: "rollback_virtual_version",
      title: "回滚虚拟版本",
      rationale: "恢复此前配置",
      risk: "medium",
      requires_approval: true,
    },
  ],
  evidence_index: [
    {
      id: "ev-deploy",
      kind: "log",
      timestamp: "2026-01-10T09:04:00Z",
      service: "checkout-service",
      source: "seed/deploy",
      locator: "line:1",
      excerpt: "release v2.4 deployed; PAYMENT_TIMEOUT_MS changed to 120",
      content_hash: "hash",
      attributes: { level: "INFO" },
    },
  ],
  model_usage: {
    provider: "offline",
    model: "evidence-rules-v1",
    prompt_tokens: 0,
    completion_tokens: 0,
    model_calls: 0,
    tool_calls: 4,
  },
  total_cost_cny: 0,
  total_latency_ms: 31,
};

describe("InvestigationWorkspace", () => {
  it("shows the causal spine, top hypothesis and run action", () => {
    render(
      <InvestigationWorkspace incident={incident} report={report} loading={false} onRun={vi.fn()} />,
    );

    expect(screen.getByRole("heading", { name: "结算发布后支付超时" })).toBeInTheDocument();
    expect(screen.getByText("发布配置将支付超时阈值错误降低")).toBeInTheDocument();
    expect(screen.getByText("91%")) .toBeInTheDocument();
    expect(screen.getByText("release v2.4 deployed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新调查" })).toBeInTheDocument();
  });

  it("opens linked evidence from the causal spine", async () => {
    const user = userEvent.setup();
    render(
      <InvestigationWorkspace incident={incident} report={report} loading={false} onRun={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: "查看证据 ev-deploy" }));

    expect(screen.getByRole("dialog", { name: "证据详情" })).toBeInTheDocument();
    expect(screen.getByText(/PAYMENT_TIMEOUT_MS changed to 120/)).toBeInTheDocument();
  });

  it("keeps the runner token in an explicit live-run dialog", async () => {
    const user = userEvent.setup();
    const runLive = vi.fn().mockResolvedValue(undefined);
    render(
      <InvestigationWorkspace
        incident={incident}
        report={report}
        loading={false}
        onRun={vi.fn()}
        onRunLive={runLive}
      />,
    );

    await user.click(screen.getByRole("button", { name: "实时调查" }));
    await user.type(screen.getByLabelText("Runner 令牌"), "runner-demo-token");
    await user.click(screen.getByRole("button", { name: "确认启动" }));

    expect(runLive).toHaveBeenCalledWith("runner-demo-token", {
      startAt: incident.starts_at,
      endAt: incident.ends_at,
    });
    expect(screen.queryByLabelText("Runner 令牌")).not.toBeInTheDocument();
  });

  it("explains an inconclusive report and shows the missing evidence", () => {
    const inconclusiveReport: InvestigationReport = {
      ...report,
      summary: "The available evidence does not support a root-cause conclusion.",
      timeline: [],
      ranked_hypotheses: [],
      confirmed_facts: [],
      recommended_actions: [],
      uncertainties: ["Collect logs, metrics, and traces for the affected window."],
    };

    render(
      <InvestigationWorkspace
        incident={incident}
        report={inconclusiveReport}
        loading={false}
        onRun={vi.fn()}
        liveStatus="inconclusive"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "证据不足，无法判定根因" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Collect logs, metrics, and traces for the affected window."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("所选时间窗内没有可用于因果排序的事件"),
    ).toBeInTheDocument();
  });

  it("lets the operator cancel an active live investigation", async () => {
    const user = userEvent.setup();
    const cancelLive = vi.fn().mockResolvedValue(undefined);

    render(
      <InvestigationWorkspace
        incident={incident}
        report={report}
        loading
        onRun={vi.fn()}
        onCancelLive={cancelLive}
      />,
    );

    await user.click(screen.getByRole("button", { name: "取消调查" }));

    expect(cancelLive).toHaveBeenCalledOnce();
  });
});
