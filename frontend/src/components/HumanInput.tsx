import { useState, useEffect, useRef } from 'react';
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
  const [context, setContext] = useState('');
  const [closing, setClosing] = useState(false);
  const [phaseLabel, setPhaseLabel] = useState('');
  const [targets, setTargets] = useState<{id: string; name: string; label: string}[]>([]);
  const [quickActions, setQuickActions] = useState<{value: string; label: string}[]>([]);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      // 清除上一次提交的关闭定时器，防止新弹窗被旧定时器秒关
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setSubmitting(false);  // 防止旧提交状态污染新弹窗（否则按钮卡在"提交中..."）
      setPlayerId(e.detail.player_id);
      setPlayerName(e.detail.player_name);
      setPhase(e.detail.phase || 'speech');
      setContext(e.detail.context || '');
      setPhaseLabel(e.detail.phase_label || '');
      setTargets(e.detail.targets || []);
      setQuickActions(e.detail.quick_actions || []);
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

  const isNotify = phase === 'notify';

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
    closeTimerRef.current = setTimeout(() => {
      setWaiting(false);
      setClosing(false);
      setSubmitting(false);
      setSpeech('');
      setAction('');
      useArenaStore.getState().setHumanWaiting(false);
      closeTimerRef.current = null;
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
        {resources && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>{resources}</div>}
        {context && (
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 10, padding: '8px 10px', background: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', maxHeight: 120, overflowY: 'auto', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {context}
          </div>
        )}
        <div style={{ fontSize: 12, color: 'var(--status-human)', marginBottom: 8, fontWeight: 600 }}>
          {phaseLabel || (isNotify ? '📋 行动结果' : phase === 'speech' ? '💬 发言' : phase === 'action' ? '🎯 秘密行动' : '💬 发言 + 行动')}
        </div>

        {!isNotify && (
          <>
            {(targets.length > 0 || quickActions.length > 0) && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                {/* 指向性目标按钮（刀/验/毒/枪） */}
                {targets.map(t => (
                  <button key={t.id}
                    onClick={() => setAction(t.id)}
                    style={{
                      padding: '3px 10px', fontSize: 11, fontWeight: 500,
                      borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                      border: '1px solid var(--border-default)', background: 'var(--bg-muted)',
                      color: 'var(--text-primary)', transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-muted)')}
                  >
                    {t.label || `${t.name}(${t.id})`}
                  </button>
                ))}
                {/* 分隔 */}
                {targets.length > 0 && quickActions.length > 0 && (
                  <span style={{ width: 4 }} />
                )}
                {/* 非指向性行动按钮（救/跳过/压枪）——不同底色 */}
                {quickActions.map(a => (
                  <button key={a.value}
                    onClick={() => setAction(a.value)}
                    style={{
                      padding: '3px 10px', fontSize: 11, fontWeight: 600,
                      borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                      border: '1px solid var(--color-accent)', background: 'var(--color-accent-soft)',
                      color: 'var(--color-accent)', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'var(--color-accent)';
                      e.currentTarget.style.color = '#fff';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'var(--color-accent-soft)';
                      e.currentTarget.style.color = 'var(--color-accent)';
                    }}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            )}
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
              {phase === 'speech' ? '你的发言将对所有存活玩家公开' : '输入你的秘密行动，只有系统能看到'}
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
          </>
        )}

        <button onClick={submit} disabled={submitting}
          style={{
            marginTop: 12, width: '100%', padding: '10px', fontSize: 14, fontWeight: 600,
            background: submitting ? '#FCD34D' : 'var(--status-human)', color: '#FFFFFF', border: 'none', borderRadius: 'var(--radius-md)',
          }}>
          {submitting ? '提交中...' : isNotify ? '知道了' : '提交'}
        </button>
      </motion.div>
    </motion.div>
  );
}
