// ============================================
// MAGA Arena — WebSocket 连接 Hook
// ============================================

import { useEffect, useRef, useCallback } from 'react';
import { useArenaStore } from '../store/arenaStore';
import type { WSEvent, WSEventType } from '../types/arena';

const handlers: Record<WSEventType, (payload: Record<string, unknown>, store: ReturnType<typeof useArenaStore.getState>) => void> = {
  GAME_INIT: (payload, store) => {
    if (payload.ctx) {
      store.setCtx(payload.ctx as unknown as import('../types/arena').GameContext);
    }
    store.setGameStatus('running');
  },

  ROUND_START: (payload, _store) => {
    // 轮次开始，前端高亮效果由组件处理
  },

  PLAYER_THINKING: (payload, store) => {
    const playerId = payload.player_id as string;
    store.updatePlayer(playerId, { is_thinking: true });
  },

  PLAYER_SPEECH: (payload, store) => {
    const playerId = payload.player_id as string;
    const playerName = payload.player_name as string;
    const speech = payload.speech as string;
    const round = payload.round as number;
    store.addSpeech(playerId, playerName, speech, round);
    store.updatePlayer(playerId, {
      is_thinking: false,
      is_current_speaker: false,
      last_public_speech: speech,
    });
  },

  PLAYER_COT: (payload, store) => {
    const playerId = payload.player_id as string;
    const cot = payload.cot as unknown as import('../types/arena').CoTOutput;
    store.updatePlayer(playerId, { last_cot: cot });
  },

  DM_JUDGMENT: (payload, store) => {
    const verdict = payload.verdict as unknown as import('../types/arena').DMVerdict;
    store.addVerdict(verdict);
  },

  STATE_UPDATE: (payload, store) => {
    if (payload.phase === 'round_paused') {
      store.setGameStatus('round_paused');
    }
    if (payload.ctx) {
      store.setCtx(payload.ctx as unknown as import('../types/arena').GameContext);
    }
  },

  PLAYER_ERROR: (payload, _store) => {
    // 玩家错误
  },

  GAME_OVER: (_payload, store) => {
    store.setGameStatus('finished');
  },

  ENGINE_ERROR: (payload, store) => {
    const msg = payload.message as string;
    store.addError(msg);
    store.setGameStatus('error');
    alert(`引擎错误: ${msg}`);
  },
};

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const setConnected = useArenaStore((s) => s.setConnected);
  const setGameStatus = useArenaStore((s) => s.setGameStatus);
  const reset = useArenaStore((s) => s.reset);
  const store = useArenaStore;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // 启动心跳
      const heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 15000);
      ws.addEventListener('close', () => clearInterval(heartbeat));
    };

    ws.onclose = () => {
      setConnected(false);
      // 自动重连
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const eventType = data.event_type as WSEventType;
        const payload = (data.payload || {}) as Record<string, unknown>;

        const handler = handlers[eventType];
        if (handler) {
          handler(payload, store.getState());
        }
      } catch {
        // 忽略解析错误
      }
    };
  }, [setConnected, store]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      reset();
    };
  }, [connect, reset]);

  return {
    connected: useArenaStore((s) => s.connected),
    reconnect: connect,
  };
}
