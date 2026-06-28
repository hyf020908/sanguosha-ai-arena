import type { DistanceInfo, GameState } from '../types';

interface Props {
  state: GameState;
}

export function DistancePanel({ state }: Props) {
  const alivePlayers = state.players.filter((player) => player.alive);

  function distanceFor(sourceId: string, targetId: string): DistanceInfo | undefined {
    return state.distances.find((item) => item.source_player_id === sourceId && item.target_player_id === targetId);
  }

  return (
    <section className="panel-section">
      <div className="section-title">距离与攻击范围</div>
      <div className="distance-table-wrap">
        <table className="distance-table">
          <thead>
            <tr>
              <th>来源</th>
              {alivePlayers.map((player) => (
                <th key={player.id}>{player.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alivePlayers.map((source) => (
              <tr key={source.id}>
                <th>{source.name}</th>
                {alivePlayers.map((target) => {
                  const item = distanceFor(source.id, target.id);
                  if (source.id === target.id) {
                    return <td key={target.id} className="self-cell">-</td>;
                  }
                  return (
                    <td key={target.id} className={item?.in_attack_range ? 'in-range' : 'out-range'}>
                      <span>{item?.distance ?? '-'}</span>
                      <small>/{item?.attack_range ?? '-'}</small>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
