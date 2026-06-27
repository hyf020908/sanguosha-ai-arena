import type { Card } from '../types';

const cardLabels: Record<Card['name'], string> = {
  sha: '杀',
  shan: '闪',
  tao: '桃'
};

export function HandCards({ cards }: { cards: Card[] }) {
  return (
    <section className="panel-section">
      <div className="section-title">你的手牌</div>
      <div className="hand-row">
        {cards.length === 0 ? <p className="muted">当前没有手牌</p> : null}
        {cards.map((card) => (
          <div className={`hand-card ${card.name}`} key={card.id}>
            <strong>{cardLabels[card.name]}</strong>
            <span>
              {card.suit} {card.rank}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

