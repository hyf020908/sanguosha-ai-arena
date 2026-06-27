from __future__ import annotations

from app.models import GameState


def public_state_for_human(state: GameState) -> dict:
    human = next((player for player in state.players if player.is_human), None)
    human_id = human.id if human else ""

    players: list[dict] = []
    for player in state.players:
        role_visible = player.role_public or player.id == human_id
        players.append(
            {
                "id": player.id,
                "name": player.name,
                "is_human": player.is_human,
                "role": player.role if role_visible else "unknown",
                "role_public": player.role_public,
                "hp": player.hp,
                "max_hp": player.max_hp,
                "alive": player.alive,
                "hand": [card.model_dump() for card in player.hand] if player.id == human_id else [],
                "hand_count": len(player.hand),
                "used_sha_this_turn": player.used_sha_this_turn,
            }
        )

    actor_is_human = False
    if state.pending_response:
        actor = next((player for player in state.players if player.id == state.pending_response.player_id), None)
        actor_is_human = bool(actor and actor.is_human)
    elif not state.winner and state.players:
        actor_is_human = state.players[state.current_player_index].is_human

    return {
        "game_id": state.game_id,
        "players": players,
        "deck_count": len(state.deck),
        "discard_count": len(state.discard_pile),
        "current_player_index": state.current_player_index,
        "phase": state.phase,
        "pending_response": state.pending_response.model_dump() if state.pending_response else None,
        "round": state.round,
        "recent_events": state.recent_events[-20:],
        "winner": state.winner,
        "legal_actions": [action.model_dump() for action in state.legal_actions] if actor_is_human else [],
    }
