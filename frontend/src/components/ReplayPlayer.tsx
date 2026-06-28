import { useState, useEffect, useRef, useCallback } from 'react';
import { useArenaStore } from '../store/arenaStore';
import { ArenaLayout } from './ArenaLayout';
import { Play, Pause, SkipBack, SkipForward, X, FastForward, Trash2 } from 'lucide-react';

interface ReplayInfo {
  id: string; game_id: string; game_name: string; timestamp: string; size: number;
}

export function ReplayPlayer() {
  const [open, setOpen] = useState(false);
  const [replays, setReplays] = useState<ReplayInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [eventIdx, setEventIdx] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [events, setEvents] = useState<any[]>([]);
  const timerRef = useRef<number | null>(null);
  const store = useArenaStore;

  const loadList = useCallback(async () => {
    const res = await fetch('/api/replays');
    const data = await res.json();
    setReplays(data.replays || []);
  }, []);

  const loadReplay = async (id: string) => {
    setLoading(true);
    const res = await fetch(`/api/replays/${encodeURIComponent(id)}`);
    const data = await res.json();
    setEvents(data.events || []);
    setEventIdx(0);
    setLoading(false);
    setPlaying(true);
    store.getState().reset();
    store.getState().setGameStatus('running');
  };

  const applyEvent = useCallback((ev: any) => {
    const s = store.getState();
    const type = ev.type;
    const payload = ev.payload || {};
    switch (type) {
      case 'GAME_INIT':
        s.setCtx(payload.ctx);
        break;
      case 'ROUND_START':
        s.setGameStatus('running');
        break;
      case 'PLAYER_THINKING':
        if (payload.player_id) s.updatePlayer(payload.player_id, { is_thinking: true } as any);
        break;
      case 'PLAYER_SPEECH':
        s.addSpeech(payload.player_id, payload.player_name, payload.speech, payload.round || 0);
        if (payload.player_id) s.updatePlayer(payload.player_id, {
          is_thinking: false, is_current_speaker: false,
          last_public_speech: payload.speech,
        } as any);
        break;
      case 'PLAYER_COT':
        if (payload.player_id) s.updatePlayer(payload.player_id, {
          last_cot: payload.cot || payload,
        } as any);
        break;
      case 'DM_JUDGMENT':
        s.addVerdict(payload.verdict);
        break;
      case 'STATE_UPDATE':
        if (payload.ctx) s.setCtx(payload.ctx);
        break;
      case 'NIGHT_ACTION':
        s.addNightAction(payload);
        break;
      case 'GAME_OVER':
        s.setGameOverPayload({ winner_id: payload.winner_id, winner_name: payload.winner_name, ranking: payload.ranking, extra: payload.extra });
        s.setGameStatus('finished');
        break;
      default:
        break;
    }
  }, [store]);

  // 从 0 号事件开始重放到目标位置（用于上一步/跳转）
  const replayTo = useCallback((targetIdx: number) => {
    store.getState().reset();
    store.getState().setGameStatus('running');
    for (let i = 0; i <= targetIdx && i < events.length; i++) {
      applyEvent(events[i]);
    }
  }, [events, applyEvent, store]);

  useEffect(() => {
    if (!playing || eventIdx >= events.length) {
      if (eventIdx >= events.length && events.length > 0) {
        setPlaying(false);
      }
      return;
    }
    const delay = events[eventIdx].t || 0;
    const prev = eventIdx > 0 ? events[eventIdx - 1].t || 0 : 0;
    const wait = Math.max(0, (delay - prev) / speed) * 1000;

    timerRef.current = window.setTimeout(() => {
      applyEvent(events[eventIdx]);
      setEventIdx(i => i + 1);
    }, Math.min(wait, 5000));
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [playing, eventIdx, events, speed, applyEvent]);

  const stop = () => {
    setPlaying(false);
    setEvents([]);
    setEventIdx(0);
    store.getState().reset();
  };

  const progress = events.length ? (eventIdx / events.length * 100) : 0;

  if (!open) {
    return (
      <button onClick={() => { setOpen(true); loadList(); }}
        style={{ padding: '4px 10px', fontSize: 11, border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
        <Play size={12} /> 回放
      </button>
    );
  }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 'var(--z-40)', background: 'var(--bg-root)', display: 'flex', flexDirection: 'column' }}>
      {/* 顶栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-elevated)' }}>
        <button onClick={() => { stop(); setOpen(false); }} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}><X size={18} /></button>
        <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>📼 游戏回放</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          <button onClick={() => {
              const target = Math.max(0, eventIdx - 2);
              setEventIdx(target);
              setPlaying(false);
              replayTo(target - 1 >= 0 ? target - 1 : 0);
            }}
            style={btnStyle}><SkipBack size={14} /></button>
          <button onClick={() => setPlaying(!playing)} style={btnStyle}>
            {playing ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button onClick={() => setSpeed(s => s === 4 ? 1 : s * 2)}
            style={{ ...btnStyle, fontWeight: 600, fontSize: 10 }}>
            <FastForward size={14} /> {speed}x
          </button>
        </div>
      </div>
      {/* 进度条 */}
      <div style={{ height: 4, background: 'var(--bg-muted)', flexShrink: 0 }}>
        <div style={{ height: '100%', width: `${progress}%`, background: 'var(--color-accent)', transition: 'width 0.2s' }} />
      </div>

      {events.length === 0 ? (
        /* 回放列表 */
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          <h3 style={{ fontSize: 14, marginBottom: 8, color: 'var(--text-primary)' }}>选择回放文件</h3>
          {replays.map(r => (
            <div key={r.id}
              style={{ padding: '8px 12px', borderRadius: 'var(--radius-md)', cursor: 'pointer', marginBottom: 4, background: 'var(--bg-surface)', border: '1px solid var(--border-light)', display: 'flex', alignItems: 'center' }}>
              <div onClick={() => loadReplay(r.id)} style={{ flex: 1 }}>
                <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{r.game_name}</span>
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 8 }}>{r.timestamp}</span>
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 8 }}>{(r.size / 1024).toFixed(0)} KB</span>
              </div>
              <button onClick={async (e) => {
                e.stopPropagation();
                if (!confirm(`确定要删除回放「${r.game_name} - ${r.timestamp}」吗？`)) return;
                await fetch(`/api/replays/${encodeURIComponent(r.id)}`, { method: 'DELETE' });
                loadList();
              }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: '4px' }}
                title="删除回放">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {replays.length === 0 && <p style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>暂无回放文件。每局游戏结束后自动保存。</p>}
        </div>
      ) : (
        /* 回放播放中 */
        <div style={{ flex: 1, overflow: 'auto', background: 'var(--bg-root)' }}>
          <ArenaLayout />
        </div>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  padding: '4px 8px', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
  background: 'var(--bg-surface)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 2,
  color: 'var(--text-secondary)',
};
