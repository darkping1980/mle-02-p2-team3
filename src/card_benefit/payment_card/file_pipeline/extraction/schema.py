"""온톨로지 v1의 추출 데이터 구조. LLM이 채우는 모양이며, 위치 숫자는 받지 않는다.

엔티티는 Benefit(혜택), Condition(조건), Limit(한도), Target(대상) 4개이고, 모든 항목은 원문 인용문(Quote)을 1개 이상 가진다.
관계는 Relation으로 두 엔티티의 id를 잇는다. 허용하는 연결 쌍은 ALLOWED_RELATIONS에서만 정한다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VER = "ONTOLOGY_V1"

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]

ConditionKind = Literal["SPEND_REQ", "EXCLUDE", "USAGE", "PAYMENT", "MERCHANT", "OTHER"]
LimitPeriod = Literal["TXN", "DAY", "MONTH", "YEAR", "UNKNOWN"]
TargetKind = Literal["MERCHANT", "INDUSTRY", "CHANNEL", "SERVICE", "OTHER"]
RelationType = Literal["HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO", "EXCLUDES", "MUTUALLY_EXCLUSIVE"]

# 관계 유형마다 허용하는 (출발, 도착) 엔티티 종류
ALLOWED_RELATIONS: dict[str, tuple[str, str]] = {
    "HAS_CONDITION": ("Benefit", "Condition"),
    "HAS_LIMIT": ("Benefit", "Limit"),
    "APPLIES_TO": ("Benefit", "Target"),
    "EXCLUDES": ("Benefit", "Target"),
    "MUTUALLY_EXCLUSIVE": ("Benefit", "Benefit"),   # "장기할부 청구할인과 중복 제공 안됨"
}


class _Strict(BaseModel):
    # 알 수 없는 필드(특히 start_pos, end_pos 같은 위치 값)는 거부한다.
    model_config = ConfigDict(extra="forbid")


class Quote(_Strict):
    text: str = Field(min_length=1)


class _Entity(_Strict):
    id: Id
    evidence: list[Quote] = Field(min_length=1)


BenefitMethod = Literal["DISCOUNT", "CASHBACK", "POINT"]   # 할인, 청구 시 적립(현금성), 포인트(하나머니 등)


class Benefit(_Entity):
    name: str = Field(min_length=1)
    method: BenefitMethod | None = None   # 할인/적립 구분. 원문에 "할인 또는 적립 택1"이면 None으로 두고 Condition에 적는다
    rate: str | None = None      # 원문 표기 그대로 (예: "5%", "리터당 50원", "0.5%")
    amount: str | None = None    # 원문 표기 그대로 (예: "3만원 이상")


class Condition(_Entity):
    text: str = Field(min_length=1)
    kind: ConditionKind
    min_amount: int | None = Field(default=None, ge=0)   # 실적·결제 기준 금액(원). "30만원 이상" -> 300000


class Limit(_Entity):
    text: str = Field(min_length=1)    # 원문 표기 그대로 (예: "월 할인한도 5천원")
    period: LimitPeriod
    amount: int | None = Field(default=None, ge=0)   # 금액·횟수. 원문에 숫자가 있을 때만
    unlimited: bool = False   # "할인한도 제한 없음"
    shared: bool = False      # "통합 월 2회"처럼 여러 혜택·회원이 나눠 쓰는 한도

    @model_validator(mode="after")
    def check_amount_or_unlimited(self) -> "Limit":
        if self.unlimited and self.amount is not None:
            raise ValueError("unlimited 한도는 amount를 가질 수 없습니다")
        return self


class Target(_Entity):
    text: str = Field(min_length=1)
    kind: TargetKind


class Relation(_Strict):
    source: Id
    target: Id
    type: RelationType
    evidence: list[Quote] = Field(min_length=1)


class Extraction(_Strict):
    schema_ver: Literal["ONTOLOGY_V1"] = SCHEMA_VER
    benefits: list[Benefit] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    limits: list[Limit] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_ids_and_relations(self) -> "Extraction":
        kinds: dict[str, str] = {}
        for kind, items in (("Benefit", self.benefits), ("Condition", self.conditions),
                            ("Limit", self.limits), ("Target", self.targets)):
            for item in items:
                if item.id in kinds:
                    raise ValueError(f"id가 겹칩니다: {item.id}")
                kinds[item.id] = kind
        for rel in self.relations:
            if rel.source not in kinds or rel.target not in kinds:
                raise ValueError(f"관계가 없는 id를 가리킵니다: {rel.source} -> {rel.target}")
            if rel.source == rel.target:
                raise ValueError(f"관계가 자기 자신을 가리킵니다: {rel.source}")
            want_from, want_to = ALLOWED_RELATIONS[rel.type]
            if kinds[rel.source] != want_from or kinds[rel.target] != want_to:
                raise ValueError(f"{rel.type}은 {want_from}->{want_to}만 허용합니다: {rel.source} -> {rel.target}")
        return self


def all_quotes(extraction: Extraction) -> list[str]:
    """추출 결과의 모든 인용문. 위치 변환 검사에 쓴다."""
    quotes: list[str] = []
    for group in (extraction.benefits, extraction.conditions, extraction.limits, extraction.targets, extraction.relations):
        for item in group:
            quotes.extend(q.text for q in item.evidence)
    return quotes
