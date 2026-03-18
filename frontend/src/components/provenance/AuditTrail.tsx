import React from 'react';
import { Clock, FileText, Database } from 'lucide-react';

interface AuditEntry {
  id: string;
  timestamp: string;
  event_type: string;
  actor: string;
  description: string;
}

interface AuditTrailProps {
  entries?: AuditEntry[];
}

const ICON_MAP: Record<string, React.ElementType> = {
  config_change: FileText,
  calibration: Database,
  default: Clock,
};

export function AuditTrail({ entries = [] }: AuditTrailProps) {
  if (entries.length === 0) {
    return (
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
          Audit Trail
        </h3>
        <div className="text-xs text-white/20">No audit events recorded</div>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Audit Trail
      </h3>
      <div className="space-y-2">
        {entries.map((entry) => {
          const Icon = ICON_MAP[entry.event_type] ?? ICON_MAP.default;
          return (
            <div key={entry.id} className="flex items-start gap-2">
              <Icon size={12} className="text-white/30 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs text-white/70">{entry.description}</div>
                <div className="text-[10px] text-white/30">
                  {entry.actor} - {entry.timestamp}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
