import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/twins/schema')) {
        return {
          ok: true,
          json: async () => ({
            subsystems: {
              airframe: { label: 'Airframe', description: '', parameters: {} },
              mission_profile: { label: 'Mission', description: '', parameters: {} },
            },
            twin_id: '00000000-0000-0000-0000-000000000001',
            version: { major: 0, minor: 1, patch: 0 },
          }),
        };
      }
      if (url.includes('/twins') && !url.includes('/twins/schema')) {
        return { ok: true, json: async () => [] };
      }
      return { ok: true, json: async () => ({}) };
    }),
  );
});

describe('App', () => {
  it('renders shell title', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>,
    );
    expect(await screen.findByAltText('Vertical Autonomy')).toBeInTheDocument();
  });
});
