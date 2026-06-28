import { useEffect, useRef } from 'react';
import { Gavel, TrendingUp } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';
import { ResourceChart } from './ResourceChart';
import { NightPanel } from './NightPanel';

export function DMPanel() {
  const ctx = useArenaStore((s) => s.ctx);
  const verdictHistory = useArenaStore((s) => s.verdictHistory);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [verdictHistory]);

  return (
    <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', padding: 16, border: '1px solid var(--border-default)',
                  boxShadow: 'var(--shadow-L1)', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexShrink: 0 }}>
        <Gavel size={16} style={{ color: 'var(--color-accent)' }} />
        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>DM 裁判</span>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>{verdictHistory.length} 条裁定</span>
      </div>

      <NightPanel />

      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minHeight: 0, fontSize: 11, lineHeight: 1.5 }}>
        {verdictHistory.length === 0 ? (
          <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 24, fontSize: 12 }}>等待游戏开始...</div>
        ) : (
          verdictHistory.map((v, i) => (
            <div key={i} style={{
              padding: '6px 0', borderBottom: '1px solid var(--border-light)',
              borderLeft: i === verdictHistory.length - 1 ? '2px solid var(--color-accent)' : '2px solid transparent',
              paddingLeft: i === verdictHistory.length - 1 ? 8 : 10,
            }}>
              <span style={{ fontWeight: 600, color: 'var(--color-accent)', fontSize: 11 }}>Round {v.round_number}</span>
              <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>{v.round_summary}</div>
            </div>
          ))
        )}
      </div>

      {ctx && Object.keys(ctx.round.players).length > 0 && (
        <div style={{ marginTop: 'auto', paddingTop: 8, borderTop: '1px solid var(--border-default)', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2, fontSize: 10, color: 'var(--text-tertiary)' }}>
            <TrendingUp size={11} /> 资源走势
          </div>
          <div style={{ height: 60 }}>
            <ResourceChart players={Object.values(ctx.round.players)} resources={ctx.game_config.resources} />
          </div>
        </div>
      )}
    </div>
  );
}
