import { useState, useCallback } from 'react';
import { GameControlBar } from './components/GameControlBar';
import { GameSelector } from './components/GameSelector';
import { ArenaLayout } from './components/ArenaLayout';
import { CyberBackground } from './components/CyberBackground';
import { useWebSocket } from './hooks/useWebSocket';
import { useArenaStore } from './store/arenaStore';

export default function App() {
  const [selectedGameId, setSelectedGameId] = useState('');
  const { connected } = useWebSocket();
  const gameStatus = useArenaStore((s) => s.gameStatus);
  const setGameStatus = useArenaStore((s) => s.setGameStatus);
  const gameOverPayload = useArenaStore((s) => s.gameOverPayload);
  const winnerName = gameOverPayload?.winner_name || null;

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

  const handleStart = useCallback(async () => {
    if (!selectedGameId) return;
    setGameStatus('loading');
    await api(`/api/arena/run?game_id=${encodeURIComponent(selectedGameId)}`);
  }, [selectedGameId, api, setGameStatus]);

  const reset = useArenaStore((s) => s.reset);

  const handleStop = useCallback(async () => {
    await api('/api/arena/stop');
    setGameStatus('idle');
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

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#f5f5f5' }}>
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
      />

      <div style={{ padding: '6px 20px', borderBottom: '1px solid #eee', background: '#fafafa', display: 'flex', alignItems: 'center' }}>
        <GameSelector onSelect={setSelectedGameId} disabled={gameStatus === 'running' || gameStatus === 'paused'} />
        {gameStatus === 'idle' && <span style={{ fontSize: 11, color: '#bbb', marginLeft: 12 }}>Select a game and press Start</span>}
      </div>

      {gameStatus === 'finished' && winnerName && (
        <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 9999,
                      background: '#fff', borderRadius: 12, padding: 32, textAlign: 'center',
                      border: '2px solid #f59e0b', boxShadow: '0 4px 24px rgba(0,0,0,0.12)' }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🏆</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#333', marginBottom: 4 }}>游戏结束</h2>
          <p style={{ fontSize: 15, color: '#666' }}>胜者：<span style={{ fontWeight: 700, color: '#f59e0b' }}>{winnerName}</span></p>
          <button onClick={() => useArenaStore.getState().setGameStatus('idle')}
            style={{ marginTop: 12, padding: '4px 16px', fontSize: 12, border: '1px solid #ddd', borderRadius: 6, background: '#fff', cursor: 'pointer', color: '#666' }}>
            关闭
          </button>
        </div>
      )}

      <ArenaLayout />
    </div>
  );
}
