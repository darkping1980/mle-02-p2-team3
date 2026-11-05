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
    SET_RULE_TARGETS    {"rule_key", "target_nms"}                           규칙 대상을 혜택 대상의 일부로 한정
    SPLIT_RULE          {"rule_key", "source_conditions": "COPY"|"DROP", "reason"?,
                         "into": [{"rule_key", "target_nms", "drop_min_txn"?}]}
                                                                             규칙 하나를 대상 묶음별 규칙으로 나눔(값·단위는 원 규칙 그대로,
                                                                             원 규칙의 값 근거는 새 규칙마다 같은 인용으로 둠).
                                                                             원 규칙 조건을 버릴 때(DROP)는 사유가 필요하다
    DROP_RULE           {"rule_key", "reason"}                               같은 값의 중복 규칙 제외(예: 한도 구간별로 복제된 규칙)
    MOVE_CONDITION      {"cond_key", "rule_keys", "for_targets"}             혜택 공통 조건을 지정한 규칙으로만 옮김.
                                                                             for_targets는 그 규칙들의 대상 합과 같아야 한다
    SET_LIMIT_TIERS     {"table_quote", "basis_cd", "tiers", "columns", "own_column", "shared"?}
                                                                             원문 한도 표를 구간·열 단위로 검증해 기록(공유 한도 포함)

규칙 대상 한정(SET_RULE_TARGETS·SPLIT_RULE)을 쓰면 모든 규칙의 대상이 정해져야 하고, 규칙 대상들의 합은 혜택 대상과
빠짐·겹침 없이 같아야 한다. 특정 카드에 의존하지 않는다. 어느 실행·후보든 대장에 적힌 보정만 적용한다.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .extraction_schema import BenefitItem

KIND = "BENEFIT_REVIEW_PATCH"
APPROVED = "APPROVED"
DRAFT = "DRAFT_PENDING_USER_REVIEW"
OPS = ("ADD_EVIDENCE", "SET_TARGET_TYPE", "ADD_CONDITION", "ADD_RULE_CONDITION", "ADD_RELATION", "DROP_RELATION",
       "SET_RULE_TARGETS", "SPLIT_RULE", "DROP_RULE", "MOVE_CONDITION", "SET_LIMIT_TIERS")
LIMIT_TIERS_VER = "LIMIT_TIERS_V1"
AMOUNT_CELL = re.compile(r"\d[\d,]*\s*(?:만\s*)?(?:천\s*)?원")


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


def _amount(text: str) -> int:
    """'3,000원'·'5천원'·'50만원' 금액 표기 하나를 원 단위 정수로 읽는다. 하나로 읽히지 않으면 오류."""
    from .extraction_service import amounts_in
    values = amounts_in(text)
    if len(values) != 1:
        raise ValueError(f"금액 표기를 하나로 읽을 수 없습니다: {text!r}")
    return next(iter(values))


