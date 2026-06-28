import { useEffect, useRef, useState } from 'react';
import type { GameState } from '../types';
import { ActionPanel } from './ActionPanel';
import { DistancePanel } from './DistancePanel';
import { EventLog } from './EventLog';
import { HandCards } from './HandCards';
import { PlayerPanel } from './PlayerPanel';
import { formatCard, suitColorClass } from '../cardLabels';

interface Props {
  state: GameState;
  loading: boolean;
  onAction: (actionId: string) => Promise<void>;
  onNewGame: () => void;
}

const phaseLabels: Record<GameState['phase'], string> = {
  judge: '判定',
  draw: '摸牌',
  play: '出牌',
  discard: '弃牌',
  response: '响应',
  game_over: '结束'
};

const winnerLabels: Record<string, string> = {
  zhu: '主公阵营胜利',
  fan: '反贼胜利',
  nei: '内奸胜利'
};

export function GameBoard({ state, loading, onAction, onNewGame }: Props) {
  const human = state.players.find((player) => player.is_human);
  const current = state.players[state.current_player_index];
  const isHumanPlayPhase = Boolean(current?.is_human && state.phase === 'play');
  const wasHumanPlayPhase = useRef(false);
  const [pulseTitle, setPulseTitle] = useState(false);

  useEffect(() => {
    if (isHumanPlayPhase && !wasHumanPlayPhase.current) {
      setPulseTitle(true);
      const timer = window.setTimeout(() => setPulseTitle(false), 1100);
      wasHumanPlayPhase.current = true;
      return () => window.clearTimeout(timer);
    }
    if (!isHumanPlayPhase) {
      wasHumanPlayPhase.current = false;
      setPulseTitle(false);
    }
    return undefined;
  }, [isHumanPlayPhase]);

  return (
    <main className="game-shell">
      <header className="game-header">
        <div>
          <p className="eyebrow">第 {state.round} 轮</p>
          <h1 className={pulseTitle ? 'turn-title-pulse' : ''}>{current?.name ?? '-'} 的 {phaseLabels[state.phase]}阶段</h1>
        </div>
        <div className="header-actions">
          <div className="deck-info">牌堆 {state.deck_count} · 弃牌 {state.discard_count}</div>
          <button className="secondary-button" onClick={onNewGame}>新建游戏</button>
        </div>
      </header>

      {state.winner ? <div className="winner-banner">{winnerLabels[state.winner] ?? state.winner}</div> : null}

      <PlayerPanel state={state} />

      <div className="board-columns">
        <div>
          <HandCards cards={human?.hand ?? []} />
          {state.pending_response?.type === 'wugu' ? (
            <section className="panel-section">
              <div className="section-title">五谷丰登公共牌池</div>
              <div className="wugu-pool">
                {(state.pending_response.wugu_pool ?? []).map((card) => (
                  <span className={`pool-card ${suitColorClass(card.suit)}`} key={card.id}>
                    {formatCard(card)}
                  </span>
                ))}
              </div>
            </section>
          ) : null}
          <DistancePanel state={state} />
          <ActionPanel actions={state.legal_actions} loading={loading} onAction={onAction} />
        </div>
        <EventLog events={state.recent_events} players={state.players} />
      </div>
    </main>
  );
}
