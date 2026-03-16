export function getApiBase() {
  return (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000').replace(/\/$/, '');
}

export function getWsDashboardUrl() {
  const apiBase = getApiBase();
  return (
    import.meta.env.VITE_WS_DASHBOARD_URL ||
    `${apiBase.replace(/^http/, 'ws')}/ws/dashboard`
  );
}