def check_limit_tiers(spec: dict, bnft_nm: str) -> dict:
    """SET_LIMIT_TIERS 명세를 원문 표(table_quote)와 대조해 검사하고, 저장 형태(item_data.limit_tiers)를 만든다.

    표 원문은 '열 이름들 → (구간 표기 → 그 구간의 금액 칸들)' 순서여야 한다. 구간마다 금액 칸을 열 순서대로 읽으며,
    병합 칸(merged_cell) 열은 첫 구간에만 칸이 있고 모든 구간에 같은 값이어야 한다. 칸 수·순서·값이 하나라도 다르면 오류.
    """
    table = spec.get("table_quote") or ""
    tiers, columns = spec.get("tiers") or [], spec.get("columns") or []
    if not table or not tiers or not columns:
        raise ValueError("한도 표 원문·구간·열이 모두 필요합니다")
    keys = [t["tier_key"] for t in tiers]
    if len(keys) != len(set(keys)):
        raise ValueError("한도 구간 키가 중복입니다")
    # 열 이름은 첫 구간 표기보다 앞에 원문 순서대로 있어야 한다.
    head_end = table.find(tiers[0]["label"])
    if head_end < 0:
        raise ValueError(f"구간 표기가 표 원문에 없습니다: {tiers[0]['label']}")
    cursor = 0
    for column in columns:
        found = table.find(column["column"], cursor, head_end)
        if found < 0:
            raise ValueError(f"한도 열 이름이 표 머리에 원문 순서대로 없습니다: {column['column']}")
        cursor = found + len(column["column"])
        if set(column["caps"]) != set(keys):
            raise ValueError(f"모든 구간의 한도가 필요합니다: {column['column']}")
    # 구간 표기 → 그 구간의 금액 칸
    starts = []
    cursor = 0
    previous_max = None
    for n, tier in enumerate(tiers):
        found = table.find(tier["label"], cursor)
        if found < 0:
            raise ValueError(f"구간 표기가 표 원문에 원문 순서대로 없습니다: {tier['label']}")
        starts.append(found)
        cursor = found + len(tier["label"])
        written = sorted(_amount(x) for x in re.findall(r"\d[\d,]*\s*만\s*원", tier["label"]))
        bounds = sorted(x for x in (tier.get("min_amt"), tier.get("max_amt_excl")) if x is not None)
        if written != bounds:
            raise ValueError(f"구간 금액이 표기와 다릅니다: {tier['label']}")
        if n and tier.get("min_amt") != previous_max:
            raise ValueError("한도 구간이 이어지지 않습니다")
        previous_max = tier.get("max_amt_excl")
    for n, tier in enumerate(tiers):
        row = table[starts[n] + len(tier["label"]): starts[n + 1] if n + 1 < len(tiers) else len(table)]
        cells = [c.strip() for c in AMOUNT_CELL.findall(row)]
        expected = [c["caps"][tier["tier_key"]] for c in columns if n == 0 or not c.get("merged_cell")]
        if [re.sub(r"\s", "", c) for c in cells] != [re.sub(r"\s", "", c) for c in expected]:
            raise ValueError(f"구간 '{tier['label']}'의 한도 칸이 표 원문과 다릅니다: {cells} != {expected}")
    for column in columns:
        if column.get("merged_cell") and len({column["caps"][k] for k in keys}) != 1:
            raise ValueError(f"병합 칸 열은 모든 구간의 값이 같아야 합니다: {column['column']}")

    def caps(column):
        return {k: {"raw": column["caps"][k], "amount": _amount(column["caps"][k])} for k in keys}

    by_name = {c["column"]: c for c in columns}
    if spec.get("own_column") not in by_name:
        raise ValueError("이 혜택의 한도 열(own_column)이 표에 없습니다")
    shared = []
    for group in spec.get("shared") or []:
        members = group.get("member_benefit_nms") or []
        if group.get("column") not in by_name or group["column"] == spec["own_column"]:
            raise ValueError("공유 한도 열이 표에 없거나 이 혜택의 열과 같습니다")
        if bnft_nm not in members or len(set(members)) < 2:
            raise ValueError("공유 한도에는 이 혜택을 포함한 두 개 이상의 혜택이 필요합니다")
        if not group.get("group_key"):
            raise ValueError("공유 한도 그룹 키가 필요합니다")
        shared.append({"group_key": group["group_key"], "column": group["column"],
                       "member_benefit_nms": sorted(set(members)), "caps": caps(by_name[group["column"]])})
    own = by_name[spec["own_column"]]
    return {"schema_ver": LIMIT_TIERS_VER, "basis_cd": spec.get("basis_cd"), "table_quote": table,
            "tiers": [{k: t.get(k) for k in ("tier_key", "label", "min_amt", "max_amt_excl")} for t in tiers],
            "own": {"column": own["column"], "merged_cell": bool(own.get("merged_cell")), "caps": caps(own)},
            "shared": shared}


