import type { WeatherResponse } from '../types/api';

/** Wind + temperature fields used by feasibility and analysis (matches EnvironmentIntel → App wiring). */
export function feasibilityEnvFromWeather(w: WeatherResponse): {
  wind_ms: number;
  temperature_c: number;
} {
  const surface = w.wind_layers?.[0];
  return {
    wind_ms: surface?.speed_ms ?? 0,
    temperature_c: w.temperature_c,
  };
}
