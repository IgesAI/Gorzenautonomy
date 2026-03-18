import React from 'react';
import type { Waypoint, PayloadAction } from '../../types/mission';

interface WaypointEditorProps {
  waypoints: Waypoint[];
  payloadActions: PayloadAction[];
  onUpdate?: (waypoints: Waypoint[]) => void;
}

export function WaypointEditor({ waypoints, payloadActions, onUpdate }: WaypointEditorProps) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Waypoints ({waypoints.length})
      </h3>
      <div className="max-h-64 overflow-y-auto space-y-1">
        {waypoints.map((wp) => {
          const action = payloadActions.find((a) => a.waypoint_sequence === wp.sequence);
          return (
            <div
              key={wp.sequence}
              className="flex items-center gap-3 px-2 py-1.5 rounded-md hover:bg-white/5 transition-colors"
            >
              <span className="text-[10px] font-mono text-white/30 w-6">{wp.sequence}</span>
              <span className="text-xs text-gorzen-400 w-16">{wp.wp_type}</span>
              <span className="text-[10px] font-mono text-white/50 flex-1">
                {wp.latitude_deg.toFixed(6)}, {wp.longitude_deg.toFixed(6)}
              </span>
              <span className="text-[10px] font-mono text-white/40">
                {wp.altitude_m.toFixed(0)}m
              </span>
              {wp.speed_ms && (
                <span className="text-[10px] font-mono text-white/40">
                  {wp.speed_ms.toFixed(1)}m/s
                </span>
              )}
              {action && (
                <span className="text-[10px] bg-gorzen-500/20 text-gorzen-400 px-1.5 py-0.5 rounded">
                  {action.action_type}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
