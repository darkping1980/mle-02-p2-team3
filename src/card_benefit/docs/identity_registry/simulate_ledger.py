"""읽기 전용: 업무 식별자 대장으로 공통 혜택 등록(CommonBenefitService.register_run)을 시뮬레이션한다.

- 후보와 대장 항목은 혜택명·stg_id가 아니라 원문 근거 줄(anchor.line_sha256)과 값(value_key)으로만 대응시킨다.
- 대응이 정확히 1건일 때만 식별자를 넘긴다. 제외(excluded) 항목의 reserved_identity는 넘기지 않는다.
- 등록 SQL(write)은 가로채서 기록만 하고, 트랜잭션은 READ ONLY 후 ROLLBACK한다. API 호출 없음.
- ``--rename`` 은 모든 후보의 혜택명을 바꿔(재추출로 이름이 달라진 상황) 같은 대응이 나오는지 확인한다.

사용법(프로젝트 루트): uv run python src/card_benefit/docs/identity_registry/simulate_ledger.py HANA_MP004 [--run-id ID] [--rename]
"""
from __future__ import annotations

import argparse
import collections
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2])]
sys.stdout.reconfigure(encoding="utf-8")
from common.query_log_config import load_project_environment  # noqa: E402
from common.postgres_db_session import PostgresDbSession  # noqa: E402
from card_benefit.payment_card.db_pipeline.document_repository import MAPPER_ROOT  # noqa: E402
from card_benefit.payment_card.db_pipeline.common_benefit_service import CommonBenefitService, benefit_code  # noqa: E402

BULLETS = "·•*-‧∙ "
OWN_SUPPORTS = ("BNFT", "RULE", "TARGET", "LIMIT")


def anchor_norm(text: str | None) -> str:
    """대장 규칙 anchor_norm: NFKC → casefold → 공백 제거 → 앞쪽 글머리표 제거."""
    return "".join(unicodedata.normalize("NFKC", text or "").casefold().split()).lstrip(BULLETS)


def candidate_keys(candidate: dict, located: list[dict]) -> tuple[set[str], list[str]]:
    """후보의 위치 확인된 자기 근거 줄 해시들과 값 키."""
    raw = candidate["stg_raw_item"]
    own = {anchor_norm(e.get("quote_txt")) for e in raw.get("evidence", []) if e.get("supports") in OWN_SUPPORTS}
    lines = {hashlib.sha256(anchor_norm(e["quote_txt"]).encode()).hexdigest()
             for e in located if anchor_norm(e["quote_txt"]) in own}
    return lines, sorted(anchor_norm(r.get("value_raw_txt")) for r in raw.get("rules", []))


def match(ledger_rows: list[dict], candidates: list[dict], located: dict[str, list[dict]]) -> tuple[dict, list[str]]:
    """대장 항목 → 후보 stg_id. 0건·2건 이상은 대응하지 않고 문제로 보고한다."""
    keys = {c["card_extr_stg_id"]: candidate_keys(c, located[c["card_extr_stg_id"]]) for c in candidates}
    mapping, problems = {}, []
    for row in ledger_rows:
        a = row["anchor"]
        hits = [stg for stg, (lines, values) in keys.items() if a["line_sha256"] in lines and values == a["value_key"]]
        if len(hits) == 1:
            mapping[row["card_extr_stg_id"]] = hits[0]
        else:
            problems.append(f"{row['card_extr_stg_id']} 대응 {len(hits)}건: {hits}")
    used = collections.Counter(mapping.values())
    problems += [f"후보 {stg}가 대장 {n}건에 대응" for stg, n in used.items() if n > 1]
    return mapping, problems


