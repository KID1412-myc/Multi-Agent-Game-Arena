import { useState, useEffect, useRef } from 'react';
import { Play, Square, Activity, Wifi, WifiOff, Pause, SkipForward, BookOpen, Sun, Moon } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';
import { ModelSettings } from './ModelSettings';
import { RuleModal } from './RuleModal';
import { ReadmeModal } from './ReadmeModal';
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
  const [showReadme, setShowReadme] = useState(false);
  const [stopKey, setStopKey] = useState(0);
  const getSystemTheme = () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light' as const;

  const [theme, setTheme] = useState<'light' | 'dark'>(getSystemTheme);
  const ctx = useArenaStore((s) => s.ctx);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // 系统主题变了立刻跟，不用刷新
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setTheme(e.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const manualThemeRef = useRef(false);
  const prevRoundRef = useRef(ctx?.round?.round_number);

  const toggleTheme = () => {
    setTheme(t => t === 'light' ? 'dark' : 'light');
    manualThemeRef.current = true;  // 手动切换后本轮不再自动覆盖
  };

  const gameStatus = useArenaStore((s) => s.gameStatus);

  // 夜晚自动切暗色，白天切亮色（不锁定，玩家可手动改回）
  useEffect(() => {
    const round = ctx?.round?.round_number;
    if (round == null || gameStatus !== 'running') return;
    if (round !== prevRoundRef.current) {
      prevRoundRef.current = round;
      manualThemeRef.current = false;
      setTheme(round % 2 === 1 ? 'dark' : 'light');
    }
  }, [ctx?.round?.round_number, gameStatus]);
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
      <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontSize: 16, letterSpacing: '-0.01em' }}>MAGA <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 400, fontFamily: 'var(--font-sans)' }}>v2.4.0</span></span>

      {ctx && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--text-secondary)' }}>
          <span>{ctx.game_config.name}</span>
          <span style={{ color: 'var(--border-default)' }}>|</span>
          <span>Round {ctx.round.round_number}{ctx.game_config.total_rounds > 0 ? `/${ctx.game_config.total_rounds}` : ''}</span>
          {/* 昼夜指示：奇数轮=夜晚，偶数轮=白天 */}
          {ctx.round.round_number > 0 && (
            <span style={{
              fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-sm)',
              background: ctx.round.round_number % 2 === 1 ? 'var(--color-primary-soft)' : 'var(--color-warning-soft)',
              color: ctx.round.round_number % 2 === 1 ? 'var(--color-primary)' : 'var(--color-warning)',
            }}>
              {ctx.round.round_number % 2 === 1 ? '🌙 夜晚' : '☀️ 白天'}
            </span>
          )}
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
                     border: '1px solid var(--color-warning)', borderRadius: 'var(--radius-md)', background: 'var(--color-warning-soft)', color: '#B45309' }}>
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
                       border: '1px solid var(--color-secondary)', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)', color: 'var(--color-secondary)' }}>
              <SkipForward size={12} /> 单步
            </button>
          </>
        )}

        <button onClick={() => { setStopKey(k => k + 1); onStop(); }}
          key={stopKey}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-md)', background: 'var(--color-danger-soft)', color: 'var(--color-danger)',
                   animation: stopKey > 0 ? 'stop-pulse 0.4s ease-out' : 'none' }}
          disabled={!isActive}>
          <Square size={12} /> 停止
        </button>

        <button onClick={toggleTheme} title={theme === 'light' ? '切换暗色模式' : '切换浅色模式'}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 8px', fontSize: 12,
                   border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {theme === 'light' ? <Moon size={12} /> : <Sun size={12} />}
        </button>

        <button onClick={() => setShowReadme(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          <BookOpen size={12} /> 说明
        </button>

        <button onClick={() => setShowRules(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '5px 12px', fontSize: 12,
                   border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          <BookOpen size={12} /> 规则
        </button>

        <ModelSettings gameId={selectedGameId} disabled={isActive} />
        <ReplayPlayer />

        {showReadme && (
          <ReadmeModal onClose={() => setShowReadme(false)} />
        )}

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
