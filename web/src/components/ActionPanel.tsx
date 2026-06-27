import type { Action } from '../types';

interface Props {
  actions: Action[];
  loading: boolean;
  onAction: (actionId: string) => Promise<void>;
  onStepAi: () => Promise<void>;
}

export function ActionPanel({ actions, loading, onAction, onStepAi }: Props) {
  return (
    <section className="panel-section">
      <div className="section-title">可执行动作</div>
      <div className="actions-row">
        {actions.length === 0 ? <p className="muted">当前没有人类可执行动作。</p> : null}
        {actions.map((action) => (
          <button key={action.action_id} disabled={loading} onClick={() => onAction(action.action_id)}>
            {action.label}
          </button>
        ))}
      </div>
      <button className="secondary-button" disabled={loading} onClick={onStepAi}>
        调试：推进 AI 一步
      </button>
    </section>
  );
}

