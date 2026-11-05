"""현재 PostgreSQL 전체 상품·혜택을 ``dp_`` 그래프로 변환해 검증한다. Neo4j에 접속하지 않는다.

라벨은 PostgreSQL 테이블명에 ``dp_`` 를 붙이고, 식별자는 실제 PK를 그대로 쓴다. 연결 테이블은 관계로 표현한다.
임베딩과 검색 텍스트는 옮기지 않는다. 원천을 해석할 수 없으면 건너뛰지 않고 모두 모아
``GraphValidationError`` 로 중단한다. 예상 건수는 고정값이 아니라 원천 행에서 따로 계산해 대조한다.
"""
# 주의: 위 모듈 docstring은 main()의 argparse description(--help 출력)으로 쓰이므로 내용을 바꾸지 않았다.
#
# [등록 파이프라인에서의 위치] 4단계 "PostgreSQL → Neo4j 적재"의 변환·검증부. 적재(쓰기)는 neo4j_load_draft.py가 한다.
#
# 처리 흐름
#     load_snapshot(conn) : REPEATABLE READ READ ONLY 트랜잭션 하나에서 원천 테이블 전체를 읽는다(일관된 스냅샷).
#                           card_product_item은 BENEFIT(혜택)와 그 밖(연회비 등 items)으로 나눠 읽고,
#                           혜택은 이전 card_bnft 컬럼명 별칭으로 바꿔 그래프 key가 유지되게 한다.
#     build(snapshot)     : 원천 행 → Preview(nodes, edges). 노드 key = JSON 배열 [라벨, PK...].
#                           부모가 없는 행(고아)·해석 불가 JSON은 건너뛰지 않고 errors에 모은 뒤 한 번에 중단한다.
#                           expected_counts(원천 행에서 직접 센 건수)와 변환 건수를 대조한다.
#     main()              : --dry-run 필수. 변환 통계와 스냅샷 해시를 출력한다(neo4j_writes=0).
#
# 테이블 → 노드/관계 매핑(라벨은 dp_ 접두사)
#     card_product, card_doc, card_doc_page, card_doc_chunk, card_source_evidence(연결된 근거만), card_common,
#     card_common_bnft → 같은 이름 노드 / card_product_item BENEFIT → dp_card_bnft, 그 밖 → dp_card_product_item
#     rule_list[] → dp_bnft_rule, target_list[] → dp_rule_target(카드 간 공유), cond_expr → dp_cond_expr/branch/atom
#     card_product_doc·card_common_doc → has_document, card_common_bnft_apply → has_common_benefit,
#     card_evidence_link → supported_by, brand_bnft_compare 결과 SAME → same_as
#     (근거 주체 CARD→상품, BNFT·REL→혜택, RULE→규칙, ITEM→혜택 외 항목. REL은 혜택 relation_list의 relation_key가 있어야 한다)
#
# 호출하는 곳: neo4j_load_draft.py, neo4j_validate.py, test_neo4j_dry_run.py
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from common.postgres_db_session import PostgresDbSession

from .common_benefit_service import compare_brand_bnft

PREFIX = "dp_"
COMMON_LABEL = "dp_node"                                    # dp_ 전체를 가리키는 보조 라벨. 내부 key 고유 제약에 쓴다.
SEARCH_COLUMNS = ("bnft_search_txt", "bnft_embedding")      # 그래프 원본이 아닌 검색용 컬럼
MAPPER_ROOT = Path(__file__).resolve().parent

