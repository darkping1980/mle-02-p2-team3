"""발표용 자동 승인 후보 판정. 판정만 하며 DB 상태를 변경하지 않는다.

호출자는 동일 트랜잭션에서 대상 행과 근거를 잠그고 상위키·중복 검사를 수행해야 한다.
이 함수의 결과만으로 승인이나 업무 등록을 수행해서는 안 된다.

호출하는 곳: common_auto_pipeline.PostgresCommonApproval.process (판정 결과로 card_extr_stg.stg_status를 UPDATE).
상품설명서 등록(ProductBenefitService)은 이 정책을 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .common_benefit_service import compact


@dataclass(frozen=True)
class ApprovalDecision:
    eligible: bool
    reasons: tuple[str, ...]


def check_auto_approval(candidate: dict, evidence: list[dict], *,
                        parent_integrity_ok: bool, duplicate_free: bool) -> ApprovalDecision:
    """후보와 원문 근거가 보수적 자동 승인 기준을 만족하는지 판정한다.

    ``candidate`` 는 ``CommonBenefitRepository.attach_normalized`` 가 붙인 normalized·source_cnt·conflicts·check_cd를 가진다.
    저장된 검증 코드 OK는 값 검증 OK와 대상 연결 TEXT_CONFIRMED가 모두 통과했고 계약 오류가 없다는 뜻이다(sql_check_code).

    Returns:
        ApprovalDecision. 사유(reasons)가 하나도 없을 때만 eligible=True다.
    """
    reasons = []
    norm = candidate.get("normalized") or {}
    raw = candidate.get("stg_raw_item") or {}
    if candidate.get("stg_status") not in ("PENDING_REVIEW", "AUTO_APPROVED"):
        reasons.append("후보 상태가 자동 승인 대상이 아님")
    if candidate.get("stg_kind_cd") != "BENEFIT":
        reasons.append("혜택 후보가 아님")
    if candidate.get("stg_sql_check_cd") != "OK":
        reasons.append("SQL 검증이 OK가 아님")
    if candidate.get("check_cd") != "OK" or not candidate.get("normalized"):
        reasons.append("값 또는 대상 연결 검증 미통과")
    if raw.get("certainty") != "HIGH" or raw.get("uncertainty_note"):
        reasons.append("추출 의미가 불확실함")
    if candidate.get("source_cnt") != 1 or candidate.get("conflicts"):
        reasons.append("복수 출처 또는 병합 충돌")
    if norm.get("relation_list") or raw.get("relations"):
        reasons.append("혜택 관계는 별도 검토 필요")
    if not parent_integrity_ok:
        reasons.append("상위키 또는 논리 관계 미확인")
    if not duplicate_free:
        reasons.append("중복 또는 충돌 미확인")
    if not evidence:
        reasons.append("원문 근거 없음")
    for item in evidence:
        if (item.get("approval_status_cd") not in ("PENDING", "APPROVED")
                or item.get("start_pos") is None or item.get("end_pos") is None
                or item["start_pos"] < 1 or item["end_pos"] < item["start_pos"]
                or not item.get("quote_txt") or item.get("source_txt") is None
                or compact(item["quote_txt"]) != compact(item["source_txt"])):
            reasons.append("위치 또는 텍스트가 일치하지 않는 근거")
            break
    return ApprovalDecision(not reasons, tuple(reasons))
