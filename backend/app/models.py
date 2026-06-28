from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


Role = Literal["zhu", "zhong", "fan", "nei"]
Phase = Literal["judge", "draw", "play", "discard", "response", "game_over"]
CardName = Literal[
    "sha",
    "shan",
    "tao",
    "wuzhongshengyou",
    "guohechaiqiao",
    "shunshouqianyang",
    "jiedaosharen",
    "nanmanruqin",
    "wanjianqifa",
    "taoyuanjieyi",
    "wugufengdeng",
    "juedou",
    "wuxiekeji",
    "lebusishu",
    "shandian",
    "zhugeliannu",
    "qinggangjian",
    "cixiongshuanggujian",
    "hanbingjian",
    "qinglongyanyuedao",
    "zhangbashemao",
    "guanshifu",
    "fangtianhuaji",
    "qilingong",
    "baguazhen",
    "renwangdun",
    "jueying",
    "dilu",
    "zhuahuangfeidian",
    "dawan",
    "chitu",
    "zixing",
]


class AIConfig(BaseModel):
    name: str = "AI"
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model: str = "qwen"
    temperature: float = 0.2


class Card(BaseModel):
    id: str
    name: CardName
    suit: str
    rank: str


class Action(BaseModel):
    action_id: str
    type: str
    card_id: str | None = None
    card_name: CardName | None = None
    target_player_id: str | None = None
    secondary_target_player_id: str | None = None
    target_card_ids: list[str] | None = None
    target_card_names: list[CardName] | None = None
    label: str


class PendingResponse(BaseModel):
    type: Literal["respond_shan", "respond_sha", "dying_tao", "discard", "wuxie"]
    player_id: str
    source_player_id: str | None = None
    origin_player_id: str | None = None
    target_player_id: str | None = None
    secondary_target_player_id: str | None = None
    card_id: str | None = None
    card_name: CardName | None = None
    effect_type: str | None = None
    target_player_ids: list[str] | None = None
    remaining_player_ids: list[str] | None = None
    queue_player_ids: list[str] | None = None
    responded_player_ids: list[str] | None = None
    required_count: int | None = None


class Equipment(BaseModel):
    weapon: Card | None = None
    armor: Card | None = None
    attack_horse: Card | None = None
    defense_horse: Card | None = None


class Player(BaseModel):
    id: str
    name: str
    is_human: bool
    role: Role
    role_public: bool = False
    hp: int = 4
    max_hp: int = 4
    alive: bool = True
    hand: list[Card] = Field(default_factory=list)
    hand_count: int = 0
    used_sha_this_turn: bool = False
    equipment: Equipment = Field(default_factory=Equipment)
    judgment_area: list[Card] = Field(default_factory=list)
    ai_config: AIConfig | None = None


class GameState(BaseModel):
    game_id: str
    players: list[Player]
    ai_timeout_seconds: int = 30
    deck: list[Card] = Field(default_factory=list)
    discard_pile: list[Card] = Field(default_factory=list)
    current_player_index: int = 0
    phase: Phase = "draw"
    pending_response: PendingResponse | None = None
    round: int = 1
    recent_events: list[str] = Field(default_factory=list)
    winner: str | None = None
    legal_actions: list[Action] = Field(default_factory=list)

    @property
    def deck_count(self) -> int:
        return len(self.deck)

    @property
    def discard_count(self) -> int:
        return len(self.discard_pile)


class CreateGameRequest(BaseModel):
    human_name: str = "Human"
    ai_players: list[AIConfig]
    ai_timeout_seconds: int = 30
    seed: int | None = None

    @field_validator("ai_timeout_seconds", mode="before")
    @classmethod
    def validate_ai_timeout_seconds(cls, value: object) -> int:
        try:
            if isinstance(value, bool):
                return 30
            timeout = int(float(value)) if value is not None else 30
        except (TypeError, ValueError):
            return 30
        return timeout if 10 <= timeout <= 120 else 30


class SubmitActionRequest(BaseModel):
    action_id: str
