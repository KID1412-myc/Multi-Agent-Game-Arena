import { useEffect, useRef, useState } from 'react';
import { Moon, ChevronDown, ChevronRight } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';

const ACTION_ICONS: Record<string, string> = {
  wolf_chat: '💬',
  wolf_vote: '🗡️',
  seer_check: '🔮',
  witch_action: '🧪',
  wolf_kill: '💀',
  hunter_shoot: '🔫',
};

export function NightPanel() {
  const nightLog = useArenaStore((s) => s.nightLog);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (scrollRef.current && !collapsed)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [nightLog, collapsed]);

  if (nightLog.length === 0) return null;

  return (
    <div style={{ marginBottom: 8, flexShrink: 0 }}>
      <div
        onClick={() => setCollapsed(!collapsed)}
        style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, cursor: 'pointer', userSelect: 'none' }}
      >
        {collapsed ? <ChevronRight size={11} style={{ color: 'var(--color-secondary)' }} /> : <ChevronDown size={11} style={{ color: 'var(--color-secondary)' }} />}
        <Moon size={13} style={{ color: 'var(--color-secondary)' }} />
        <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--color-secondary)' }}>夜晚行动</span>
        <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>{nightLog.length} 条</span>
      </div>
      {!collapsed && (
        <div ref={scrollRef} style={{
          maxHeight: 200, overflowY: 'auto', overflowX: 'hidden',
          fontSize: 10, lineHeight: 1.5, color: 'var(--text-secondary)',
          background: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', padding: '4px 6px',
          border: '1px solid var(--border-default)',
        }}>
          {nightLog.map((entry, i) => (
            <div key={i} style={{ padding: '1px 0', wordBreak: 'break-word' }}>
              <span style={{ marginRight: 3 }}>{ACTION_ICONS[entry.action] || '•'}</span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{entry.player_name}({entry.player_id})</span>
              <span>: {entry.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
