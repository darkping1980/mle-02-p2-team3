"""Source labels derived from document index metadata."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


_BRAND_TOKENS = (
    (re.compile(r"(?i)(?<![A-Za-z0-9])VISA(?:[-_ ]?[A-Z])?(?:\.T)?(?![A-Za-z0-9])"), "VISA"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])MC(?:[-_ .]?[A-Z])?(?:\.T)?(?![A-Za-z0-9])"), "Mastercard"),
    (re.compile(r"(?i)\bMastercard\b"), "Mastercard"),
    (re.compile(r"(?i)\bAMEX\b"), "AMEX"),
    (re.compile(r"(?i)\bJCB\b"), "JCB"),
    (re.compile(r"(?i)\bUnionPay\b"), "UnionPay"),
    (re.compile(r"(?i)\bUPI(?:[-_ ]?[A-Z])?\b"), "UPI"),
    (re.compile(r"(?i)\bDinersClub\b"), "DinersClub"),
)


def label_for_document(file_path: str, doc_role: str = "") -> str | None:
    """Return a short display label, or None for a card-specific document."""
    path = str(file_path or "")
    name = Path(path).name
    if "브랜드서비스" in name:
        for pattern, brand in _BRAND_TOKENS:
            if pattern.search(name):
                return f"국제브랜드 공통 안내장({brand})"
        # Preserve an unfamiliar English brand token when present in the filename.
        match = re.search(r"[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)*", name)
        if match:
            return f"국제브랜드 공통 안내장({match.group(0)})"
        return "국제브랜드 공통 안내장"
    if "/common/" in f"/{path.lower().strip('/')}" or "공통" in path:
        return "공통 안내장"
    return None


def load_document_labels(index_dirs: Iterable[str | Path]) -> dict[str, str]:
    """Load sha256-to-label mappings from one or more index directories."""
    labels: dict[str, str] = {}
    for index_dir in index_dirs:
        path = Path(index_dir)
        files = [path] if path.name == "documents.csv" else sorted(path.glob("documents.csv"))
        for csv_path in files:
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    sha = (row.get("sha256") or "").strip()
                    label = label_for_document(row.get("file_path", ""), row.get("doc_role", ""))
                    if sha and label:
                        labels.setdefault(sha, label)
    return labels


def annotate_subgraph(subgraph: dict, node_doc_shas: dict, labels: dict[str, str]) -> dict:
    """Copy a subgraph and label Benefit props from their evidence documents."""
    result = dict(subgraph or {})
    nodes = []
    for node in (subgraph or {}).get("nodes") or []:
        updated = dict(node)
        props = dict(node.get("props") or {})
        if node.get("label") == "Benefit":
            node_id = str(node.get("id", ""))
            shas = node_doc_shas.get(node_id, node_doc_shas.get(str(props.get("fp_id", "")), ()))
            names = list(dict.fromkeys(labels[sha] for sha in shas if sha in labels))
            if names:
                props["출처문서"] = ", ".join(names)
        updated["props"] = props
        nodes.append(updated)
    result["nodes"] = nodes
    return result
