import {
  Activity,
  Box,
  Database,
  LockKeyhole,
  RadioTower,
  UnlockKeyhole,
  Upload,
  X,
} from "lucide-react";
import { FormEvent, useState } from "react";

import type { AuthSession, IncidentCase } from "@/lib/types";

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
  onUnlockCatalog?: (token: string) => Promise<void>;
  catalogUnlocked?: boolean;
  sessionRole?: AuthSession["role"];
}

function CatalogAccessDialog({
  onClose,
  onUnlock,
}: {
  onClose: () => void;
  onUnlock: (token: string) => Promise<void>;
}) {
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      await onUnlock(token);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载私有事故目录");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-scrim" onMouseDown={onClose}>
      <form
        className="live-dialog catalog-dialog"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">Private catalog</span>
            <h2>打开私有目录</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="关闭私有目录登录"
          >
            <X size={18} />
          </button>
        </header>
        <p>
          使用 Runner 或 Admin 令牌读取导入的生产事故。令牌仅保留在当前页面内存中，刷新后会清除。
        </p>
        <label htmlFor="incident-catalog-token">Runner / Admin 令牌</label>
        <input
          id="incident-catalog-token"
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="输入访问令牌"
          autoComplete="off"
          required
        />
        {error && <p className="form-error">{error}</p>}
        <button className="run-button" disabled={!token || submitting}>
          {submitting ? "正在验证" : "加载私有事故"}
        </button>
      </form>
    </div>
  );
}

function ImportIncidentDialog({
  onClose,
  onImport,
  useSession,
}: {
  onClose: () => void;
  onImport: (file: File, adminToken: string) => Promise<void>;
  useSession: boolean;
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
        {useSession ? (
          <p className="session-assurance">
            企业 Admin 会话已验证，导入动作会写入审计记录。
          </p>
        ) : (
          <>
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
          </>
        )}
        {error && <p className="form-error">{error}</p>}
        <button
          className="run-button"
          disabled={!file || (!useSession && !token) || submitting}
        >
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
  onUnlockCatalog,
  catalogUnlocked = false,
  sessionRole = "guest",
}: IncidentRailProps) {
  const [showImport, setShowImport] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const hasCatalogSession =
    sessionRole === "runner" || sessionRole === "admin";
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

      {(onImportIncident || onUnlockCatalog) && (
        <div className="rail-actions">
          {onUnlockCatalog && (
            <button
              className={`rail-catalog-button ${
                catalogUnlocked || hasCatalogSession ? "unlocked" : ""
              }`}
              onClick={() => {
                if (hasCatalogSession) {
                  void onUnlockCatalog("");
                } else {
                  setShowCatalog(true);
                }
              }}
            >
              {catalogUnlocked || hasCatalogSession ? (
                <UnlockKeyhole size={14} />
              ) : (
                <LockKeyhole size={14} />
              )}
              {hasCatalogSession
                ? "刷新私有目录"
                : catalogUnlocked
                  ? "私有目录已解锁"
                  : "打开私有目录"}
            </button>
          )}
          {onImportIncident && (
            <button className="rail-import-button" onClick={() => setShowImport(true)}>
              <Upload size={14} />导入事故包
            </button>
          )}
        </div>
      )}

      <div className="rail-note">
        <Activity size={15} />
        <p>公开模式使用已缓存的完整调查轨迹，不消耗模型额度。</p>
      </div>
      {showImport && onImportIncident && (
        <ImportIncidentDialog
          onClose={() => setShowImport(false)}
          onImport={onImportIncident}
          useSession={sessionRole === "admin"}
        />
      )}
      {showCatalog && onUnlockCatalog && (
        <CatalogAccessDialog
          onClose={() => setShowCatalog(false)}
          onUnlock={onUnlockCatalog}
        />
      )}
    </aside>
  );
}
