import React from 'react';
import type { MissionPlan } from '../../types/mission';

interface MissionMapProps {
  plan?: MissionPlan | null;
}

export function MissionMap({ plan }: MissionMapProps) {
  if (!plan || plan.waypoints.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-white/20 text-sm">
        No mission plan loaded
      </div>
    );
  }

  const wps = plan.waypoints;
  const lats = wps.map((w) => w.latitude_deg);
  const lons = wps.map((w) => w.longitude_deg);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  const pad = 0.1;
  const rangeX = maxLon - minLon || 0.001;
  const rangeY = maxLat - minLat || 0.001;

  const toSvg = (lat: number, lon: number) => ({
    x: ((lon - minLon) / rangeX) * 280 + 10,
    y: (1 - (lat - minLat) / rangeY) * 180 + 10,
  });

  const points = wps.map((w) => toSvg(w.latitude_deg, w.longitude_deg));
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Mission Trajectory
      </h3>
      <svg viewBox="0 0 300 200" className="w-full h-auto">
        <rect x="0" y="0" width="300" height="200" fill="rgba(0,0,0,0.2)" rx="8" />
        <path d={pathD} fill="none" stroke="#2f7fff" strokeWidth="1.5" opacity="0.7" />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={i === 0 || i === points.length - 1 ? 4 : 2}
            fill={i === 0 ? '#10b981' : i === points.length - 1 ? '#ef4444' : '#56a4ff'}
          />
        ))}
      </svg>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-white/50 font-mono">
        <div>Distance: {(plan.estimated_distance_m / 1000).toFixed(2)} km</div>
        <div>Duration: {(plan.estimated_duration_s / 60).toFixed(1)} min</div>
        <div>Energy: {plan.estimated_energy_wh.toFixed(0)} Wh</div>
      </div>
    </div>
  );
}
