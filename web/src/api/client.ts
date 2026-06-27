import type { AIConfig, CreateGameResponse, GameState } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {})
    },
    ...options
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function createGame(humanName: string, aiPlayers: AIConfig[]): Promise<CreateGameResponse> {
  return request<CreateGameResponse>('/api/games', {
    method: 'POST',
    body: JSON.stringify({ human_name: humanName, ai_players: aiPlayers })
  });
}

export async function getGame(gameId: string): Promise<GameState> {
  return request<GameState>(`/api/games/${gameId}`);
}

export async function submitAction(gameId: string, actionId: string): Promise<GameState> {
  return request<GameState>(`/api/games/${gameId}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action_id: actionId })
  });
}

export async function stepAi(gameId: string): Promise<{ message: string; state: GameState }> {
  return request<{ message: string; state: GameState }>(`/api/games/${gameId}/step-ai`, {
    method: 'POST'
  });
}

