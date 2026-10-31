"""AI 추출 데이터 구조. LLM이 채우는 페이지 계층과 Python이 만드는 검증·통합 계층을 나눈다.

LLM은 원문 표기와 값만 내고, DB ID와 V6 조건식 트리는 만들지 않는다.
코드 필드는 V6 공통코드에 ``UNKNOWN`` 을 더한 값이며, 고르지 못한 값은 정규화에서 검토 대상이 된다.
금액과 횟수는 정수, 비율처럼 소수가 필요한 값은 ``Decimal`` 이고 원문 표기를 함께 둔다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

SCHEMA_VER = "EXTRACT_SCHEMA_V1"
MERGE_VER = "MERGE_V1"

BnftType = Literal["DISCOUNT", "CASHBACK", "POINT", "FEE_WAIVER", "SERVICE", "INSTALLMENT", "ETC", "UNKNOWN"]
CalcMethod = Literal[
    "PERCENT_OF_TXN", "FIXED_PER_TXN", "UNITS_PER_AMOUNT", "MULTIPLY_EXTERNAL_POINTS", "FREE_SERVICE", "UNKNOWN",
]
ValueUnit = Literal["PERCENT", "KRW", "UNIMILE", "MULTIPLIER", "UNKNOWN"]
PayoutUnit = Literal["KRW", "HANAMONEY", "UNIMILE", "WALLET_POINT", "SERVICE", "UNKNOWN"]
LimitPeriod = Literal["TXN", "DAY", "MONTH", "YEAR", "UNKNOWN"]
LimitUnit = Literal["KRW", "HANAMONEY", "COUNT", "UNKNOWN"]
CondType = Literal[
    "SPEND_REQ", "SPEND_EXCL", "BNFT_EXCL", "USAGE_REQ", "PAYMENT_METHOD", "MERCHANT_RULE", "GRACE", "ETC", "UNKNOWN",
]
CondBasis = Literal["PREV_MONTH_SPEND", "PREV_YEAR_SPEND", "TXN_AMT", "MONTH_USAGE", "ROLLING_MONTHS", "UNKNOWN"]
TargetType = Literal["MERCHANT", "INDUSTRY", "CHANNEL", "SERVICE", "UNKNOWN"]
RelType = Literal["MUTUALLY_EXCLUSIVE", "HIGHER_VALUE_WINS", "FALLBACK_AFTER_CAP", "OVERRIDES", "UNKNOWN"]
PageRole = Literal["SUMMARY", "DETAIL", "NOTICE", "MIXED"]
Certainty = Literal["HIGH", "LOW"]
CondScope = Literal["ALL_BENEFITS", "NAMED_BENEFITS", "THIS_BENEFIT", "UNKNOWN"]
LinkBasis = Literal["SAME_TEXT", "TABLE_IMAGE", "NOT_SURE"]
EvidenceSubject = Literal["BNFT", "RULE", "LIMIT", "TARGET", "REL"]

# LLM 스키마에는 숫자로만 보이게 한다. Pydantic 기본 표현은 문자열도 허용해 제공자 호환 범위가 좁아진다.
NumberValue = Annotated[Decimal, WithJsonSchema({"type": "number"})]


class ExtractionModel(BaseModel):
    """LLM 계층 공통 설정. 정의하지 않은 필드는 거부한다."""

    model_config = ConfigDict(extra="forbid")


class EvidenceQuote(ExtractionModel):
    """원문 근거 1건. ``quote_txt`` 는 페이지 텍스트를 그대로 옮긴 문자열이다."""

    quote_txt: str
    supports: EvidenceSubject
    support_key: str | None = None
    link_basis: LinkBasis


class TargetItem(ExtractionModel):
    """혜택 대상 가맹점·업종."""

    target_type_cd: TargetType
    target_nm: str


class ConditionItem(ExtractionModel):
    """조건 1건. 조건식 트리는 Python이 만든다."""

    cond_key: str
    cond_type_cd: CondType
    cond_basis_cd: CondBasis | None = None
    cond_min_amt: int | None = None
    cond_max_amt_excl: int | None = None
    negate_yn: bool = False
    excl_raw_txt: str | None = None
    cond_raw_txt: str
    scope: CondScope
    target_benefit_nms: list[str] = Field(default_factory=list)
    evidence: list[EvidenceQuote]


class LimitItem(ExtractionModel):
    """횟수·금액 한도 1건. 공유 표현이 원문에 있을 때만 ``shared_scope_txt`` 를 채운다."""

    limit_key: str
    period_cd: LimitPeriod
    cap_unit_cd: LimitUnit
    limit_num: int | None = None
    limit_raw_txt: str
    shared_scope_txt: str | None = None
    applies_to_benefit_nms: list[str] = Field(default_factory=list)


class RuleItem(ExtractionModel):
    """계산 규칙 1건."""

    rule_key: str
    calc_method_cd: CalcMethod
    value_num: NumberValue | None = None
    value_raw_txt: str
    value_unit_cd: ValueUnit | None = None
    payout_unit_cd: PayoutUnit | None = None
    min_txn_amt: int | None = None
    conditions: list[ConditionItem] = Field(default_factory=list)
    limit_keys: list[str] = Field(default_factory=list)


class RelationItem(ExtractionModel):
    """혜택 간 관계 1건. 페이지를 넘을 수 있어 대상은 혜택명으로 적는다."""

    relation_key: str
    rel_type_cd: RelType
    to_benefit_nm: str
    trigger_limit_key: str | None = None


class BenefitItem(ExtractionModel):
    """페이지에서 읽은 혜택 1건."""

    item_key: str
    bnft_nm: str
    bnft_type_cd: BnftType
    is_common_candidate: bool = False
    no_condition_stated: bool = False
    certainty: Certainty
    targets: list[TargetItem] = Field(default_factory=list)
    rules: list[RuleItem] = Field(default_factory=list)
    limits: list[LimitItem] = Field(default_factory=list)
    conditions: list[ConditionItem] = Field(default_factory=list)
    relations: list[RelationItem] = Field(default_factory=list)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    uncertainty_note: str | None = None


class ProductMention(ExtractionModel):
    """페이지의 상품 정보. V6 상품은 사람이 등록하므로 원본 응답에만 남긴다."""

    product_nm: str | None = None
    issuer: str | None = None
    card_kind_cd: Literal["CREDIT", "DEBIT"] | None = None
    brand_txts: list[str] = Field(default_factory=list)
    annual_fee_txt: str | None = None
    issue_target_txt: str | None = None


class UnresolvedItem(ExtractionModel):
    """LLM이 판단을 보류한 문구."""

    raw_txt: str
    reason: str


class PageExtraction(ExtractionModel):
    """LLM 응답 1건. 페이지 1쪽에 대응한다."""

    page_no: int
    page_role: PageRole
    product: ProductMention | None = None
    benefits: list[BenefitItem] = Field(default_factory=list)
    card_conditions: list[ConditionItem] = Field(default_factory=list)
    unresolved: list[UnresolvedItem] = Field(default_factory=list)


class EvidenceCheck(BaseModel):
    """근거 1건의 위치 확인 결과. 위치는 청크 원문 기준 1부터다."""

    quote_txt: str
    supports: str
    support_key: str | None = None
    link_basis: str
    page_no: int
    card_doc_chunk_id: str
    start_pos: int | None = None
    end_pos: int | None = None

    @property
    def located(self) -> bool:
        return self.start_pos is not None


class ItemCheck(BaseModel):
    """항목 1건의 검증 결과. 값이 원문에 있는지와 값이 이 혜택의 값인지를 따로 판단한다."""

    value_check_cd: str = "OK"
    link_check_cd: str = "TEXT_CONFIRMED"
    issues: list[str] = Field(default_factory=list)
    evidence: list[EvidenceCheck] = Field(default_factory=list)


class SourceRef(BaseModel):
    """통합 결과가 온 페이지 항목."""

    page_no: int
    card_doc_chunk_id: str
    stg_item_seq: int


class MergeInfo(BaseModel):
    """문서 단위 통합 정보."""

    merge_ver: str = MERGE_VER
    item_key: str
    source_refs: list[SourceRef]
    source_pages: list[int]
    conflicts: list[str] = Field(default_factory=list)


class MergedBenefit(BaseModel):
    """문서 단위로 통합한 혜택과 V6 계약 형태의 정제본."""

    merge: MergeInfo
    check: ItemCheck
    normalized: dict[str, Any]
    sql_check_cd: str


class MergedCondition(BaseModel):
    """문서 단위로 통합한 조건과 적용 대상."""

    merge: MergeInfo
    check: ItemCheck
    scope_cd: str
    applies_to_item_keys: list[str]
    normalized: dict[str, Any]
    sql_check_cd: str
