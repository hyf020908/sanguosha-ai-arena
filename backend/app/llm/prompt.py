from __future__ import annotations

from app.game.rules import objective_hint, role_policy
from app.models import Action, GameState, Player


SYSTEM_PROMPT = (
    "You are an AI player in a simplified Sanguosha game. "
    "Only roles shown in public_players are known; role='unknown' means hidden and must be inferred from behavior. "
    "Follow your role objective and role_policy strictly. "
    "Never choose an action that violates role_policy.forbidden. "
    "If legal_actions contains play_sha, choose a play_sha action unless a listed role_policy rule forbids it. "
    "If legal_actions contains respond_shan, choose respond_shan. "
    "If legal_actions contains dying_tao, choose dying_tao. "
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
        "pending_response": state.pending_response.model_dump() if state.pending_response else None,
        "recent_events": state.recent_events[-8:],
        "legal_actions": [action.model_dump(exclude_none=True) for action in legal_actions],
        "objective_hint": objective_hint(player.role),
        "role_policy": role_policy(player.role),
        "decision_guidance": [
            "公开主公是确定信息；unknown 身份不能当作已知身份，只能结合 recent_events 推理。",
            "使用杀时先判断每个目标是否符合你的身份目标，再选择最有利目标。",
            "如果多个攻击目标都合理，优先攻击当前体力更低、对己方目标威胁更高的玩家。",
            "不要因为看不到身份就机械结束阶段；有合理攻击目标时应积极行动。",
        ],
    }
