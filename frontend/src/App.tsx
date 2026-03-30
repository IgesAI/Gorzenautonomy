import { useState, useCallback, useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import type { MissionConfig } from './data/missions';

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
