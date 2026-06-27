import { useState } from 'react';
import { createGame, stepAi, submitAction } from './api/client';
import { GameBoard } from './components/GameBoard';
import { GameSetup } from './components/GameSetup';
import type { AIConfig, GameState } from './types';

export default function App() {
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  async function handleCreate(humanName: string, aiPlayers: AIConfig[]) {
    const result = await run(() => createGame(humanName, aiPlayers));
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

  async function handleStepAi() {
    if (!gameId) {
      return;
    }
    const result = await run(() => stepAi(gameId));
    if (result) {
      setState(result.state);
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
          onStepAi={handleStepAi}
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

