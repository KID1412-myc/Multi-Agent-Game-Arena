import { PlayerCard } from './PlayerCard';
import { DMPanel } from './DMPanel';
import { PublicBoard } from './PublicBoard';
import { useArenaStore } from '../store/arenaStore';

export function ArenaLayout() {
  const ctx = useArenaStore((s) => s.ctx);

  if (!ctx) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: '#999' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>arena</div>
          <h2 style={{ fontSize: 18, fontWeight: 600, color: '#333', marginBottom: 4 }}>MAGA</h2>
          <p style={{ fontSize: 13 }}>Select a game and press Start</p>
        </div>
      </div>
    );
  }

  const players = Object.values(ctx.round.players);
  const resources = ctx.game_config.resources;
  const topPlayers = players.slice(0, 3);
  const bottomPlayers = players.slice(3, 6);

  // Responsive player card height: use vh so cards scale with viewport
  // ~18-22% of viewport height per row, clamped between 120–160px
  const cardRowH = 'clamp(120px, 20vh, 160px)';

  return (
    <div style={{
      flex: 1, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6,
      background: '#f5f5f5', minHeight: 0,
    }}>
      {/* Top: 3 player cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 8,
        flexShrink: 0,
        height: cardRowH,
        minWidth: 0,
      }}>
        {topPlayers.map((p, i) => (
          <PlayerCard key={p.id} player={p} resources={resources} index={i} />
        ))}
      </div>

      {/* Middle: DM + PublicBoard */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 2fr)',
        gap: 8,
        flex: 1,
        minHeight: 180,
        overflow: 'hidden',
      }}>
        <DMPanel />
        <PublicBoard />
      </div>

      {/* Bottom: 3 player cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 8,
        flexShrink: 0,
        height: cardRowH,
        minWidth: 0,
      }}>
        {bottomPlayers.map((p, i) => (
          <PlayerCard key={p.id} player={p} resources={resources} index={i + 3} />
        ))}
      </div>
    </div>
  );
}
