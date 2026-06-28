import { useEffect, useState } from 'react';
import { X, BookOpen } from 'lucide-react';

interface Props {
  onClose: () => void;
}

export function ReadmeModal({ onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/readme')
      .then(r => r.json())
      .then(d => setContent(d.content || null))
      .catch(() => setContent(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 'var(--z-40)',
      background: 'var(--bg-overlay)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--bg-surface)', borderRadius: 'var(--radius-xl)',
        maxWidth: 800, width: '90%', maxHeight: '85vh', display: 'flex', flexDirection: 'column',
        boxShadow: 'var(--shadow-L4)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
          padding: '16px 20px', borderBottom: '1px solid var(--border-default)',
        }}>
          <BookOpen size={18} style={{ color: 'var(--color-primary)' }} />
          <span style={{ fontWeight: 700, fontSize: 15, flex: 1, color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>项目说明</span>
          <button onClick={onClose} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: 4 }}>
            <X size={18} />
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', minHeight: 0 }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 32 }}>加载中...</div>
          ) : content ? (
            <div dangerouslySetInnerHTML={{ __html: mdToHtml(content) }} />
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 32 }}>暂无内容</div>
          )}
        </div>
      </div>
    </div>
  );
}

function mdToHtml(md: string): string {
  const codeBlocks: string[] = [];
  let html = md.replace(/```[\s\S]*?```/g, (block) => {
    codeBlocks.push(block);
    return '%%CODE' + (codeBlocks.length - 1) + '%%';
  });

  html = html.replace(/\n{3,}/g, '\n\n');

  html = html
    .replace(/^#### (.+)$/gm, '<h4 style="margin:10px 0 2px;font-size:13px;font-weight:600;">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 style="margin:12px 0 4px;font-size:14px;font-weight:600;">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="margin:14px 0 4px;font-size:15px;font-weight:700;">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="margin:16px 0 6px;font-size:17px;font-weight:700;">$1</h1>');

  html = html
    .replace(/^- (.+)$/gm, '<li style="margin:1px 0 1px 16px;">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li style="margin:1px 0 1px 16px;">$2</li>');

  html = html.replace(/(<li[^>]*>.*?<\/li>\n?)+/gm, (match) => {
    return '<ul style="margin:2px 0;padding:0;">' + match.replace(/\n/g, '') + '</ul>';
  });

  html = html.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

  // 表格（必须先匹配多行，再处理单行）
  html = html.replace(/(^\|.+\|$\n?)+/gm, (tableBlock) => {
    const rows = tableBlock.trim().split('\n').filter(line => line.includes('|'));
    if (rows.length < 2) return tableBlock;
    const cells = rows.map(row =>
      row.split('|').filter((_, i, arr) => i > 0 && i < arr.length - 1).map(c => c.trim())
    );
    const isHeader = rows.length > 1 && /^[\s\|:-]+$/.test(cells[1]?.join('') || '');
    const dataRows = isHeader ? cells.slice(2) : cells;
    const headerRow = isHeader ? cells[0] : null;
    const renderRow = (cols: string[], tag: string, bold: boolean) =>
      '<tr>' + cols.map(c => '<' + tag + ' style="padding:3px 8px;border:1px solid var(--border-default);font-size:11px;' + (bold ? 'font-weight:600;' : '') + '">' + c + '</' + tag + '>').join('') + '</tr>';
    let tableHtml = '<table style="border-collapse:collapse;margin:6px 0;width:100%;">';
    if (headerRow) tableHtml += '<thead>' + renderRow(headerRow, 'th', true) + '</thead>';
    tableHtml += '<tbody>' + dataRows.map(r => renderRow(r, 'td', false)).join('') + '</tbody>';
    tableHtml += '</table>';
    return tableHtml;
  });

  const paragraphs = html.split(/\n\n+/);
  html = paragraphs.map(p => {
    const trimmed = p.trim();
    if (!trimmed) return '';
    if (/^<(h[1-4]|ul|table|div|pre)/.test(trimmed)) return trimmed;
    return '<p style="margin:4px 0;">' + trimmed.replace(/\n/g, '<br/>') + '</p>';
  }).join('');

  html = html.replace(/%%CODE(\d+)%%/g, (_, i) => {
    const block = codeBlocks[parseInt(i)];
    return '<pre style="background:var(--bg-muted);padding:8px;border-radius:4px;font-size:11px;overflow-x:auto;margin:4px 0;">'
      + block.replace(/```/g, '').trim() + '</pre>';
  });

  return html;
}
