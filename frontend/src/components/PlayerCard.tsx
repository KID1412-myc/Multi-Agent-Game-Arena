import { Brain } from 'lucide-react';
import { motion } from 'framer-motion';
import type { PlayerState, ResourceDef } from '../types/arena';
import { useArenaStore } from '../store/arenaStore';

interface Props { player: PlayerState; resources: ResourceDef[]; index: number; }

export function PlayerCard({ player, resources }: Props) {
  const isSelected = useArenaStore((s) => s.selectedPlayerId === player.id);
  const showCoT = useArenaStore((s) => s.showCoT);
  const setSelectedPlayer = useArenaStore((s) => s.setSelectedPlayer);

  const isActive = player.is_current_speaker;
  const isThinking = player.is_thinking;
  const isDead = !player.is_alive;
  const cot = player.last_cot;

  return (
    <motion.div
      onClick={() => setSelectedPlayer(isSelected ? null : player.id)}
      animate={{ scale: isActive ? 1.02 : 1 }}
      style={{
        background: '#fff', borderRadius: 10, padding: '8px 10px', cursor: 'pointer',
        border: isActive ? '2px solid #3b82f6' : '1px solid #e5e5e5',
        boxShadow: isActive ? '0 2px 12px rgba(59,130,246,0.15)' : '0 1px 3px rgba(0,0,0,0.05)',
        opacity: isDead ? 0.4 : 1, transition: 'all 0.2s',
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
          background: isActive ? '#3b82f6' : isThinking ? '#f59e0b' : isDead ? '#ccc' : '#4ade80',
        }} />
        <span style={{
          fontSize: 11, fontWeight: 600, color: '#1a1a1a', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{player.name}</span>
        {isThinking && <span style={{ fontSize: 9, color: '#f59e0b', flexShrink: 0 }}>思考中</span>}
        <span style={{ fontSize: 9, color: '#999', fontFamily: 'monospace', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 80 }}>{player.model}</span>
      </div>

      {/* Resources */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4, flexShrink: 0, overflow: 'hidden', maxHeight: 40 }}>
        {resources.map((r) => (
          <span key={r.id} style={{ fontSize: 10, color: '#666', background: '#f5f5f5', padding: '1px 5px', borderRadius: 4, whiteSpace: 'nowrap' }}>
            {r.icon} {player.resources[r.id] ?? 0}{r.unit}
          </span>
        ))}
      </div>

      {/* 内心分析：局势评估 + 内心策略 均分空间，各自独立滚动，不依赖点击 */}
      {cot && !isDead && (
        <div style={{
          flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 4,
          fontSize: 10, color: '#555', lineHeight: 1.4,
        }}>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: '#3b82f6', flexShrink: 0, marginBottom: 1 }}>局势评估</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
              {cot.situation_assessment}
            </div>
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontWeight: 600, color: '#8b5cf6', flexShrink: 0, marginBottom: 1 }}>内心策略</div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
              {cot.internal_strategy}
            </div>
          </div>
          {cot.secret_action && isSelected && (
            <div style={{ flexShrink: 0 }}>
              <div style={{ fontWeight: 600, color: '#ef4444', marginBottom: 1 }}>秘密行动</div>
              <div style={{ maxHeight: 60, overflowY: 'auto', overflowX: 'hidden' }}>
                {cot.secret_action}
              </div>
            </div>
          )}
        </div>
      )}

      {/* CoT 占位标记 */}
      {!cot && !isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: '#ccc' }}>等待行动...</span>
        </div>
      )}

      {!cot && isDead && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 9, color: '#ccc' }}>已淘汰</span>
        </div>
      )}

      {/* CoT 角标 */}
      {cot && (
        <Brain size={10} style={{ position: 'absolute', bottom: 4, right: 6, color: isSelected ? '#3b82f6' : '#ccc' }} />
      )}
    </motion.div>
  );
}
