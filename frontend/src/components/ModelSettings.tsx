import { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { Settings, Save, X, Cpu, Gavel, Wifi, Shuffle } from 'lucide-react';
import { useArenaStore } from '../store/arenaStore';

// ── Styles ──
const B: React.CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 'var(--z-40)' as any,
  backgroundColor: 'var(--bg-overlay)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const P: React.CSSProperties = {
  background: 'var(--bg-root)', borderRadius: 'var(--radius-xl)', width: '100%', maxWidth: 780,
  maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: 'var(--shadow-L4)',
};
const I: React.CSSProperties = {
  background: 'var(--bg-muted)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
  padding: '6px 10px', fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', outline: 'none',
};
const S: React.CSSProperties = { ...I, fontFamily: 'var(--font-sans)', color: 'var(--text-secondary)', cursor: 'pointer' };
const L: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' };
const R: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'center' };
const BTN = (bg: string, c: string, bc: string): React.CSSProperties => ({
  padding: '5px 14px', fontSize: 12, borderRadius: 'var(--radius-md)', fontWeight: 500,
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

  // 分配模式
  const assignMode = useArenaStore((s) => s.assignMode);
  const assignments = useArenaStore((s) => s.assignments);
  const setAssignMode = useArenaStore((s) => s.setAssignMode);
  const setAssignments = useArenaStore((s) => s.setAssignments);

  // 根据游戏类型计算可用角色/目标
  const assignOptions = useMemo(() => {
    if (!gameId) return null;
    if (gameId === 'werewolf') {
      return {
        title: '角色分配',
        options: [
          { label: '🐺 狼人', value: '狼人', max: 3 },
          { label: '🔮 预言家', value: '预言家', max: 1 },
          { label: '🧪 女巫', value: '女巫', max: 1 },
          { label: '🔫 猎人', value: '猎人', max: 1 },
          { label: '👤 平民', value: '平民', max: 3 },
        ],
        type: 'role' as const,
      };
    }
    if (gameId === 'loot_share') {
      return {
        title: '目标分配',
        options: [
          { label: '🏆 称霸', value: '称霸', max: 1 },
          { label: '📉 垫底', value: '垫底', max: 1 },
          { label: '📊 中游', value: '中游', max: 1 },
          { label: '💥 毁灭者', value: '毁灭者', max: 1 },
          { label: '🕊️ 和平奖', value: '和平奖', max: 1 },
          { label: '🎯 盯上', value: '盯上', max: 1 },
        ],
        type: 'goal' as const,
      };
    }
    if (gameId === 'bomb_collar_v2') {
      return {
        title: '欺诈师分配',
        options: [],
        type: 'fraudster' as const,
      };
    }
    return null;
  }, [gameId]);

  // 用量计数
  const optionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    Object.values(assignments).forEach(v => { counts[v] = (counts[v] || 0) + 1; });
    return counts;
  }, [assignments]);

  useEffect(() => {
    fetch('/api/models/providers').then(r => r.json()).then(d => setProviders(d.providers || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (open && gameId) {
      setMsg('');
      // 加载游戏配置 + 已保存的分配
      Promise.all([
        fetch('/api/games/' + gameId + '/config').then(r => r.json()),
        fetch('/api/games/' + gameId + '/assignments').then(r => r.json()),
      ]).then(([configData, assignData]) => {
        setCfg(configData);
        if (assignData && Object.keys(assignData).length > 0) {
          setAssignments(assignData);
          setAssignMode('manual');
        }
      }).catch(() => setMsg('加载失败'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async () => {
    if (!cfg || !gameId) return;
    setSaving(true); setMsg('');
    try {
      const [cfgRes] = await Promise.all([
        fetch('/api/games/' + gameId + '/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dm_model: cfg.dm_model, dm_provider: cfg.dm_provider, players: cfg.players }) }),
        fetch('/api/games/' + gameId + '/assignments', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(assignments) }),
      ]);
      const data = await cfgRes.json();
      setMsg(cfgRes.ok ? '已保存' : '错误：' + data.detail);
    } catch (e: any) { setMsg(`错误：${e.message}`); }
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
        style={{ padding: '4px 10px', fontSize: 11, border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, opacity: (disabled || !gameId) ? 0.4 : 1 }}>
        <Settings size={14} /> 设置
      </button>
    );
  }

  return createPortal(
    <div style={B} onClick={e => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div style={P} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '24px 24px 0', flexShrink: 0 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>设置</h3>
          <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', minHeight: 0 }}>
        {!cfg ? <p style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 32 }}>加载中...</p> : (
          <>
            {/* DM */}
            <TestableRow
              label="主裁判 (DM)"
              icon={<Gavel size={14} style={{ color: 'var(--color-accent)' }} />}
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
                <Cpu size={14} style={{ color: 'var(--color-primary)' }} /> <span style={L}>博弈玩家 ({cfg.players?.length || 0})</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {(cfg.players || []).map((p: any, i: number) => {
                  const slotKey = `p${i}`;
                  const isHuman = p.is_human || false;
                  return (
                    <div key={p.id} style={{ ...R, padding: '6px 8px', borderRadius: 'var(--radius-md)', background: 'var(--bg-muted)', border: '1px solid var(--border-light)', opacity: isHuman ? 0.7 : 1 }}>
                      <span style={{ color: 'var(--text-tertiary)', fontSize: 10, width: 16, textAlign: 'center', flexShrink: 0 }}>{i + 1}</span>
                      <input value={p.name || ''} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], name: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                        style={{ ...I, width: 80, flexShrink: 0, border: 'none', borderBottom: '1px solid var(--border-default)', borderRadius: 0, background: 'transparent' }} />
                      {/* AI / Human toggle */}
                      <button onClick={() => { const pl = [...cfg.players]; pl[i] = { ...pl[i], is_human: !isHuman }; setCfg({ ...cfg, players: pl }); }}
                        style={{ ...BTN(isHuman ? 'var(--color-accent-soft)' : 'var(--color-primary-soft)', isHuman ? 'var(--color-accent)' : 'var(--color-primary)', isHuman ? 'var(--color-accent-soft)' : 'var(--color-primary-soft)'), fontSize: 10, padding: '2px 6px', flexShrink: 0 }}>
                        {isHuman ? '👤 人类' : '🤖 AI'}
                      </button>
                      {!isHuman && <>
                        <select value={p.provider || 'relay'} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], provider: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                          style={{ ...S, width: 80, fontSize: 11, flexShrink: 0 }}>
                          {providers.map(pr => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                        </select>
                        <input value={p.model || ''} onChange={e => { const pl = [...cfg.players]; pl[i] = { ...pl[i], model: e.target.value }; setCfg({ ...cfg, players: pl }); }}
                          style={{ ...I, flex: 1, minWidth: 60 }} placeholder="模型名" />
                        <button onClick={() => testSlot(slotKey, p.provider || 'relay', p.model || 'gpt-4o')} disabled={!!testing[slotKey]}
                          style={{ ...BTN(testing[slotKey] ? 'var(--bg-muted)' : 'var(--color-primary-soft)', testing[slotKey] ? 'var(--text-tertiary)' : 'var(--color-primary)', testing[slotKey] ? 'var(--border-default)' : 'var(--color-primary-soft)'),
                                   display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, padding: '3px 8px', flexShrink: 0 }}>
                          <Wifi size={10} /> {testing[slotKey] ? '...' : '测试'}
                        </button>
                      </>}
                      {testResults[slotKey] && (
                        <span style={{
                          fontSize: 10, flexShrink: 0, maxWidth: 200, wordBreak: 'break-all', lineHeight: 1.3,
                          color: testResults[slotKey].startsWith('✓') ? 'var(--color-success)' : 'var(--color-danger)',
                        }}>
                          {testResults[slotKey]}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── 分配模式 ── */}
            {assignOptions && (
              <div style={{ marginBottom: 18, padding: '12px 0', borderTop: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                  <Shuffle size={14} style={{ color: 'var(--color-secondary)' }} />
                  <span style={L}>{assignOptions.title}</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                    <button onClick={() => { setAssignMode('random'); setAssignments({}); }}
                      style={{ ...BTN(assignMode === 'random' ? 'var(--color-secondary)' : 'var(--bg-surface)', assignMode === 'random' ? '#fff' : 'var(--text-secondary)', assignMode === 'random' ? 'var(--color-secondary)' : 'var(--border-default)'), fontSize: 11 }}>
                      随机
                    </button>
                    <button onClick={() => setAssignMode('manual')}
                      style={{ ...BTN(assignMode === 'manual' ? 'var(--color-secondary)' : 'var(--bg-surface)', assignMode === 'manual' ? '#fff' : 'var(--text-secondary)', assignMode === 'manual' ? 'var(--color-secondary)' : 'var(--border-default)'), fontSize: 11 }}>
                      手动
                    </button>
                  </div>
                </div>
                {assignMode === 'manual' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {(cfg?.players || []).map((p: any) => (
                      <div key={p.id} style={{ ...R, padding: '4px 8px', borderRadius: 'var(--radius-md)', background: 'var(--bg-muted)' }}>
                        <span style={{ fontSize: 12, width: 90, color: 'var(--text-secondary)' }}>{p.name} ({p.id})</span>
                        {assignOptions.type === 'fraudster' ? (
                          <label style={{ fontSize: 12, cursor: 'pointer' }}>
                            <input type="checkbox" checked={assignments[p.id] === '欺诈师'}
                              onChange={e => {
                                const a = { ...assignments };
                                if (e.target.checked) {
                                  Object.keys(a).forEach(k => { if (a[k] === '欺诈师') delete a[k]; });
                                  a[p.id] = '欺诈师';
                                } else {
                                  delete a[p.id];
                                }
                                setAssignments(a);
                              }} />
                            {' '}🎭 欺诈师
                          </label>
                        ) : (
                          <select value={assignments[p.id] || ''}
                            onChange={e => {
                              const a = { ...assignments };
                              if (e.target.value) a[p.id] = e.target.value; else delete a[p.id];
                              setAssignments(a);
                            }}
                            style={{ ...S, flex: 1, fontSize: 12 }}>
                            <option value="">— 不指定 —</option>
                            {assignOptions.options.map(opt => (
                              <option key={opt.value} value={opt.value}
                                disabled={(optionCounts[opt.value] || 0) >= opt.max && assignments[p.id] !== opt.value}>
                                {opt.label} ({(optionCounts[opt.value] || 0)}/{opt.max})
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: '1px solid var(--border-default)' }}>
              <span style={{ fontSize: 12, color: msg?.includes('错误') ? 'var(--color-danger)' : 'var(--color-success)' }}>{msg}</span>
              <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
                <button onClick={() => setOpen(false)} style={BTN('var(--bg-surface)', 'var(--text-secondary)', 'var(--border-default)')}>取消</button>
                <button onClick={save} disabled={saving} style={BTN('var(--color-primary)', '#fff', 'var(--color-primary)')}>
                  <Save size={12} style={{ marginRight: 3, display: 'inline' }} />{saving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
          </>
        )}
        </div>
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
          style={{ ...BTN(testing ? 'var(--bg-muted)' : 'var(--color-primary-soft)', testing ? 'var(--text-tertiary)' : 'var(--color-primary)', testing ? 'var(--border-default)' : 'var(--color-primary-soft)'), marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, padding: '3px 10px' }}>
          <Wifi size={11} /> {testing ? '测试中...' : '测试'}
        </button>
      </div>
      {testResult && (
        <div style={{ marginBottom: 6, padding: '6px 10px', borderRadius: 'var(--radius-md)', fontSize: 11, lineHeight: 1.4, wordBreak: 'break-all',
          background: testResult.startsWith('✓') ? 'var(--color-success-soft)' : 'var(--color-danger-soft)',
          color: testResult.startsWith('✓') ? 'var(--color-success)' : 'var(--color-danger)' }}>
          {testResult}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select value={provider} onChange={e => onProviderChange(e.target.value)} style={{ ...S, minWidth: 160 }}>
          {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input value={model} onChange={e => onModelChange(e.target.value)} placeholder="例如 gpt-4o" style={{ ...I, flex: 1 }} />
      </div>
    </div>
  );
}
