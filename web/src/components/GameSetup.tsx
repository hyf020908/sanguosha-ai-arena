import { useMemo, useState } from 'react';
import type { AIConfig } from '../types';

interface Props {
  onCreate: (humanName: string, aiPlayers: AIConfig[]) => Promise<void>;
  loading: boolean;
}

const defaultAi = (index: number): AIConfig => ({
  name: `AI-${index + 1}`,
  base_url: 'http://localhost:8000/v1',
  api_key: 'EMPTY',
  model: 'qwen',
  temperature: 0.2
});

export function GameSetup({ onCreate, loading }: Props) {
  const [humanName, setHumanName] = useState('Human');
  const [aiCount, setAiCount] = useState(3);
  const [aiPlayers, setAiPlayers] = useState<AIConfig[]>([defaultAi(0), defaultAi(1), defaultAi(2)]);

  const visibleAiPlayers = useMemo(() => aiPlayers.slice(0, aiCount), [aiPlayers, aiCount]);

  function changeAiCount(value: number) {
    const next = Math.min(5, Math.max(1, value));
    setAiCount(next);
    setAiPlayers((current) => {
      const copy = [...current];
      while (copy.length < next) {
        copy.push(defaultAi(copy.length));
      }
      return copy;
    });
  }

  function updateAi(index: number, patch: Partial<AIConfig>) {
    setAiPlayers((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  return (
    <section className="setup-shell">
      <div className="setup-header">
        <p className="eyebrow">v0.1 简化身份局</p>
        <h1>sanguosha-ai-arena</h1>
        <p>人与 AI 同桌进行一局只包含杀、闪、桃的简化身份局。</p>
      </div>

      <div className="setup-grid">
        <div className="form-block">
          <label>
            人类玩家名称
            <input value={humanName} onChange={(event) => setHumanName(event.target.value)} />
          </label>
          <label>
            AI 数量
            <select value={aiCount} onChange={(event) => changeAiCount(Number(event.target.value))}>
              {[1, 2, 3, 4, 5].map((count) => (
                <option key={count} value={count}>
                  {count} 个 AI
                </option>
              ))}
            </select>
          </label>
          <button className="primary-button" disabled={loading} onClick={() => onCreate(humanName, visibleAiPlayers)}>
            {loading ? '创建中...' : '创建新游戏'}
          </button>
        </div>

        <div className="ai-configs">
          {visibleAiPlayers.map((ai, index) => (
            <div className="ai-config" key={index}>
              <div className="config-title">{ai.name || `AI-${index + 1}`}</div>
              <label>
                名称
                <input value={ai.name} onChange={(event) => updateAi(index, { name: event.target.value })} />
              </label>
              <label>
                base_url
                <input value={ai.base_url} onChange={(event) => updateAi(index, { base_url: event.target.value })} />
              </label>
              <label>
                api_key
                <input
                  type="password"
                  value={ai.api_key}
                  onChange={(event) => updateAi(index, { api_key: event.target.value })}
                />
              </label>
              <label>
                model
                <input value={ai.model} onChange={(event) => updateAi(index, { model: event.target.value })} />
              </label>
              <label>
                temperature
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={ai.temperature ?? 0.2}
                  onChange={(event) => updateAi(index, { temperature: Number(event.target.value) })}
                />
              </label>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

