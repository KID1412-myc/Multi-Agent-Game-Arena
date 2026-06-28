import { useState } from 'react';
import { Play, Square, Activity, Wifi, WifiOff, Pause, SkipForward, BookOpen } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';
import { ModelSettings } from './ModelSettings';
import { RuleModal } from './RuleModal';
import { ReplayPlayer } from './ReplayPlayer';

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
  gameName?: string;
}

export function GameControlBar({ connected, onStart, onStop, onPause, onResume, onStep, onNextRound, onAuto, selectedGameId, gameName }: Props) {
  const [showRules, setShowRules] = useState(false);
  const [stopKey, setStopKey] = useState(0);
  const ctx = useArenaStore((s) => s.ctx);
  const gameStatus = useArenaStore((s) => s.gameStatus);
  const isLoading = gameStatus === 'loading';
  const isRunning = gameStatus === 'running';
  const isPaused = gameStatus === 'paused';
  const isRoundPaused = gameStatus === 'round_paused';
  const isActive = isLoading || isRunning || isPaused || isRoundPaused || gameStatus === 'finished';

  return (
    <div style={{
      background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)',
      padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 12,
      fontSize: 13, flexWrap: 'wrap',
    }}>
      <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontSize: 16, letterSpacing: '-0.01em' }}>MAGA <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 400, fontFamily: 'var(--font-sans)' }}>v2.2.1</span></span>

      {ctx && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--text-secondary)' }}>
          <span>{ctx.game_config.name}</span>
          <span style={{ color: 'var(--border-default)' }}>|</span>
          <span>Round {ctx.round.round_number}/{ctx.game_config.total_rounds}</span>
          {isPaused && <span style={{ background: 'var(--color-warning-soft)', color: 'var(--color-warning)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', fontSize: 11, fontWeight: 600 }}>已暂停</span>}
          {isRoundPaused && <span style={{ background: 'var(--color-primary-soft)', color: 'var(--color-primary)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', fontSize: 11, fontWeight: 600 }}>轮间等待</span>}
        </div>
      )}

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        {connected
          ? <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--status-alive)', fontSize: 11 }}><Wifi size={12} /> 在线</span>
          : <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--status-danger)', fontSize: 11 }}><WifiOff size={12} /> 离线</span>
        }

        {isRunning && <Activity size={14} style={{ color: 'var(--color-primary)' }} />}
        {isPaused && <Activity size={14} style={{ color: 'var(--color-warning)' }} />}

        <button onClick={onStart} disabled={isActive}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--color-primary)', borderRadius: 'var(--radius-md)', background: 'var(--color-primary)', color: 'var(--text-on-brand)' }}>
          {isLoading ? <Activity size={12} style={{ animation: 'pulse-breathing 1s ease-in-out infinite' }} /> : <Play size={12} />}
          {isLoading ? '启动中...' : '启动'}
        </button>

        {isRunning && (
          <button onClick={onPause}
            style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                     border: '1px solid var(--color-warning)', borderRadius: 'var(--radius-md)', background: 'transparent', color: '#D97706' }}>
            <Pause size={12} /> 暂停
          </button>
        )}

        {isRoundPaused && (
          <>
            <button onClick={onNextRound}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid var(--color-primary)', borderRadius: 'var(--radius-md)', background: 'var(--color-primary)', color: 'var(--text-on-brand)' }}>
              <SkipForward size={12} /> 下一轮
            </button>
            <button onClick={onAuto}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid var(--color-success)', borderRadius: 'var(--radius-md)', background: 'var(--color-success)', color: 'var(--text-on-brand)' }}>
              <Play size={12} /> 自动
            </button>
          </>
        )}

        {isPaused && (
          <>
            <button onClick={onResume}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid var(--color-success)', borderRadius: 'var(--radius-md)', background: 'var(--color-success)', color: 'var(--text-on-brand)' }}>
              <Play size={12} /> 继续
            </button>
            <button onClick={onStep}
              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                       border: '1px solid var(--color-secondary)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--color-secondary)' }}>
              <SkipForward size={12} /> 单步
            </button>
          </>
        )}

        <button onClick={() => { setStopKey(k => k + 1); onStop(); }}
          key={stopKey}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--color-danger)',
                   animation: stopKey > 0 ? 'stop-pulse 0.4s ease-out' : 'none' }}
          disabled={!isActive}>
          <Square size={12} /> 停止
        </button>

        <button onClick={() => setShowRules(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-secondary)' }}>
          <BookOpen size={12} /> 规则
        </button>

        <ModelSettings gameId={selectedGameId} disabled={isActive} />
        <ReplayPlayer />

        {showRules && (
          <RuleModal
            gameId={selectedGameId}
            gameName={gameName || selectedGameId}
            onClose={() => setShowRules(false)}
          />
        )}
      </div>
    </div>
  );
}
