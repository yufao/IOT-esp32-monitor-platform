import { defineStore } from 'pinia';

function nowMs() {
  return Date.now();
}

function formatTs(ts) {
  if (!ts) return '--';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function toNumberOrNull(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function pushPoint(series, point, limit = 240) {
  series.push(point);
  if (series.length > limit) series.splice(0, series.length - limit);
}

export const useMonitorStore = defineStore('monitor', {
  state: () => ({
    devicesById: {},
    latestById: {},
    seriesById: {},
    selectedDeviceId: null,

    wsConnected: false,
    wsUrl: null,
    lastMsgText: '(no data)',
    lastMsgAtMs: null,
  }),

  getters: {
    devicesList(state) {
      return Object.values(state.devicesById).sort((a, b) =>
        String(a.device_id || '').localeCompare(String(b.device_id || '')),
      );
    },

    onlineCount(state) {
      return Object.values(state.devicesById).filter((d) => d.status === 'online').length;
    },

    totalCount(state) {
      return Object.keys(state.devicesById).length;
    },

    selectedDevice(state) {
      if (!state.selectedDeviceId) return null;
      return state.devicesById[state.selectedDeviceId] || null;
    },

    selectedSeries(state) {
      if (!state.selectedDeviceId) return null;
      return state.seriesById[state.selectedDeviceId] || { temp: [], pressure: [], light: [] };
    },

    formatTs() {
      return formatTs;
    },
  },

  actions: {
    setSelected(deviceId) {
      this.selectedDeviceId = deviceId;
    },

    setWsStatus(connected, url = null) {
      this.wsConnected = connected;
      this.wsUrl = url || this.wsUrl;
    },

    setLastMsg(text) {
      this.lastMsgText = text;
      this.lastMsgAtMs = nowMs();
    },

    applySnapshot({ devices = [], latest = [] }) {
      for (const d of devices) {
        if (!d || !d.device_id) continue;
        const existing = this.devicesById[d.device_id] || { device_id: d.device_id };
        this.devicesById[d.device_id] = { ...existing, ...d };
      }

      for (const t of latest) {
        if (!t || !t.device_id) continue;
        this.applyTelemetry(t);
      }

      if (!this.selectedDeviceId) {
        const first = Object.keys(this.devicesById).sort()[0];
        if (first) this.selectedDeviceId = first;
      }
    },

    applyDeviceStatus(s) {
      if (!s || !s.device_id) return;
      const existing = this.devicesById[s.device_id] || { device_id: s.device_id };
      this.devicesById[s.device_id] = { ...existing, ...s };
    },

    applyTelemetry(t) {
      if (!t || !t.device_id) return;

      this.latestById[t.device_id] = t;

      const existing = this.devicesById[t.device_id] || { device_id: t.device_id };
      const merged = { ...existing };
      if (!merged.last_seen && t.timestamp) merged.last_seen = t.timestamp;
      this.devicesById[t.device_id] = merged;

      const env = t.environment || {};
      const bmp = env.bmp280 || {};
      const light = env.light || {};

      const ts = toNumberOrNull(t.timestamp);
      if (!ts) return;

      if (!this.seriesById[t.device_id]) {
        this.seriesById[t.device_id] = { temp: [], pressure: [], light: [] };
      }
      const series = this.seriesById[t.device_id];

      const temp = toNumberOrNull(bmp.temp);
      const pressure = toNumberOrNull(bmp.pressure);
      const lightPercent = toNumberOrNull(light.percent);

      if (temp !== null) pushPoint(series.temp, [ts * 1000, temp]);
      if (pressure !== null) pushPoint(series.pressure, [ts * 1000, pressure]);
      if (lightPercent !== null) pushPoint(series.light, [ts * 1000, lightPercent]);

      if (!this.selectedDeviceId) this.selectedDeviceId = t.device_id;
    },
  },
});
