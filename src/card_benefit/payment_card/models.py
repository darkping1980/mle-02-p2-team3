"""카드 상품 데이터 모델과 입력 검증."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

CARD_TYPES = ("CREDIT", "DEBIT")  # CREDIT: 신용카드, DEBIT: 체크카드


@dataclass
class NewCard:
    """등록할 카드 상품. 생성 시 필수값과 카드 종류를 검증한다.

    Raises:
        ValueError: 필수값이 비어 있거나 ``card_type`` 이 ``CARD_TYPES`` 에 없는 경우.
    """

    issuer: str
    card_name: str
    card_type: str

    def __post_init__(self) -> None:
        for name in ("issuer", "card_name", "card_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
            setattr(self, name, value.strip())
        if self.card_type not in CARD_TYPES:
            raise ValueError(f"card_type must be one of {', '.join(CARD_TYPES)}: {self.card_type}")


@dataclass
class Card:
    """DB에 등록된 카드 상품. ``card_benefit.card_product`` 한 행에 해당한다."""

    card_id: int
    issuer: str
    card_name: str
    card_type: str
    created_at: datetime
