import { useState, useCallback, useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import type { MissionConfig } from './data/missions';
import { feasibilityEnvFromWeather } from './data/environmentSnapshot';
import { api } from './api/client';

export default function App() {
  const [selectedAircraftId, setSelectedAircraftId] = useState<string | null>(null);
  const [missionConfig, setMissionConfig] = useState<MissionConfig | null>(null);
  const [geoLocation, setGeoLocation] = useState<{ lat: number; lon: number } | null>(null);
  const [envSnapshot, setEnvSnapshot] = useState<{ wind_ms?: number; temperature_c?: number }>({});

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setGeoLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);

  // Feasibility needs wind/temp before the Weather panel is ever opened; prefetch when GPS is known.
  useEffect(() => {
    if (!geoLocation) return;
    let cancelled = false;
    (async () => {
      try {
        const w = await api.environment.weather(geoLocation.lat, geoLocation.lon);
        if (cancelled) return;
        setEnvSnapshot(feasibilityEnvFromWeather(w));
      } catch {
        /* Backend or network down — Weather tab refresh / Live telemetry can still populate */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [geoLocation]);

  const handleEnvUpdate = useCallback(
    (wind_ms: number, temperature_c: number) => {
      setEnvSnapshot({ wind_ms, temperature_c });
    },
    [],
  );

  return (
    <AppShell
      selectedAircraftId={selectedAircraftId}
      onSelectAircraft={setSelectedAircraftId}
      missionConfig={missionConfig}
      onMissionConfigChange={setMissionConfig}
      geoLocation={geoLocation}
      envSnapshot={envSnapshot}
      onEnvUpdate={handleEnvUpdate}
    />
  );
}
