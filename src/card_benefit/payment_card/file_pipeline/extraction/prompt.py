"""청크 한 개를 온톨로지 v1 형식으로 추출하도록 요청하는 프롬프트."""

from __future__ import annotations

import json
from typing import Literal, get_args, get_origin

from .schema import ALLOWED_RELATIONS, Benefit, Condition, Extraction, Limit, Relation, Target, TargetKind


EXAMPLE_OUTPUT = {
    "schema_ver": "ONTOLOGY_V1",
    "benefits": [{
        "id": "b1",
        "name": "식사 할인",
        "method": "DISCOUNT",
        "rate": "5%",
        "amount": "3만원 이상",
        "evidence": [{"text": "식사 결제는 5% 할인되며"}],
    }],
    "conditions": [{
        "id": "c1",
        "text": "3만원 이상 결제",
        "kind": "SPEND_REQ",
        "min_amount": 30000,
        "evidence": [{"text": "3만원 이상 결제 시 적용됩니다"}],
    }],
    "limits": [{
        "id": "l1",
        "text": "월 할인 한도는 5천원",
        "period": "MONTH",
        "amount": 5000,
        "unlimited": False,
        "shared": False,
        "evidence": [{"text": "월 할인 한도는 5천원"}],
    }],
    "targets": [{
        "id": "t1",
        "text": "식사 결제",
        "kind": "OTHER",
        "evidence": [{"text": "식사 결제"}],
    }],
    "relations": [
        {
            "source": "b1",
            "target": "c1",
            "type": "HAS_CONDITION",
            "evidence": [{"text": "3만원 이상 결제 시 적용됩니다"}],
        },
        {
            "source": "b1",
            "target": "l1",
            "type": "HAS_LIMIT",
            "evidence": [{"text": "월 할인 한도는 5천원"}],
        },
        {
            "source": "b1",
            "target": "t1",
            "type": "APPLIES_TO",
            "evidence": [{"text": "식사 결제는 5% 할인되며"}],
        },
    ],
}

# Description text only; enum values always come from schema.py Literal annotations.
ENUM_DESCRIPTIONS = {
    "ONTOLOGY_V1": "현재 온톨로지 스키마 버전",
    "DISCOUNT": "할인",
    "CASHBACK": "청구 시 현금성 적립",
    "POINT": "포인트 적립",
    "SPEND_REQ": "전월 실적·결제 기준 금액 조건",
    "EXCLUDE": "실적·혜택 제외 항목",
    "USAGE": "이용 방식/횟수 조건",
    "PAYMENT": "결제 수단/방식",
    "MERCHANT": "가맹점 조건 또는 대상",
    "OTHER": "그 밖의 조건 또는 대상",
    "TXN": "거래 1건 기준",
    "DAY": "일 한도",
    "MONTH": "월 한도",
    "YEAR": "연 한도",
    "UNKNOWN": "기간을 알 수 없음",
    "INDUSTRY": "업종 대상",
    "CHANNEL": "결제 채널 대상",
    "SERVICE": "서비스 대상",
    "HAS_CONDITION": "혜택에 조건을 연결",
    "HAS_LIMIT": "혜택에 한도를 연결",
    "APPLIES_TO": "혜택이 적용되는 대상을 연결",
    "EXCLUDES": "혜택에서 제외되는 대상을 연결",
    "MUTUALLY_EXCLUSIVE": "혜택 간 중복 불가 관계",
}


def _literal_values(annotation: object) -> list[str]:
    """타입 표기 안에 들어 있는 Literal 값을 모은다(선택 타입 포함)."""
    if get_origin(annotation) is Literal:
        return [str(value) for value in get_args(annotation)]
    values: list[str] = []
    for argument in get_args(annotation):
        values.extend(_literal_values(argument))
    return values


def _model_fields(model: type) -> str:
    lines = []
    for name, field in model.model_fields.items():
        requirement = "필수" if field.is_required() else "선택"
        enums = _literal_values(field.annotation)
        suffix = f"; 허용값: {', '.join(enums)}" if enums else ""
        lines.append(f"- {name}: {requirement}{suffix}")
    return "\n".join(lines)


def _enum_values(annotation: object) -> list[str]:
    if get_origin(annotation) is Literal:
        return [str(value) for value in get_args(annotation)]
    return [value for arg in get_args(annotation) for value in _enum_values(arg)]


def enum_values_from_schema() -> set[str]:
    """모든 스키마 모델의 Literal 필드에서 enum 값을 수집한다."""
    values = set()
    for model in (Extraction, Benefit, Condition, Limit, Target, Relation):
        for field in model.model_fields.values():
            values.update(_enum_values(field.annotation))
    return values


def _enum_summary() -> str:
    lines = [f"- {value}: {ENUM_DESCRIPTIONS[value]}" for value in sorted(enum_values_from_schema())]
    return "\n".join(lines)


