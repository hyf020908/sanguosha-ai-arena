import type { Action } from '../types';
import { renderActionLabel } from '../cardLabels';

interface Props {
  actions: Action[];
  loading: boolean;
  onAction: (actionId: string) => Promise<void>;
}

export function ActionPanel({ actions, loading, onAction }: Props) {
  return (
    <section className="panel-section">
      <div className="section-title">可执行动作</div>
      <div className="actions-row">
        {actions.length === 0 ? <p className="muted">当前没有人类可执行动作。</p> : null}
        {actions.map((action) => (
          <button className={`action-button action-${action.type}`} key={action.action_id} disabled={loading} onClick={() => onAction(action.action_id)}>
            {renderActionLabel(action)}
          </button>
        ))}
      </div>
    </section>
  );
}
