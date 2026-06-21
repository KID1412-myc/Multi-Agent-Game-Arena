// ============================================
// MAGA Arena — TypeScript 类型定义
// 与 Python engine/schema.py 保持同步
// ============================================

export interface ResourceDef {
  id: string;
  label: string;
  unit: string;
  icon: string;
}

export interface PlayerDef {
  id: string;
  name: string;
  model: string;
  provider: string;
  secret_identity: string;
  initial_resources: Record<string, number>;
}

export interface CoTOutput {
  situation_assessment: string;
  internal_strategy: string;
  public_speech: string;
  secret_action: string;
}

export interface PlayerState {
  id: string;
  name: string;
  model: string;
  provider: string;
  resources: Record<string, number>;
  is_alive: boolean;
  is_current_speaker: boolean;
  is_thinking: boolean;
  last_public_speech: string;
  last_cot: CoTOutput | null;
  private_notebook: string[];
}

export interface DMVerdict {
  round_number: number;
  round_summary: string;
  global_narrative: string;
  resource_delta: ResourceDelta[];
  private_messages: PrivateMessage[];
  winner_id: string | null;
  critical_events: CriticalEvent[];
  next_round_phase: string;
}

export interface ResourceDelta {
  player_id: string;
  changes: Record<string, number>;
}

export interface PrivateMessage {
  player_id: string;
  message: string;
}

export interface CriticalEvent {
  round_number: number;
  event: string;
  related_players: string[];
  timestamp: string;
}

export interface RoundState {
  round_number: number;
  total_rounds: number;
  phase: string;
  current_speaker_id: string | null;
  players: Record<string, PlayerState>;
  public_log: string[];
}

export interface GameConfig {
  game_id: string;
  name: string;
  version: string;
  description: string;
  min_players: number;
  max_players: number;
  total_rounds: number;
  mode: string;
  language: string;
  turn_timeout_seconds: number;
  dm_model: string;
  dm_provider: string;
  resources: ResourceDef[];
  players: PlayerDef[];
}

export interface GameContext {
  game_config: GameConfig;
  round: RoundState;
  dm_last_verdict: DMVerdict | null;
  total_tokens_spent: number;
  total_cost_usd: number;
  elapsed_time_seconds: number;
  errors: string[];
}

// ─── WebSocket 事件 ──────────────────────────────

export type WSEventType =
  | 'GAME_INIT'
  | 'ROUND_START'
  | 'PLAYER_THINKING'
  | 'PLAYER_SPEECH'
  | 'PLAYER_COT'
  | 'DM_JUDGMENT'
  | 'STATE_UPDATE'
  | 'PLAYER_ERROR'
  | 'GAME_OVER'
  | 'ENGINE_ERROR';

export interface WSEvent {
  event_type: WSEventType;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface GameListItem {
  id: string;
  name: string;
  version: string;
  description: string;
  players: number;
  rounds: number;
  mode: string;
  locked?: boolean;
}
