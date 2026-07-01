import { Brain } from 'lucide-react';
import { motion } from 'framer-motion';
import type { PlayerState, ResourceDef } from '../types/arena';
import { useArenaStore } from '../store/arenaStore';

interface Props { player: PlayerState; resources: ResourceDef[]; index: number; }

export function PlayerCard({ player, resources, index }: Props) {
  const isSelected = useArenaStore((s) => s.selectedPlayerId === player.id);
  const showCoT = useArenaStore((s) => s.showCoT);
  const setSelectedPlayer = useArenaStore((s) => s.setSelectedPlayer);
  const ctx = useArenaStore((s) => s.ctx);
  const hasHuman = Object.values(ctx?.round?.players || {}).some(p => p.is_human);
  const isActive = player.is_current_speaker;
  const isThinking = player.is_thinking;
  const isDead = !player.is_alive;
  const cot = player.last_cot;
  const colorTag = player.color_tag || '';
  const fraudTag = player.fraud_tag || '';
  const seeTag = player.see_tag || '';

  const staggerDelay = index * 0.05;

  return (
    <motion.div
      onClick={() => { if (!hasHuman) setSelectedPlayer(isSelected ? null : player.id); }}
      initial={{ opacity: 0, y: 12 }}
      animate={{
        opacity: isDead ? 0.4 : 1,
        y: 0,
        scale: isActive ? 1.02 : isDead ? 0.97 : 1,
        filter: isDead ? 'grayscale(0.5)' : 'grayscale(0)',
        backgroundColor: isActive ? 'var(--bg-active)' : 'var(--bg-surface)',
      }}
      transition={{
        duration: isActive ? 0.25 : isDead ? 0.35 : 0.18,
        ease: isActive ? [0.34, 1.3, 0.64, 1] : isDead ? [0.4, 0, 1, 1] : [0, 0, 0.2, 1],
        delay: staggerDelay,
      }}
      whileHover={{ y: -2, boxShadow: 'var(--shadow-L2)', transition: { duration: 0.18 } }}
      whileTap={{ scale: 0.98, transition: { duration: 0.1 } }}
      style={{
        height: '100%',
        borderRadius: 'var(--radius-lg)', padding: '6px 10px',
        cursor: hasHuman ? 'default' : 'pointer',
        borderLeft: isActive ? '4px solid var(--color-primary)'
          : player.is_human ? '4px solid var(--status-human)'
          : '3px solid var(--color-primary)',
        borderTop: '1px solid var(--border-default)',
        borderRight: '1px solid var(--border-default)',
        borderBottom: isActive ? '1px solid var(--color-primary)' : '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-L1)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0, position: 'relative',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 3, flexShrink: 0 }}>
        <div style={{
          width: 8, height: 8,
          borderRadius: player.is_human ? '1px' : '50%',
          transform: player.is_human ? 'rotate(45deg)' : 'none',
          flexShrink: 0,
          background: isActive ? 'var(--color-primary)' : isThinking ? 'var(--status-thinking)' : isDead ? 'var(--status-dead)' : player.is_human ? 'var(--status-human)' : 'var(--status-alive)',
          animation: isActive ? 'glow-ring 1.5s ease-in-out infinite'
            : isThinking ? 'pulse-breathing 2s ease-in-out infinite'
            : 'none',
        }} />
        <span style={{
          fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', flex: 1,
          fontFamily: 'var(--font-display)', letterSpacing: '-0.01em',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{player.name}</span>
        {(!hasHuman || player.is_human) && colorTag && (
          <span style={{ fontSize: 9, fontWeight: 600, flexShrink: 0,
            color: colorTag === '红' ? 'var(--faction-wolf)' : colorTag === '蓝' ? 'var(--faction-villager)' : 'var(--color-primary)',
            background: 'var(--bg-muted)', padding: '1px 5px', borderRadius: 'var(--radius-sm)' }}>{colorTag}</span>
        )}
        {(!hasHuman || player.is_human) && fraudTag && (
          <span style={{ fontSize: 9, fontWeight: 600, color: 'var(--faction-fraud)', flexShrink: 0,
            background: 'var(--color-danger-soft)', padding: '1px 5px', borderRadius: 'var(--radius-sm)' }}>{fraudTag}</span>
        )}
        {!hasHuman && seeTag && (
          <span style={{ fontSize: 8, color: 'var(--text-tertiary)', flexShrink: 0 }}>{seeTag}</span>
        )}
        {isThinking && <span style={{ fontSize: 9, color: 'var(--status-thinking)', flexShrink: 0 }}>思考中</span>}
        <span style={{ fontSize: 9, color: 'var(--text-tertiary)', fontFamily: player.is_human ? 'var(--font-sans)' : 'var(--font-mono)', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 80 }}>{player.is_human ? '👤' : player.model}</span>
      </div>

      {/* Resources */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 3, flexShrink: 0, overflow: 'hidden', maxHeight: 32 }}>
        {resources.map((r) => (
          <span key={r.id} style={{ fontSize: 10, color: 'var(--text-secondary)', background: 'var(--bg-muted)', padding: '2px 6px', borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap' }}>
            {r.icon} {player.resources[r.id] ?? 0}{r.unit}
          </span>
        ))}
      </div>

      {/* CoT */}
      {cot && !isDead && !hasHuman && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'row', gap: 8, fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: 'var(--color-primary)', flexShrink: 0, marginBottom: 2, fontSize: 10, fontFamily: 'var(--font-display)' }}>局势评估</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>{cot.situation_assessment}</div>
          </div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: 'var(--color-accent)', flexShrink: 0, marginBottom: 2, fontSize: 10, fontFamily: 'var(--font-display)' }}>内心策略</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>{cot.internal_strategy}</div>
          </div>
          {cot.secret_action && isSelected && (
            <div style={{ flexShrink: 0, maxWidth: 120 }}>
              <div style={{ fontWeight: 600, color: 'var(--color-danger)', marginBottom: 2, fontSize: 10, fontFamily: 'var(--font-display)' }}>秘密行动</div>
              <div style={{ maxHeight: 60, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>{cot.secret_action}</div>
            </div>
          )}
        </div>
      )}

      {!cot && !isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: 'var(--text-tertiary)', fontStyle: 'italic' }}>等待行动…</span>
        </div>
      )}
      {!cot && isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: 'var(--text-tertiary)' }}>已淘汰</span>
        </div>
      )}
      {cot && !hasHuman && (
        <Brain size={10} style={{ position: 'absolute', bottom: 6, right: 8, color: isSelected ? 'var(--color-primary)' : 'var(--text-tertiary)' }} />
      )}
    </motion.div>
  );
}
