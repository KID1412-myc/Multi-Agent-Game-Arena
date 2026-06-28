import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { MessageCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';

const COLORS = ['#0D9488', '#78716C', '#B45309', '#D97706', '#DC2626', '#F43F5E', '#6366F1', '#14B8A6'];
const PAGE_SIZE = 25;

export function PublicBoard() {
  const speechLog = useArenaStore((s) => s.speechLog);
  const ctx = useArenaStore((s) => s.ctx);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showAll, setShowAll] = useState(false);

  const publicLog = ctx?.round?.public_log || [];

  useEffect(() => {
    if (scrollRef.current && !showAll) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [speechLog, showAll]);

  const getColor = (pid: string) => {
    if (!ctx) return COLORS[0];
    const idx = Object.keys(ctx.round.players).indexOf(pid);
    return COLORS[idx >= 0 ? idx % COLORS.length : 0];
  };

  const visible = showAll ? speechLog : speechLog.slice(-PAGE_SIZE);
  const hiddenCount = speechLog.length - PAGE_SIZE;

  const grouped: Record<number, typeof speechLog> = {};
  for (const s of visible) {
    if (!grouped[s.round]) grouped[s.round] = [];
    grouped[s.round].push(s);
  }

  return (
    <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', padding: 16,
                  border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-L1)',
                  height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexShrink: 0 }}>
        <MessageCircle size={15} style={{ color: 'var(--color-primary)' }} />
        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>公共看板</span>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{speechLog.length} 条发言</span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {!showAll && hiddenCount > 0 && (
            <button onClick={() => setShowAll(true)}
              style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: 'var(--text-link)',
                       border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', cursor: 'pointer', padding: '2px 6px' }}>
              <ChevronDown size={10} /> 显示全部 ({hiddenCount} 条更多)
            </button>
          )}
          {showAll && (
            <button onClick={() => { setShowAll(false); }}
              style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: 'var(--text-secondary)',
                       border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', cursor: 'pointer', padding: '2px 6px' }}>
              <ChevronUp size={10} /> 仅最新
            </button>
          )}
        </div>
      </div>

      <div style={{
        flexShrink: 0, padding: '4px 8px', marginBottom: 4,
        background: publicLog.length > 0 ? 'var(--color-accent-soft)' : 'var(--bg-muted)',
        borderLeft: `3px solid ${publicLog.length > 0 ? 'var(--color-accent)' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600,
        color: publicLog.length > 0 ? 'var(--text-primary)' : 'var(--text-tertiary)',
      }}>
        {publicLog.length > 0 ? publicLog[publicLog.length - 1] : '等待开局...'}
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', fontSize: 12, lineHeight: 1.5, minHeight: 0 }}>
        {publicLog.length > 1 && (
          <div style={{ marginBottom: 8 }}>
            {publicLog.slice(0, -1).reverse().map((entry, i) => (
              <div key={`pl-${i}`} style={{
                padding: '2px 8px', marginBottom: 1, fontSize: 10, color: '#B45309', opacity: 0.7,
              }}>
                {entry}
              </div>
            ))}
          </div>
        )}
        {speechLog.length === 0 && publicLog.length === 0 ? (
          <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 32 }}>等待玩家发言...</div>
        ) : (
          Object.entries(grouped).map(([round, entries]) => (
            <div key={round}>
              <div style={{
                fontSize: 10, color: 'var(--text-tertiary)', padding: '6px 0 2px',
                borderBottom: '1px solid var(--border-light)', marginBottom: 2, fontWeight: 600,
                position: 'sticky', top: 0, background: 'var(--bg-surface)', zIndex: 1,
              }}>
                Round {round}
              </div>
              {entries.map((s, i) => {
                const player = ctx?.round?.players[s.playerId];
                const isLastWord = !player?.is_alive;
                const isHuman = player?.is_human;
                return (
                <motion.div
                  key={`${s.round}-${i}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: [0, 0, 0.2, 1] }}
                  style={{
                    padding: '4px 0 4px 10px',
                    borderLeft: isHuman ? '3px solid var(--status-human)' : '2px solid var(--border-default)',
                    marginLeft: isHuman ? 1 : 2,
                    transition: 'background-color var(--duration-slow) var(--easing-enter)',
                    background: isLastWord ? 'var(--color-danger-soft)' : 'transparent',
                    animation: isLastWord ? 'ink-bleed 0.5s ease-in forwards' : 'none',
                  }}>
                  <span style={{ fontWeight: 600, color: getColor(s.playerId), fontSize: 11 }}>
                    {s.playerName}{isHuman ? ' (人类)' : ''}{isLastWord ? ' (遗言)' : ''}
                  </span>
                  <div style={{ color: 'var(--text-secondary)', marginTop: 2, fontSize: 11 }}>
                    {s.content}
                  </div>
                </motion.div>
              )})}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
