import { useEffect, useState } from 'react';
import { X, BookOpen } from 'lucide-react';

interface Props {
  gameId: string | null;
  gameName: string;
  onClose: () => void;
}

export function RuleModal({ gameId, gameName, onClose }: Props) {
  const [rules, setRules] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!gameId) return;
    setLoading(true);
    fetch(`/api/games/${gameId}/rules`)
      .then((r) => r.json())
      .then((d) => setRules(d.rules || null))
      .catch(() => setRules(null))
      .finally(() => setLoading(false));
  }, [gameId]);

  if (!gameId) return null;

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.35)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 12, maxWidth: 640, width: '90%',
        maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '16px 20px', borderBottom: '1px solid #eee', flexShrink: 0,
        }}>
          <BookOpen size={18} style={{ color: '#3b82f6' }} />
          <span style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>{gameName} — 规则</span>
          <button onClick={onClose} style={{
            border: 'none', background: 'none', cursor: 'pointer', color: '#999', padding: 4,
          }}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1, fontSize: 13, lineHeight: 1.8, color: '#333' }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: '#999', padding: 32 }}>加载中...</div>
          ) : rules ? (
            <div dangerouslySetInnerHTML={{ __html: mdToHtml(rules) }} />
          ) : (
            <div style={{ textAlign: 'center', color: '#999', padding: 32 }}>该游戏暂无规则文档</div>
          )}
        </div>
      </div>
    </div>
  );
}

/** 极简 Markdown → HTML */
function mdToHtml(md: string): string {
  let html = md
    // 标题
    .replace(/^#### (.+)$/gm, '<h4 style="margin:12px 0 4px;font-size:13px;">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 style="margin:14px 0 4px;font-size:14px;">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="margin:16px 0 6px;font-size:15px;font-weight:700;">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="margin:18px 0 8px;font-size:17px;font-weight:700;">$1</h1>')
    // 列表
    .replace(/^- (.+)$/gm, '<li style="margin-left:16px">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li style="margin-left:16px">$2</li>')
    // 粗体
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    // 表格（简单处理：用 pre 包裹）
    .replace(/^\|(.+)\|$/gm, (line) => `<span style="font-family:monospace;font-size:11px;">${line}</span><br/>`)
    // 代码块
    .replace(/```[\s\S]*?```/g, (block) => `<pre style="background:#f5f5f5;padding:8px;border-radius:4px;font-size:11px;overflow-x:auto;">${block.replace(/```/g, '').trim()}</pre>`)
    // 空行 → 段落分隔
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');

  // 把连续的 <li> 包进 <ul>
  html = html.replace(/(<li[^>]*>.*?<\/li>(<br\/>)?)+/g, (match) => {
    const items = match.replace(/<br\/>/g, '');
    return `<ul style="margin:4px 0;padding:0;">${items}</ul>`;
  });

  return html;
}
