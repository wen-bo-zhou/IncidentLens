import { Activity, Box, Database, RadioTower } from "lucide-react";

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
}

export function IncidentRail({ incidents, selectedId, onSelect, loading }: IncidentRailProps) {
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

      <div className="rail-note">
        <Activity size={15} />
        <p>公开模式使用已缓存的完整调查轨迹，不消耗模型额度。</p>
      </div>
    </aside>
  );
}

