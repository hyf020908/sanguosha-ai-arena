import { cardLabels } from '../cardLabels';
import type { Player } from '../types';

interface Props {
  events: string[];
  players: Player[];
}

const actionWords = [
  '使用',
  '装备',
  '打出',
  '摸了',
  '获得',
  '弃置',
  '判定',
  '响应',
  '求桃',
  '回复',
  '抵消',
  '跳过',
  '移动',
  '结束回合'
];

const statusWords = ['受到', '伤害', '濒死', '死亡', '胜利', '未出', '未使用', '没有桃'];

export function EventLog({ events, players }: Props) {
  const playerNames = players.map((player) => player.name);
  const cardNames = Object.values(cardLabels);

  return (
    <section className="panel-section event-panel">
      <div className="section-title">最近事件</div>
      <ol className="event-log">
        {events.length === 0 ? <li className="muted">暂无事件</li> : null}
        {events.map((event, index) => (
          <li key={`${event}-${index}`} className={eventClass(event)}>
            <span className="event-index">{String(index + 1).padStart(2, '0')}</span>
            <span className="event-text">{renderEvent(event, playerNames, cardNames)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function eventClass(event: string) {
  if (event.includes('死亡') || event.includes('濒死') || event.includes('伤害')) {
    return 'event-danger';
  }
  if (event.includes('胜利') || event.includes('脱离濒死') || event.includes('回复')) {
    return 'event-success';
  }
  if (event.includes('无懈可击') || event.includes('判定')) {
    return 'event-response';
  }
  return '';
}

function renderEvent(event: string, playerNames: string[], cardNames: string[]) {
  const tokens = buildTokens(playerNames, cardNames);
  const pieces: JSX.Element[] = [];
  let cursor = 0;

  while (cursor < event.length) {
    const match = tokens.find((token) => event.startsWith(token.text, cursor));
    if (!match) {
      pieces.push(<span key={cursor}>{event[cursor]}</span>);
      cursor += 1;
      continue;
    }
    pieces.push(
      <span key={`${match.text}-${cursor}`} className={match.className}>
        {match.text}
      </span>
    );
    cursor += match.text.length;
  }

  return pieces;
}

function buildTokens(playerNames: string[], cardNames: string[]) {
  return [
    ...playerNames.map((text) => ({ text, className: 'event-player' })),
    ...cardNames.map((text) => ({ text, className: 'event-card' })),
    ...actionWords.map((text) => ({ text, className: 'event-action' })),
    ...statusWords.map((text) => ({ text, className: 'event-status' }))
  ].sort((left, right) => right.text.length - left.text.length);
}
