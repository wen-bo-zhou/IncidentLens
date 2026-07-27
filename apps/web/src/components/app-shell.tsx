"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CircleDotDashed,
  ClipboardList,
  FlaskConical,
  Radar,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { IncidentRail } from "@/components/incident-rail";
import { InvestigationWorkspace } from "@/components/investigation-workspace";
import { api } from "@/lib/api";
import type {
  InvestigationReport,
  InvestigationWindow,
  RemediationProposal,
  WorkflowEvent,
  WorkflowEventType,
} from "@/lib/types";

const streamedEventTypes: WorkflowEventType[] = [
  "stage_started",
  "stage_completed",
  "tool_started",
  "tool_completed",
  "hypothesis_updated",
  "usage_updated",
  "report_ready",
  "run_failed",
  "run_canceled",
];
const terminalStatuses = new Set(["completed", "failed", "canceled", "inconclusive"]);

export function AppShell() {
  const incidentsQuery = useQuery({ queryKey: ["incidents"], queryFn: api.incidents });
  const [chosenId, setChosenId] = useState<string>();
  const [liveReport, setLiveReport] = useState<InvestigationReport>();
  const [liveStatus, setLiveStatus] = useState<string>();
  const [liveEvents, setLiveEvents] = useState<WorkflowEvent[]>([]);
  const [remediations, setRemediations] = useState<RemediationProposal[]>([]);
  const eventSource = useRef<EventSource | null>(null);
  const liveCredentials = useRef<
    { investigationId: string; runnerToken: string } | undefined
  >(undefined);
  const selectedId = chosenId ?? incidentsQuery.data?.[0]?.id;
  const incident = incidentsQuery.data?.find((item) => item.id === selectedId);

  const reportQuery = useQuery({
    queryKey: ["replay", selectedId],
    queryFn: () => api.replay(selectedId!),
    enabled: Boolean(selectedId && incident?.replay_available),
  });
  const liveRunning = Boolean(
    liveStatus && !["completed", "failed", "canceled", "inconclusive", "report pending"].includes(liveStatus),
  );

  useEffect(() => () => eventSource.current?.close(), []);

  function selectIncident(caseId: string) {
    eventSource.current?.close();
    setLiveReport(undefined);
    setLiveStatus(undefined);
    setLiveEvents([]);
    setRemediations([]);
    liveCredentials.current = undefined;
    setChosenId(caseId);
  }

  async function loadCompletedReport(investigationId: string): Promise<void> {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      let detail;
      try {
        detail = await api.investigation(investigationId);
      } catch {
        await new Promise((resolve) => window.setTimeout(resolve, 200));
        continue;
      }
      if (detail.report) {
        setLiveReport(detail.report);
        setRemediations(detail.remediation_proposals);
        setLiveStatus(detail.status);
        liveCredentials.current = undefined;
        eventSource.current?.close();
        return;
      }
      if (terminalStatuses.has(detail.status)) {
        setLiveStatus(detail.status);
        liveCredentials.current = undefined;
        eventSource.current?.close();
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    setLiveStatus("report pending");
  }

  async function runLive(
    runnerToken: string,
    window: InvestigationWindow,
  ): Promise<void> {
    if (!selectedId) return;
    eventSource.current?.close();
    setLiveReport(undefined);
    setLiveEvents([]);
    setRemediations([]);
    setLiveStatus("queued");
    const key = `${selectedId}-${crypto.randomUUID()}`;
    const created = await api.createInvestigation(selectedId, runnerToken, key, window);
    liveCredentials.current = {
      investigationId: created.investigation_id,
      runnerToken,
    };
    const stream = new EventSource(api.eventsUrl(created.investigation_id));
    let fallbackStarted = false;
    eventSource.current = stream;

    for (const eventType of streamedEventTypes) {
      stream.addEventListener(eventType, (message) => {
        const event = JSON.parse((message as MessageEvent<string>).data) as WorkflowEvent;
        setLiveEvents((current) =>
          current.some((item) => item.sequence === event.sequence) ? current : [...current, event],
        );
        if (event.type === "stage_started" || event.type === "tool_started") {
          setLiveStatus(event.type === "tool_started" ? `${event.stage} · ${event.message}` : event.stage);
        }
        if (event.type === "report_ready") void loadCompletedReport(created.investigation_id);
        if (event.type === "run_failed" || event.type === "run_canceled") {
          setLiveStatus(event.type === "run_failed" ? "failed" : "canceled");
          liveCredentials.current = undefined;
          stream.close();
        }
      });
    }
    stream.onerror = () => {
      setLiveStatus((current) =>
        current && terminalStatuses.has(current) ? current : "SSE reconnecting",
      );
      if (!fallbackStarted) {
        fallbackStarted = true;
        void loadCompletedReport(created.investigation_id);
      }
    };
  }

  async function cancelLive(): Promise<void> {
    const active = liveCredentials.current;
    if (!active) return;
    await api.cancelInvestigation(active.investigationId, active.runnerToken);
    liveCredentials.current = undefined;
    eventSource.current?.close();
    setLiveStatus("canceled");
  }

  async function approveRemediation(proposalId: string, adminToken: string): Promise<void> {
    const investigationId = liveReport?.investigation_id;
    if (!investigationId) throw new Error("仅实时调查报告可以审批处置");
    const result = await api.approveRemediation(investigationId, proposalId, adminToken);
    setRemediations((current) =>
      current.map((proposal) =>
        proposal.id === proposalId ? { ...proposal, status: result.status } : proposal,
      ),
    );
  }

  async function importIncident(file: File, adminToken: string): Promise<void> {
    const imported = await api.importIncident(file, adminToken);
    await incidentsQuery.refetch();
    selectIncident(imported.id);
  }

  return (
    <div className="app-frame">
      <header className="topbar">
        <Link href="/" className="brand" aria-label="IncidentLens 首页">
          <span className="brand-mark"><Radar size={19} /></span>
          <span><strong>IncidentLens</strong><small>事故证据调查系统</small></span>
        </Link>
        <nav aria-label="主导航">
          <Link className="nav-link active" href="/"><CircleDotDashed size={15} />调查台</Link>
          <Link className="nav-link" href="/evaluations"><FlaskConical size={15} />评测</Link>
          <Link className="nav-link" href="/operations"><ClipboardList size={15} />运营</Link>
        </nav>
        <div className="system-status"><span />DEMO REPLAY · HEALTHY</div>
      </header>

      <div className="shell-body">
        <IncidentRail
          incidents={incidentsQuery.data ?? []}
          selectedId={selectedId}
          onSelect={selectIncident}
          loading={incidentsQuery.isLoading}
          onImportIncident={importIncident}
        />
        {incidentsQuery.error ? (
          <main className="connection-error">
            <AlertTriangle size={28} />
            <h1>无法连接调查 API</h1>
            <p>{incidentsQuery.error.message}</p>
            <button onClick={() => incidentsQuery.refetch()}>重新连接</button>
          </main>
        ) : incident ? (
          <InvestigationWorkspace
            incident={incident}
            report={liveReport ?? reportQuery.data}
            loading={reportQuery.isFetching || liveRunning}
            onRun={() => {
              setLiveReport(undefined);
              setLiveStatus(undefined);
              setLiveEvents([]);
              setRemediations([]);
              void reportQuery.refetch();
            }}
            onRunLive={runLive}
            onCancelLive={liveRunning ? cancelLive : undefined}
            liveStatus={liveStatus}
            liveEventCount={liveEvents.length}
            remediationProposals={remediations}
            onApproveRemediation={approveRemediation}
          />
        ) : (
          <main className="workspace"><div className="report-empty"><div className="scanner" /><h2>正在读取事故演练</h2></div></main>
        )}
      </div>
    </div>
  );
}
