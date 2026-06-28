import { useEffect, useState } from 'react';
import { createGame, gameStreamUrl, submitAction } from './api/client';
import { GameBoard } from './components/GameBoard';
import { GameSetup } from './components/GameSetup';
import type { AIConfig, GameState } from './types';

export default function App() {
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!gameId) {
      return undefined;
    }
    const source = new EventSource(gameStreamUrl(gameId));
    source.addEventListener('state', (event) => {
      try {
        setState(JSON.parse((event as MessageEvent).data) as GameState);
      } catch {
        setError('实时状态解析失败');
      }
    });
    source.onerror = () => {
      setError('实时状态连接中断，仍可手动操作刷新');
    };
    return () => {
      source.close();
    };
  }, [gameId]);

  async function run<T>(task: () => Promise<T>): Promise<T | null> {
    setLoading(true);
    setError(null);
    try {
      return await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败');
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(humanName: string, aiPlayers: AIConfig[], aiTimeoutSeconds: number) {
    const result = await run(() => createGame(humanName, aiPlayers, aiTimeoutSeconds));
    if (result) {
      setGameId(result.game_id);
      setState(result.state);
    }
  }

  async function handleAction(actionId: string) {
    if (!gameId) {
      return;
    }
    const result = await run(() => submitAction(gameId, actionId));
    if (result) {
      setState(result);
    }
  }

  return (
    <div className="app-root">
      {error ? <div className="error-banner">{error}</div> : null}
      {state ? (
        <GameBoard
          state={state}
          loading={loading}
          onAction={handleAction}
          onNewGame={() => {
            setGameId(null);
            setState(null);
          }}
        />
      ) : (
        <GameSetup onCreate={handleCreate} loading={loading} />
      )}
    </div>
  );
}
