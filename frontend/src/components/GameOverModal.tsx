interface PlayerInfo {
  id: string; name: string; role: string; icon?: string;
  is_alive?: boolean; side?: string; points?: number;
  identity?: string; goal_name?: string; goal_met?: boolean; rank?: number;
}

interface Props {
  winnerName: string | null;
  ranking: { name: string; score: number }[];
  extra: Record<string, any> | null;
  onClose: () => void;
}

const medalIcons = ['🥇', '🥈', '🥉'];

export function GameOverModal({ winnerName, ranking, extra, onClose }: Props) {
  const gameType = extra?.game_type as string | undefined;
  const players: PlayerInfo[] = extra?.players || [];

  return (
    <div style={{
      position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
      zIndex: 9999, background: '#fff', borderRadius: 12, padding: 28,
      minWidth: 340, maxWidth: 480, maxHeight: '85vh', overflow: 'auto',
      border: '2px solid #f59e0b', boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, marginBottom: 4 }}>🏆</div>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: '#333', marginBottom: 16 }}>
        {renderTitle(gameType, extra, winnerName)}
      </h2>

      {gameType === 'werewolf' && renderWerewolf(players, extra)}
      {gameType === 'bomb_collar_v2' && renderBombCollar(players, extra)}
      {gameType === 'loot_share' && renderLootShare(players)}
      {!gameType && renderDefault(ranking, winnerName)}

      <button onClick={onClose}
        style={{ marginTop: 12, padding: '4px 20px', fontSize: 12, border: '1px solid #ddd',
                 borderRadius: 6, background: '#fff', cursor: 'pointer', color: '#666' }}>
        关闭
      </button>
    </div>
  );
}

function renderTitle(gameType: string | undefined, extra: any, winnerName: string | null) {
  if (gameType === 'werewolf') {
    const side = extra?.winner_side || '?';
    return `游戏结束 —— ${side}阵营获胜`;
  }
  if (gameType === 'bomb_collar_v2') {
    const side = extra?.winner_side || '?';
    return `游戏结束 —— ${side}胜利`;
  }
  if (gameType === 'loot_share') {
    return winnerName ? `胜者：${winnerName}` : '游戏结束（无人达成目标）';
  }
  return winnerName ? `胜者：${winnerName}` : '游戏结束';
}

function renderWerewolf(players: PlayerInfo[], extra: any) {
  const wolves = players.filter(p => p.side === '狼人');
  const goods = players.filter(p => p.side === '好人');

  return (
    <div style={{ textAlign: 'left', fontSize: 13 }}>
      {extra?.desc && (
        <div style={{ marginBottom: 10, color: '#666', fontSize: 12, textAlign: 'center' }}>
          {extra.desc}
        </div>
      )}
      <div style={{ marginBottom: 8, fontWeight: 600, color: '#dc2626' }}>🐺 狼人阵营</div>
      {wolves.map(p => (
        <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 8px' }}>
          <span>{p.icon} {p.name} <span style={{ fontSize: 11, color: '#999' }}>{p.role}</span></span>
          <span style={{ color: p.is_alive ? '#16a34a' : '#999' }}>{p.is_alive ? '存活' : '已淘汰'}</span>
        </div>
      ))}
      <div style={{ marginTop: 8, marginBottom: 8, fontWeight: 600, color: '#2563eb' }}>
        🔮🧪🔫👤 好人阵营
      </div>
      {goods.map(p => (
        <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 8px' }}>
          <span>{p.icon} {p.name} <span style={{ fontSize: 11, color: '#999' }}>{p.role}</span></span>
          <span style={{ color: p.is_alive ? '#16a34a' : '#999' }}>{p.is_alive ? '存活' : '已淘汰'}</span>
        </div>
      ))}
    </div>
  );
}

function renderBombCollar(players: PlayerInfo[], extra: any) {
  const fraudName = extra?.fraudster_name || '?';
  return (
    <div style={{ textAlign: 'left', fontSize: 13 }}>
      <div style={{ marginBottom: 8, color: '#666', fontSize: 12, textAlign: 'center' }}>
        {extra?.reason}　|　欺诈师：<b style={{ color: '#dc2626' }}>{fraudName}</b>
        {extra?.accuser_name ? <>　|　指认者：<b style={{ color: '#16a34a' }}>{extra.accuser_name}</b></> : null}
      </div>
      {players.map((p, i) => (
        <div key={p.id} style={{
          display: 'flex', justifyContent: 'space-between', padding: '3px 8px',
          background: p.role === '欺诈师' ? '#fef2f2' : 'transparent',
          borderRadius: 4, marginBottom: 1,
        }}>
          <span>
            <span style={{ fontWeight: p.role === '欺诈师' ? 700 : 400 }}>
              {p.name}
            </span>
            <span style={{ fontSize: 11, color: p.role === '欺诈师' ? '#dc2626' : '#999', marginLeft: 4 }}>
              {p.role === '欺诈师' ? '🎭 欺诈师' : '👤 平民'}
            </span>
          </span>
          <span>
            <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{p.points} 分</span>
            <span style={{ marginLeft: 6, color: p.is_alive ? '#16a34a' : '#999', fontSize: 11 }}>
              {p.is_alive ? '存活' : '已淘汰'}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function renderLootShare(players: PlayerInfo[]) {
  const winners = players.filter(p => p.goal_met);
  return (
    <div style={{ textAlign: 'left', fontSize: 13 }}>
      {winners.length > 0 && (
        <div style={{ marginBottom: 8, color: '#f59e0b', fontSize: 12, textAlign: 'center', fontWeight: 600 }}>
          达成秘密目标：{winners.map(w => w.name).join('、')}
        </div>
      )}
      {players.map((p, i) => (
        <div key={p.id} style={{
          display: 'flex', justifyContent: 'space-between', padding: '3px 8px',
          background: p.goal_met ? '#fffbeb' : 'transparent',
          borderRadius: 4, marginBottom: 1,
        }}>
          <span>
            <span style={{ fontWeight: p.goal_met ? 700 : 400 }}>
              {p.name}
            </span>
            <span style={{ fontSize: 11, color: '#999', marginLeft: 4 }}>
              {p.identity} · {p.goal_name}
            </span>
          </span>
          <span>
            {p.goal_met ? <span style={{ color: '#f59e0b', marginRight: 6 }}>✅</span> : <span style={{ color: '#ddd', marginRight: 6 }}>—</span>}
            <span style={{ fontFamily: 'monospace' }}>{p.points} 分</span>
          </span>
        </div>
      ))}
      {winners.length === 0 && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 12 }}>无人达成秘密目标</div>
      )}
    </div>
  );
}

function renderDefault(ranking: { name: string; score: number }[], winnerName: string | null) {
  if (ranking.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      {ranking.map((r, i) => (
        <div key={i} style={{
          display: 'flex', justifyContent: 'space-between', padding: '4px 12px',
          fontSize: 13, fontWeight: r.name === ranking[0].name ? 700 : 400,
          color: i === 0 ? '#f59e0b' : '#333',
          background: i === 0 ? '#fffbeb' : 'transparent',
          borderRadius: 4, marginBottom: 2,
        }}>
          <span>{medalIcons[i] || i + 1} {r.name}</span>
          <span style={{ fontFamily: 'monospace' }}>{r.score} 分</span>
        </div>
      ))}
    </div>
  );
}
