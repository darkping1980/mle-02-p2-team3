"""PostgreSQL table-faithful read-model conversion for the project's dp_ graph."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from uuid import UUID

from psycopg.rows import dict_row

PREFIX = "dp_"
EXCLUDED_TABLES = {
    "app_log": "실행 질문·답변 로그. 요청에 따라 PostgreSQL에만 유지",
    "app_log_event_archive": "실행 로그 아카이브. 요청에 따라 PostgreSQL에만 유지",
}
RELATION_TABLE_NAMES = {
    "card_product_doc": "dp_has_document",
    "card_common_doc": "dp_has_document",
    "card_common_bnft_apply": "dp_applies_to",
    "card_evidence_link": ("dp_supported_by", None, "card_source_evidence"),
}
# The live PostgreSQL database currently declares zero FOREIGN KEY constraints.
# These links therefore follow the named FK-equivalent columns and primary keys in
# the actual table definitions; every populated reference is endpoint-checked.
MANUAL_RELATIONS = (
    ("card_product_item", ("card_id",), "card_product", ("card_id",), "dp_has_item", "parent_child"),
    ("card_common_bnft", ("card_common_id",), "card_common", ("card_common_id",), "dp_belongs_to", "child_parent"),
    ("card_doc_page", ("card_doc_id",), "card_doc", ("card_doc_id",), "dp_in_document", "child_parent"),
    ("card_doc_chunk", ("card_doc_id", "page_no"), "card_doc_page", ("card_doc_id", "page_no"), "dp_on_page", "child_parent"),
    ("card_source_evidence", ("card_doc_id", "page_no", "card_doc_chunk_id"), "card_doc_chunk",
     ("card_doc_id", "page_no", "card_doc_chunk_id"), "dp_in_chunk", "child_parent"),
    ("card_source_evidence", ("card_extr_stg_id",), "card_extr_stg", ("card_extr_stg_id",),
     "dp_from_extraction", "child_parent"),
    ("card_ai_call", ("card_ai_run_id",), "card_ai_run", ("card_ai_run_id",), "dp_called_in_run", "child_parent"),
    ("card_ai_call", ("card_doc_id", "page_no", "card_doc_chunk_id"), "card_doc_chunk",
     ("card_doc_id", "page_no", "card_doc_chunk_id"), "dp_called_on_chunk", "child_parent"),
    ("card_extr_stg", ("card_id",), "card_product", ("card_id",), "dp_extracted_for_card", "child_parent"),
    ("card_extr_stg", ("card_ai_run_id", "card_doc_id", "page_no", "card_doc_chunk_id", "call_seq"),
     "card_ai_call", ("card_ai_run_id", "card_doc_id", "page_no", "card_doc_chunk_id", "call_seq"), "dp_extracted_by_call", "child_parent"),
    ("card_extr_stg", ("stg_parent_card_extr_stg_id",), "card_extr_stg", ("card_extr_stg_id",), "dp_child_of_candidate", "child_parent"),
    ("card_ai_run", ("run_target_card_doc_id",), "card_doc", ("card_doc_id",), "dp_targets_document", "child_parent"),
    ("backup_card_bnft", ("card_id",), "card_product", ("card_id",), "dp_backup_of_card", "child_parent"),
    ("common_cd", ("common_code_grp_id",), "common_code_grp", ("common_code_grp_id",), "dp_code_in_group", "child_parent"),
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time, UUID, IPv4Address, IPv6Address, IPv4Network, IPv6Network)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if hasattr(value, "tolist"):
        return _normalize(value.tolist())
    return str(value)


def _normalize_vector(value):
    """Convert pgvector's text adapter form or array value to a float list."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            text = value.strip()
            if not (text.startswith("[") and text.endswith("]")):
                raise ValueError("embedding text is not a bracketed pgvector value")
            value = [part.strip() for part in text[1:-1].split(",")]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"unsupported pgvector value type: {type(value).__name__}")
    try:
        vector = [float(item) for item in value]
    except (TypeError, ValueError) as error:
        raise ValueError("pgvector contains a non-numeric component") from error
    if not vector:
        raise ValueError("pgvector value is empty")
    return vector


