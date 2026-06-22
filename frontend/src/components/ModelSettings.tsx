import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Settings, Save, X, Cpu, Gavel, Wifi } from 'lucide-react';

// ── Styles ──
const B: React.CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 9999,
  backgroundColor: 'rgba(0,0,0,0.4)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const P: React.CSSProperties = {
  background: '#fff', borderRadius: 12, padding: 24, width: '100%', maxWidth: 780,
  maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
};
const I: React.CSSProperties = {
  background: '#f9f9f9', border: '1px solid #e5e5e5', borderRadius: 6,
  padding: '6px 10px', fontSize: 12, color: '#333', fontFamily: 'monospace', outline: 'none',
};
const S: React.CSSProperties = { ...I, fontFamily: 'system-ui', color: '#555', cursor: 'pointer' };
const L: React.CSSProperties = { fontSize: 13, fontWeight: 600 };
const R: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'center' };
const BTN = (bg: string, c: string, bc: string): React.CSSProperties => ({
  padding: '5px 14px', fontSize: 12, borderRadius: 6, fontWeight: 500,
  background: bg, color: c, border: `1px solid ${bc}`, cursor: 'pointer',
});

// ── types ──
interface ProviderInfo { id: string; name: string; description: string; }
interface Props { gameId: string; disabled: boolean; }

