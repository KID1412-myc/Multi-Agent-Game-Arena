import { Play, Square, Activity, Wifi, WifiOff, Pause, SkipForward } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';
import { ModelSettings } from './ModelSettings';

interface Props {
  connected: boolean;
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onStep: () => void;
  onNextRound: () => void;
  onAuto: () => void;
  selectedGameId: string;
}

export function GameControlBar({ connected, onStart, onStop, onPause, onResume, onStep, onNextRound, onAuto, selectedGameId }: Props) {
  const ctx = useArenaStore((s) => s.ctx);
  const gameStatus = useArenaStore((s) => s.gameStatus);
  const isRunning = gameStatus === 'running';
  const isPaused = gameStatus === 'paused';
  const isRoundPaused = gameStatus === 'round_paused';
  const isActive = isRunning || isPaused || isRoundPaused;

  return (
    <div style={{
      background: '#fff', borderBottom: '1px solid #e5e5e5',
      padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 12,
      fontSize: 13, flexWrap: 'wrap',
    }}>
      <span style={{ fontWeight: 700, color: '#1a1a1a', letterSpacing: '-0.5px' }}>MAGA <span style={{ fontSize: 10, color: '#bbb', fontWeight: 400 }}>v1.0</span></span>

      {ctx && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: '#666' }}>
          <span>{ctx.game_config.name}</span>
          <span style={{ color: '#ddd' }}>|</span>
          <span>Round {ctx.round.round_number}/{ctx.game_config.total_rounds}</span>
          {isPaused && <span style={{ background: '#fef3c7', color: '#d97706', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600 }}>已暂停</span>}
          {isRoundPaused && <span style={{ background: '#dbeafe', color: '#2563eb', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600 }}>轮间等待</span>}
        </div>
      )}

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        {connected
          ? <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#4ade80', fontSize: 11 }}><Wifi size={12} /> 在线</span>
          : <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#f87171', fontSize: 11 }}><WifiOff size={12} /> 离线</span>
        }

        {isRunning && <Activity size={14} style={{ color: '#3b82f6' }} />}
        {isPaused && <Activity size={14} style={{ color: '#f59e0b' }} />}

        <button onClick={onStart} disabled={isActive}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid #3b82f6', borderRadius: 6, background: '#3b82f6', color: '#fff',
                   cursor: isActive ? 'not-allowed' : 'pointer', opacity: isActive ? 0.4 : 1 }}>
          <Play size={12} /> 启动
        </button>

        {isRunning && (
          <button onClick={onPause}
            style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                     border: '1px solid #f59e0b', borderRadius: 6, background: '#fff', color: '#d97706',
                     cursor: 'pointer' }}>
            <Pause size={12} /> 暂停
          </button>
        )}

        {isRoundPaused && (
          <>
            <button onClick={onNextRound}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid #2563eb', borderRadius: 6, background: '#2563eb', color: '#fff',
                       cursor: 'pointer' }}>
              <SkipForward size={12} /> 下一轮
            </button>
            <button onClick={onAuto}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid #10b981', borderRadius: 6, background: '#10b981', color: '#fff',
                       cursor: 'pointer' }}>
              <Play size={12} /> 自动
            </button>
          </>
        )}

        {isPaused && (
          <>
            <button onClick={onResume}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid #10b981', borderRadius: 6, background: '#10b981', color: '#fff',
                       cursor: 'pointer' }}>
              <Play size={12} /> 继续
            </button>
            <button onClick={onStep}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid #8b5cf6', borderRadius: 6, background: '#fff', color: '#7c3aed',
                       cursor: 'pointer' }}>
              <SkipForward size={12} /> 单步
            </button>
          </>
        )}

        <button onClick={onStop}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid #ef4444', borderRadius: 6, background: '#fff', color: '#ef4444',
                   cursor: isActive ? 'pointer' : 'not-allowed', opacity: isActive ? 1 : 0.4 }}
          disabled={!isActive}>
          <Square size={12} /> 停止
        </button>

        <ModelSettings gameId={selectedGameId} disabled={isActive} />
      </div>
    </div>
  );
}