def limit_tiers_text(limit_tiers: dict) -> str:
    """item_limit_txt에 붙일 한도 구간 설명. 구간 표기·열 이름·금액 표기는 모두 원문 표 그대로다."""
    lines = []
    for tier in limit_tiers["tiers"]:
        parts = [f"{limit_tiers['own']['column']} {limit_tiers['own']['caps'][tier['tier_key']]['raw']}"]
        parts += [f"{g['column']} {g['caps'][tier['tier_key']]['raw']}" for g in limit_tiers["shared"]]
        lines.append(f"{tier['label']}: " + ", ".join(parts))
    for group in limit_tiers["shared"]:
        lines.append(f"{group['column']} 공유: " + ", ".join(group["member_benefit_nms"]))
    return " / ".join(lines)


def apply_patch(raw: dict, patch: dict) -> tuple[dict, list[str], dict]:
    """추출 원본(raw) 사본에 보정을 적용한다. (보정된 원본, 새로 추가한 인용 목록, 추가 정보).

    추가 정보(extras)는 추출 스키마에 없는 정보라 원본 밖에 둔다.
        rule_targets  {rule_key: [대상 이름]}  규칙 대상을 혜택 대상의 일부로 한정(등록 형태를 만든 뒤 적용)
        limit_tiers   item_data.limit_tiers로 저장할 한도 구간(check_limit_tiers 결과) 또는 None
    결과 원본은 추출 스키마(BenefitItem)를 그대로 통과해야 한다. 입력 dict는 바꾸지 않는다.
    """
    out = copy.deepcopy(raw)
    added: list[str] = []
    extras: dict = {"rule_targets": {}, "limit_tiers": None}
    target_names = [t.get("target_nm") for t in out.get("targets", [])]

    def quote(supports: str, support_key: str | None, text: str) -> None:
        if not text:
            raise ValueError("보정 인용이 비어 있습니다")
        out.setdefault("evidence", []).append({"quote_txt": text, "supports": supports, "support_key": support_key,
                                               "link_basis": "SAME_TEXT"})
        added.append(text)

    def rule_of(key: str) -> dict:
        rule = next((r for r in out.get("rules", []) if r["rule_key"] == key), None)
        if rule is None:
            raise ValueError(f"없는 규칙입니다: {key}")
        return rule

    def chosen_targets(names: list[str]) -> list[str]:
        if not names or len(names) != len(set(names)) or any(n not in target_names for n in names):
            raise ValueError(f"규칙 대상은 혜택 대상 중에서 중복 없이 골라야 합니다: {names}")
        return list(names)

    def drop_rule_evidence(key: str) -> None:
        out["evidence"] = [e for e in out.get("evidence", [])
                           if not (e.get("supports") == "RULE" and e.get("support_key") == key)]

    for op in patch["ops"]:
        kind = op["op"]
        rule_keys = {rule["rule_key"] for rule in out.get("rules", [])}
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
                rule_of(op["rule_key"]).setdefault("conditions", []).append(condition)
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
        elif kind == "SET_RULE_TARGETS":
            rule_of(op["rule_key"])
            extras["rule_targets"][op["rule_key"]] = chosen_targets(op["target_nms"])
        elif kind == "SPLIT_RULE":
            source = rule_of(op["rule_key"])
            into = op.get("into") or []
            if len(into) < 2:
                raise ValueError("SPLIT_RULE은 두 개 이상의 규칙으로 나눠야 합니다")
            mode = op.get("source_conditions")
            if mode not in ("COPY", "DROP") or (mode == "DROP" and source.get("conditions") and not op.get("reason")):
                raise ValueError("원 규칙 조건 처리(COPY/DROP)가 필요하고, DROP이면 사유가 필요합니다")
            new_keys = [part["rule_key"] for part in into]
            if len(new_keys) != len(set(new_keys)) or set(new_keys) & (rule_keys - {op["rule_key"]}):
                raise ValueError(f"새 규칙 키가 겹칩니다: {new_keys}")
            value_evidence = [e for e in out.get("evidence", [])
                              if e.get("supports") == "RULE" and e.get("support_key") == op["rule_key"]]
            new_rules = []
            for part in into:
                rule = copy.deepcopy(source)
                rule["rule_key"] = part["rule_key"]
                rule["limit_keys"] = []          # 한도는 혜택 단위(SET_LIMIT_TIERS)로 기록한다
                if mode == "DROP":
                    rule["conditions"] = []
                else:
                    for n, condition in enumerate(rule.get("conditions", []), 1):
                        condition["cond_key"] = f"{part['rule_key']}.c{n}"[:40]
                if part.get("drop_min_txn"):
                    rule["min_txn_amt"], rule["min_txn_raw_txt"] = None, None
                new_rules.append(rule)
                extras["rule_targets"][part["rule_key"]] = chosen_targets(part["target_nms"])
            index = out["rules"].index(source)
            out["rules"][index:index + 1] = new_rules
            drop_rule_evidence(op["rule_key"])
            # 원 규칙의 값 근거를 새 규칙마다 같은 인용으로 둔다(값 검증·근거 연결이 규칙별로 이루어짐).
            out.setdefault("evidence", []).extend({**e, "support_key": key} for key in new_keys for e in value_evidence)
            extras["rule_targets"].pop(op["rule_key"], None)
        elif kind == "DROP_RULE":
            if not op.get("reason"):
                raise ValueError("규칙 제외 사유가 필요합니다")
            rule_of(op["rule_key"])
            out["rules"] = [r for r in out["rules"] if r["rule_key"] != op["rule_key"]]
            drop_rule_evidence(op["rule_key"])
            extras["rule_targets"].pop(op["rule_key"], None)
            if not out["rules"]:
                raise ValueError("규칙이 모두 제외되었습니다")
        elif kind == "MOVE_CONDITION":
            condition = next((c for c in out.get("conditions", []) if c["cond_key"] == op["cond_key"]), None)
            if condition is None:
                raise ValueError(f"없는 혜택 조건입니다: {op['cond_key']}")
            if not op.get("rule_keys") or len(op["rule_keys"]) != len(set(op["rule_keys"])):
                raise ValueError("조건을 옮길 규칙이 없거나 중복입니다")
            covered = set()
            for key in op["rule_keys"]:
                rule_of(key)
                if key not in extras["rule_targets"]:
                    raise ValueError(f"대상을 한정하지 않은 규칙으로는 조건을 옮길 수 없습니다: {key}")
                covered |= set(extras["rule_targets"][key])
            if covered != set(op.get("for_targets") or []):
                raise ValueError(f"조건 {op['cond_key']}의 적용 대상과 규칙 대상이 다릅니다: "
                                 f"{sorted(covered)} != {sorted(set(op.get('for_targets') or []))}")
            out["conditions"] = [c for c in out["conditions"] if c is not condition]
            for key in op["rule_keys"]:
                moved = copy.deepcopy(condition)
                moved["cond_key"] = f"{key}.{condition['cond_key']}"[:40]
                for item in moved.get("evidence", []):
                    item["support_key"] = moved["cond_key"]
                rule_of(key).setdefault("conditions", []).append(moved)
        elif kind == "SET_LIMIT_TIERS":
            if extras["limit_tiers"] is not None:
                raise ValueError("한도 구간은 한 번만 지정합니다")
            extras["limit_tiers"] = check_limit_tiers(op, out["bnft_nm"])
            quote("LIMIT", None, op["table_quote"])
    BenefitItem.model_validate(out)      # 추출 스키마를 그대로 통과해야 한다(보정으로 형식을 넓히지 않음)
    if extras["rule_targets"]:
        unrestricted = [r["rule_key"] for r in out["rules"] if r["rule_key"] not in extras["rule_targets"]]
        if unrestricted:
            raise ValueError(f"대상을 정하지 않은 규칙이 있습니다: {unrestricted}")
        covered = [n for names in extras["rule_targets"].values() for n in names]
        if sorted(covered) != sorted(target_names):
            raise ValueError("규칙 대상의 합이 혜택 대상과 같지 않습니다(빠지거나 겹친 대상)")
    return out, list(dict.fromkeys(added)), extras


