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

  const selectedGame = games.find((g) => g.id === selected);

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => !disabled && setOpen(!open)} disabled={disabled}
        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', fontSize: 12,
                 border: '1px solid #ddd', borderRadius: 6, background: '#fff', color: '#333',
                 cursor: disabled ? 'not-allowed' : 'pointer', minWidth: 180,
                 opacity: disabled ? 0.5 : 1 }}>
        <span style={{ flex: 1, textAlign: 'left' }}>{loading ? '加载中...' : selectedGame?.name || '选择游戏'}</span>
        <ChevronDown size={12} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s' }} />
      </button>

      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff',
                      border: '1px solid #e5e5e5', borderRadius: 6, marginTop: 4, zIndex: 100,
                      boxShadow: '0 4px 12px rgba(0,0,0,0.1)', overflow: 'hidden' }}>
          {games.map((g) => (
            <button key={g.id}
              onClick={() => { if (!g.locked) { setSelected(g.id); onSelect(g.id); setOpen(false); } }}
              disabled={g.locked}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px',
                       fontSize: 12, background: selected === g.id ? '#eff6ff' : '#fff',
                       border: 'none', borderLeft: selected === g.id ? '2px solid #3b82f6' : '2px solid transparent',
                       cursor: g.locked ? 'not-allowed' : 'pointer', color: '#333',
                       opacity: g.locked ? 0.4 : 1 }}>
              <div style={{ fontWeight: 600 }}>
                {g.name}
                {g.locked && <span style={{ fontSize: 9, color: '#ef4444', marginLeft: 6, background: '#fef2f2', padding: '1px 4px', borderRadius: 3 }}>开发中</span>}
              </div>
              <div style={{ fontSize: 10, color: '#999' }}>{g.players} players · {g.rounds} rounds</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
