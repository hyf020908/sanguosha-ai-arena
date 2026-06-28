import type { GameState, Player, Role } from '../types';
import { formatCard } from '../cardLabels';

const roleLabels: Record<Role, string> = {
  zhu: '主公',
  zhong: '忠臣',
  fan: '反贼',
  nei: '内奸',
  unknown: '隐藏'
};

interface Props {
  state: GameState;
}

export function PlayerPanel({ state }: Props) {
  const currentId = state.players[state.current_player_index]?.id;

  return (
    <section className="players-grid">
      {state.players.map((player) => (
        <PlayerCard key={player.id} player={player} active={player.id === currentId} />
      ))}
    </section>
  );
}

function PlayerCard({ player, active }: { player: Player; active: boolean }) {
  return (
    <article className={`player-card ${active ? 'active' : ''} ${player.alive ? '' : 'dead'}`}>
      <div className="player-topline">
        <strong>{player.name}</strong>
        <span>{player.is_human ? '你' : 'AI'}</span>
      </div>
      <div className="role-pill">{roleLabels[player.role]}</div>
      <div className="hp-row">
        <span>
          体力 {player.hp}/{player.max_hp}
        </span>
        <span>手牌 {player.hand_count}</span>
      </div>
      <div className="zone-row">
        {player.equipment.weapon ? <span>武器 {formatCard(player.equipment.weapon)}</span> : null}
        {player.equipment.armor ? <span>防具 {formatCard(player.equipment.armor)}</span> : null}
        {player.equipment.attack_horse ? <span>-1 {formatCard(player.equipment.attack_horse)}</span> : null}
        {player.equipment.defense_horse ? <span>+1 {formatCard(player.equipment.defense_horse)}</span> : null}
        {player.judgment_area.map((card) => (
          <span key={card.id}>判定 {formatCard(card)}</span>
        ))}
      </div>
    </article>
  );
}