def restrict_rule_targets(rule_list: list[dict], rule_targets: dict[str, list[str]]) -> list[dict]:
    """등록 형태 rule_list의 규칙별 target_list를 보정에서 정한 대상만 남긴다(정규화가 모든 대상을 모든 규칙에 넣으므로)."""
    if not rule_targets:
        return rule_list
    out = []
    for rule in rule_list:
        names = rule_targets.get(rule["rule_key"])
        if names is None:
            raise ValueError(f"대상을 정하지 않은 규칙이 있습니다: {rule['rule_key']}")
        kept = [t for t in rule.get("target_list", []) if t.get("target_nm") in names]
        if sorted(t["target_nm"] for t in kept) != sorted(names):
            raise ValueError(f"규칙 {rule['rule_key']}의 대상을 등록 형태에서 찾지 못했습니다")
        out.append({**rule, "target_list": kept})
    return out


def extracted_shared_members(raw: dict) -> list[frozenset[str]]:
    """추출 원본 한도 중 여러 혜택이 함께 쓰는 한도(shared_scope_txt + 두 개 이상의 applies_to_benefit_nms)의 구성원."""
    out = []
    for limit in raw.get("limits") or []:
        members = frozenset(limit.get("applies_to_benefit_nms") or [])
        if limit.get("shared_scope_txt") and len(members) >= 2 and members not in out:
            out.append(members)
    return out


