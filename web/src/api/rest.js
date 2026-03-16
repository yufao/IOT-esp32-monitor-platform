import { getApiBase, getApiKey } from '../env';

async function requestJson(url, { method = 'GET', headers = {}, body = undefined } = {}) {
  const resp = await fetch(url, {
    method,
    headers: { Accept: 'application/json', ...headers },
    body,
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

async function fetchJson(url) {
  return requestJson(url);
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

export async function fetchTelemetryHistory({ deviceId, since, until, limit = 200 } = {}) {
  if (!deviceId) throw new Error('deviceId required');
  const apiBase = getApiBase();

  const params = new URLSearchParams({ device_id: String(deviceId) });
  if (since) params.set('since', String(since));
  if (until) params.set('until', String(until));
  if (limit) params.set('limit', String(limit));

  const data = await fetchJson(`${apiBase}/api/telemetry/history?${params.toString()}`);
  if (data.ok === false) throw new Error(data.error || 'history query failed');
  return data.items || [];
}

export async function sendCommand({ deviceId, command } = {}) {
  if (!deviceId) throw new Error('deviceId required');
  if (!command || typeof command !== 'object') throw new Error('command required');

  const apiBase = getApiBase();
  const apiKey = getApiKey();
  if (!apiKey) throw new Error('missing VITE_API_KEY');

  const data = await requestJson(`${apiBase}/api/commands/send`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ device_id: String(deviceId), command }),
  });

  if (data.ok === false) throw new Error(data.error || 'send command failed');
  return data;
}
