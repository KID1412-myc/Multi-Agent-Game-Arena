import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useArenaStore } from '../store/arenaStore';

interface Props {
  ws: WebSocket | null;
}

export function HumanInput({ ws }: Props) {
  const ctx = useArenaStore((s) => s.ctx);
  const gameStatus = useArenaStore((s) => s.gameStatus);
  const [playerId, setPlayerId] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [phase, setPhase] = useState('speech');
  const [speech, setSpeech] = useState('');
  const [action, setAction] = useState('');
  const [waiting, setWaiting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [closing, setClosing] = useState(false);

  // 游戏停止或异常时自动关闭输入框
  useEffect(() => {
    if (waiting && (gameStatus === 'idle' || gameStatus === 'error')) {
      setWaiting(false);
      setClosing(false);
      setSpeech('');
      setAction('');
      useArenaStore.getState().setHumanWaiting(false);
    }
  }, [gameStatus, waiting]);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      setPlayerId(e.detail.player_id);
      setPlayerName(e.detail.player_name);
      setPhase(e.detail.phase || 'speech');
      setSpeech('');
      setAction('');
      setWaiting(true);
      setClosing(false);
      const s = useArenaStore.getState();
      s.setHumanWaiting(true);
      s.setSelectedPlayer(null);
    };
    window.addEventListener('human-turn', handler as EventListener);
    return () => window.removeEventListener('human-turn', handler as EventListener);
  }, []);

  if (!waiting) return null;

  const submit = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert('连接已断开，请刷新页面后重试');
      return;
    }
    setSubmitting(true);
    ws.send(JSON.stringify({
      type: 'human_input',
      player_id: playerId,
      speech: speech,
      action: action,
    }));
    // 先播放收缩动画，再关闭
    setClosing(true);
    setTimeout(() => {
      setWaiting(false);
      setClosing(false);
      setSubmitting(false);
      setSpeech('');
      setAction('');
      useArenaStore.getState().setHumanWaiting(false);
    }, 350);
  };

  const player = ctx?.round.players[playerId];
  const resources = player ? Object.entries(player.resources).map(([k, v]) => `${k}: ${v}`).join(', ') : '';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: closing ? 0 : 1 }}
      transition={{ duration: 0.2 }}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 'var(--z-30)', background: 'var(--bg-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 32 }}
        animate={closing
          ? { opacity: 0, scale: 1.02 }
          : { opacity: 1, scale: 1, y: 0 }}
        transition={closing
          ? { duration: 0.15, ease: [0.4, 0, 1, 1] }
          : { type: 'spring', damping: 20, stiffness: 90, duration: 0.35 }}
        style={{
          background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', padding: 24,
          minWidth: 380, maxWidth: 480,
          border: '2px solid var(--status-human)', boxShadow: 'var(--shadow-L4)',
        }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
          轮到你了 —— {playerName} ({playerId})
        </div>
        {resources && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>{resources}</div>}
        <div style={{ fontSize: 12, color: 'var(--status-human)', marginBottom: 8 }}>
          {phase === 'speech' ? '💬 公开发言阶段' : phase === 'action' ? '🎯 行动阶段' : '💬 发言 + 行动'}
        </div>

        <textarea
          value={speech}
          onChange={e => setSpeech(e.target.value)}
          placeholder="公开发言（所有玩家可见）..."
          style={{
            width: '100%', height: 80, padding: 8, fontSize: 13,
            border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', resize: 'vertical',
            fontFamily: 'var(--font-sans)', background: 'var(--bg-root)', color: 'var(--text-primary)',
          }}
          autoFocus
        />

        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
          {phase === 'action' || phase === 'full' ? '秘密行动（如 DEV / 刀-p3 / 投-p5 / 数字）：' : '秘密行动（可选）：'}
        </div>
        <input
          value={action}
          onChange={e => setAction(e.target.value)}
          placeholder={phase === 'action' ? '如：刀-p3' : '可选'}
          style={{
            width: '100%', padding: '6px 8px', fontSize: 13,
            border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
            fontFamily: 'var(--font-mono)', marginTop: 4,
            background: 'var(--bg-root)', color: 'var(--text-primary)',
          }}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
        />

        <button onClick={submit} disabled={submitting}
          style={{
            marginTop: 12, width: '100%', padding: '10px', fontSize: 14, fontWeight: 600,
            background: submitting ? '#FCD34D' : 'var(--status-human)', color: '#FFFFFF', border: 'none', borderRadius: 'var(--radius-md)',
          }}>
          {submitting ? '提交中...' : '提交'}
        </button>
      </motion.div>
    </motion.div>
  );
}