def shared_limit_problems(declared: dict[str, dict | None],
                          required: list[frozenset[str]] | None = None) -> dict[str, str]:
    """공유 한도 누락·불일치 검출. declared = {혜택명: limit_tiers 또는 None} (같은 실행의 등록 대상 혜택 전체).

    1) 추출이 공유 한도라고 밝힌 혜택 묶음(required)은 구성원 모두가 그 묶음을 포함한 공유 그룹을 가져야 한다.
    2) 한 혜택이 공유 한도 그룹에 다른 혜택을 넣었다면, 그 혜택도 같은 그룹(같은 열·구간·한도·구성원)을 가져야 한다.
    Returns: {혜택명: 사유}. 그룹의 어느 쪽이든 문제가 있으면 구성원 모두를 문제로 돌려준다(한쪽만 등록되지 않게).
    """
    problems: dict[str, str] = {}
    for members in required or []:
        for member in sorted(members):
            groups_of = [set(g["member_benefit_nms"]) for g in ((declared.get(member) or {}).get("shared") or [])]
            if member not in declared or not any(members <= g for g in groups_of):
                for other in members:
                    problems.setdefault(other, f"추출 원문의 공유 한도가 기록되지 않았습니다: {member} ({', '.join(sorted(members))})")
    groups: dict[str, list[tuple[str, dict, dict]]] = {}
    for name, tiers in declared.items():
        for group in (tiers or {}).get("shared", []):
            groups.setdefault(group["group_key"], []).append((name, tiers, group))
    for group_key, owners in groups.items():
        members = {m for _, _, group in owners for m in group["member_benefit_nms"]}
        reason = None
        missing = sorted(m for m in members if m not in declared)
        lacking = sorted(m for m in members if m in declared and m not in {n for n, _, _ in owners})
        reference = owners[0]
        if missing:
            reason = f"공유 한도 상대 혜택이 등록 대상에 없습니다: {', '.join(missing)}"
        elif lacking:
            reason = f"공유 한도({reference[2]['column']}) 누락: {', '.join(lacking)}"
        else:
            for _, tiers, group in owners[1:]:
                if (group["caps"] != reference[2]["caps"] or tiers["tiers"] != reference[1]["tiers"]
                        or set(group["member_benefit_nms"]) != members or group["column"] != reference[2]["column"]):
                    reason = f"공유 한도({reference[2]['column']})의 구간·한도·구성원이 혜택마다 다릅니다"
                    break
        if reason:
            for member in members | {n for n, _, _ in owners}:
                problems[member] = f"{reason} [{group_key}]"
    return problems


def provenance(patch: dict) -> dict:
    """등록 항목 item_data에 남길 보정 출처."""
    return {"patch_id": patch["patch_id"], "ledger": patch["ledger"], "status": patch["status"],
            "ops": [op["op"] for op in patch["ops"]], "reason": patch["reason"]}
