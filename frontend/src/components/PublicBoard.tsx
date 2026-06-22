import { useEffect, useRef, useState } from 'react';
import { MessageCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6'];
const PAGE_SIZE = 25;

export function PublicBoard() {
  const speechLog = useArenaStore((s) => s.speechLog);
  const ctx = useArenaStore((s) => s.ctx);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showAll, setShowAll] = useState(false);

  // 从 ctx 中提取 public_log（游戏事件如赃款公布、审判等）
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

  // Group by round for collapsible display
  const grouped: Record<number, typeof speechLog> = {};
  for (const s of visible) {
    if (!grouped[s.round]) grouped[s.round] = [];
    grouped[s.round].push(s);
  }

  return (
    <div style={{ background: '#fff', borderRadius: 10, padding: 16,
                  border: '1px solid #e5e5e5', boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexShrink: 0 }}>
        <MessageCircle size={15} style={{ color: '#3b82f6' }} />
        <span style={{ fontWeight: 700, fontSize: 14, color: '#1a1a1a' }}>公共看板</span>
        <span style={{ fontSize: 11, color: '#999' }}>{speechLog.length} 条发言</span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {!showAll && hiddenCount > 0 && (
            <button onClick={() => setShowAll(true)}
              style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: '#3b82f6',
                       border: '1px solid #e5e5e5', borderRadius: 4, background: '#fff', cursor: 'pointer', padding: '2px 6px' }}>
              <ChevronDown size={10} /> 显示全部 ({hiddenCount} 条更多)
            </button>
          )}
          {showAll && (
            <button onClick={() => { setShowAll(false); }}
              style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: '#666',
                       border: '1px solid #e5e5e5', borderRadius: 4, background: '#fff', cursor: 'pointer', padding: '2px 6px' }}>
              <ChevronUp size={10} /> 仅最新
            </button>
          )}
        </div>
      </div>

      {/* 固定事件栏：最新游戏事件（赃款、谈判结果）不滚动 */}
      <div style={{
        flexShrink: 0, padding: '4px 8px', marginBottom: 4,
        background: publicLog.length > 0 ? '#fefce8' : '#f9fafb',
        borderLeft: `3px solid ${publicLog.length > 0 ? '#f59e0b' : '#ddd'}`,
        borderRadius: 4, fontSize: 12, fontWeight: 600,
        color: publicLog.length > 0 ? '#92400e' : '#999',
      }}>
        {publicLog.length > 0 ? publicLog[publicLog.length - 1] : '等待开局...'}
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', fontSize: 12, lineHeight: 1.5, minHeight: 0 }}>
        {/* 历史事件（可滚动）*/}
        {publicLog.length > 1 && (
          <div style={{ marginBottom: 8 }}>
            {publicLog.slice(0, -1).reverse().map((entry, i) => (
              <div key={`pl-${i}`} style={{
                padding: '2px 8px', marginBottom: 1, fontSize: 10, color: '#a16207', opacity: 0.7,
              }}>
                {entry}
              </div>
            ))}
          </div>
        )}
        {speechLog.length === 0 && publicLog.length === 0 ? (
          <div style={{ color: '#ccc', textAlign: 'center', padding: 32 }}>等待玩家发言...</div>
        ) : (
          Object.entries(grouped).map(([round, entries]) => (
            <div key={round}>
              <div style={{
                fontSize: 10, color: '#999', padding: '6px 0 2px',
                borderBottom: '1px solid #f0f0f0', marginBottom: 2, fontWeight: 600,
                position: 'sticky', top: 0, background: '#fff', zIndex: 1,
              }}>
                Round {round}
              </div>
              {entries.map((s, i) => (
                <div key={`${s.round}-${i}`} style={{
                  padding: '4px 0', borderBottom: '1px solid #fafafa',
                  borderLeft: '2px solid transparent',
                  paddingLeft: 10,
                  transition: 'all 0.2s',
                }}>
                  <span style={{ fontWeight: 600, color: getColor(s.playerId) }}>{s.playerName}</span>
                  <div style={{ color: '#444', marginTop: 1 }}>{s.content}</div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
