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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [filterGame, setFilterGame] = useState('');
  const [sortBy, setSortBy] = useState('time-desc');
  const [allReplays, setAllReplays] = useState<ReplayInfo[]>([]);
  const [gameNames, setGameNames] = useState<Record<string, string>>({});
  const timerRef = useRef<number | null>(null);
  const store = useArenaStore;

  const loadList = useCallback(async () => {
    const [replayRes, gameRes] = await Promise.all([
      fetch('/api/replays'),
      fetch('/api/games'),
    ]);
    const replayData = await replayRes.json();
    const gameData = await gameRes.json();
    const names: Record<string, string> = {};
    (gameData.games || []).forEach((g: any) => { names[g.id] = g.name; });
    setGameNames(names);
    setAllReplays(replayData.replays || []);
  }, []);

  const sortReplays = (list: ReplayInfo[]) => {
    const sorted = [...list];
    switch (sortBy) {
      case 'time-asc': sorted.sort((a, b) => a.timestamp.localeCompare(b.timestamp)); break;
      case 'name': sorted.sort((a, b) => (gameNames[a.game_id] || a.game_id).localeCompare(gameNames[b.game_id] || b.game_id)); break;
      case 'size': sorted.sort((a, b) => b.size - a.size); break;
      default: break; // time-desc: default from backend (already reverse sorted)
    }
    return sorted;
  };

  useEffect(() => {
    const filtered = filterGame ? allReplays.filter(r => r.game_id === filterGame) : allReplays;
    setReplays(sortReplays(filtered));
    setSelectedIds(new Set());
  }, [filterGame, allReplays, sortBy]);

  const loadReplay = async (id: string) => {
    setLoading(true);
    const res = await fetch('/api/replays/' + encodeURIComponent(id));
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

  const backToList = () => {
    setPlaying(false);
    setEvents([]);
    setEventIdx(0);
  };

  const batchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm('确定要删除选中的 ' + selectedIds.size + ' 个回放吗？此操作不可撤销。')) return;
    setBatchDeleting(true);
    const res = await fetch('/api/replays/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: Array.from(selectedIds) }),
    });
    const data = await res.json();
    setBatchDeleting(false);
    setSelectedIds(new Set());
    loadList();
    if (data.failed && data.failed.length > 0) {
      alert('成功删除 ' + (data.deleted || []).length + ' 个，失败 ' + data.failed.length + ' 个');
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedIds(next);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === replays.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(replays.map(r => r.id)));
    }
  };

  const progress = events.length ? (eventIdx / events.length * 100) : 0;

  if (!open) {
    return (
      <button onClick={() => { setOpen(true); loadList(); }}
        style={{ padding: '4px 10px', fontSize: 11, border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'transparent', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
        <Play size={12} /> 回放
      </button>
    );
  }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 'var(--z-40)', background: 'var(--bg-root)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-elevated)' }}>
        <button onClick={() => { events.length > 0 ? backToList() : (stop(), setOpen(false)); }} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}><X size={18} /></button>
        <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>回放</span>
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

      {events.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 12px', height: 20, flexShrink: 0 }}>
          <div style={{ flex: 1, height: 4, background: 'var(--border-default)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: progress + '%',
              background: 'var(--color-primary)',
              borderRadius: 2,
              transition: 'width var(--duration-normal) var(--easing-standard)',
              animation: eventIdx >= events.length && events.length > 0 ? 'progress-complete 0.5s ease-in-out' : 'none',
            }} />
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', minWidth: 32, textAlign: 'right' }}>
            {Math.round(progress) + '%'}
          </span>
        </div>
      )}

      {events.length === 0 ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
            <h3 style={{ fontSize: 14, color: 'var(--text-primary)' }}>选择回放文件</h3>
            <select value={filterGame} onChange={e => { setFilterGame(e.target.value); }}
              style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>
              <option value="">全部游戏</option>
              {[...new Set(allReplays.map(r => r.game_id))].map(gid => (
                <option key={gid} value={gid}>{gameNames[gid] || gid}</option>
              ))}
            </select>
            <select value={sortBy} onChange={e => setSortBy(e.target.value)}
              style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>
              <option value="time-desc">最新优先</option>
              <option value="time-asc">最早优先</option>
              <option value="name">按游戏名</option>
              <option value="size">按文件大小</option>
            </select>
            <div style={{ flex: 1 }} />
            {replays.length > 0 && (
              <>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', marginRight: 12 }}>
                  <input type="checkbox" checked={selectedIds.size === replays.length} onChange={toggleSelectAll}
                    style={{ accentColor: 'var(--color-primary)' }} />
                  全选
                </label>
                {selectedIds.size > 0 && (
                  <button onClick={batchDelete} disabled={batchDeleting}
                    style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '3px 10px', fontSize: 11,
                             border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-md)',
                             background: 'var(--color-danger-soft)', color: 'var(--color-danger)', cursor: 'pointer' }}>
                    <Trash2 size={12} />
                    {batchDeleting ? '删除中...' : '删除选中 (' + selectedIds.size + ')'}
                  </button>
                )}
              </>
            )}
          </div>
          {replays.map(r => {
            const deleteReplay = async (e: React.MouseEvent) => {
              e.stopPropagation();
              if (!confirm('确定要删除回放 ' + r.game_name + ' - ' + r.timestamp + ' 吗？')) return;
              await fetch('/api/replays/' + encodeURIComponent(r.id), { method: 'DELETE' });
              loadList();
            };
            return (
              <div key={r.id}
                style={{ padding: '8px 12px', borderRadius: 'var(--radius-md)', cursor: 'pointer', marginBottom: 4, background: selectedIds.has(r.id) ? 'var(--color-primary-soft)' : 'var(--bg-surface)', border: '1px solid var(--border-light)', display: 'flex', alignItems: 'center' }}>
                <input type="checkbox" checked={selectedIds.has(r.id)} onChange={() => toggleSelect(r.id)}
                  onClick={e => e.stopPropagation()}
                  style={{ marginRight: 8, accentColor: 'var(--color-primary)', flexShrink: 0 }} />
                <div onClick={() => loadReplay(r.id)} style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{r.game_name}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 8 }}>{r.timestamp}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 8 }}>{(r.size / 1024).toFixed(0)} KB</span>
                </div>
                <button onClick={deleteReplay}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: '4px' }}
                  title="删除回放">
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
          {replays.length === 0 && <p style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>暂无回放文件。每局游戏结束后自动保存。</p>}
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--bg-root)' }}>
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
