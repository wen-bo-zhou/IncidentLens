import { Activity, Box, Database, RadioTower, Upload, X } from "lucide-react";
import { FormEvent, useState } from "react";

import type { IncidentCase } from "@/lib/types";

const familyIcons = {
  deployment_config: Box,
  db_pool_exhaustion: Database,
  poison_message: RadioTower,
};

interface IncidentRailProps {
  incidents: IncidentCase[];
  selectedId?: string;
  onSelect: (id: string) => void;
  loading: boolean;
  onImportIncident?: (file: File, adminToken: string) => Promise<void>;
}

function ImportIncidentDialog({
  onClose,
  onImport,
}: {
  onClose: () => void;
  onImport: (file: File, adminToken: string) => Promise<void>;
}) {
  const [file, setFile] = useState<File>();
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError(undefined);
    try {
      await onImport(file, token);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "事故包导入失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-scrim" onMouseDown={onClose}>
      <form
        className="live-dialog import-dialog"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
        noValidate
      >
        <header>
          <div><span className="eyebrow">Incident package</span><h2>导入事故包</h2></div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭导入事故包">
            <X size={18} />
          </button>
        </header>
        <p>导入经过校验的 JSON 证据包。内容哈希、时间范围和证据引用会在保存前验证。</p>
        <label htmlFor="incident-pack">JSON 事故包</label>
        <input
          id="incident-pack"
          type="file"
          accept=".json,application/json"
          onChange={(event) => setFile(event.target.files?.[0])}
          required
        />
        <label htmlFor="incident-import-token">管理员令牌</label>
        <input
          id="incident-import-token"
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="admin-demo-token"
          autoComplete="off"
          required
        />
        {error && <p className="form-error">{error}</p>}
        <button className="run-button" disabled={!file || !token || submitting}>
          {submitting ? "正在校验" : "确认导入"}
        </button>
      </form>
    </div>
  );
}

export function IncidentRail({
  incidents,
  selectedId,
  onSelect,
  loading,
  onImportIncident,
}: IncidentRailProps) {
  const [showImport, setShowImport] = useState(false);
  return (
    <aside className="incident-rail" aria-label="事故演练列表">
      <div className="rail-heading">
        <span className="eyebrow">Replay library</span>
        <h2>事故演练</h2>
        <span className="rail-count">{incidents.length || "—"}</span>
      </div>

      <div className="rail-list">
        {loading &&
          Array.from({ length: 3 }).map((_, index) => (
            <div className="case-card skeleton" key={index} aria-hidden="true" />
          ))}
        {incidents.map((incident) => {
          const Icon = familyIcons[incident.scenario_family as keyof typeof familyIcons] ?? Activity;
          const active = incident.id === selectedId;
          return (
            <button
              className={`case-card ${active ? "active" : ""}`}
              key={incident.id}
              onClick={() => onSelect(incident.id)}
              aria-pressed={active}
            >
              <span className="case-glyph"><Icon size={16} strokeWidth={1.8} /></span>
              <span className="case-copy">
                <span className="case-severity">{incident.severity}</span>
                <strong>{incident.title}</strong>
                <small>{incident.services.length} 个服务 · {incident.evidence_count} 条证据</small>
              </span>
            </button>
          );
        })}
      </div>

      {onImportIncident && (
        <button className="rail-import-button" onClick={() => setShowImport(true)}>
          <Upload size={14} />导入事故包
        </button>
      )}

      <div className="rail-note">
        <Activity size={15} />
        <p>公开模式使用已缓存的完整调查轨迹，不消耗模型额度。</p>
      </div>
      {showImport && onImportIncident && (
        <ImportIncidentDialog
          onClose={() => setShowImport(false)}
          onImport={onImportIncident}
        />
      )}
    </aside>
  );
}