# 라벨별 식별 속성. 테이블은 PostgreSQL PK, JSONB에서 나온 노드는 소유자 PK와 JSON 내부 키로 만든다.
PK_FIELDS = {
    "card_product": ("card_id",),
    "card_bnft": ("card_id", "card_bnft_id"),
    "card_common": ("card_common_id",),
    "card_common_bnft": ("card_common_id", "card_common_bnft_id"),
    "card_doc": ("card_doc_id",),
    "card_doc_page": ("card_doc_id", "page_no"),
    "card_doc_chunk": ("card_doc_id", "page_no", "card_doc_chunk_id"),
    "card_source_evidence": ("evidence_id",),
    "bnft_rule": ("card_id", "card_bnft_id", "rule_key"),
    # 혜택이 아닌 카드 상품 항목(연회비 등). 혜택 노드는 기존 card_bnft key를 유지하고 라벨만 추가한다(neo4j_load_draft).
    "card_product_item": ("card_id", "card_product_item_id"),
    "rule_target": ("target_type_cd", "target_key"),
    "cond_expr": ("expr_key",),
    "cond_branch": ("expr_key", "branch_no"),
    "cond_atom": ("expr_key", "branch_no", "atom_key"),
}


class GraphValidationError(ValueError):
    """원천을 그래프로 옮길 수 없는 항목 목록."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def key(label, *parts):
    """라벨과 PK 값으로 만든 내부 key. JSON 배열이라 구분자 충돌이 없다."""
    return canonical([label, *parts])


class Preview:
    """메모리상의 그래프. ``nodes`` 는 {key: 노드}, ``edges`` 는 {key: 관계}이며 Neo4j에 접속하지 않는다."""

    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def node(self, label, parts, data):
        """노드를 추가하고 key를 반환한다. 같은 key가 같은 내용이면 재사용, 다른 내용이면 ValueError.

        Args:
            label: dp_ 접두사 없는 라벨(PK_FIELDS의 키).
            parts: PK 값 목록. PK_FIELDS[label]과 개수가 같아야 한다.
            data: 원천 행 또는 JSON 조각. ``source_json`` 으로 그대로 보관한다.
        """
        fields = PK_FIELDS.get(label)
        if fields is None or len(fields) != len(parts):
            raise ValueError(f"PK 정의와 다른 노드: {label} {parts}")
        k = key(label, *parts)
        entry = {"label": PREFIX + label, "key": k, "pk": dict(zip(fields, parts)), "source_json": canonical(data)}
        if k in self.nodes and self.nodes[k] != entry:
            raise ValueError(f"conflicting node: {k}")
        self.nodes[k] = entry
        return k

    def edge(self, kind, start, end, source):
        """관계를 추가한다. key는 (유형, 시작 key, 끝 key, 원천 데이터)로 만들며 같은 관계를 두 번 넣으면 ValueError."""
        k =key("relationship", kind, start, end, source)
        if k in self.edges:
            raise ValueError(f"duplicate edge: {k}")
        self.edges[k] = {"type": PREFIX + kind, "start": start, "end": end, "source_json": canonical(source)}

    def validate(self):
        """끝점 노드가 없는 관계(dangling)가 있으면 ValueError. 라벨·유형별 건수와 고립 노드 목록을 반환한다."""
        dangling =[k for k, e in self.edges.items()
                    if e["start"] not in self.nodes or e["end"] not in self.nodes]
        if dangling:
            raise ValueError(f"dangling edges: {len(dangling)}")
        connected = {k for e in self.edges.values() for k in (e["start"], e["end"])}
        return {"nodes": dict(sorted(Counter(n["label"] for n in self.nodes.values()).items())),
                "relationships": dict(sorted(Counter(e["type"] for e in self.edges.values()).items())),
                "node_total": len(self.nodes), "relationship_total": len(self.edges),
                "dangling_edges": len(dangling), "isolated_nodes": sorted(set(self.nodes) - connected)}


def load_snapshot(conn):
    """한 스냅샷에서 전체 원천 행을 읽는다. 쓰기는 하지 않는다."""
    brand_sql = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")._query(
        "common_benefit_repository.brand_bnft_compare").sql
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        out = {}
        queries = {
            "products": "SELECT * FROM db_pipeline.card_product ORDER BY card_id",
            "product_docs": "SELECT * FROM db_pipeline.card_product_doc ORDER BY card_id, card_doc_id",
            # 카드 혜택 원천은 card_product_item(BENEFIT). 그래프 매핑은 기존 card_bnft 필드명을 쓴다.
            "benefits": ("SELECT card_id, card_product_item_id AS card_bnft_id, item_cd AS bnft_cd, item_nm AS bnft_nm, "
                         "item_subtype_cd AS bnft_type_cd, item_origin_cd AS bnft_origin_cd, item_scope_cd AS bnft_scope_cd, "
                         "item_brand_opt_cds AS bnft_brand_opt_cds, item_cond_expr AS bnft_cond_expr, rule_list, relation_list, "
                         "verification_status_cd, item_valid_from AS bnft_valid_from, item_valid_to_excl AS bnft_valid_to_excl, "
                         "item_rule_txt AS bnft_rule_txt, item_limit_txt AS bnft_limit_txt, item_search_txt AS bnft_search_txt, "
                         "item_embedding AS bnft_embedding "
                         "FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT' ORDER BY card_id, card_product_item_id"),
            # Neo4j 관계 속성은 ev_link_id를 유지한다(재적재 전까지). 승계한 문서·페이지·청크 ID는 원문 근거 노드 경로로 이미 표현된다.
            # 관계 key가 원천 행으로 만들어지므로 기존 필드명(card_bnft_id)을 유지한다.
            "links": ("SELECT card_id, evidence_link_id AS ev_link_id, ev_subject_cd, card_product_item_id AS card_bnft_id, rule_key, relation_key, "
                      "ev_item_cd, ev_item_key, evidence_id FROM db_pipeline.card_evidence_link ORDER BY card_id, evidence_link_id"),
            "items": ("SELECT card_id, card_product_item_id, item_type_cd, item_cd, item_nm, item_scope_cd, item_brand_opt_cds, "
                      "item_data, verification_status_cd, item_valid_from, item_valid_to_excl, item_rule_txt, item_limit_txt "
                      "FROM db_pipeline.card_product_item WHERE item_type_cd <> 'BENEFIT' ORDER BY card_id, card_product_item_id"),
            "evidence": "SELECT * FROM db_pipeline.card_source_evidence ORDER BY evidence_id",
            "chunks": "SELECT * FROM db_pipeline.card_doc_chunk ORDER BY card_doc_id, page_no, card_doc_chunk_id",
            "pages": "SELECT * FROM db_pipeline.card_doc_page ORDER BY card_doc_id, page_no",
            "documents": "SELECT * FROM db_pipeline.card_doc ORDER BY card_doc_id",
            "commons": "SELECT * FROM db_pipeline.card_common ORDER BY card_common_id",
            "common_docs": "SELECT * FROM db_pipeline.card_common_doc ORDER BY card_common_id, card_doc_id",
            "common_benefits": "SELECT * FROM db_pipeline.card_common_bnft ORDER BY card_common_id, card_common_bnft_id",
            "common_applies": "SELECT * FROM db_pipeline.card_common_bnft_apply ORDER BY card_common_id, card_common_bnft_id, card_id",
        }
        for name, sql in queries.items():
            cur.execute(sql)
            out[name] = cur.fetchall()
        for name in ("benefits", "common_benefits"):
            for row in out[name]:
                for column in SEARCH_COLUMNS:
                    row.pop(column, None)
        cur.execute(brand_sql)
        compared = []
        for row in cur.fetchall():
            status, issues = compare_brand_bnft(row)
            compared.append({"card_id": row["card_id"], "card_bnft_id": row["card_bnft_id"], "bnft_cd": row["bnft_cd"],
                             "card_common_id": row["card_common_id"], "card_common_bnft_id": row["card_common_bnft_id"],
                             "status": status, "issues": issues})
        out["brand_compare"] = compared
        return out


def expr_key(*owner) -> str:
    """조건식 식별값. 소유자의 PK로 만든다."""
    return ":".join(str(part) for part in owner)


def expressions_of(snapshot):
    """조건식 소유자별 ``(소유자 조각, 조건식)``."""
    found = [(("CARD", row["card_id"]), row.get("card_cond_expr")) for row in snapshot["products"]]
    for row in snapshot["benefits"]:
        found.append((("BNFT", row["card_id"], row["card_bnft_id"]), row.get("bnft_cond_expr")))
        for rule in row.get("rule_list") or []:
            found.append((("RULE", row["card_id"], row["card_bnft_id"], rule.get("rule_key")), rule.get("cond_expr")))
    return [item for item in found if item[1] is not None]


def linked_evidence(snapshot):
    """등록된 카드·혜택·규칙에 연결(card_evidence_link)된 원문 근거만 그래프에 올린다.

    연결이 없는 근거는 아직 등록되지 않은 추출 후보(card_extr_stg, 검토 대기)의 인용이다. 그래프에 올리면 주체 없는
    근거 노드가 되고(orphan_nodes 규칙 위반), 검토 전 후보를 확정 데이터처럼 보이게 한다. 건수만 보고한다.
    """
    linked = {link["evidence_id"] for link in snapshot["links"]}
    return [row for row in snapshot["evidence"] if row["evidence_id"] in linked]


def expected_counts(snapshot) -> tuple[dict, dict]:
    """그래프를 만들지 않고 원천 행만으로 예상 건수를 계산한다."""
    rules = [rule for row in snapshot["benefits"] for rule in row.get("rule_list") or []]
    targets = [target for rule in rules for target in rule.get("target_list") or []]
    expressions = [expression for _, expression in expressions_of(snapshot)]
    branches = [branch for expression in expressions for branch in expression.get("branches", [])]
    atoms = [atom for branch in branches for atom in branch.get("atoms", [])]
    nodes = {"card_product": len(snapshot["products"]), "card_doc": len(snapshot["documents"]), "card_doc_page": len(snapshot["pages"]),
             "card_doc_chunk": len(snapshot["chunks"]), "card_source_evidence": len(linked_evidence(snapshot)),
             "card_bnft": len(snapshot["benefits"]), "bnft_rule": len(rules),
             "rule_target": len({(t.get("target_type_cd"), t.get("target_key")) for t in targets}),
             "cond_expr": len(expressions), "cond_branch": len(branches), "cond_atom": len(atoms),
             "card_common": len(snapshot["commons"]), "card_common_bnft": len(snapshot["common_benefits"]),
             "card_product_item": len(snapshot.get("items", []))}
    relationships = {"has_document": len(snapshot["product_docs"]) + len(snapshot["common_docs"]),
                     "has_benefit": len(snapshot["benefits"]), "has_rule": len(rules), "targets": len(targets),
                     "has_expr": len(expressions), "has_branch": len(branches), "has_atom": len(atoms),
                     "supported_by": len(snapshot["links"]), "in_chunk": len(linked_evidence(snapshot)),
                     "on_page": len(snapshot["chunks"]), "in_document": len(snapshot["pages"]),
                     "has_common_benefit": len(snapshot["common_applies"]), "belongs_to": len(snapshot["common_benefits"]),
                     "same_as": sum(row["status"] == "SAME" for row in snapshot["brand_compare"]),
                     "related_to": sum(len(row.get("relation_list") or []) for row in snapshot["benefits"]),
                     "has_item": len(snapshot.get("items", []))}
    return ({PREFIX + name: count for name, count in nodes.items() if count},
            {PREFIX + name: count for name, count in relationships.items() if count})


def build(snapshot):
    """원천 스냅샷을 dp_ 그래프로 변환하고 검증한다. DB에 접속하지 않는다.

    변환 순서: 상품(+조건식) → 문서 → 상품·문서 관계 → 페이지 → 청크 → 연결된 근거 → 혜택(+조건식·규칙·대상)
    → 혜택 외 상품 항목 → 공통서비스·문서·공통 혜택·적용 → 동일성(same_as) → 근거 연결(supported_by)
    → 건수·JSON 원본 대조.

    Returns:
        (Preview 그래프, 통계 dict)

    Raises:
        GraphValidationError: 변환·검증 오류를 모두 모은 목록.
    """
    g = Preview()
    errors: list[str] = []
    products, docs, pages, chunks, evidence, benefits, rules, commons, common_benefits = {}, {}, {}, {}, {}, {}, {}, {}, {}
    items = {}
    relations: dict[tuple, set] = {}     # 혜택별 relation_key(관계 근거 REL 연결 확인용)

    def expression(owner, owner_key, expr, label):
        if expr is None:
            return
        try:
            ek = expr_key(*owner_key)
            ex = g.node("cond_expr", [ek], expr)
            g.edge("has_expr", owner, ex, {})
            for branch in expr["branches"]:
                b = g.node("cond_branch", [ek, branch["branch_no"]], branch)
                g.edge("has_branch", ex, b, {})
                for atom in branch["atoms"]:
                    a = g.node("cond_atom", [ek, branch["branch_no"], atom["atom_key"]], atom)
                    g.edge("has_atom", b, a, {"atom_seq": atom["atom_seq"]})
        except (KeyError, TypeError) as error:
            errors.append(f"조건식 해석 실패 {label}: {type(error).__name__} {error}")

    # region 문서 계층: 상품 → 문서 → 페이지 → 청크 → 원문 근거
    for row in snapshot["products"]:
        if row["card_cond_status_cd"] != "DRAFT":
            errors.append(f"DRAFT가 아닌 카드 조건: {row['card_id']}")
        products[row["card_id"]] = g.node("card_product", [row["card_id"]], row)
        expression(products[row["card_id"]], ("CARD", row["card_id"]), row.get("card_cond_expr"), f"card {row['card_id']}")
    for row in snapshot["documents"]:
        docs[row["card_doc_id"]] = g.node("card_doc", [row["card_doc_id"]], row)
    for row in snapshot["product_docs"]:
        if row["card_id"] in products and row["card_doc_id"] in docs:
            g.edge("has_document", products[row["card_id"]], docs[row["card_doc_id"]], row)
        else:
            errors.append(f"상품·문서 관계 대상 없음: {row['card_id']}/{row['card_doc_id']}")
    for row in snapshot["pages"]:
        page = (row["card_doc_id"], row["page_no"])
        if row["card_doc_id"] not in docs:
            errors.append(f"페이지의 문서 없음: {page}")
            continue
        pages[page] = g.node("card_doc_page", [*page], row)
        g.edge("in_document", pages[page], docs[row["card_doc_id"]], {})
    for row in snapshot["chunks"]:
        page = (row["card_doc_id"], row["page_no"])
        if page not in pages:
            errors.append(f"청크의 페이지 없음: {row['card_doc_chunk_id']}")
            continue
        chunk = (*page, row["card_doc_chunk_id"])
        chunks[chunk] = g.node("card_doc_chunk", [*chunk], row)
        g.edge("on_page", chunks[chunk], pages[page], {})
    for row in linked_evidence(snapshot):
        chunk = (row["card_doc_id"], row["page_no"], row["card_doc_chunk_id"])
        if chunk not in chunks:
            errors.append(f"근거의 청크 없음: {row['evidence_id']}")
            continue
        evidence[row["evidence_id"]] = g.node("card_source_evidence", [row["evidence_id"]], row)
        g.edge("in_chunk", evidence[row["evidence_id"]], chunks[chunk], {})
    # endregion

    # region 혜택 계층: 카드 혜택 → 규칙 → 대상, 조건식 / 혜택 외 상품 항목(연회비 등)
    for row in snapshot["benefits"]:
        card_id, bnft_id = row["card_id"], row["card_bnft_id"]
        if card_id not in products:
            errors.append(f"혜택의 상품 없음: {card_id}/{bnft_id}")
            continue
        b = g.node("card_bnft", [card_id, bnft_id], row)
        benefits[(card_id, bnft_id)] = b
        relations[(card_id, bnft_id)] = {rel.get("relation_key") for rel in row.get("relation_list") or []}
        g.edge("has_benefit", products[card_id], b, {})
        expression(b, ("BNFT", card_id, bnft_id), row.get("bnft_cond_expr"), f"benefit {bnft_id}")
        for rule in row.get("rule_list") or []:
            try:
                rule_key = rule["rule_key"]
                r = g.node("bnft_rule", [card_id, bnft_id, rule_key], rule)
                g.edge("has_rule", b, r, {})
                rules[(card_id, bnft_id, rule_key)] = r
                expression(r, ("RULE", card_id, bnft_id, rule_key), rule.get("cond_expr"), f"rule {bnft_id}/{rule_key}")
                for target in rule.get("target_list") or []:
                    # 이용처는 카드 사이에 공유한다. 같은 대상에서 여러 카드로 역탐색하기 위해서다.
                    t = g.node("rule_target", [target["target_type_cd"], target["target_key"]],
                               {name: target[name] for name in ("target_type_cd", "target_key", "target_nm")})
                    g.edge("targets", r, t, target)
            except KeyError as error:
                errors.append(f"규칙 해석 실패 {bnft_id}: 필드 {error}")

    # 모든 혜택 노드를 만든 뒤 원천 관계를 연결한다. 같은 카드의 대상만 허용한다.
    for row in snapshot["benefits"]:
        source = benefits.get((row["card_id"], row["card_bnft_id"]))
        for relation in row.get("relation_list") or []:
            target_id = relation.get("to_bnft_id")
            target = benefits.get((row["card_id"], target_id))
            if source is None or target is None:
                errors.append(f"혜택 관계 대상 없음: {row['card_id']}/{row['card_bnft_id']}/{relation.get('relation_key')} -> {target_id}")
                continue
            g.edge("related_to", source, target, relation)

    for row in snapshot.get("items", []):
        card_id, item_id = row["card_id"], row["card_product_item_id"]
        if card_id not in products:
            errors.append(f"상품 항목의 상품 없음: {card_id}/{item_id}")
            continue
        items[(card_id, item_id)] = g.node("card_product_item", [card_id, item_id], row)
        g.edge("has_item", products[card_id], items[(card_id, item_id)], {"item_type_cd": row["item_type_cd"]})
    # endregion

    # region 공통서비스 계층과 근거 연결
    for row in snapshot["commons"]:
        commons[row["card_common_id"]] = g.node("card_common", [row["card_common_id"]], row)
    for row in snapshot["common_docs"]:
        if row["card_common_id"] not in commons or row["card_doc_id"] not in docs:
            errors.append(f"공통서비스·문서 관계 대상 없음: {row['card_common_id']}/{row['card_doc_id']}")
            continue
        g.edge("has_document", commons[row["card_common_id"]], docs[row["card_doc_id"]], row)
    for row in snapshot["common_benefits"]:
        pair = (row["card_common_id"], row["card_common_bnft_id"])
        if row["card_common_id"] not in commons:
            errors.append(f"공통 혜택의 공통서비스 없음: {pair}")
            continue
        common_benefits[pair] = g.node("card_common_bnft", [*pair], row)
        g.edge("belongs_to", common_benefits[pair], commons[row["card_common_id"]], {})
    for row in snapshot["common_applies"]:
        pair = (row["card_common_id"], row["card_common_bnft_id"])
        if pair not in common_benefits or row["card_id"] not in products:
            errors.append(f"공통 혜택 적용 대상 없음: {pair}/{row['card_id']}")
            continue
        g.edge("has_common_benefit", products[row["card_id"]], common_benefits[pair], row)
    # 동일성이 SAME으로 확인된 행만 연결한다. REVIEW·NO_COMMON은 연결하지 않고 통계로 보고한다.
    for row in snapshot["brand_compare"]:
        if row["status"] == "SAME":
            start = benefits.get((row["card_id"], row["card_bnft_id"]))
            end = common_benefits.get((row["card_common_id"], row["card_common_bnft_id"]))
            if start is None or end is None:
                errors.append(f"동일성 대상 없음: {row['card_bnft_id']}")
                continue
            g.edge("same_as", start, end, row)

    for link in snapshot["links"]:
        subject = link["ev_subject_cd"]
        if subject == "CARD":
            owner = products.get(link["card_id"])
        elif subject == "BNFT":
            owner = benefits.get((link["card_id"], link["card_bnft_id"]))
        elif subject == "RULE":
            owner = rules.get((link["card_id"], link["card_bnft_id"], link["rule_key"]))
        elif subject == "ITEM":
            owner = items.get((link["card_id"], link["card_bnft_id"]))
        elif subject == "REL":
            # 혜택 간 관계(relation_list)는 혜택 노드 source_json 안에 있고 별도 노드가 아니다. 관계 근거는 그 혜택 노드에
            # 연결하고, 연결 행(relation_key 포함)을 관계 원본으로 둔다. 혜택에 없는 relation_key면 대상 없음으로 본다.
            relation_keys = relations.get((link["card_id"], link["card_bnft_id"]), set())
            owner = benefits.get((link["card_id"], link["card_bnft_id"])) if link.get("relation_key") in relation_keys else None
        else:
            errors.append(f"지원하지 않는 근거 주체: {subject} {link['ev_link_id']}")
            continue
        if owner is None or link["evidence_id"] not in evidence:
            errors.append(f"근거 연결 대상 없음: {link['ev_link_id']}")
            continue
        g.edge("supported_by", owner, evidence[link["evidence_id"]], link)
    # endregion

    # region 사후 검증: 끝점·건수·JSON 원본 대조
    stats = g.validate()
    node_counts, relationship_counts = expected_counts(snapshot)
    if not errors and (stats["nodes"] != node_counts or stats["relationships"] != relationship_counts):
        errors.append(f"원천 건수 불일치: 예상 {node_counts} {relationship_counts}, 변환 {stats['nodes']} {stats['relationships']}")
    if not errors:
        for row in snapshot["benefits"]:
            for rule in row.get("rule_list") or []:
                stored = g.nodes[key("bnft_rule", row["card_id"], row["card_bnft_id"], rule["rule_key"])]["source_json"]
                if json.loads(stored) != json.loads(canonical(rule)):
                    errors.append(f"규칙 JSON 불일치: {row['card_bnft_id']}/{rule['rule_key']}")
        for owner_key, expr in expressions_of(snapshot):
            stored = g.nodes[key("cond_expr", expr_key(*owner_key))]["source_json"]
            if json.loads(stored) != json.loads(canonical(expr)):
                errors.append(f"조건식 JSON 불일치: {owner_key}")
    if errors:
        raise GraphValidationError(errors)
    stats["expected"] = {"nodes": node_counts, "relationships": relationship_counts}
    # 그래프에 올리지 않은 근거(등록 전 추출 후보의 인용). 건수와 ID만 보고한다.
    stats["unlinked_evidence"] = sorted({row["evidence_id"] for row in snapshot["evidence"]} - set(evidence))
    stats["common_benefits_without_direct_evidence"] = [row["card_common_bnft_id"] for row in snapshot["common_benefits"]]
    stats["brand_compare"] = [{name: row[name] for name in ("card_bnft_id", "card_common_bnft_id", "status", "issues")}
                              for row in snapshot["brand_compare"]]
    # endregion
    return g, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
        graph, stats = build(snapshot)
    stats["snapshot_sha256"] = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
    stats["neo4j_writes"] = 0
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
