from __future__ import annotations

from app.game.rules import objective_hint
from app.models import Action, GameState, Player


SYSTEM_PROMPT = (
    "You are an AI player in a simplified Sanguosha game. "
    "You must choose exactly one action_id from legal_actions. Return strict JSON only."
)


def compact_prompt(state: GameState, player: Player, legal_actions: list[Action]) -> dict:
    public_players = []
    for target in state.players:
        public_players.append(
            {
                "id": target.id,
                "name": target.name,
                "hp": target.hp,
                "max_hp": target.max_hp,
                "role": target.role if target.role_public or target.id == player.id else "unknown",
                "hand_count": len(target.hand),
                "alive": target.alive,
            }
        )
    return {
        "you": {
            "id": player.id,
            "role": player.role,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "hand": [{"id": card.id, "name": card.name} for card in player.hand],
        },
        "public_players": public_players,
        "phase": state.phase,
        "recent_events": state.recent_events[-8:],
        "legal_actions": [action.model_dump(exclude_none=True) for action in legal_actions],
        "objective_hint": objective_hint(player.role),
    }

