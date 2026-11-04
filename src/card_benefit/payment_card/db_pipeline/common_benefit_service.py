"""브랜드 공통 문서 후보를 공통 혜택으로 등록하고 카드 적용 관계를 기록한다.

공통 혜택은 ``card_common_bnft`` 에 한 번만 저장하고 ``card_bnft`` 로 복제하지 않는다. 카드 적용은
브랜드·등급·선택서비스와 원문 근거를 확인한 카드만 ``card_common_bnft_apply`` 에 기록한다.
식별자는 호출자가 근거를 검토해 제공한다. 자동 승인은 하지 않는다.
혜택 설명과 한도는 원문 인용만 모아 TEXT로 저장한다. 금액을 계산하거나 원문에 없는 표현을 만들지 않는다.
(``card_bnft`` 는 2026-11-04에 ``card_product_item`` 으로 전환되었다. SQL find_benefit은 card_product_item을 읽는다.)

[등록 파이프라인에서의 위치] 3단계(브랜드 공통 안내서, doc_type_cd='BRAND_SERVICE').
    1단계 RegisterService._link도 이 모듈의 ensure_common / link_doc으로 공통서비스·문서 연결을 만든다.

처리 흐름
    register_run(run_id, identities)   [1트랜잭션]
        정합성 기준선 → candidates(list_candidates + attach_normalized) → 후보마다 _register_candidate
        → 신규 정합성 위반이면 rollback → (커밋 후) 임베딩
        _register_candidate: 판정 → common_of_doc(문서의 공통서비스 1개) → 브랜드·등급·선택서비스·기간 확인
            → benefit_code(문서 계열 + 검토 식별자)로 bnft_cd 생성 → 근거 확인(_evidence_ids)
            → card_common 잠금 → 기존 행 없음: INSERT / 같음: UNCHANGED / 이전 판에서 왔음: UPDATE / 그 외: CHANGE_REVIEW
    apply_run(card_id, run_id, identities)   [카드마다 1트랜잭션]
        card_product 잠금 → 후보마다 _apply_candidate: 대상·제외 카드, 브랜드·등급·선택서비스 옵션, 기간 근거 확인
        → 이미 등록된 card_common_bnft를 찾아 card_common_bnft_apply INSERT(ON CONFLICT DO NOTHING)

식별자와 중복 방지
    bnft_cd = "BRAND_" + SHA-256(doc_family_cd + "\\0" + 검토 식별자). 문서 버전·혜택명은 쓰지 않으므로
    개정판 문서에서도 같은 혜택은 같은 코드가 된다. (card_common_id, bnft_cd)가 같으면 새로 INSERT하지 않는다.
    card_common_bnft_id(PK)는 DB가 발급한다. 물리 FK 대신 v_card_integrity_issue·common_integrity_errors로
    등록 전후 정합성 위반 증가를 검사한다.

관련 테이블: card_common, card_common_doc, card_common_bnft, card_common_bnft_apply, card_product, card_product_doc,
            card_extr_stg, card_source_evidence, card_evidence_link(상품 근거 조회), card_product_item(동일 코드 확인)
SQL: common_benefit_repository.sql
호출하는 곳: benefit_main.py, register_service.py, common_auto_pipeline.py, product_benefit_service.py(Repository·함수),
            neo4j_dry_run.py(compare_brand_bnft), 그리고 GraphRAG 검색 코드(db_pipeline_origin_search)도 import한다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import re

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from .extraction_service import normalize_stored_run
from .unresolved_review import load_registry, links_for_candidate, unresolved_queue, verified_reviews_for_run


# region 문자열 비교·코드 생성·기간 해석 도우미 (DB 미사용)
def compact(value: str) -> str:
    """대소문자(casefold)와 공백을 무시하고 비교하기 위한 키."""
    return "".join(value.casefold().split())


def brand_key(value: str | None) -> str:
    """공통코드 UPI와 안내서의 UnionPay 표기를 같은 브랜드로 비교한다."""
    key = compact(value or '')
    return 'upi' if key in ('upi', 'unionpay', '유니온페이') else key


def benefit_code(family: str, identity: str) -> str:
    """문서 계열과 검토된 업무 식별자만 사용한다. 문서 버전과 혜택명은 사용하지 않는다."""
    if not family or not identity or len(identity) > 200:
        raise ValueError("문서 계열과 검토된 혜택 식별자가 필요합니다")
    key = (family + "\0" + identity).encode("utf-8")
    return "BRAND_" + hashlib.sha256(key).hexdigest().upper()


def quote_text(evidence: list[dict], supports: str) -> str | None:
    """같은 종류의 원문 인용을 순서대로 모은다. 공백만 정리하고 중복은 한 번만 쓴다."""
    quotes = [" ".join(item["quote_txt"].split()) for item in evidence
              if item.get("supports") == supports and item.get("quote_txt")]
    return " / ".join(dict.fromkeys(quotes)) or None


def period(raw: str | None):
    """``YYYY년 M월 D일 ~ (YYYY년) M월 D일`` 형식의 제공 기간을 ``(시작일, 종료일+1일)`` 로 해석한다.

    종료일은 포함 기준이라 다음 날을 배타 종료(bnft_valid_to_excl)로 돌려준다. 값이 없으면 ``(None, None)``.

    Raises:
        ValueError: 형식이 다르거나 종료가 시작보다 앞선 경우.
    """
    if raw is None or not raw.strip():
        return None, None
    # 끝의 "까지"는 종료일을 포함한다는 뜻이라 해석에 영향이 없다.
    match = re.fullmatch(r"\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*[~～-]\s*(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(?:까지)?\s*", raw)
    if not match:
        raise ValueError("제공 기간을 안전하게 해석할 수 없습니다")
    y, m, d, y2, m2, d2 = match.groups()
    start = date(int(y), int(m), int(d))
    end = date(int(y2 or y), int(m2), int(d2)) + timedelta(days=1)
    if end <= start:
        raise ValueError("제공 기간이 올바르지 않습니다")
    return start, end


# "이용기간 별도 표기한 경우 외에는 <기간>"(UnionPay), "기간이 (따로) 명시되지 않는/않은 한 <기간>"(Mastercard·Visa):
# 혜택에 별도 기간이 없을 때만 문서의 기본 기간이 적용된다.
DEFAULT_PERIOD_PREFIX = re.compile(
    r"\s*(?:이용\s*기간\s*별도\s*표기한\s*경우\s*외에는|기간\s*이\s*(?:따로\s*)?명시\s*되지\s*않(?:는|은)\s*한)\s*")
# 혜택 자신의 인용에 이런 표현이 있으면 별도 기간일 수 있어 기본 기간을 쓰지 않는다.
OWN_PERIOD_HINT = re.compile(r"\d{4}\s*년|\d{1,2}\s*월|\d{1,2}\s*\.\s*\d{1,2}|개월|기간|까지|부터")


def candidate_period(raw: dict):
    """후보의 제공 기간. 조건부 기본 기간은 혜택·규칙·한도 인용에 기간 표현이 없을 때만 적용한다."""
    text = raw.get('validity_period_txt')
    match = DEFAULT_PERIOD_PREFIX.match(text or '')
    if not match:
        return period(text)
    own = [item.get('quote_txt') or '' for item in raw.get('evidence', []) if item.get('supports') != 'APPLICABILITY']
    if any(OWN_PERIOD_HINT.search(quote) for quote in own):
        raise ValueError("혜택 원문에 별도 기간 표현이 있어 기본 제공 기간을 적용할 수 없습니다")
    return period(text[match.end():])


# 등급 표기 앞에 붙는 브랜드명. 안내서는 "Mastercard Platinum"처럼 브랜드와 등급을 함께 쓰기도 한다.
BRAND_PREFIXES = ('mastercard', 'visa', 'unionpay', '유니온페이', 'upi', 'americanexpress', 'amex')


def grade_key(value: str | None) -> str:
    """등급 비교 키. 앞의 브랜드명과 끝의 선택서비스 번호(01~04), 공백·밑줄을 지운다.

    예: "Mastercard Platinum", "Platinum04", 공통코드 PLATINUM은 모두 platinum이다.
    선택서비스 번호 자체는 ``service_type_of`` 가 선택서비스 표기로 따로 확인한다.
    """
    key = compact(value or '').replace('_', '')
    for prefix in BRAND_PREFIXES:
        if key.startswith(prefix) and len(key) > len(prefix):
            key = key[len(prefix):]
            break
    return re.sub(r'(?<=\D)0[1-4]$', '', key)


def service_type_of(selection: str | None) -> str | None:
    """선택서비스 번호 또는 등급 공통. 번호가 하나로 확인되지 않으면 ``None`` 이다."""
    if not selection:
        return "COMMON"
    codes = set(re.findall(r"(?<!\d)(0[1-4])(?!\d)", selection))
    return codes.pop() if len(codes) == 1 else None


def condition_quotes(norm: dict) -> list[str]:
    """공통 혜택에는 조건식 컬럼이 없어 조건 원문을 이용 조건 TEXT로 보존한다."""
    expression = norm.get("bnft_cond_expr") or {}
    return [" ".join(atom["cond_raw_txt"].split()) for branch in expression.get("branches", [])
            for atom in branch.get("atoms", []) if atom.get("cond_raw_txt")]


def common_texts(raw: dict, norm: dict) -> tuple[str | None, str | None]:
    """원문 인용으로 혜택 내용과 이용 조건 TEXT를 만든다."""
    evidence = raw.get("evidence", [])
    rule_txt = quote_text(evidence, "RULE") or quote_text(evidence, "BNFT")
    limits = [quote_text(evidence, "LIMIT"), *condition_quotes(norm)]
    return rule_txt, " / ".join(dict.fromkeys(item for item in limits if item)) or None
# endregion


@dataclass(frozen=True)
class Decision:
    """후보 1건의 판정. 공통 혜택 등록이면 ``card_id`` 는 ``None`` 이다."""
    card_id: int | None
    stg_id: str
    status: str
    reason: str
    bnft_cd: str | None = None
    card_bnft_id: str | None = None         # 같은 코드의 기존 BRAND_SERVICE 행. 수정하지 않는다.
    card_common_id: int | None = None
    card_common_bnft_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


def compare_brand_bnft(row: dict) -> tuple[str, list[str]]:
    """카드별 BRAND_SERVICE 행과 공통 혜택의 동일성을 판정한다. ``(상태, 불일치 항목)`` 을 반환한다.

    SAME은 코드, 혜택명·유형, 출처 문서, 브랜드·등급, 적용 카드, 유효기간, 혜택 내용, 근거가 모두 확인된 경우뿐이다.
    하나라도 다르거나 확인할 수 없으면 REVIEW이고, 같은 코드의 공통 혜택이 없으면 NO_COMMON이다.
    """
    if row.get('card_common_bnft_id') is None:
        return 'NO_COMMON', ['bnft_cd']
    issues = []
    if row['bnft_nm'] != row['common_bnft_nm'] or row['bnft_type_cd'] != row['common_bnft_type_cd']:
        issues.append('혜택명·유형')
    if not row.get('doc_ids') or not set(row['doc_ids']) <= set(row.get('common_doc_ids') or []):
        issues.append('출처 문서')
    if row.get('brand_grades') != [row.get('common_brand_grade')]:
        issues.append('브랜드·등급')
    if not row.get('applied'):
        issues.append('적용 카드')
    if (row['bnft_valid_from'], row['bnft_valid_to_excl']) != (row['common_valid_from'], row['common_valid_to_excl']):
        issues.append('유효기간')
    for own, common, label in ((row['bnft_rule_txt'], row['common_rule_txt'], '혜택 내용'),
                               (row['bnft_limit_txt'], row['common_limit_txt'], '이용 조건')):
        if own is not None and own != common:
            issues.append(label)
    if not row.get('evidence_ids') or not set(row['evidence_ids']) <= set(row.get('common_evidence_ids') or []):
        issues.append('원문 근거')
    return ('REVIEW', issues) if issues else ('SAME', [])


# region Repository (common_benefit_repository.sql 호출)
class CommonBenefitRepository:
    """기존 세션과 mapper를 이용한다. 연결과 트랜잭션은 호출자가 관리한다.

    ``rows/one/write('쿼리이름', 파라미터=값)`` 은 ``common_benefit_repository.쿼리이름`` 을 실행하는 얇은 래퍼다.
    ProductBenefitService도 이 Repository를 그대로 쓴다.
    """
    def __init__(self, session):
        self.session = session

    def rows(self, name, **params):
        """SELECT 결과 전체(list[dict])."""
        return self.session.select_list('common_benefit_repository.' + name, params)

    def one(self, name, **params):
        """SELECT 결과 1행(dict) 또는 None. ``FOR UPDATE`` 잠금 쿼리(lock_card·lock_common)도 이것으로 실행한다."""
        return self.session.select_one('common_benefit_repository.' + name, params)

    def write(self, name, **params):
        """INSERT/UPDATE 실행. ``RETURNING`` 행 목록을 돌려주며, ON CONFLICT DO NOTHING으로 건너뛰면 빈 목록이다."""
        return self.session.execute('common_benefit_repository.' + name, params) or []

    def stored_run(self, run_id: str) -> dict | None:
        """실행 1건의 대표 혜택을 추출 원본에서 다시 만든다. 원본을 읽을 수 없으면 ``None`` 이다."""
        try:
            return normalize_stored_run(self.rows('list_run_items', RUN_ID=run_id))
        except (ValidationError, KeyError, TypeError, ValueError):
            return None

    def attach_normalized(self, run_id: str, rows: list[dict]) -> list[dict]:
        """대표 혜택 행에 등록 형태(normalized)·통합 출처 수·병합 충돌·현재 기준 검증 코드(check_cd)를 붙인다.

        정제본은 DB에 저장하지 않는다(2026-11-03 stg_normalized_item 제거). 등록할 때마다 같은 규칙으로 다시 만든다.
        """
        stored = self.stored_run(run_id) or {}
        registry = load_registry()
        run_reviews = [review for review in registry if review['run_id'] == run_id]
        reviews = verified_reviews_for_run(
            run_id, self.rows('list_unresolved_review_items', RUN_ID=run_id), run_reviews) if run_reviews else []
        out = []
        for row in rows:
            item = stored.get(row['card_extr_stg_id'])
            out.append({**row, 'normalized': item.normalized if item else None,
                        'source_cnt': item.source_cnt if item else 0,
                        'conflicts': item.conflicts if item else [],
                        'check_cd': item.check_cd if item else None,
                        'reviewed_unresolved_links': links_for_candidate(
                            run_id, row.get('card_doc_id', ''), row.get('stg_raw_item', {}).get('bnft_nm', ''), reviews)})
        return out

    def unresolved_review_queue(self, run_id: str) -> list[dict]:
        """Read unresolved entries from immutable call responses and join separate review decisions."""
        return unresolved_queue(self.rows('list_unresolved_review_items', RUN_ID=run_id), load_registry())
# endregion


# region Service (공통 혜택 등록·카드 적용)
class CommonBenefitService:
    """공통 혜택 등록과 카드 적용을 나눠 처리한다. 상태 승격과 기존 혜택 삭제는 하지 않는다."""
    def __init__(self, session, user_id='SYSTEM', embedding_service=None):
        self.session = session
        self.repo = CommonBenefitRepository(session)
        self.user_id = user_id
        self.embedding_service = embedding_service

    def stored_run(self, run_id: str) -> dict | None:
        return self.repo.stored_run(run_id)

    def attach_normalized(self, run_id: str, rows: list[dict]) -> list[dict]:
        return self.repo.attach_normalized(run_id, rows)

    def candidates(self, run_id: str) -> list[dict]:
        """실행의 공통 혜택 후보. 등록과 적용이 같은 목록을 쓴다."""
        return self.attach_normalized(run_id, self.repo.rows('list_candidates', RUN_ID=run_id))

    def register_card(self, product: dict) -> int:
        """상품 코드가 같으면 입력 정보도 일치해야 한다."""
        values = {k: product[k] for k in ('product_cd', 'product_nm', 'issuer', 'card_kind_cd', 'brand_opt_list')}
        with self.session.transaction():
            before = self._integrity_errors()
            self.repo.write('insert_card', PRODUCT_CD=values['product_cd'], PRODUCT_NM=values['product_nm'],
                            ISSUER=values['issuer'], CARD_KIND_CD=values['card_kind_cd'],
                            BRAND_OPT_LIST=Jsonb(values['brand_opt_list']), USER_ID=self.user_id)
            row = self.repo.one('find_card_by_code', PRODUCT_CD=values['product_cd'])
            if not row or any(row[k] != v for k, v in values.items()):
                raise ValueError('기존 상품 코드의 정보가 입력과 다릅니다')
            self._assert_no_new_errors(before)
            return row['card_id']

    def ensure_common(self, common: dict) -> int:
        """공통서비스를 등록한다. 코드가 같으면 입력 정보도 일치해야 한다.

        card_common INSERT(ON CONFLICT (common_cd) DO NOTHING) 후 다시 조회해 이름·브랜드·등급이 입력과 같은지 확인한다.
        트랜잭션을 직접 열지 않는다(호출자 RegisterService._link의 트랜잭션 안에서 실행).

        Returns:
            card_common_id.

        Raises:
            ValueError: 같은 common_cd의 기존 행이 입력과 다른 경우.
        """
        self.repo.write('insert_common', COMMON_CD=common['common_cd'], COMMON_NM=common['common_nm'],
                        BRAND_CD=common.get('brand_cd'), SERVICE_GRADE_CD=common.get('service_grade_cd'),
                        COMMON_NOTE=common.get('common_note'), USER_ID=self.user_id)
        row = self.repo.one('find_common', COMMON_CD=common['common_cd'])
        if not row or any(row[k] != common.get(k) for k in ('common_nm', 'brand_cd', 'service_grade_cd')):
            raise ValueError('기존 공통서비스 코드의 정보가 입력과 다릅니다')
        return row['card_common_id']

    def link_doc(self, common_id: int, card_doc_id: str) -> None:
        """브랜드 공통서비스 문서만 공통서비스에 연결한다. 이미 있으면 그대로 둔다."""
        document = self.repo.one('find_doc_type', DOC_ID=card_doc_id)
        if not document or document['doc_type_cd'] != 'BRAND_SERVICE':
            raise ValueError('BRAND_SERVICE 문서만 공통서비스에 연결할 수 있습니다')
        self.repo.write('insert_common_doc', COMMON_ID=common_id, DOC_ID=card_doc_id)

    def register_run(self, run_id: str, identities: dict) -> list[Decision]:
        """추출 실행의 후보를 공통 혜택으로 등록한다. 카드 적용은 ``apply_run`` 이 따로 판단한다.

        Args:
            run_id: BRAND_SERVICE 문서의 SUCCEEDED 추출 실행 ID.
            identities: ``{card_extr_stg_id: 검토된 업무 식별자}``. 없는 후보는 REVIEW가 된다.

        Returns:
            후보별 Decision(INSERTED / UPDATED / UNCHANGED / CHANGE_REVIEW / REVIEW / EXCLUDED).
        """
        results = []
        # 트랜잭션 시작: 모든 후보의 INSERT/UPDATE를 한 단위로 commit/rollback한다.
        with self.session.transaction():
            before = self._integrity_errors()
            for candidate in self.candidates(run_id):
                evidence = self.repo.rows('candidate_evidence', STG_ID=candidate['card_extr_stg_id'])
                results.append(self._register_candidate(candidate, evidence, identities))
            self._assert_no_new_errors(before)
        # 커밋 후 임베딩. UPDATE된 행은 SQL에서 검색 텍스트·벡터를 NULL로 비웠으므로 다시 만든다.
        changed = [item.card_common_bnft_id for item in results if item.status in ('INSERTED', 'UPDATED')]
        if changed and self.embedding_service is not None:
            self.embedding_service.embed_new('card_common_bnft', changed)
        return results

    def path_a(self, card_id: int, identities: dict):
        """기존 공통 문서 실행을 검색한다. AI 추출을 호출하지 않는다."""
        results = []
        for run in self.repo.rows('list_runs'):
            results.extend(self.apply_run(card_id, run['card_ai_run_id'], identities))
        return results

    def register_card_and_apply(self, product: dict, identities: dict):
        """카드 상품을 등록(register_card)한 뒤 기존 공통 문서 실행 전체에 적용 판단(path_a)을 한다."""
        card_id = self.register_card(product)
        return card_id, self.path_a(card_id, identities)

    def path_b(self, run_id: str, identities: dict):
        """이미 등록·추출된 문서의 기존 카드들을 같은 적용 로직으로 처리한다."""
        results = []
        for card in self.repo.rows('list_cards'):
            results.extend(self.apply_run(card['card_id'], run_id, identities))
        return results

    def register_document_and_apply(self, pdf, register_service, extraction_service, identities: dict, common_link):
        """문서 등록·추출은 기존 서비스를 재사용한다. 호출자가 LLM 실행을 명시적으로 선택해야 한다."""
        registration = register_service.register(pdf, apply=True, common_link=common_link)
        if not registration.card_doc_id:
            raise ValueError('문서 ID가 없습니다')
        extraction = extraction_service.run(registration.card_doc_id, card_id=None)
        if extraction.status != 'SUCCEEDED':
            raise ValueError('문서 추출이 완료되지 않아 혜택을 적용하지 않습니다')
        registered = self.register_run(extraction.card_ai_run_id, identities)
        return registration, extraction, registered, self.path_b(extraction.card_ai_run_id, identities)

    def apply_run(self, card_id: int, run_id: str, identities: dict):
        """카드 1장에 대해 실행의 공통 혜택 후보마다 적용 여부를 판단하고 card_common_bnft_apply를 기록한다.

        공통 혜택(card_common_bnft)이 먼저 register_run으로 등록되어 있어야 한다(없으면 REVIEW).
        카드마다 별도 트랜잭션이며, 신규 정합성 위반이 생기면 이 카드의 적용 기록 전체가 rollback된다.
        """
        results = []
        # 카드 행 잠금으로 카드별 적용 판단을 직렬화한다.
        with self.session.transaction():
            before = self._integrity_errors()
            card = self.repo.one('lock_card', CARD_ID=card_id)
            if not card:
                raise ValueError('카드가 없습니다')
            for candidate in self.candidates(run_id):
                evidence = self.repo.rows('candidate_evidence', STG_ID=candidate['card_extr_stg_id'])
                results.append(self._apply_candidate(card, candidate, evidence, identities))
            self._assert_no_new_errors(before)
        return results

    def compare_brand_benefits(self) -> list[dict]:
        """기존 BRAND_SERVICE 행의 동일성 판정. 데이터를 바꾸지 않는다."""
        results = []
        for row in self.repo.rows('brand_bnft_compare'):
            status, issues = compare_brand_bnft(row)
            results.append({'card_id': row['card_id'], 'card_bnft_id': row['card_bnft_id'], 'bnft_cd': row['bnft_cd'],
                            'card_common_id': row.get('card_common_id'),   # 공통 혜택은 소유자까지 있어야 식별된다
                            'card_common_bnft_id': row.get('card_common_bnft_id'), 'status': status, 'issues': issues})
        return results

    def _integrity_errors(self):
        """정합성 위반(v_card_integrity_issue + 공통서비스 전용 검사)을 (gate_cd, issue_key) 개수로 센다.

        물리 FK가 없는 구조라서, 등록 전후 이 값을 비교해 새로 생긴 고아 행·잘못된 연결을 막는다.
        """
        rows =[*self.repo.rows('integrity_errors'), *self.repo.rows('common_integrity_errors')]
        return Counter((r['gate_cd'], r['issue_key']) for r in rows)

    def _assert_no_new_errors(self, before):
        """기준선보다 늘어난 위반이 있으면 ValueError를 내서 호출자의 트랜잭션을 rollback시킨다."""
        new =self._integrity_errors() - before
        if new:
            raise ValueError('신규 정합성 위반으로 트랜잭션을 롤백합니다: ' + ', '.join(sorted({g for g, _ in new})))

    @staticmethod
    def _candidate_problem(candidate) -> str | None:
        """후보 자체를 쓸 수 없는 사유. 등록과 적용이 같은 기준을 쓴다.

        ``check_cd`` 는 저장된 검증 코드를 현재 계약으로 다시 판단한 값이다(``effective_check_cd``).
        OK·LINK_REVIEW는 값 검증(원문 숫자 대조)이 통과한 경우에만 나온다.
        """
        norm = candidate.get('normalized')
        if norm is None:
            return '추출 원본에서 등록 형태를 다시 만들 수 없습니다'
        if candidate.get('check_cd') not in ('OK', 'LINK_REVIEW'):
            return '후보 값 또는 구조 검증이 필요합니다'
        if candidate.get('source_cnt') != 1:
            return '이름 기준 다중 항목 병합을 별도 검토해야 합니다'
        if norm.get('relation_list'):
            return '혜택 간 관계의 카드별 ID 연결을 확인해야 합니다'
        return None

    @staticmethod
    def _located(evidence) -> list[dict]:
        """위치가 있고 승인 상태가 PENDING·APPROVED이며, 위치로 잘라낸 원문(source_txt)이 인용과 같은 근거만 남긴다."""
        return [e for e in evidence if e['start_pos'] is not None and e['end_pos'] is not None
                and e.get('approval_status_cd') in ('PENDING', 'APPROVED')
                and e.get('source_txt') is not None and compact(e['source_txt']) == compact(e['quote_txt'])]

    @staticmethod
    def _evidence_ids(raw, norm, located) -> tuple[list[str], str | None]:
        """인용이 어떤 혜택·규칙·한도를 뒷받침하는지 확인한다. ``(근거 ID, 검토 사유)`` 를 반환한다."""
        rules = norm.get('rule_list', [])
        # 한도는 추출 원본의 limit_key로 근거를 확인한다(한도 풀 정규화 limit_list는 2026-11-03에 제거).
        limit_keys = {limit['limit_key'] for limit in raw.get('limits', []) if limit.get('limit_key')}
        quotes = [compact(e['quote_txt']) for e in located]
        # 원천 테이블에는 supports/support_key가 없으므로 원문 인용이 유일하게
        # 하나의 대상에 대응할 때만 인정한다. 중복 인용은 임의로 배정하지 않는다.
        # 대상(TARGET) 인용은 혜택 자신의 근거다(예: "대상 호텔"). 별도 연결 키가 없어 혜택 근거로 본다.
        kinds = {'BNFT': 'BNFT', 'APPLICABILITY': 'BNFT', 'TARGET': 'BNFT', 'RULE': 'RULE', 'LIMIT': 'BNFT'}
        source_targets = {}
        rule_keys = {r['rule_key'] for r in rules}
        # 같은 청크·같은 위치의 근거는 같은 원문 구간이다(규칙과 조건이 같은 구절을 인용하면 두 행으로 저장된다).
        # 한 구간으로 세고, 같은 문자열이라도 위치가 다르면 서로 다른 후보로 남겨 모호성 검증을 유지한다.
        spans = {}
        for e in located:
            spans.setdefault((e.get('card_doc_chunk_id'), e['start_pos'], e['end_pos']), e)
        located = list(spans.values())
        for item in raw.get('evidence', []):
            supports = item.get('supports')
            kind = kinds.get(supports)
            key = item.get('support_key') if supports == 'RULE' else None
            if kind is None or (supports == 'RULE' and key not in rule_keys) or (supports == 'LIMIT' and item.get('support_key') not in limit_keys):
                return [], '근거가 어떤 혜택·규칙·한도에 속하는지 확인해야 합니다'
            quote = compact(item.get('quote_txt') or '')
            matches = [e for e in located if compact(e['quote_txt']) == quote]
            if not quote or len(matches) != 1:
                return [], '원문 근거가 없거나 동일한 인용이 중복되어 대상이 모호합니다'
            # 한 구절이 혜택과 그 혜택의 규칙 하나를 함께 설명하는 경우(예: "Europcar 최대 15% 할인")는 같은 근거로 인정한다.
            # 서로 다른 규칙 두 개가 같은 구절을 쓰면 어느 값이 어느 규칙인지 알 수 없어 계속 막는다.
            # 적용 범위·한도 인용을 규칙 근거로 함께 쓰는 경우는 종전처럼 막는다.
            known, sources, _ = source_targets.get(quote, (set(), set(), None))
            joined, sources = known | {(kind, key)}, sources | {supports}
            shared_ok = sources <= {'BNFT', 'TARGET', 'RULE'} and len({k for t, k in joined if t == 'RULE'}) <= 1
            if len(joined) > 1 and not shared_ok:
                return [], '동일 인용이 여러 대상에 사용되어 근거 연결을 검토해야 합니다'
            source_targets[quote] = (joined, sources, matches[0]['evidence_id'])
        targets = {target for joined, _, _ in source_targets.values() for target in joined}
        if ('BNFT', None) not in targets or any(('RULE', k) not in targets for k in rule_keys):
            return [], '혜택 또는 계산 규칙을 뒷받침하는 근거가 없습니다'
        for limit_key in limit_keys:
            source_quotes = [compact(e['quote_txt']) for e in raw.get('evidence', [])
                             if e.get('supports') == 'LIMIT' and e.get('support_key') == limit_key]
            if not any(q in quotes for q in source_quotes):
                return [], '한도의 원문 근거를 확인해야 합니다'
        return sorted({evidence_id for _, _, evidence_id in source_targets.values()}), None

    def _register_candidate(self, candidate, evidence, identities) -> Decision:
        """후보 1건을 공통 혜택으로 등록·갱신하거나 검토 사유를 반환한다. register_run의 트랜잭션 안에서 실행된다.

        DB 변경: card_common 잠금(FOR UPDATE) 후 card_common_bnft INSERT 또는 UPDATE.
        Raises:
            ValueError: 동시 등록·갱신 충돌. register_run 전체가 rollback된다.
        """
        stg_id = candidate['card_extr_stg_id']
        def review(reason, status='REVIEW', common_id=None):
            return Decision(None, stg_id, status, reason, card_common_id=common_id)
        raw, norm = candidate['stg_raw_item'], candidate.get('normalized')
        if candidate['stg_status'] in ('REJECTED', 'RETIRED'):
            return review('제외된 후보입니다', 'EXCLUDED')
        problem = self._candidate_problem(candidate)
        if problem:
            return review(problem)
        commons = self.repo.rows('common_of_doc', DOC_ID=candidate['card_doc_id'])
        if len(commons) != 1:
            return review('문서의 공통서비스가 하나로 확인되지 않습니다')
        common = commons[0]
        common_id = common['card_common_id']
        brand, grade = raw.get('brand_txt'), raw.get('service_grade_txt')
        if ((brand and brand_key(brand) != brand_key(common.get('brand_cd')))
                or (grade and grade_key(grade) != grade_key(common.get('service_grade_cd')))):
            return review('후보의 브랜드·등급이 공통서비스와 다릅니다', common_id=common_id)
        service_type = service_type_of(raw.get('selection_service_txt'))
        if service_type is None:
            return review('선택서비스 번호가 하나로 확인되지 않습니다', common_id=common_id)
        try:
            start, end = candidate_period(raw)
            code = benefit_code(candidate.get('doc_family_cd'), identities.get(stg_id))
        except (ValueError, OverflowError) as error:
            return review(str(error), common_id=common_id)
        evidence_ids, problem = self._evidence_ids(raw, norm, self._located(evidence))
        if problem:
            return review(problem, common_id=common_id)
        rule_txt, limit_txt = common_texts(raw, norm)
        values = dict(BNFT_NM=norm['bnft_nm'], BNFT_TYPE=norm['bnft_type_cd'], SERVICE_TYPE=service_type,
                      RULE_TXT=rule_txt, LIMIT_TXT=limit_txt, VALID_FROM=start, VALID_TO=end, USER_ID=self.user_id)
        # 공통서비스 행 잠금 후 같은 (card_common_id, bnft_cd)가 있는지 확인한다(중복 등록 방지).
        self.repo.one('lock_common', COMMON_ID=common_id)
        existing = self.repo.one('find_common_bnft', COMMON_ID=common_id, BNFT_CD=code)
        done = dict(bnft_cd=code, card_common_id=common_id, evidence_ids=tuple(evidence_ids))
        # 분기: 기존 행 있음 → 같으면 UNCHANGED, 이전 판 추출값 그대로면 UPDATE, 수동 수정 가능성이 있으면 CHANGE_REVIEW.
        if existing:
            benefit_id = existing['card_common_bnft_id']
            if self._same_common(existing, values):
                return Decision(None, stg_id, 'UNCHANGED', '등록된 공통 혜택과 같습니다', card_common_bnft_id=benefit_id, **done)
            if not self._can_update(common_id, candidate['doc_family_cd'], candidate['doc_version_no'], existing):
                return Decision(None, stg_id, 'CHANGE_REVIEW', '변경 또는 출처를 안전하게 비교할 수 없어 자동 갱신하지 않습니다',
                                card_common_bnft_id=benefit_id, **done)
            if not self.repo.write('update_common_bnft', COMMON_ID=common_id, BNFT_ID=benefit_id, **values):
                raise ValueError('기존 공통 혜택이 변경되어 갱신을 중단합니다')
            return Decision(None, stg_id, 'UPDATED', '검토 대기', card_common_bnft_id=benefit_id, **done)
        inserted = self.repo.write('insert_common_bnft', COMMON_ID=common_id, BNFT_CD=code, **values)
        if not inserted:
            raise ValueError('동시 등록 충돌: 전체 트랜잭션을 롤백합니다')
        return Decision(None, stg_id, 'INSERTED', '검토 대기', card_common_bnft_id=inserted[0]['card_common_bnft_id'], **done)

    @staticmethod
    def _same_common(existing, values) -> bool:
        """기존 card_common_bnft 행이 이번에 저장할 값과 모든 업무 컬럼에서 같은지 비교한다."""
        return (existing['bnft_nm'] == values['BNFT_NM'] and existing['bnft_type_cd'] == values['BNFT_TYPE']
                and existing['service_type_cd'] == values['SERVICE_TYPE'] and existing['bnft_rule_txt'] == values['RULE_TXT']
                and existing['bnft_limit_txt'] == values['LIMIT_TXT'] and existing['bnft_valid_from'] == values['VALID_FROM']
                and existing['bnft_valid_to_excl'] == values['VALID_TO'])

    def _can_update(self, common_id, family, version, existing) -> bool:
        """같은 계열의 이전 판 후보와 현재 행이 같을 때만 갱신한다. 수동 수정을 덮어쓰지 않는다."""
        if version is None:
            return False
        runs = {}
        for source in self.repo.rows('prior_common_sources', COMMON_ID=common_id):
            if source['doc_family_cd'] != family or source['doc_version_no'] >= version:
                continue
            if source['card_ai_run_id'] not in runs:
                runs[source['card_ai_run_id']] = self.stored_run(source['card_ai_run_id']) or {}
            stored = runs[source['card_ai_run_id']].get(source['card_extr_stg_id'])
            if stored is None:
                continue
            old = stored.normalized
            try:
                start, end = candidate_period(source['stg_raw_item'])
            except (ValueError, OverflowError):
                continue
            rule_txt, limit_txt = common_texts(source['stg_raw_item'], old)
            if (existing['bnft_nm'] == old.get('bnft_nm') and existing['bnft_type_cd'] == old.get('bnft_type_cd')
                    and existing['bnft_valid_from'] == start and existing['bnft_valid_to_excl'] == end
                    and existing['bnft_rule_txt'] == rule_txt and existing['bnft_limit_txt'] == limit_txt):
                return True
        return False

    def _apply_candidate(self, card, candidate, evidence, identities):
        """문서·상품 근거로 카드 적용을 판단하고 ``card_common_bnft_apply`` 만 기록한다."""
        card_id, stg_id = card['card_id'], candidate['card_extr_stg_id']
        def review(reason, status='REVIEW'):
            return Decision(card_id, stg_id, status, reason)
        raw, norm = candidate['stg_raw_item'], candidate.get('normalized')
        if card['product_status_cd'] != 'ACTIVE':
            return review('활성 카드가 아닙니다', 'EXCLUDED')
        if candidate['stg_status'] in ('REJECTED', 'RETIRED'):
            return review('제외된 후보입니다', 'EXCLUDED')
        problem = self._candidate_problem(candidate)
        if problem:
            return review(problem)
        located = self._located(evidence)
        quotes = [compact(e['quote_txt']) for e in located]
        applicability_quotes = [compact(e['quote_txt']) for e in raw.get('evidence', [])
                                if e.get('supports') == 'APPLICABILITY']
        def applies_supported(value):
            return bool(value) and any(q in quotes and compact(value) in q for q in applicability_quotes)
        names = raw.get('applicable_cards') or []
        exclusions = raw.get('excluded_cards') or []
        if any(not applies_supported(v) for v in [*names, *exclusions]):
            return review('대상 또는 제외 카드의 원문 근거를 확인해야 합니다')
        card_names = {compact(card['product_cd']), compact(card['product_nm'])}
        if any(compact(v) in card_names for v in exclusions):
            return review('문서에서 제외한 카드입니다', 'EXCLUDED')
        if names and not any(compact(v) in card_names for v in names):
            return review('대상 카드 목록에서 해당 상품을 확인하지 못했습니다')
        brand, grade = raw.get('brand_txt'), raw.get('service_grade_txt')
        selection = raw.get('selection_service_txt')
        if not all(applies_supported(v) for v in (brand, grade)):
            return review('브랜드와 등급의 적용 근거가 불명확합니다')
        if selection and not applies_supported(selection):
            return review('선택서비스의 적용 근거가 불명확합니다')
        selection_codes = set(re.findall(r'(?<!\d)(0[1-4])(?!\d)', selection or ''))
        if selection and len(selection_codes) != 1:
            return review('선택서비스 번호가 하나로 확인되지 않습니다')
        options = [o for o in card['brand_opt_list'] if o.get('brand_opt_status_cd') == 'ACTIVE'
                   and brand_key(o.get('brand_cd')) == brand_key(brand)
                   and grade_key(o.get('service_grade_cd')) == grade_key(grade)
                   and (not selection or o.get('service_type_cd') in selection_codes)]
        if len(options) != 1:
            return review('브랜드·등급·선택서비스 선택지가 하나로 확인되지 않습니다')
        if not names:
            # 등급 전체 공통서비스는 안내서의 명시적 공통 범위와 상품설명서의
            # 해당 카드 브랜드·등급 근거를 둘 다 확인한다. 선택서비스에는 쓰지 않는다.
            broad = next((e['quote_txt'] for e in located if compact(e['quote_txt']) in applicability_quotes
                          and all(compact(t) in compact(e['quote_txt']) for t in (brand, grade, '등급카드', '소지자에게공통으로제공됩니다'))), None)
            if selection or not broad:
                return review('명시적 전체 등급 공통서비스 또는 대상 카드 근거가 없습니다')
            if not self._product_basis(card, options[0], brand, grade):
                return review('상품설명서에서 카드의 브랜드·등급을 확인해야 합니다')
        elif not selection and options[0].get('service_type_cd') != 'NONE':
            return review('선택서비스 여부가 확인되지 않았습니다')
        validity = raw.get('validity_period_txt')
        if validity and not applies_supported(validity):
            return review('제공 기간의 원문 근거가 없습니다')
        try:
            code = benefit_code(candidate.get('doc_family_cd'), identities.get(stg_id))
        except ValueError as error:
            return review(str(error))
        evidence_ids, problem = self._evidence_ids(raw, norm, located)
        if problem:
            return review(problem)
        commons = self.repo.rows('common_of_doc', DOC_ID=candidate['card_doc_id'])
        if len(commons) != 1:
            return review('문서의 공통서비스가 하나로 확인되지 않습니다')
        common_id = commons[0]['card_common_id']
        benefit = self.repo.one('find_common_bnft', COMMON_ID=common_id, BNFT_CD=code)
        if not benefit:
            return review('공통 혜택이 먼저 등록되어야 합니다')
        benefit_id = benefit['card_common_bnft_id']
        # 카드 적용 관계 INSERT. 이미 있으면 ON CONFLICT DO NOTHING으로 빈 결과 → UNCHANGED.
        inserted = self.repo.write('insert_common_apply', COMMON_ID=common_id, BNFT_ID=benefit_id, CARD_ID=card_id)
        # 같은 코드의 카드별 혜택(card_product_item)이 있으면 수정하지 않고 사유에만 알린다.
        legacy = self.repo.one('find_benefit', CARD_ID=card_id, BNFT_CD=code)
        reason = '카드별 혜택에 같은 코드의 기존 행이 있습니다. brand_bnft_compare로 동일성을 확인하세요' if legacy else '검토 대기'
        return Decision(card_id, stg_id, 'INSERTED' if inserted else 'UNCHANGED', reason, code,
                        legacy['card_bnft_id'] if legacy else None, common_id, benefit_id, tuple(evidence_ids))

    def _product_basis(self, card, option, brand, grade) -> str | None:
        """상품설명서 근거에서 카드의 브랜드·등급을 찾는다."""
        for proof in self.repo.rows('product_brand_evidence', CARD_ID=card['card_id']):
            quote = proof.get('quote_txt') or ''
            source = proof.get('source_txt') or ''
            service_type = option.get('service_type_cd')
            if (compact(card['product_nm'] + ' 상품설명서') == compact(proof.get('doc_title') or '')
                    and compact(quote) == compact(source)
                    and compact(brand) in compact(quote) and compact(grade) in compact(quote)
                    and (service_type in ('NONE', 'COMMON') or service_type in re.findall(r'(?<!\d)(0[1-4])(?!\d)', quote))):
                return quote
        return None
# endregion
