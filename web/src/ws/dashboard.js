import { getWsDashboardUrl } from '../env';

export function connectDashboardWs({
  onOpen,
  onClose,
  onError,
  onMessage,
  reconnectDelayMs = 1500,
} = {}) {
  let ws = null;
  let closed = false;
  let reconnectTimer = null;

  function cleanup() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      try {
        ws.close();
      } catch {
        // ignore
      }
      ws = null;
    }
  }

  function scheduleReconnect() {
    if (closed) return;
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, reconnectDelayMs);
  }

  function open() {
    cleanup();
    const url = getWsDashboardUrl();
    ws = new WebSocket(url);

    ws.addEventListener('open', () => {
      onOpen && onOpen({ url });
    });

    ws.addEventListener('close', () => {
      onClose && onClose();
      scheduleReconnect();
    });

    ws.addEventListener('error', (e) => {
      onError && onError(e);
    });

    ws.addEventListener('message', (ev) => {
      onMessage && onMessage(ev.data);
    });
  }

  open();

  return {
    close() {
      closed = true;
      cleanup();
    },
    sendJson(obj) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      try {
        ws.send(JSON.stringify(obj));
        return true;
      } catch {
        return false;
      }
    },
    get readyState() {
      return ws ? ws.readyState : WebSocket.CLOSED;
    },
  };
}
