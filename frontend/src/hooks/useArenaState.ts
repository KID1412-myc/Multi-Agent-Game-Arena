// ============================================
// 竞技场状态订阅 Hook（便捷封装）
// ============================================

import { useArenaStore } from '../store/arenaStore';
import type { PlayerState, DMVerdict } from '../types/arena';

export function useArenaState() {
  return {
    ctx: useArenaStore((s) => s.ctx),
    connected: useArenaStore((s) => s.connected),
    gameStatus: useArenaStore((s) => s.gameStatus),
    speechLog: useArenaStore((s) => s.speechLog),
    selectedPlayerId: useArenaStore((s) => s.selectedPlayerId),
    showCoT: useArenaStore((s) => s.showCoT),
    verdictHistory: useArenaStore((s) => s.verdictHistory),
    errors: useArenaStore((s) => s.errors),
  };
}

export function usePlayerStates(): PlayerState[] {
  const ctx = useArenaStore((s) => s.ctx);
  if (!ctx) return [];
  return Object.values(ctx.round.players);
}

export function useLastVerdict(): DMVerdict | null {
  return useArenaStore((s) => {
    const history = s.verdictHistory;
    return history.length > 0 ? history[history.length - 1] : s.ctx?.dm_last_verdict ?? null;
  });
}

export function useCurrentSpeaker(): PlayerState | null {
  const ctx = useArenaStore((s) => s.ctx);
  if (!ctx) return null;
  return Object.values(ctx.round.players).find((p) => p.is_current_speaker) ?? null;
}
