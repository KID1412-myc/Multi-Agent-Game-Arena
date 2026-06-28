import { Brain } from 'lucide-react';
import { motion } from 'framer-motion';
import type { PlayerState, ResourceDef } from '../types/arena';
import { useArenaStore } from '../store/arenaStore';

interface Props { player: PlayerState; resources: ResourceDef[]; index: number; }

export function PlayerCard({ player, resources }: Props) {
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

  return (
    <motion.div
      onClick={() => { if (!hasHuman) setSelectedPlayer(isSelected ? null : player.id); }}
      animate={{ scale: isActive ? 1.02 : 1 }}
      style={{
        background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', padding: '8px 10px', cursor: 'pointer',
        border: isActive ? '2px solid var(--color-primary)' : '1px solid var(--border-default)',
        boxShadow: isActive ? '0 2px 12px rgba(59,130,246,0.12)' : 'var(--shadow-L1)',
        opacity: isDead ? 0.4 : 1, transition: 'all var(--duration-fast) var(--easing-default)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        minWidth: 0,
        position: 'relative',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, flexShrink: 0 }}>
        <div style={{
          width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
          background: isActive ? 'var(--color-primary)' : isThinking ? 'var(--status-thinking)' : isDead ? 'var(--status-dead)' : 'var(--status-alive)',
        }} />
        <span style={{
          fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{player.name}</span>
        {colorTag && (
          <span style={{ fontSize: 9, fontWeight: 600, flexShrink: 0,
            color: colorTag === '红' ? 'var(--color-danger)' : colorTag === '蓝' ? 'var(--color-primary)' : 'var(--color-success)',
            background: 'var(--bg-muted)', padding: '1px 4px', borderRadius: 'var(--radius-sm)' }}>
            {colorTag}
          </span>
        )}
        {fraudTag && (
          <span style={{ fontSize: 9, fontWeight: 600, color: 'var(--color-danger)', flexShrink: 0,
            background: '#FEF2F2', padding: '1px 4px', borderRadius: 'var(--radius-sm)' }}>
            {fraudTag}
          </span>
        )}
        {seeTag && (
          <span style={{ fontSize: 8, color: 'var(--text-tertiary)', flexShrink: 0 }}>{seeTag}</span>
        )}
        {isThinking && <span style={{ fontSize: 9, color: 'var(--status-thinking)', flexShrink: 0 }}>思考中</span>}
        <span style={{ fontSize: 9, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 80 }}>{player.model}</span>
      </div>

      {/* Resources */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4, flexShrink: 0, overflow: 'hidden', maxHeight: 40 }}>
        {resources.map((r) => (
          <span key={r.id} style={{ fontSize: 10, color: 'var(--text-secondary)', background: 'var(--bg-muted)', padding: '1px 5px', borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap' }}>
            {r.icon} {player.resources[r.id] ?? 0}{r.unit}
          </span>
        ))}
      </div>

      {/* CoT: hidden when human players present */}
      {cot && !isDead && !hasHuman && (
        <div style={{
          flex: 1, minHeight: 0, display: 'flex', flexDirection: 'row', gap: 6,
          fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.4,
        }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: 'var(--color-primary)', flexShrink: 0, marginBottom: 1 }}>局势评估</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>
              {cot.situation_assessment}
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: 'var(--color-secondary)', flexShrink: 0, marginBottom: 1 }}>内心策略</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>
              {cot.internal_strategy}
            </div>
          </div>
          {cot.secret_action && isSelected && (
            <div style={{ flexShrink: 0, maxWidth: 120 }}>
              <div style={{ fontWeight: 600, color: 'var(--color-danger)', marginBottom: 1 }}>秘密行动</div>
              <div style={{ maxHeight: 60, overflowY: 'auto', overflowX: 'hidden', wordBreak: 'break-word' }}>
                {cot.secret_action}
              </div>
            </div>
          )}
        </div>
      )}

      {/* CoT placeholder */}
      {!cot && !isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: 'var(--text-tertiary)' }}>等待行动...</span>
        </div>
      )}

      {!cot && isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: 'var(--text-tertiary)' }}>已淘汰</span>
        </div>
      )}

      {/* CoT corner icon */}
      {cot && !hasHuman && (
        <Brain size={10} style={{ position: 'absolute', bottom: 4, right: 6, color: isSelected ? 'var(--color-primary)' : 'var(--text-tertiary)' }} />
      )}
    </motion.div>
  );
}
