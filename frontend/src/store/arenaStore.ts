// ============================================
// MAGA Arena — Zustand 全局状态管理
// ============================================

import { create } from 'zustand';
import type { GameContext, PlayerState, DMVerdict, CoTOutput, NightAction } from '../types/arena';

interface ArenaState {
  // 游戏上下文
  ctx: GameContext | null;
  // 连接状态
  connected: boolean;
  gameStatus: 'idle' | 'loading' | 'running' | 'paused' | 'round_paused' | 'finished' | 'error';
  gameOverPayload: { winner_id?: string; winner_name?: string; ranking?: { name: string; score: number }[]; extra?: Record<string, any> } | null;
  // 分配模式
  assignMode: 'random' | 'manual';
  assignments: Record<string, string>;
  setAssignMode: (m: 'random' | 'manual') => void;
  setAssignments: (a: Record<string, string>) => void;
  // 人类玩家等待中（禁止查看CoT）
  humanWaiting: boolean;
  setHumanWaiting: (v: boolean) => void;
  // 发言历史
  speechLog: { playerId: string; playerName: string; content: string; round: number }[];
  // CoT 展示控制
  selectedPlayerId: string | null;
  showCoT: boolean;
  // DM 历史
  verdictHistory: DMVerdict[];
  // 夜晚行动日志（仅前端展示，不进入玩家上下文）
  nightLog: NightAction[];
  // 错误
  errors: string[];

  // Actions
  setCtx: (ctx: GameContext) => void;
  setConnected: (v: boolean) => void;
  setGameStatus: (s: ArenaState['gameStatus']) => void;
  setGameOverPayload: (p: { winner_id?: string; winner_name?: string; ranking?: { name: string; score: number }[]; extra?: Record<string, any> } | null) => void;
  addSpeech: (playerId: string, playerName: string, content: string, round: number) => void;
  setSelectedPlayer: (id: string | null) => void;
  toggleCoT: () => void;
  addVerdict: (v: DMVerdict) => void;
  addNightAction: (a: NightAction) => void;
  clearNightLog: () => void;
  addError: (e: string) => void;
  updatePlayer: (playerId: string, updates: Partial<PlayerState>) => void;
  reset: () => void;
}

export const useArenaStore = create<ArenaState>((set) => ({
  ctx: null,
  connected: false,
  gameStatus: 'idle',
  gameOverPayload: null,
  assignMode: 'random',
  assignments: {},
  setAssignMode: (m) => set({ assignMode: m }),
  setAssignments: (a) => set({ assignments: a }),
  humanWaiting: false,
  setHumanWaiting: (v) => set({ humanWaiting: v }),
  speechLog: [],
  selectedPlayerId: null,
  showCoT: false,
  verdictHistory: [],
  nightLog: [],
  errors: [],

  setCtx: (ctx) => set({ ctx }),
  setConnected: (v) => set({ connected: v }),
  setGameStatus: (s) => set({ gameStatus: s }),
  setGameOverPayload: (p) => set({ gameOverPayload: p }),

  addSpeech: (playerId, playerName, content, round) =>
    set((state) => ({
      speechLog: [...state.speechLog.slice(-100), { playerId, playerName, content, round }],
    })),

  setSelectedPlayer: (id) => set({ selectedPlayerId: id, showCoT: id !== null }),
  toggleCoT: () => set((state) => ({ showCoT: !state.showCoT })),

  addVerdict: (v) =>
    set((state) => ({
      verdictHistory: [...state.verdictHistory, v],
    })),

  addNightAction: (a) =>
    set((state) => ({
      nightLog: [...state.nightLog, a],
    })),

  clearNightLog: () => set({ nightLog: [] }),

  addError: (e) =>
    set((state) => ({
      errors: [...state.errors.slice(-50), e],
    })),

  updatePlayer: (playerId, updates) =>
    set((state) => {
      if (!state.ctx) return state;
      const players = { ...state.ctx.round.players };
      if (players[playerId]) {
        players[playerId] = { ...players[playerId], ...updates };
      }
      return {
        ctx: {
          ...state.ctx,
          round: { ...state.ctx.round, players },
        },
      };
    }),

  reset: () =>
    set({
      ctx: null,
      gameStatus: 'idle',
      gameOverPayload: null,
      assignMode: 'random',
      assignments: {},
      humanWaiting: false,
      speechLog: [],
      selectedPlayerId: null,
      showCoT: false,
      verdictHistory: [],
      nightLog: [],
      errors: [],
    }),
}));