export function ModelSettings({ gameId, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [cfg, setCfg] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  // Per-slot test state: key is "dm" or "p0".."p5"
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  useEffect(() => {
    fetch('/api/models/providers').then(r => r.json()).then(d => setProviders(d.providers || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (open && gameId) { setMsg(''); fetch(`/api/games/${gameId}/config`).then(r => r.json()).then(d => setCfg(d)).catch(() => setMsg('加载失败')); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async () => {
    if (!cfg || !gameId) return;
    setSaving(true); setMsg('');
    try {
      const res = await fetch(`/api/games/${gameId}/config`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dm_model: cfg.dm_model, dm_provider: cfg.dm_provider, players: cfg.players }) });
      const data = await res.json();
      setMsg(res.ok ? 'Saved' : `Error: ${data.detail}`);
    } catch (e: any) { setMsg(`Error: ${e.message}`); }
    setSaving(false);
  };

  const testSlot = async (slotKey: string, provider: string, model: string) => {
    setTesting(t => ({ ...t, [slotKey]: true }));
    setTestResults(t => ({ ...t, [slotKey]: '' }));
    try {
      const res = await fetch('/api/models/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model }),
      });
      const data = await res.json();
      setTestResults(t => ({ ...t, [slotKey]: data.ok ? `✓ ${data.detail || ''}` : `✗ ${data.error || JSON.stringify(data)}` }));
    } catch (e: any) {
      setTestResults(t => ({ ...t, [slotKey]: `请求失败: ${e.message}` }));
    }
    setTesting(t => ({ ...t, [slotKey]: false }));
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} disabled={disabled || !gameId}
        style={{ ...BTN('#fff', '#333', '#ddd'), display: 'flex', alignItems: 'center', gap: 4, opacity: (disabled || !gameId) ? 0.4 : 1 }}>
        <Settings size={14} /> 配置模型
      </button>
    );
  }

  return createPortal(
    <div style={B} onClick={e => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div style={P} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>模型配置</h3>
          <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999' }}>
            <X size={20} />
          </button>
        </div>

        {!cfg ? <p style={{ color: '#999', textAlign: 'center', padding: 32 }}>加载中...</p> : (
          <>
            {/* DM */}
            <TestableRow
              label="主裁判 (DM)"
              icon={<Gavel size={14} color="#f59e0b" />}
              slotKey="dm"
              provider={cfg.dm_provider || 'relay'}
              model={cfg.dm_model || ''}
              onProviderChange={v => setCfg({ ...cfg, dm_provider: v })}
              onModelChange={v => setCfg({ ...cfg, dm_model: v })}
              providers={providers}
              testing={!!testing['dm']}
              testResult={testResults['dm'] || ''}
              onTest={() => testSlot('dm', cfg.dm_provider || 'relay', cfg.dm_model || 'gpt-4o')}
            />

            {/* Players */}
            <div style={{ marginBottom: 18 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Cpu size={14} color="#3b82f6" /> <span style={L}>博弈玩家 ({cfg.players?.length || 0})</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {(cfg.players || []).map((p: any, i: number) => {
                  const slotKey = `p${i}`;
                  return (
                    <div key={p.id} style={{ ...R, padding: '6px 8px', borderRadius: 8, background: '#fafafa', border: '1px solid #f0f0f0' }}>
                      <span style={{ color: '#ccc', fontSize: 10, width: 16, textAlign: 'center', flexShrink: 0 }}>{i + 1}</span>
                      <input value={p.name || ''} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], name: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                        style={{ ...I, width: 100, flexShrink: 0, border: 'none', borderBottom: '1px solid #eee', borderRadius: 0, background: 'transparent' }} />
                      <select value={p.provider || 'relay'} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], provider: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                        style={{ ...S, width: 90, fontSize: 11, flexShrink: 0 }}>
                        {providers.map(pr => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                      </select>
                      <input value={p.model || ''} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], model: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                        style={{ ...I, flex: 1, minWidth: 80 }} placeholder="model name" />
                      <button onClick={() => testSlot(slotKey, p.provider || 'relay', p.model || 'gpt-4o')} disabled={!!testing[slotKey]}
                        style={{ ...BTN(testing[slotKey] ? '#f5f5f5' : '#eff6ff', testing[slotKey] ? '#999' : '#3b82f6', testing[slotKey] ? '#e5e5e5' : '#bfdbfe'),
                                 display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, padding: '3px 8px', flexShrink: 0 }}>
                        <Wifi size={10} /> {testing[slotKey] ? '...' : 'Test'}
                      </button>
                      {testResults[slotKey] && (
                        <span style={{
                          fontSize: 10, flexShrink: 0, maxWidth: 200, wordBreak: 'break-all', lineHeight: 1.3,
                          color: testResults[slotKey].startsWith('✓') ? '#065f46' : '#991b1b',
                        }}>
                          {testResults[slotKey]}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: '1px solid #eee' }}>
              <span style={{ fontSize: 12, color: msg?.includes('Error') ? '#ef4444' : '#10b981' }}>{msg}</span>
              <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
                <button onClick={() => setOpen(false)} style={BTN('#fff', '#666', '#ddd')}>取消</button>
                <button onClick={save} disabled={saving} style={BTN('#3b82f6', '#fff', '#3b82f6')}>
                  <Save size={12} style={{ marginRight: 3, display: 'inline' }} />{saving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}

// ── DM test row sub-component ──
function TestableRow({ label, icon, slotKey, provider, model, onProviderChange, onModelChange, providers, testing, testResult, onTest }: {
  label: string; icon: React.ReactNode; slotKey: string;
  provider: string; model: string;
  onProviderChange: (v: string) => void; onModelChange: (v: string) => void;
  providers: ProviderInfo[]; testing: boolean; testResult: string; onTest: () => void;
}) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        {icon} <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
        <button onClick={onTest} disabled={testing}
          style={{ ...BTN(testing ? '#f5f5f5' : '#eff6ff', testing ? '#999' : '#3b82f6', testing ? '#e5e5e5' : '#bfdbfe'), marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, padding: '3px 10px' }}>
          <Wifi size={11} /> {testing ? 'Testing...' : 'Test'}
        </button>
      </div>
      {testResult && (
        <div style={{ marginBottom: 6, padding: '6px 10px', borderRadius: 6, fontSize: 11, lineHeight: 1.4, wordBreak: 'break-all',
          background: testResult.startsWith('✓') ? '#ecfdf5' : '#fef2f2',
          color: testResult.startsWith('✓') ? '#065f46' : '#991b1b' }}>
          {testResult}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select value={provider} onChange={e => onProviderChange(e.target.value)} style={{ ...S, minWidth: 160 }}>
          {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input value={model} onChange={e => onModelChange(e.target.value)} placeholder="e.g. gpt-4o" style={{ ...I, flex: 1 }} />
      </div>
    </div>
  );
}
