"""AI 추출 데이터 구조. LLM이 채우는 페이지 계층과 Python이 만드는 검증·통합 계층을 나눈다.

LLM은 원문 표기와 값만 내고, DB ID와 V6 조건식 트리는 만들지 않는다.
코드 필드는 V6 공통코드에 ``UNKNOWN`` 을 더한 값이며, 고르지 못한 값은 정규화에서 검토 대상이 된다.
금액과 횟수는 정수, 비율처럼 소수가 필요한 값은 ``Decimal`` 이고 원문 표기를 함께 둔다.

[등록 파이프라인에서의 위치] 2단계 "LLM 추출 → 검증"의 데이터 계약. Java의 DTO + Bean Validation에 해당한다.
    - LLM 계층(ExtractionModel 하위): PageExtraction ⊃ BenefitItem ⊃ RuleItem/LimitItem/ConditionItem/EvidenceQuote.
      TerraClient가 ``to_strict_json_schema(PageExtraction)`` 으로 응답 형식을 강제하고,
      ExtractionService._parse가 ``PageExtraction.model_validate`` 로 다시 검증한다(정의 밖 필드는 거부: extra="forbid").
    - Python 계층(BaseModel 하위): EvidenceCheck, ItemCheck, SourceRef, MergeInfo, MergedBenefit, MergedCondition.
      LLM이 아니라 extraction_service의 검증·통합 함수가 만든다.
이 모듈은 DB·LLM에 접근하지 않는다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, model_validator

SCHEMA_VER = "EXTRACT_SCHEMA_V3"     # V3: 규칙의 계산 방법·지급 단위 제거(2026-11-03 계산 구조 정리)
MERGE_VER = "MERGE_V1"

BnftType = Literal["DISCOUNT", "CASHBACK", "POINT", "FEE_WAIVER", "SERVICE", "INSTALLMENT", "ETC", "UNKNOWN"]
ValueUnit = Literal["PERCENT", "KRW", "UNIMILE", "MULTIPLIER", "UNKNOWN"]
# 이전 스키마(V2) 응답에만 있는 규칙 키. 저장된 응답·추출 원본을 다시 읽을 때 무시한다.
LEGACY_RULE_KEYS = ("calc_method_cd", "payout_unit_cd")
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
EvidenceSubject = Literal["BNFT", "RULE", "LIMIT", "COND", "TARGET", "REL", "APPLICABILITY"]

# LLM 스키마에는 숫자로만 보이게 한다. Pydantic 기본 표현은 문자열도 허용해 제공자 호환 범위가 좁아진다.
NumberValue = Annotated[Decimal, WithJsonSchema({"type": "number"})]


# region LLM 응답 계층 (strict JSON Schema로 LLM에 전달되는 구조)
class ExtractionModel(BaseModel):
    """LLM 계층 공통 설정. 정의하지 않은 필드는 거부한다."""

    model_config = ConfigDict(extra="forbid")


class EvidenceQuote(ExtractionModel):
    """원문 근거 1건. ``quote_txt`` 는 페이지 텍스트를 그대로 옮긴 문자열이다."""

    quote_txt: str = Field(description='페이지 텍스트에서 그대로 복사한 근거 문구. 요약하거나 고치지 않는다.')
    supports: EvidenceSubject = Field(description='근거 대상: BNFT 혜택, RULE 규칙, LIMIT 한도, COND 조건, TARGET 대상, REL 관계, APPLICABILITY 적용 대상·기간.')
    support_key: str | None = Field(default=None, description='근거가 뒷받침하는 대상의 키. RULE·LIMIT·COND는 해당 rule_key·limit_key·cond_key와 일치시키고 해당 없으면 null.')
    link_basis: LinkBasis = Field(description='값과 대상의 연결 근거: SAME_TEXT 같은 문장, TABLE_IMAGE 표 이미지의 행·열, NOT_SURE 불확실.')


class TargetItem(ExtractionModel):
    """혜택 대상 가맹점·업종."""

    target_type_cd: TargetType = Field(description='대상 유형: MERCHANT 가맹점, INDUSTRY 업종, CHANNEL 채널, SERVICE 서비스, UNKNOWN 미확정.')
    target_nm: str = Field(description='PDF 텍스트에 등장하는 가맹점·업종·서비스 이름을 그대로 복사한다.')


class ConditionItem(ExtractionModel):
    """조건 1건. 조건식 트리는 Python이 만든다."""

    cond_key: str = Field(description='조건을 식별하고 evidence.support_key에서 참조할 키.')
    cond_type_cd: CondType = Field(description='조건 유형: SPEND_REQ 실적 요구, SPEND_EXCL 실적 제외, BNFT_EXCL 혜택 제외, USAGE_REQ 이용 요구, PAYMENT_METHOD 결제수단, MERCHANT_RULE 가맹점 규칙, GRACE 유예, ETC 기타, UNKNOWN 미확정.')
    cond_basis_cd: CondBasis | None = Field(default=None, description='조건 기준: PREV_MONTH_SPEND 전월 실적, PREV_YEAR_SPEND 전년 실적, TXN_AMT 거래 금액, MONTH_USAGE 월 이용, ROLLING_MONTHS 연속 월, UNKNOWN 미확정. 기준이 없으면 null.')
    cond_min_amt: int | None = Field(default=None, description='조건 금액의 하한을 원 단위 정수로 기재하고 없으면 null.')
    cond_max_amt_excl: int | None = Field(default=None, description='조건 금액의 배타적 상한을 원 단위 정수로 기재하고 없으면 null.')
    negate_yn: bool = Field(default=False, description='해당 조건을 부정하거나 제외하는지 여부.')
    excl_raw_txt: str | None = Field(default=None, description='실적 또는 혜택에서 제외되는 항목의 원문 표기. 없으면 null.')
    cond_raw_txt: str = Field(description='조건을 설명하는 페이지 원문 표기.')
    scope: CondScope = Field(description='적용 범위: ALL_BENEFITS 전체, NAMED_BENEFITS 명시 혜택, THIS_BENEFIT 해당 혜택, UNKNOWN 불확실.')
    target_benefit_nms: list[str] = Field(default_factory=list, description='조건 적용 대상으로 명시된 혜택명 목록.')
    evidence: list[EvidenceQuote] = Field(description='이 조건의 cond_raw_txt를 포함하며 supports=COND, support_key=cond_key인 원문 근거 목록.')


class LimitItem(ExtractionModel):
    """횟수·금액 한도 1건. 공유 표현이 원문에 있을 때만 ``shared_scope_txt`` 를 채운다."""

    limit_key: str = Field(description='한도를 식별하고 rule.limit_keys와 evidence.support_key에서 참조할 키.')
    period_cd: LimitPeriod = Field(description='한도 기간: TXN 결제 1건, DAY 일, MONTH 월, YEAR 연, UNKNOWN 미확정.')
    cap_unit_cd: LimitUnit = Field(description='한도 단위: KRW 원, HANAMONEY 하나머니, COUNT 회, UNKNOWN 그 밖의 단위 또는 미확정. 환산하지 않는다.')
    limit_num: int | None = Field(default=None, description='한도 수치. 원·하나머니·횟수는 정수로 적고 확인할 수 없으면 null.')
    limit_raw_txt: str = Field(description='한도 수치와 관련된 원문 표기.')
    shared_scope_txt: str | None = Field(default=None, description='원문에 한도 공유 표현이 있을 때 그 범위의 원문. 없으면 null이며 값이 같다는 이유로 공유를 추정하지 않는다.')
    applies_to_benefit_nms: list[str] = Field(default_factory=list, description='한도가 적용되는 혜택의 이름 목록.')


class RuleItem(ExtractionModel):
    """혜택 값 1건. 값과 단위는 원문 인용과 대조하는 설명 값이며 보상액을 계산하지 않는다."""

    rule_key: str = Field(description='규칙을 식별하고 evidence.support_key에서 참조할 키.')
    value_num: NumberValue | None = Field(default=None, description='원문에 표시된 혜택 수치. 비율은 % 수치 그대로, 금액은 원 단위로 기록하며 비수치 혜택은 null. 보상액을 계산하지 않는다.')
    value_raw_txt: str = Field(description='혜택 값의 원문 표기. 수치로 표현할 수 없는 혜택도 원문 그대로 적는다.')
    value_unit_cd: ValueUnit | None = Field(default=None, description='값의 단위: PERCENT %, KRW 원, UNIMILE 유니마일, MULTIPLIER 배, UNKNOWN 단위 미확정. 비수치 혜택은 null.')
    min_txn_amt: int | None = Field(default=None, description='건당 최소 결제 금액을 원 단위 정수로 기록하며 없으면 null.')
    min_txn_raw_txt: str | None = Field(default=None, description='건당 최소 결제 금액의 원문 표기. 없으면 null.')
    conditions: list[ConditionItem] = Field(default_factory=list, description='이 규칙에 적용되는 조건 목록.')
    limit_keys: list[str] = Field(default_factory=list, description='이 규칙에 연결되는 한도의 limit_key 목록.')

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_keys(cls, data: Any) -> Any:
        """이전 스키마 응답의 계산 방법·지급 단위는 읽지 않는다. 새 응답 스키마에는 없다."""
        if isinstance(data, dict) and any(key in data for key in LEGACY_RULE_KEYS):
            return {key: value for key, value in data.items() if key not in LEGACY_RULE_KEYS}
        return data


class RelationItem(ExtractionModel):
    """혜택 간 관계 1건. 페이지를 넘을 수 있어 대상은 혜택명으로 적는다."""

    relation_key: str = Field(description='혜택 간 관계를 식별할 키.')
    rel_type_cd: RelType = Field(description='관계 유형: MUTUALLY_EXCLUSIVE 중복 불가, HIGHER_VALUE_WINS 높은 값 우선, FALLBACK_AFTER_CAP 한도 이후 대체, OVERRIDES 우선 적용, UNKNOWN 미확정.')
    to_benefit_nm: str = Field(description='관계의 대상 혜택 이름. 페이지를 넘을 수 있으므로 DB ID가 아닌 혜택명으로 기록한다.')
    trigger_limit_key: str | None = Field(default=None, description='관계가 특정 한도에 의해 발생하면 해당 limit_key, 아니면 null.')


class BenefitItem(ExtractionModel):
    """페이지에서 읽은 혜택 1건."""

    item_key: str = Field(description='페이지에서 추출한 혜택 항목의 키.')
    bnft_nm: str = Field(description='혜택 내용 문장에서 정한 혜택명. 제목과 내용이 다른 서비스를 가리키면 내용을 따른다.')
    bnft_type_cd: BnftType = Field(description='혜택 유형: DISCOUNT 할인, CASHBACK 캐시백, POINT 포인트, FEE_WAIVER 수수료 면제, SERVICE 서비스, INSTALLMENT 할부, ETC 기타, UNKNOWN 미확정.')
    is_common_candidate: bool = Field(default=False, description='공통 혜택 후보인지 여부.')
    no_condition_stated: bool = Field(default=False, description='혜택에 조건이 명시되지 않았는지 여부.')
    certainty: Certainty = Field(description='추출 판단의 확실성: HIGH 높음, LOW 낮음. 제목과 내용이 다른 서비스를 가리키면 LOW.')
    brand_txt: str | None = Field(default=None, description='혜택별 브랜드 원문. 없거나 불명확하면 null.')
    service_grade_txt: str | None = Field(default=None, description='혜택별 서비스 등급 원문. 없거나 불명확하면 null.')
    applicable_cards: list[str] = Field(default_factory=list, description='혜택 대상 카드의 원문 목록.')
    selection_service_txt: str | None = Field(default=None, description='선택 서비스의 원문. 없거나 불명확하면 null.')
    excluded_cards: list[str] = Field(default_factory=list, description='혜택에서 제외되는 카드의 원문 목록.')
    validity_period_txt: str | None = Field(default=None, description='혜택 제공 기간의 원문. 없거나 불명확하면 null.')
    targets: list[TargetItem] = Field(default_factory=list, description='혜택의 가맹점·업종·서비스 등 대상 목록.')
    rules: list[RuleItem] = Field(default_factory=list, description='혜택 값별 규칙 목록. 원문 수치와 비수치 혜택을 모두 포함한다.')
    limits: list[LimitItem] = Field(default_factory=list, description='혜택의 금액·횟수 한도 목록.')
    conditions: list[ConditionItem] = Field(default_factory=list, description='혜택에 적용되는 조건 목록.')
    relations: list[RelationItem] = Field(default_factory=list, description='다른 혜택과의 관계 목록. 원문에 없는 관계를 추정하지 않는다.')
    evidence: list[EvidenceQuote] = Field(default_factory=list, description='혜택·규칙·한도·대상·관계 및 적용 정보를 뒷받침하는 원문 인용 목록. 규칙과 한도는 각각 해당 키의 근거를 남긴다.')
    uncertainty_note: str | None = Field(default=None, description='추출 판단의 불확실성 또는 제목과 내용의 차이 설명. 없으면 null.')


class ProductMention(ExtractionModel):
    """페이지의 상품 정보. V6 상품은 사람이 등록하므로 원본 응답에만 남긴다."""

    product_nm: str | None = Field(default=None, description='페이지에 언급된 카드 상품명. 없으면 null.')
    issuer: str | None = Field(default=None, description='페이지에 언급된 발행사. 없으면 null.')
    card_kind_cd: Literal["CREDIT", "DEBIT"] | None = Field(default=None, description='카드 종류: CREDIT 신용카드, DEBIT 체크카드. 확인할 수 없으면 null.')
    brand_txts: list[str] = Field(default_factory=list, description='페이지에 언급된 브랜드 원문 목록.')
    annual_fee_txt: str | None = Field(default=None, description='연회비 원문 표기. 없으면 null.')
    issue_target_txt: str | None = Field(default=None, description='발급 대상 원문 표기. 없으면 null.')


class UnresolvedItem(ExtractionModel):
    """LLM이 판단을 보류한 문구."""

    raw_txt: str = Field(description='해석하거나 추출할 수 없어 판단을 보류한 원문 문구.')
    reason: str = Field(description='판단을 보류한 이유.')


class PageExtraction(ExtractionModel):
    """LLM 응답 1건. 페이지 1쪽에 대응한다."""

    page_no: int = Field(description='입력 PDF 페이지 번호.')
    page_role: PageRole = Field(description='페이지 역할: SUMMARY 요약, DETAIL 상세, NOTICE 유의사항, MIXED 혼합.')
    product: ProductMention | None = Field(default=None, description='페이지에 언급된 상품 정보. 없으면 null.')
    benefits: list[BenefitItem] = Field(default_factory=list, description='이 페이지의 추출 대상에서 확인한 혜택 목록.')
    card_conditions: list[ConditionItem] = Field(default_factory=list, description='이 페이지에서 확인한 카드 단위 조건 목록.')
    unresolved: list[UnresolvedItem] = Field(default_factory=list, description='해석하지 못하거나 이미지에서만 확인된 내용과 그 이유 목록.')
# endregion


# region Python 검증·통합 계층 (LLM 스키마에 포함되지 않음)
class EvidenceCheck(BaseModel):
    """근거 1건의 위치 확인 결과. 위치는 청크 원문 기준 1부터다."""

    quote_txt: str                    # 페이지 원문 인용
    supports: str                     # 근거 대상 종류
    support_key: str | None = None    # 근거 대상 키
    link_basis: str                   # 값과 대상의 연결 근거
    page_no: int                      # 원문 페이지 번호
    card_doc_chunk_id: str            # 원문 청크 식별자
    start_pos: int | None = None      # 청크 내 시작 위치(1부터)
    end_pos: int | None = None        # 청크 내 끝 위치

    @property
    def located(self) -> bool:
        return self.start_pos is not None


class ItemCheck(BaseModel):
    """항목 1건의 검증 결과. 값이 원문에 있는지와 값이 이 혜택의 값인지를 따로 판단한다."""

    value_check_cd: str = "OK"                                    # 원문 값 검증 코드
    link_check_cd: str = "TEXT_CONFIRMED"                         # 혜택 연결 검증 코드
    issues: list[str] = Field(default_factory=list)                # 검증 문제 목록
    evidence: list[EvidenceCheck] = Field(default_factory=list)    # 위치 확인된 근거


class SourceRef(BaseModel):
    """통합 결과가 온 페이지 항목."""

    page_no: int            # 출처 페이지 번호
    card_doc_chunk_id: str  # 출처 청크 식별자
    stg_item_seq: int       # 출처 staging 항목 순번


class MergeInfo(BaseModel):
    """문서 단위 통합 정보."""

    merge_ver: str = MERGE_VER                     # 통합 로직 버전
    item_key: str                                   # 통합 항목 키
    source_refs: list[SourceRef]                    # 통합 원천 참조
    source_pages: list[int]                        # 원천 페이지 목록
    conflicts: list[str] = Field(default_factory=list)  # 페이지 간 충돌


class MergedBenefit(BaseModel):
    """문서 단위로 통합한 혜택과 V6 계약 형태의 정제본."""

    merge: MergeInfo              # 문서 통합 정보
    check: ItemCheck               # 통합 혜택 검증 결과
    normalized: dict[str, Any]     # 등록용 정규화 데이터
    sql_check_cd: str              # 등록 계약 검사 코드


class MergedCondition(BaseModel):
    """문서 단위로 통합한 조건과 적용 대상."""

    merge: MergeInfo                     # 문서 통합 정보
    check: ItemCheck                      # 통합 조건 검증 결과
    scope_cd: str                         # 정규화된 적용 범위
    applies_to_item_keys: list[str]       # 적용 혜택 키 목록
    normalized: dict[str, Any]            # 등록용 정규화 데이터
    sql_check_cd: str                     # 등록 계약 검사 코드
# endregion