def build_prompt(chunk: dict) -> str:
    """LLM에 전달할 JSON 출력 지시와 청크 원문을 만든다."""
    schema_fields = "\n\n".join((
        f"Benefit:\n{_model_fields(Benefit)}",
        f"Condition:\n{_model_fields(Condition)}",
        f"Limit:\n{_model_fields(Limit)}",
        f"Target:\n{_model_fields(Target)}",
        f"Relation:\n{_model_fields(Relation)}",
    ))
    relation_pairs = ", ".join(f"{name}: {source}→{target}"
                                for name, (source, target) in ALLOWED_RELATIONS.items())
    target_kinds = ", ".join(get_args(TargetKind))
    example_json = json.dumps(EXAMPLE_OUTPUT, ensure_ascii=False, indent=2)
    return f"""카드 혜택 청크에서 혜택, 조건, 한도, 대상, 관계를 추출하세요.
원문에 없는 내용을 추측하지 마세요. 모든 엔티티와 관계의 evidence에는 원문 그대로의 인용문을 하나 이상 넣으세요.
evidence는 반드시 객체의 목록: 문자열이나 문자열 목록은 안 됨
id는 예시처럼 목록별 영문 접두사와 순번을 사용하세요: Benefit은 b1, b2; Condition은 c1, c2; Limit은 l1, l2; Target은 t1, t2. 의미 기반 이름은 id로 쓰지 마세요.
id에는 ASCII 영문자, 숫자, 밑줄(_), 하이픈(-)만 허용합니다. 한글과 공백은 쓰지 말고 1~64자로 만드세요. 전체 엔티티에서 id는 서로 달라야 합니다.
관계 source와 target에는 해당 엔티티의 id를 그대로 복사하세요.
관계는 아래 허용 쌍만 사용하고, 자기 자신을 가리키거나 존재하지 않는 id를 참조하지 마세요.
{relation_pairs}
출력은 설명이나 마크다운 없이 JSON 객체만 반환하세요. 위치 숫자는 출력하지 마세요.
최상위 키는 schema_ver(값 ONTOLOGY_V1), benefits, conditions, limits, targets, relations입니다.

출력 JSON 예시 (가상의 짧은 원문을 바탕으로 한 예시):
{example_json}

필드와 허용값 (필수/선택 필드는 스키마 기준):
{schema_fields}

**모든 enum 허용값과 뜻 (목록 밖의 값을 만들지 마세요. 확신이 없으면 해당 enum에 OTHER가 있을 때는 OTHER를 쓰고, 없으면 항목을 생략하세요):**
{_enum_summary()}

추출 규칙:
- CHANNEL 은 Target(대상)의 kind 전용 값이다. Condition(조건)의 kind 에는 쓰지 말고, 온라인/오프라인·앱 결제 같은 채널성 조건은 PAYMENT 또는 USAGE 로, 가맹점 조건은 MERCHANT 로, 해당하지 않으면 OTHER 로 분류하라.
- Limit.amount 는 정수 타입이므로 금액은 원, 횟수는 횟수 단위로 환산한 숫자만 쓰세요. 만원·천원·억 등의 금액 단위는 원 단위 정수로 환산하세요(예: 3만원 → 30000). 숫자로 환산할 수 없거나 '무제한'·구간 표·비율이면 amount는 null로 두고 원문 표현은 evidence에 남기세요. Condition.amount는 원문 문자열을 허용하지만 Limit.amount에는 문자열을 넣지 마세요.
- Target.kind 허용값은 {target_kinds}뿐입니다. PAYMENT, USAGE, SPEND_REQ, EXCLUDE는 Condition 전용이므로 Target.kind에 쓰지 마세요. 결제수단·카드 종류 같은 대상은 해당하는 Target 값 또는 OTHER로 분류하세요.
- evidence의 text는 청크 원문에서 연속된 구간을 한 글자도 바꾸지 말고 그대로 복사하세요. 요약, 줄임표, 재서술을 금지하며 공백과 문장부호도 그대로 유지하세요.
- 인용문은 가능한 한 짧고 항목을 뒷받침하는 한 구간으로 쓰고, 한 인용문에 여러 문장을 이어 붙이지 마세요.
- 같은 인용문이 청크 안에 두 번 이상 나오지 않도록, 한 문장 안에서 해당 항목에만 해당하는 금액·업종명·혜택명 같은 구별되는 단어를 가능한 한 포함해 인용문을 고르세요.
- 한 청크에서 추출 항목이 지나치게 많아지지 않게 하고, 중복되거나 같은 문장에서 나온 항목은 합치세요.
- 혜택 문장에 직접 붙은 한도는 그 혜택에 연결하세요.
- 여러 혜택이 함께 쓰는 통합 한도는 Limit 하나를 만들어 여러 혜택이 같은 Limit을 참조하게 하고 shared=true로 표시하세요.
- 품목 택1은 Benefit 하나에 여러 Target을 연결하고 선택 표현을 원문에 남기세요.
- 할인/적립 방식 택1은 Benefit.method=None으로 두고 선택 조건을 Condition에 기록하세요.
- 전월 실적 제외 목록은 목록 전체 문구를 보존한 Condition(kind=EXCLUDE) 하나로 기록하세요.
- 혜택에서 제외되는 가맹점/업종이 명확한 경우에만 EXCLUDES를 사용하세요.
- 표에서 분리된 한도 값/라벨 등 확정되지 않은 연결은 규칙으로 추정하지 마세요. 원문에 있는 그대로만 기록하고, 확실하지 않으면 연결하지 마세요.

청크 메타데이터:
page_no={chunk['page_no']}
start_pos={chunk['start_pos']}
청크 원문:
{chunk['text']}"""
