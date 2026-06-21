// ============================================
// WebSocket 客户端封装（备用 / 手动控制）
// ============================================

export type WSMessageHandler = (data: Record<string, unknown>) => void;

export class ArenaWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<string, WSMessageHandler[]> = new Map();
  private reconnectDelay = 3000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;

  constructor(url?: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = url || `${protocol}//${window.location.host}/ws`;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.emit('connected', {});
      this.startHeartbeat();
    };

    this.ws.onclose = () => {
      this.emit('disconnected', {});
      this.stopHeartbeat();
      setTimeout(() => this.connect(), this.reconnectDelay);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const eventType = data.event_type || 'message';
        this.emit(eventType, data.payload || data);
        this.emit('*', data);
      } catch {
        // ignore
      }
    };
  }

  disconnect() {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
  }

  on(event: string, handler: WSMessageHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);
  }

  off(event: string, handler: WSMessageHandler) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      const idx = handlers.indexOf(handler);
      if (idx >= 0) handlers.splice(idx, 1);
    }
  }

  send(type: string, payload: Record<string, unknown> = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...payload }));
    }
  }

  private emit(event: string, data: Record<string, unknown>) {
    const handlers = this.handlers.get(event) || [];
    handlers.forEach((h) => h(data));
  }

  private startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      this.send('ping');
    }, 15000);
  }

  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }
}
