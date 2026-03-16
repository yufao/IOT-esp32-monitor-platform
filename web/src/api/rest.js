import { getApiBase } from '../env';

async function fetchJson(url) {
  const resp = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

export async function fetchDevices() {
  const apiBase = getApiBase();
  const data = await fetchJson(`${apiBase}/api/devices`);
  return data.items || [];
}

export async function fetchLatestTelemetry() {
  const apiBase = getApiBase();
  const data = await fetchJson(`${apiBase}/api/telemetry/latest`);
  return data.items || [];
}

export async function fetchSnapshot() {
  const [devices, latest] = await Promise.all([fetchDevices(), fetchLatestTelemetry()]);
  return { devices, latest };
}