class OuterSession(PostgresDbSession):
    """서비스 내부 트랜잭션을 바깥 READ ONLY 트랜잭션에 합친다."""
    @contextmanager
    def transaction(self):
        if self._active_connection is not None:
            yield self
        else:
            with super().transaction():
                yield self


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family")
    parser.add_argument("--run-id")
    parser.add_argument("--rename", action="store_true")
    args = parser.parse_args()
    ledger = json.loads((HERE / f"{args.family}.json").read_text(encoding="utf-8"))
    run_id = args.run_id or ledger["source_run_id"]
    family = ledger["doc_family_cd"]
    register, excluded = ledger["register"], ledger["excluded"]

    # 1) 대장 자체 검사: 식별자·코드 재계산, 대장 안 중복
    issues = []
    all_ids = [r["identity"] for r in register] + [r["reserved_identity"] for r in excluded]
    for r in register:
        if benefit_code(family, r["identity"]) != r["bnft_cd"]:
            issues.append(f"bnft_cd 재계산 불일치 {r['card_extr_stg_id']}")
    dup_ids = [k for k, n in collections.Counter(all_ids).items() if n > 1]
    codes = [benefit_code(family, i) for i in all_ids]
    dup_codes = [k for k, n in collections.Counter(codes).items() if n > 1]

    load_project_environment()
    session = OuterSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
    svc = CommonBenefitService(session)
    writes = []

    def fake_write(name, **params):
        writes.append((name, params))
        return [{"card_common_bnft_id": f"SIM{len(writes)}"}]

    real_one = svc.repo.one
    svc.repo.write = fake_write
    svc.repo.one = lambda name, **p: None if name == "lock_common" else real_one(name, **p)   # FOR UPDATE는 READ ONLY에서 불가
    try:
        with session.transaction():
            conn = session._active_connection
            conn.execute("SET TRANSACTION READ ONLY")
            existing = conn.execute(
                "select 'card_common_bnft' t, card_common_id::text owner, card_common_bnft_id id, bnft_cd from db_pipeline.card_common_bnft where bnft_cd = any(%s) "
                "union all select 'card_bnft', card_id::text, card_bnft_id, bnft_cd from db_pipeline.card_bnft where bnft_cd = any(%s)",
                (codes, codes)).fetchall()
            common_rows = conn.execute("select count(*) n from db_pipeline.card_common_bnft where card_common_id=%s",
                                       (ledger["card_common_id"],)).fetchone()["n"]
            candidates = svc.candidates(run_id)
            located = {c["card_extr_stg_id"]: svc._located(svc.repo.rows("candidate_evidence", STG_ID=c["card_extr_stg_id"]))
                       for c in candidates}
            mapping, problems = match(register, candidates, located)
            ex_mapping, ex_problems = match(excluded, candidates, located)
            renamed_same = None
            if args.rename:
                renamed = copy.deepcopy(candidates)
                for c in renamed:
                    c["stg_raw_item"]["bnft_nm"] = "재추출 이름 " + c["stg_raw_item"]["bnft_nm"][::-1]
                renamed_same = match(register, renamed, located)[0] == mapping
            identities = {mapping[r["card_extr_stg_id"]]: r["identity"] for r in register if r["card_extr_stg_id"] in mapping}
            decisions = svc.register_run(run_id, identities)
            conn.rollback()
    finally:
        session.database_manager.close()

    by_stg = {r["card_extr_stg_id"]: r for r in register}
    inserted = {d.stg_id: d for d in decisions if d.status == "INSERTED"}
    write_by_cd = {p["BNFT_CD"]: p for n, p in writes if n == "insert_common_bnft"}
    detail_issues = []
    for ledger_stg, cand_stg in mapping.items():
        row, d = by_stg[ledger_stg], inserted.get(cand_stg)
        if d is None:
            continue
        if d.bnft_cd != row["bnft_cd"]:
            detail_issues.append(f"{ledger_stg} bnft_cd 다름")
        if list(d.evidence_ids) != row["evidence_ids"]:
            detail_issues.append(f"{ledger_stg} 근거 ID 다름 {list(d.evidence_ids)} != {row['evidence_ids']}")
        w = write_by_cd.get(row["bnft_cd"], {})
        if (w.get("SERVICE_TYPE"), str(w.get("VALID_FROM")), str(w.get("VALID_TO"))) != (row["service_type_cd"], row["valid_from"], row["valid_to_excl"]):
            detail_issues.append(f"{ledger_stg} 선택서비스·기간 다름")

    print(f"대장 {family} run={run_id} 등록 대상 {len(register)} / 제외 {len(excluded)}")
    print(f"[대장 검사] 식별자 중복 {dup_ids or 0} / bnft_cd 중복 {dup_codes or 0} / 재계산 불일치 {issues or 0}")
    # 대장 등록 대상이 같은 공통서비스에 이미 있는 것은 등록 이후의 정상 상태다. 그 밖의 같은 코드는 충돌이다.
    register_codes = {r["bnft_cd"] for r in register}
    own = [r for r in existing if r["t"] == "card_common_bnft" and r["owner"] == str(ledger["card_common_id"]) and r["bnft_cd"] in register_codes]
    conflicts = [dict(r) for r in existing if r not in own]
    print(f"[기존 DB] 대장 등록분 {len(own)}건 / 충돌(다른 행의 같은 bnft_cd) {conflicts or 0} / 공통서비스 {ledger['card_common_id']} 기존 혜택 {common_rows}건")
    print(f"[대응] 등록 대상 {len(mapping)}/{len(register)} 대응, 기록된 stg_id와 일치 {sum(k == v for k, v in mapping.items())}건, 문제 {problems or 0}")
    print(f"[대응] 제외 항목 {len(ex_mapping)}/{len(excluded)} 대응(식별자 미전달), 문제 {ex_problems or 0}")
    if renamed_same is not None:
        print(f"[이름 변경 시험] 모든 혜택명을 바꾼 뒤 대응 결과 동일: {renamed_same}")
    print(f"[판정] {dict(collections.Counter(d.status for d in decisions))} / 가로챈 쓰기 {dict(collections.Counter(n for n, _ in writes))}")
    targeted = {mapping[s] for s in mapping}
    print(f"[판정] 대장 {len(register)}건 중 INSERTED {sum(s in inserted for s in targeted)}건, 대장 밖 INSERTED {len(set(inserted) - targeted)}건")
    for (status, reason), n in collections.Counter((d.status, d.reason) for d in decisions if d.status != "INSERTED").most_common():
        print(f"    {status:9s} {n:3d}  {reason}")
    print(f"[대장 기록과 비교] 근거 ID·bnft_cd·선택서비스·기간 불일치 {detail_issues or 0}")
    by_decision = {d.stg_id: d for d in decisions}
    for row in register:
        d = by_decision.get(mapping.get(row["card_extr_stg_id"], ""))
        values = ", ".join(v["value_raw_txt"] or "" for v in row["values"])
        print(f"  {d.status if d else 'NOT_MATCHED':9s} {row['card_extr_stg_id']} {row['identity'][:40]:40s} {row['bnft_cd'][:16]}… "
              f"type={row['service_type_cd']} 값=[{values}] 근거 {len(row['evidence_ids'])}")
    unexpected = [d for d in decisions if d.stg_id in targeted and d.status not in ("INSERTED", "UNCHANGED")]
    return 0 if not (dup_ids or dup_codes or issues or conflicts or problems or detail_issues or unexpected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
