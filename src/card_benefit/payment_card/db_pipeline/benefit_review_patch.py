"""사람 검토 보정 대장(BENEFIT REVIEW PATCH): AI 추출 후보를 원문 근거로 보완하는 예외 수단(2026-11-05).

추출 원본(card_extr_stg)은 바꾸지 않는다. 등록할 때 메모리에서만 보정을 적용하고, 보정한 후보는 기존 추출 검증
(check_benefit → sql_check_code)을 다시 통과해야 등록된다. 보정 내역은 등록 항목의 item_data.review_patch에 남긴다.

대장 형식(JSON)::

    {"ledger_version": 1, "kind": "BENEFIT_REVIEW_PATCH",
     "patches": [{"patch_id": "...", "run_id": "...", "card_extr_stg_id": "...", "status": "APPROVED" | "DRAFT_PENDING_USER_REVIEW",
                  "reason": "...", "pdf_check": "...", "ops": [...]}]}

연산(op) — 모두 원문 인용(quote_txt)이 필요한 연산은 등록 시 청크 원문에서 위치를 찾지 못하면 실패한다.
    ADD_EVIDENCE        {"supports", "support_key", "quote_txt"}           혜택·규칙·한도·관계 근거 인용 추가
    SET_TARGET_TYPE     {"target_nm", "target_type_cd"}                     대상 종류 지정(UNKNOWN 보완)
    ADD_CONDITION       {"condition": ConditionItem}                         혜택 조건 추가
    ADD_RULE_CONDITION  {"rule_key", "condition": ConditionItem}             규칙 조건 추가
    ADD_RELATION        {"relation": RelationItem, "quote_txt"}              혜택 간 관계 + 관계 근거(REL) 추가
    DROP_RELATION       {"relation_key", "reason"}                           추출한 관계 제외(예: 대상이 묶음 이름이라 연결할 수 없고
                                                                             다른 혜택 쪽 ADD_RELATION으로 다시 표현한 경우). 근거 인용은 남긴다

특정 카드에 의존하지 않는다. 어느 실행·후보든 대장에 적힌 보정만 적용한다.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .extraction_schema import BenefitItem

KIND = "BENEFIT_REVIEW_PATCH"
APPROVED = "APPROVED"
DRAFT = "DRAFT_PENDING_USER_REVIEW"
OPS = ("ADD_EVIDENCE", "SET_TARGET_TYPE", "ADD_CONDITION", "ADD_RULE_CONDITION", "ADD_RELATION", "DROP_RELATION")


def load_patches(paths: list[str | Path]) -> list[dict]:
    """대장 파일들을 읽어 형식을 검사한다. 같은 후보에 보정이 두 건 이상이면 오류."""
    patches = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("ledger_version") != 1 or data.get("kind") != KIND or not isinstance(data.get("patches"), list):
            raise ValueError(f"보정 대장 형식이 아닙니다: {path}")
        for patch in data["patches"]:
            for key in ("patch_id", "run_id", "card_extr_stg_id", "status", "reason", "ops"):
                if not patch.get(key):
                    raise ValueError(f"보정 {patch.get('patch_id')}에 {key}가 없습니다")
            if patch["status"] not in (APPROVED, DRAFT):
                raise ValueError(f"보정 상태가 올바르지 않습니다: {patch['status']}")
            for op in patch["ops"]:
                if op.get("op") not in OPS:
                    raise ValueError(f"알 수 없는 보정 연산: {op.get('op')}")
            patches.append({**patch, "ledger": Path(path).name})
    keys = [(p["run_id"], p["card_extr_stg_id"]) for p in patches]
    if len(keys) != len(set(keys)):
        raise ValueError("같은 후보의 보정이 두 건 이상입니다")
    return patches


def usable(patches: list[dict], run_id: str, allow_draft: bool) -> dict[str, dict]:
    """이 실행에 적용할 보정. 기본은 APPROVED만이며, allow_draft는 ROLLBACK 시험에서만 쓴다."""
    allowed = (APPROVED, DRAFT) if allow_draft else (APPROVED,)
    return {p["card_extr_stg_id"]: p for p in patches if p["run_id"] == run_id and p["status"] in allowed}


def apply_patch(raw: dict, patch: dict) -> tuple[dict, list[str]]:
    """추출 원본(raw) 사본에 보정을 적용한다. (보정된 원본, 새로 추가한 인용 목록).

    결과는 추출 스키마(BenefitItem)를 그대로 통과해야 한다. 원본 dict는 바꾸지 않는다.
    """
    out = copy.deepcopy(raw)
    added: list[str] = []

    def quote(supports: str, support_key: str | None, text: str) -> None:
        if not text:
            raise ValueError("보정 인용이 비어 있습니다")
        out.setdefault("evidence", []).append({"quote_txt": text, "supports": supports, "support_key": support_key,
                                               "link_basis": "SAME_TEXT"})
        added.append(text)

    rule_keys = {rule["rule_key"] for rule in out.get("rules", [])}
    for op in patch["ops"]:
        kind = op["op"]
        if kind == "ADD_EVIDENCE":
            if op["supports"] == "RULE" and op.get("support_key") not in rule_keys:
                raise ValueError(f"없는 규칙의 근거입니다: {op.get('support_key')}")
            quote(op["supports"], op.get("support_key"), op["quote_txt"])
        elif kind == "SET_TARGET_TYPE":
            hits = [t for t in out.get("targets", []) if t.get("target_nm") == op["target_nm"]]
            if len(hits) != 1:
                raise ValueError(f"대상 '{op['target_nm']}'이 {len(hits)}건입니다")
            hits[0]["target_type_cd"] = op["target_type_cd"]
        elif kind in ("ADD_CONDITION", "ADD_RULE_CONDITION"):
            condition = copy.deepcopy(op["condition"])
            for item in condition.get("evidence", []):
                added.append(item["quote_txt"])
            if kind == "ADD_CONDITION":
                out.setdefault("conditions", []).append(condition)
            else:
                rule = next((r for r in out.get("rules", []) if r["rule_key"] == op["rule_key"]), None)
                if rule is None:
                    raise ValueError(f"없는 규칙입니다: {op['rule_key']}")
                rule.setdefault("conditions", []).append(condition)
        elif kind == "DROP_RELATION":
            if not op.get("reason"):
                raise ValueError("관계 제외 사유가 필요합니다")
            kept = [r for r in out.get("relations", []) if r.get("relation_key") != op["relation_key"]]
            if len(kept) == len(out.get("relations", [])):
                raise ValueError(f"없는 관계입니다: {op['relation_key']}")
            out["relations"] = kept
        elif kind == "ADD_RELATION":
            relation = copy.deepcopy(op["relation"])
            if any(r.get("relation_key") == relation["relation_key"] for r in out.get("relations", [])):
                raise ValueError(f"관계 키가 이미 있습니다: {relation['relation_key']}")
            out.setdefault("relations", []).append(relation)
            quote("REL", relation["relation_key"], op["quote_txt"])
    BenefitItem.model_validate(out)      # 추출 스키마를 그대로 통과해야 한다(보정으로 형식을 넓히지 않음)
    return out, list(dict.fromkeys(added))


def provenance(patch: dict) -> dict:
    """등록 항목 item_data에 남길 보정 출처."""
    return {"patch_id": patch["patch_id"], "ledger": patch["ledger"], "status": patch["status"],
            "ops": [op["op"] for op in patch["ops"]], "reason": patch["reason"]}
