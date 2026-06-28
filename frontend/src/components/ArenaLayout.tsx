import { PlayerCard } from './PlayerCard';
import { DMPanel } from './DMPanel';
import { PublicBoard } from './PublicBoard';
import { useArenaStore } from '../store/arenaStore';

export function ArenaLayout() {
  const ctx = useArenaStore((s) => s.ctx);

  if (!ctx) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>arena</div>
          <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-display)', marginBottom: 4 }}>MAGA</h2>
          <p style={{ fontSize: 13 }}>Select a game and press Start</p>
        </div>
      </div>
    );
  }

  const players = Object.values(ctx.round.players);
  const resources = ctx.game_config.resources;
  const activeId = players.find(p => p.is_current_speaker)?.id || null;

  const topPlayers = players.slice(0, 3);
  const bottomPlayers = players.slice(3);

  const bottomRows: typeof players[] = [];
  for (let i = 0; i < bottomPlayers.length; i += 3) {
    bottomRows.push(bottomPlayers.slice(i, i + 3));
  }

  const cardRowH = 'clamp(105px, 16vh, 140px)';

  return (
    <div style={{
      flex: 1, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6,
      background: 'var(--bg-root)', minHeight: 0, overflowY: 'auto',
    }}>
      {/* 顶部：固定 1 行玩家 — Bento Grid：发言者占 2 列 */}
      {topPlayers.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: 8,
          flexShrink: 0,
          height: cardRowH,
          minWidth: 0,
        }}>
          {topPlayers.map((p, i) => (
            <div key={p.id} style={{
              gridColumn: p.id === activeId ? 'span 2' : undefined,
              height: '100%', overflow: 'hidden',
            }}>
              <PlayerCard player={p} resources={resources} index={i} />
            </div>
          ))}
        </div>
      )}

      {/* 中间：DM + PublicBoard */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 2fr)',
        gap: 8,
        flex: 1,
        minHeight: 200,
        overflow: 'hidden',
      }}>
        <DMPanel />
        <PublicBoard />
      </div>

      {/* 底部：其余玩家，可滚动 */}
      {bottomRows.length > 0 && (
        <div style={{
          flexShrink: 0,
          maxHeight: 300,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}>
          {bottomRows.map((row, rowIdx) => (
            <div key={rowIdx} style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: 8,
              flexShrink: 0,
              height: cardRowH,
              minWidth: 0,
            }}>
              {row.map((p, colIdx) => (
                <div key={p.id} style={{
                  gridColumn: p.id === activeId ? 'span 2' : undefined,
                  height: '100%', overflow: 'hidden',
                }}>
                  <PlayerCard player={p} resources={resources} index={3 + rowIdx * 3 + colIdx} />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
