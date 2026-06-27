export function EventLog({ events }: { events: string[] }) {
  return (
    <section className="panel-section">
      <div className="section-title">最近事件</div>
      <ol className="event-log">
        {events.length === 0 ? <li className="muted">暂无事件</li> : null}
        {events.map((event, index) => (
          <li key={`${event}-${index}`}>{event}</li>
        ))}
      </ol>
    </section>
  );
}