def inspect_schema(conn) -> dict:
    """Read actual db_pipeline base-table/view, column, PK and FK metadata."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT current_database() AS database,inet_server_addr()::text AS server_addr,inet_server_port() AS server_port,version() AS version")
        identity = cur.fetchone()
        cur.execute("""SELECT table_name,table_type FROM information_schema.tables
          WHERE table_schema='db_pipeline' ORDER BY table_type,table_name""")
        relations = cur.fetchall()
        cur.execute("""SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable
          FROM information_schema.columns WHERE table_schema='db_pipeline' ORDER BY table_name,ordinal_position""")
        columns = cur.fetchall()
        cur.execute("""SELECT tc.table_name,tc.constraint_name,kcu.column_name,kcu.ordinal_position
          FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu
            ON tc.constraint_catalog=kcu.constraint_catalog AND tc.constraint_schema=kcu.constraint_schema
           AND tc.constraint_name=kcu.constraint_name AND tc.table_name=kcu.table_name
          WHERE tc.table_schema='db_pipeline' AND tc.constraint_type='PRIMARY KEY'
          ORDER BY tc.table_name,tc.constraint_name,kcu.ordinal_position""")
        pk_rows = cur.fetchall()
        cur.execute("""SELECT child.relname AS table_name,con.conname AS constraint_name,
                 child_att.attname AS column_name,parent.relname AS ref_table,parent_att.attname AS ref_column,pair.ord
          FROM pg_constraint con
          JOIN pg_class child ON child.oid=con.conrelid
          JOIN pg_namespace child_ns ON child_ns.oid=child.relnamespace
          JOIN pg_class parent ON parent.oid=con.confrelid
          JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS child_key(attnum,ord) ON true
          JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS parent_key(attnum,ord) ON parent_key.ord=child_key.ord
          JOIN LATERAL (SELECT child_key.ord) AS pair ON true
          JOIN pg_attribute child_att ON child_att.attrelid=child.oid AND child_att.attnum=child_key.attnum
          JOIN pg_attribute parent_att ON parent_att.attrelid=parent.oid AND parent_att.attnum=parent_key.attnum
          WHERE child_ns.nspname='db_pipeline' AND con.contype='f'
          ORDER BY child.relname,con.conname,pair.ord""")
        fk_rows = cur.fetchall()
    col_map = {}
    for col in columns:
        col_map.setdefault(col["table_name"], []).append(col)
    pks = {}
    for row in pk_rows:
        pks.setdefault(row["table_name"], []).append(row["column_name"])
    fks = {}
    for row in fk_rows:
        key = (row["table_name"], row["constraint_name"])
        fk = fks.setdefault(key, {"table": row["table_name"], "name": row["constraint_name"],
                                  "ref_table": row["ref_table"], "columns": [], "ref_columns": []})
        fk["columns"].append(row["column_name"])
        fk["ref_columns"].append(row["ref_column"])
    return {"identity": identity, "relations": relations,
            "tables": [{"name": rel["table_name"], "type": rel["table_type"],
                        "columns": col_map.get(rel["table_name"], []), "pk": pks.get(rel["table_name"], []),
                        "fks": [fk for (table, _), fk in fks.items() if table == rel["table_name"]]}
                       for rel in relations]}


def load_snapshot(conn) -> dict:
    """Read one consistent read-only PostgreSQL snapshot for all base tables."""
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    schema = inspect_schema(conn)
    tables = [table for table in schema["tables"] if table["type"] == "BASE TABLE"]
    rows = {}
    counts = {}
    with conn.cursor(row_factory=dict_row) as cur:
        for table in tables:
            name = table["name"]
            if name in EXCLUDED_TABLES:
                continue
            if not table["pk"]:
                raise ValueError(f"db_pipeline.{name} has no declared primary key; cannot preserve node identity")
            order = ",".join('"' + col.replace('"', '""') + '"' for col in table["pk"])
            cur.execute(f'SELECT * FROM db_pipeline."{name}" ORDER BY {order}')
            rows[name] = [{k: _normalize_vector(v) if k in {"item_embedding", "bnft_embedding"}
                           else _normalize(v) for k, v in row.items()} for row in cur.fetchall()]
            counts[name] = len(rows[name])
    return {**schema, "rows": rows, "counts": counts,
            "views": [table for table in schema["tables"] if table["type"] != "BASE TABLE"],
            "excluded": EXCLUDED_TABLES.copy()}


def row_key(table: str, pk_fields: list[str], row: dict) -> str:
    return _json([table, *[row[field] for field in pk_fields]])


def _direct_props(table: dict, row: dict, key: str) -> dict:
    json_types = {"json", "jsonb"}
    props = {"key": key, "source_table": table["name"], "source_json": _json(row),
             "null_columns_json": _json([name for name, value in row.items() if value is None])}
    for column in table["columns"]:
        name, value = column["column_name"], row.get(column["column_name"])
        if value is None:
            continue
        normalized = _normalize(value)
        if column["udt_name"] in json_types or isinstance(normalized, dict):
            props[name] = _json(normalized)
        elif isinstance(normalized, list) and (not normalized or all(isinstance(x, (str, int, float, bool)) for x in normalized)):
            props[name] = normalized
        elif isinstance(normalized, (str, int, float, bool)):
            props[name] = normalized
        else:
            props[name] = _json(normalized)
    if table["name"] == "card_product_item":
        pieces = [row.get(name) for name in ("item_nm", "item_rule_txt", "item_limit_txt", "item_search_txt") if row.get(name)]
        props["search_text"] = "\n".join(str(x) for x in pieces)
        if row.get("item_embedding") is not None:
            props["embedding"] = _normalize(row["item_embedding"])
    if table["name"] == "card_common_bnft":
        pieces = [row.get(name) for name in ("bnft_nm", "bnft_rule_txt", "bnft_limit_txt") if row.get(name)]
        props["search_text"] = "\n".join(str(x) for x in pieces)
        if row.get("bnft_embedding") is not None:
            props["embedding"] = _normalize(row["bnft_embedding"])
    return props


def _relationship_type(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not value or value[0].isdigit():
        value = "R_" + value
    return PREFIX + value


def build(snapshot: dict) -> dict:
    """Build exact table-row nodes plus PK/FK-driven relationships, preserving original rows."""
    table_map = {table["name"]: table for table in snapshot["tables"] if table["type"] == "BASE TABLE"}
    rows_by_table = snapshot["rows"]
    if not rows_by_table:
        raise ValueError("PostgreSQL snapshot contains no source tables")
    missing_pk = [name for name in rows_by_table if not table_map[name]["pk"]]
    if missing_pk:
        raise ValueError(f"tables lack primary keys: {missing_pk}")
    relation_only = {name for name in RELATION_TABLE_NAMES if name in rows_by_table}
    nodes, edges, table_keys = [], [], {}
    for table_name, rows in rows_by_table.items():
        table = table_map[table_name]
        if table_name in relation_only:
            continue
        keys = {}
        for row in rows:
            key = row_key(table_name, table["pk"], row)
            keys[tuple(row.get(field) for field in table["pk"])] = key
            nodes.append({"table": table_name, "label": PREFIX + table_name, "pk_fields": table["pk"],
                          "pk": {field: row.get(field) for field in table["pk"]}, "key": key,
                          "props": _direct_props(table, row, key), "source": row})
        table_keys[table_name] = keys
    node_lookup = {node["key"]: node for node in nodes}
    edge_keys = set()

    def add_edge(rel_type: str, start: str, end: str, row: dict, source_table: str,
                 constraint: str | None = None, suffix: str = ""):
        if start not in node_lookup or end not in node_lookup:
            raise ValueError(f"unresolved FK endpoint {source_table}:{constraint}: {start} -> {end}")
        signature = _json([source_table, row, constraint, rel_type, start, end, suffix])
        key = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        if key in edge_keys:
            raise ValueError(f"duplicate relationship derived from source row {source_table}/{constraint}")
        edge_keys.add(key)
        props = {"key": key, "source_table": source_table, "source_json": _json(row)}
        if constraint:
            props["fk_constraint"] = constraint
        for name, value in row.items():
            if value is None:
                continue
            normalized = _normalize(value)
            props[name] = _json(normalized) if isinstance(normalized, (dict, list)) else normalized
        edges.append({"type": rel_type, "start": start, "end": end, "key": key, "props": props,
                      "source_table": source_table, "source": row})

    def find_key(table_name: str, fields: tuple[str, ...], row: dict):
        table = table_map.get(table_name)
        if table is None or table_name not in rows_by_table:
            return None
        values = tuple(row.get(field) for field in fields)
        matches = [row_key(table_name, table["pk"], candidate) for candidate in rows_by_table[table_name]
                   if tuple(candidate.get(field) for field in fields) == values]
        if len(matches) > 1:
            raise ValueError(f"ambiguous source reference {table_name}.{fields}: {values} matches {len(matches)} rows")
        return matches[0] if matches else None

    # The actual database has no declared FKs. Use only the explicit FK-equivalent
    # columns listed above and fail closed whenever a non-null reference dangles.
    for child_table, child_fields, parent_table, parent_fields, rel_type, direction in MANUAL_RELATIONS:
        if child_table not in rows_by_table:
            continue
        for row in rows_by_table[child_table]:
            values = tuple(row.get(field) for field in child_fields)
            if any(value is None for value in values):
                continue
            child_key = find_key(child_table, table_map[child_table]["pk"], row)
            parent_key = find_key(parent_table, parent_fields, {p: row[c] for c, p in zip(child_fields, parent_fields)})
            if parent_key is None:
                raise ValueError(f"unresolved source reference {child_table}.{child_fields} -> {parent_table}.{parent_fields}: {values}")
            start, end = (parent_key, child_key) if direction == "parent_child" else (child_key, parent_key)
            add_edge(rel_type, start, end, row, child_table,
                     constraint="inferred-columns:" + ",".join(child_fields) + "->" + parent_table + "." + ",".join(parent_fields))

    # PostgreSQL association tables are represented by relationships, retaining the
    # original row (including relationship-table PK and payload) in relationship props.
    for table_name in relation_only:
        table = table_map[table_name]
        for row in rows_by_table[table_name]:
            if table_name == "card_evidence_link":
                subject = row.get("ev_subject_cd")
                if subject == "CARD":
                    owner = find_key("card_product", ("card_id",), {"card_id": row.get("card_id")})
                elif subject in {"BNFT", "RULE", "REL", "ITEM"}:
                    owner = find_key("card_product_item", ("card_id", "card_product_item_id"),
                                     {"card_id": row.get("card_id"), "card_product_item_id": row.get("card_product_item_id")})
                else:
                    raise ValueError(f"unknown card_evidence_link.ev_subject_cd: {subject!r}")
                evidence_fields = ("card_doc_id", "page_no", "card_doc_chunk_id", "evidence_id")
                end = find_key("card_source_evidence", evidence_fields, row)
                add_edge("dp_supported_by", owner, end, row, table_name, suffix=str(row.get("evidence_link_id") or ""))
                continue
            if table_name == "card_product_doc":
                start = find_key("card_product", ("card_id",), row)
                end = find_key("card_doc", ("card_doc_id",), row)
            elif table_name == "card_common_doc":
                start = find_key("card_common", ("card_common_id",), row)
                end = find_key("card_doc", ("card_doc_id",), row)
            elif table_name == "card_common_bnft_apply":
                start = find_key("card_common_bnft", ("card_common_id", "card_common_bnft_id"), row)
                end = find_key("card_product", ("card_id",), row)
            else:
                raise ValueError(f"relationship-only table has no explicit mapping: {table_name}")
            add_edge(RELATION_TABLE_NAMES[table_name], start, end, row, table_name)

    # Extend a product/common benefit's evidence only through a directly linked
    # evidence row's exact extraction-stage ID. This recovers sibling quotes from
    # the same extraction (for example a spend-condition quote beside a cap quote)
    # without guessing by document text or flattening JSON into graph nodes.
    evidence_by_key = {node["key"]: node for node in nodes if node["table"] == "card_source_evidence"}
    evidence_by_stage = {}
    for evidence_node in evidence_by_key.values():
        stage_id = evidence_node["source"].get("card_extr_stg_id")
        if stage_id is not None:
            evidence_by_stage.setdefault(stage_id, []).append(evidence_node)
    stage_key_by_id = {}
    if "card_extr_stg" in table_map:
        for row in rows_by_table.get("card_extr_stg", []):
            stage_key = find_key("card_extr_stg", ("card_extr_stg_id",), row)
            stage_key_by_id.setdefault(row.get("card_extr_stg_id"), stage_key)
    direct_owner_evidence = {(edge["start"], edge["end"]) for edge in edges if edge["type"] == "dp_supported_by"}
    expanded_owner_evidence = set(direct_owner_evidence)
    owner_stage_seen = set()
    for edge in [item for item in edges if item["type"] == "dp_supported_by"]:
        anchor = evidence_by_key.get(edge["end"])
        if anchor is None:
            continue
        stage_id = anchor["source"].get("card_extr_stg_id")
        stage_key = stage_key_by_id.get(stage_id)
        if stage_key is None:
            continue
        lineage = {"owner_evidence_relationship": edge["props"], "anchor_evidence": anchor["source"],
                   "card_extr_stg_id": stage_id}
        owner_stage = (edge["start"], stage_key)
        if owner_stage not in owner_stage_seen:
            owner_stage_seen.add(owner_stage)
            add_edge("dp_supported_by_extraction", edge["start"], stage_key, lineage,
                     "derived:dp_supported_by+card_source_evidence+card_extr_stg",
                     constraint="supported evidence shares exact card_extr_stg_id")
        for sibling in evidence_by_stage.get(stage_id, []):
            pair = (edge["start"], sibling["key"])
            if pair in expanded_owner_evidence:
                continue
            expanded_owner_evidence.add(pair)
            sibling_lineage = {**lineage, "sibling_evidence": sibling["source"]}
            add_edge("dp_supported_by", edge["start"], sibling["key"], sibling_lineage,
                     "derived:card_evidence_link+card_source_evidence+card_extr_stg",
                     constraint="same exact extraction stage as directly linked evidence")

    # The live ledger has no direct common-benefit/evidence FK table. Preserve the
    # existing extraction provenance only when all four source joins match exactly:
    # common service -> document, staged BENEFIT name -> card_common_bnft.bnft_nm,
    # and staged extraction id -> source evidence. The relationship keeps its full
    # derivation in source_json so it remains distinguishable from a declared FK.
    if all(name in rows_by_table for name in
           ("card_common_bnft", "card_common_doc", "card_extr_stg", "card_source_evidence")):
        docs_by_common = {}
        for row in rows_by_table["card_common_doc"]:
            docs_by_common.setdefault(row.get("card_common_id"), set()).add(row.get("card_doc_id"))
        staged = {}
        for row in rows_by_table["card_extr_stg"]:
            raw = row.get("stg_raw_item")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (TypeError, ValueError):
                    raw = None
            if (row.get("stg_kind_cd") == "BENEFIT" and row.get("stg_sql_check_cd") is not None
                    and row.get("stg_parent_card_extr_stg_id") is None and isinstance(raw, dict)):
                staged.setdefault((row.get("card_doc_id"), raw.get("bnft_nm")), []).append(row)
        evidence_by_stage = {}
        for row in rows_by_table["card_source_evidence"]:
            evidence_by_stage.setdefault(row.get("card_extr_stg_id"), []).append(row)
        for benefit in rows_by_table["card_common_bnft"]:
            owner = find_key("card_common_bnft", ("card_common_id", "card_common_bnft_id"), benefit)
            for document_id in docs_by_common.get(benefit.get("card_common_id"), set()):
                for extraction in staged.get((document_id, benefit.get("bnft_nm")), []):
                    for evidence in evidence_by_stage.get(extraction.get("card_extr_stg_id"), []):
                        end = find_key("card_source_evidence", table_map["card_source_evidence"]["pk"], evidence)
                        lineage = {"card_common_bnft": benefit, "card_common_doc": {"card_common_id": benefit.get("card_common_id"),
                                                                                   "card_doc_id": document_id},
                                   "card_extr_stg": extraction, "card_source_evidence": evidence}
                        add_edge("dp_supported_by", owner, end, lineage,
                                 "derived:card_common_bnft+card_common_doc+card_extr_stg+card_source_evidence",
                                 constraint="exact-name-and-document extraction lineage")

    node_keys = {node["key"] for node in nodes}
    if len(node_keys) != len(nodes):
        raise ValueError("duplicate node PK keys in transformed snapshot")
    return {"nodes": nodes, "relationships": edges, "table_map": table_map, "table_keys": table_keys,
            "relation_only": sorted(relation_only),
            "stats": {"source_table_rows": dict(snapshot["counts"]), "node_count": len(nodes),
                      "relationship_count": len(edges), "node_counts": dict(Counter(n["table"] for n in nodes)),
                      "relationship_counts": {f"{table}:{rel}": count for (table, rel), count in
                                               Counter((e["source_table"], e["type"]) for e in edges).items()},
                      "relation_only_tables": sorted(relation_only)}}
