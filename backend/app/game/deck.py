from __future__ import annotations

import random
from itertools import cycle

from app.models import Card


SUITS = ["spade", "heart", "club", "diamond"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def build_deck(rng: random.Random) -> list[Card]:
    """生成 v0.1 牌堆；牌面字段只用于展示，不参与规则。"""
    names = ["sha"] * 30 + ["shan"] * 15 + ["tao"] * 10
    suit_rank = cycle((suit, rank) for suit in SUITS for rank in RANKS)
    cards: list[Card] = []
    for index, name in enumerate(names):
        suit, rank = next(suit_rank)
        cards.append(Card(id=f"c{index + 1}", name=name, suit=suit, rank=rank))
    rng.shuffle(cards)
    return cards

