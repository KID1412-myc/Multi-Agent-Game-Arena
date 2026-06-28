import { useState, useCallback, useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { GameControlBar } from './components/GameControlBar';
import { GameSelector } from './components/GameSelector';
import { ArenaLayout } from './components/ArenaLayout';
import { CyberBackground } from './components/CyberBackground';
import { GameOverModal } from './components/GameOverModal';
import { HumanInput } from './components/HumanInput';
import { useWebSocket } from './hooks/useWebSocket';
import { useArenaStore } from './store/arenaStore';

export default function App() {
  const [selectedGameId, setSelectedGameId] = useState('');
  const [needSetup, setNeedSetup] = useState(false);
  const [setupProviders, setSetupProviders] = useState<any[]>([]);
  const [setupForm, setSetupForm] = useState<Record<string, string>>({});
  const [gameOverDismissed, setGameOverDismissed] = useState(false);
  const { connected, ws } = useWebSocket();
  const gameStatus = useArenaStore((s) => s.gameStatus);
  const ctx = useArenaStore((s) => s.ctx);
  const setGameStatus = useArenaStore((s) => s.setGameStatus);
  const gameOverPayload = useArenaStore((s) => s.gameOverPayload);
  const winnerName = gameOverPayload?.winner_name || null;
  const ranking = gameOverPayload?.ranking || [];
  const extra = gameOverPayload?.extra || null;

  // 首次启动检测：没有 .env 则进入配置模式
  useEffect(() => {
    fetch('/api/setup/status').then(r => r.json()).then(d => {
      if (!d.has_env) { setNeedSetup(true); setSetupProviders(d.providers || []); }
    }).catch(() => {});
  }, []);

  const saveSetup = async () => {
    await fetch('/api/setup/save-env', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(setupForm),
    });
    window.location.reload();
  };

  const api = useCallback(async (path: string) => {
    try {
      const res = await fetch(path, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        alert(`请求失败: ${err.detail || JSON.stringify(err)}`);
      }
      return res.json();
    } catch (e: any) {
      alert(`请求失败: ${e.message}`);
    }
  }, []);

  const assignMode = useArenaStore((s) => s.assignMode);
  const assignments = useArenaStore((s) => s.assignments);

  const handleStart = useCallback(async () => {
    if (!selectedGameId) return;
    setGameOverDismissed(false);
    setGameStatus('loading');
    const body = assignMode === 'manual' && Object.keys(assignments).length > 0
      ? JSON.stringify({ assignments })
      : undefined;
    const res = await fetch(`/api/arena/run?game_id=${encodeURIComponent(selectedGameId)}`, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body,
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`请求失败: ${err.detail || JSON.stringify(err)}`);
      setGameStatus('idle');
    }
  }, [selectedGameId, setGameStatus, assignMode, assignments]);

  const reset = useArenaStore((s) => s.reset);

  const handleStop = useCallback(async () => {
    await api('/api/arena/stop');
    setGameStatus('idle');
    setGameOverDismissed(false);
    reset();
  }, [api, setGameStatus, reset]);

  const handlePause = useCallback(async () => {
    const data = await api('/api/arena/pause');
    if (data?.status === 'paused') setGameStatus('paused');
  }, [api, setGameStatus]);

  const handleResume = useCallback(async () => {
    const data = await api('/api/arena/resume');
    if (data?.status === 'resumed') setGameStatus('running');
  }, [api, setGameStatus]);

  const handleStep = useCallback(async () => {
    await api('/api/arena/step');
  }, [api]);

  const handleNextRound = useCallback(async () => {
    await api('/api/arena/next-round');
  }, [api]);

  const handleAuto = useCallback(async () => {
    await api('/api/arena/auto');
    setGameStatus('running');
  }, [api, setGameStatus]);

  if (needSetup) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f5f5f5' }}>
        <div style={{ background: '#fff', borderRadius: 12, padding: 32, maxWidth: 520, width: '100%', boxShadow: '0 4px 24px rgba(0,0,0,0.1)' }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>🔑 首次配置</h2>
          <p style={{ fontSize: 13, color: '#666', marginBottom: 20 }}>至少填写一个 API Key（推荐中转站，一个 Key 走天下）</p>
          {setupProviders.map(p => (
            <div key={p.id} style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
              <label style={{ width: 130, fontSize: 12, fontWeight: 600 }}>{p.name}</label>
              <input placeholder={p.env_key} value={setupForm[p.env_key] || ''}
                onChange={e => setSetupForm({ ...setupForm, [p.env_key]: e.target.value })}
                style={{ flex: 1, padding: '6px 10px', fontSize: 12, border: '1px solid #ddd', borderRadius: 6, fontFamily: 'monospace' }} />
            </div>
          ))}
          <div style={{ marginTop: 8 }}>
            <label style={{ fontSize: 12, fontWeight: 600 }}>中转站 API Base（如果使用 relay）</label>
            <input placeholder="RELAY_API_BASE" value={setupForm['RELAY_API_BASE'] || ''}
              onChange={e => setSetupForm({ ...setupForm, 'RELAY_API_BASE': e.target.value })}
              style={{ width: '100%', padding: '6px 10px', fontSize: 12, border: '1px solid #ddd', borderRadius: 6, fontFamily: 'monospace', marginTop: 4 }} />
          </div>
          <button onClick={saveSetup}
            style={{ marginTop: 20, width: '100%', padding: '10px', fontSize: 14, fontWeight: 600, background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
            保存并开始
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--bg-root)' }}>
      <CyberBackground />

      <GameControlBar
        connected={connected}
        onStart={handleStart}
        onStop={handleStop}
        onPause={handlePause}
        onResume={handleResume}
        onStep={handleStep}
        onNextRound={handleNextRound}
        onAuto={handleAuto}
        selectedGameId={selectedGameId}
        gameName={ctx?.game_config.name}
      />

      <div style={{ padding: '6px 20px', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-elevated)', display: 'flex', alignItems: 'center' }}>
        <GameSelector onSelect={setSelectedGameId} disabled={gameStatus === 'running' || gameStatus === 'paused'} />
        {gameStatus === 'idle' && <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 12 }}>Select a game and press Start</span>}
      </div>

      <AnimatePresence>
        {gameStatus === 'finished' && !gameOverDismissed && (
          <GameOverModal winnerName={winnerName} ranking={ranking} extra={extra}
            onClose={() => setGameOverDismissed(true)} />
        )}
      </AnimatePresence>

      <ArenaLayout />
      <HumanInput ws={ws} />
    </div>
  );
}
