import { useEffect, useMemo, useState } from 'react';
import type { AIConfig } from '../types';

interface Props {
  onCreate: (humanName: string, aiPlayers: AIConfig[], aiTimeoutSeconds: number) => Promise<void>;
  loading: boolean;
}

const defaultAi = (index: number): AIConfig => ({
  name: `AI-${index + 1}`,
  base_url: 'http://localhost:8000/v1',
  api_key: 'EMPTY',
  model: 'qwen',
  temperature: 0.2
});

const setupStorageKey = 'sanguosha-ai-arena.setup.v1';

interface SavedSetup {
  humanName: string;
  aiCount: number;
  aiTimeoutSeconds: string;
  aiPlayers: AIConfig[];
}

function loadSavedSetup(): SavedSetup {
  if (typeof window === 'undefined') {
    return defaultSetup();
  }
  try {
    const raw = window.localStorage.getItem(setupStorageKey);
    if (!raw) {
      return defaultSetup();
    }
    const parsed = JSON.parse(raw) as Partial<SavedSetup>;
    const aiCount = clampAiCount(Number(parsed.aiCount ?? 3));
    const aiPlayers = normalizeAiPlayers(parsed.aiPlayers, aiCount);
    return {
      humanName: typeof parsed.humanName === 'string' && parsed.humanName.trim() ? parsed.humanName : 'Human',
      aiCount,
      aiTimeoutSeconds: typeof parsed.aiTimeoutSeconds === 'string' ? parsed.aiTimeoutSeconds : '30',
      aiPlayers,
    };
  } catch {
    return defaultSetup();
  }
}

function defaultSetup(): SavedSetup {
  return {
    humanName: 'Human',
    aiCount: 3,
    aiTimeoutSeconds: '30',
    aiPlayers: [defaultAi(0), defaultAi(1), defaultAi(2)],
  };
}

function clampAiCount(value: number) {
  return Math.min(5, Math.max(1, Number.isFinite(value) ? Math.trunc(value) : 3));
}

function normalizeAiPlayers(value: unknown, aiCount: number): AIConfig[] {
  const source = Array.isArray(value) ? value : [];
  const normalized: AIConfig[] = source.slice(0, 5).map((item, index) => {
    const fallback = defaultAi(index);
    const ai = typeof item === 'object' && item !== null ? (item as Partial<AIConfig>) : {};
    return {
      name: typeof ai.name === 'string' ? ai.name : fallback.name,
      base_url: typeof ai.base_url === 'string' ? ai.base_url : fallback.base_url,
      api_key: typeof ai.api_key === 'string' ? ai.api_key : fallback.api_key,
      model: typeof ai.model === 'string' ? ai.model : fallback.model,
      temperature: typeof ai.temperature === 'number' && Number.isFinite(ai.temperature) ? ai.temperature : fallback.temperature,
    };
  });
  while (normalized.length < aiCount) {
    normalized.push(defaultAi(normalized.length));
  }
  return normalized;
}

export function GameSetup({ onCreate, loading }: Props) {
  const savedSetup = useMemo(() => loadSavedSetup(), []);
  const [humanName, setHumanName] = useState(savedSetup.humanName);
  const [aiCount, setAiCount] = useState(savedSetup.aiCount);
  const [aiTimeoutSeconds, setAiTimeoutSeconds] = useState(savedSetup.aiTimeoutSeconds);
  const [aiPlayers, setAiPlayers] = useState<AIConfig[]>(savedSetup.aiPlayers);

  const visibleAiPlayers = useMemo(() => aiPlayers.slice(0, aiCount), [aiPlayers, aiCount]);

  useEffect(() => {
    window.localStorage.setItem(
      setupStorageKey,
      JSON.stringify({
        humanName,
        aiCount,
        aiTimeoutSeconds,
        aiPlayers,
      })
    );
  }, [humanName, aiCount, aiTimeoutSeconds, aiPlayers]);

  function changeAiCount(value: number) {
    const next = clampAiCount(value);
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

  function normalizedAiTimeoutSeconds() {
    const parsed = Number(aiTimeoutSeconds);
    return Number.isFinite(parsed) && parsed >= 10 && parsed <= 120 ? Math.trunc(parsed) : 30;
  }

  return (
    <section className="setup-shell">
      <div className="setup-header">
        <p className="eyebrow">v0.2 标准牌型身份局</p>
        <h1>sanguosha-ai-arena</h1>
        <p>人与 AI 同桌进行一局包含基础牌、锦囊牌、装备牌和距离规则的身份局。</p>
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
          <label>
            AI 请求超时秒数
            <input
              type="number"
              min="10"
              max="120"
              step="1"
              value={aiTimeoutSeconds}
              onChange={(event) => setAiTimeoutSeconds(event.target.value)}
              onBlur={() => setAiTimeoutSeconds(String(normalizedAiTimeoutSeconds()))}
            />
          </label>
          <button
            className="primary-button"
            disabled={loading}
            onClick={() => onCreate(humanName, visibleAiPlayers, normalizedAiTimeoutSeconds())}
          >
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
