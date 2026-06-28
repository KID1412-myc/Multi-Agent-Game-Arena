import { useState, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import type { GameListItem } from '../types/arena';

interface Props { onSelect: (gameId: string) => void; disabled: boolean; }

export function GameSelector({ onSelect, disabled }: Props) {
  const [games, setGames] = useState<GameListItem[]>([]);
  const [selected, setSelected] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/games')
      .then((r) => r.json())
      .then((data) => {
        const list = data.games || [];
        setGames(list);
        const first = list.find((g: any) => !g.locked) || list[0];
        if (first) {
          setSelected(first.id);
          onSelect(first.id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  const selectedGame = games.find((g) => g.id === selected);

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => !disabled && setOpen(!open)} disabled={disabled}
        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', fontSize: 12,
                 border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
                 background: 'transparent', color: 'var(--text-primary)',
                 cursor: disabled ? 'not-allowed' : 'pointer', minWidth: 180,
                 opacity: disabled ? 0.5 : 1 }}>
        <span style={{ flex: 1, textAlign: 'left' }}>{loading ? '加载中...' : selectedGame?.name || '选择游戏'}</span>
        <ChevronDown size={12} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform var(--duration-fast) var(--easing-standard)' }} />
      </button>

      <div style={{
        position: 'absolute', top: '100%', left: 0, right: 0,
        background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)', marginTop: 4, zIndex: 'var(--z-20)',
        boxShadow: 'var(--shadow-L3)', overflow: 'hidden',
        opacity: open ? 1 : 0,
        transform: open ? 'scaleY(1) translateY(0)' : 'scaleY(0.9) translateY(-4px)',
        transformOrigin: 'top',
        transition: `opacity var(--duration-fast) var(--easing-enter),
                     transform var(--duration-fast) var(--easing-enter)`,
        pointerEvents: open ? 'auto' : 'none',
      }}>
          {games.map((g) => (
            <button key={g.id}
              onClick={() => { if (!g.locked) { setSelected(g.id); onSelect(g.id); setOpen(false); } }}
              disabled={g.locked}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px',
                       fontSize: 12, background: selected === g.id ? 'var(--color-primary-soft)' : 'var(--bg-surface)',
                       border: 'none', borderLeft: selected === g.id ? '3px solid var(--color-primary)' : '3px solid transparent',
                       cursor: g.locked ? 'not-allowed' : 'pointer', color: 'var(--text-primary)',
                       opacity: g.locked ? 0.4 : 1 }}>
              <div style={{ fontWeight: 600 }}>
                {g.name}
                {g.locked && <span style={{ fontSize: 9, color: 'var(--color-danger)', marginLeft: 6, background: 'var(--color-danger-soft)', padding: '1px 4px', borderRadius: 'var(--radius-sm)' }}>开发中</span>}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{g.players} players · {g.rounds} rounds</div>
            </button>
          ))}
        </div>
    </div>
  );
}
