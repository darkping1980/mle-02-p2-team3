"""Neo4j 드라이버 생성 — TLS 인증서 검증을 유지하면서 신뢰할 CA 번들을 명시한다.

일부 Python 배포판(예: uv가 설치한 CPython)은 OS 인증서 저장소에서 AuraDB 인증서 체인의 루트를 찾지 못해
``CERTIFICATE_VERIFY_FAILED`` 가 난다. 검증을 끄지 않고, 신뢰할 CA 번들을 드라이버에 직접 지정해 해결한다.

    NEO4J_URI=neo4j+s://...      → neo4j://... + encrypted=True + TrustCustomCAs(<CA 번들>)  (같은 의미, 검증 유지)
    NEO4J_URI=bolt+s://...       → bolt://...  + encrypted=True + TrustCustomCAs(<CA 번들>)
    NEO4J_URI=neo4j+ssc / bolt+ssc → 거부(인증서 검증을 하지 않는 스킴)
    그 밖(neo4j://, bolt:// 로컬 등) → 그대로 사용

CA 번들: 환경변수 ``NEO4J_TRUSTED_CA_FILE`` 이 있으면 그 PEM 파일, 없으면 ``certifi`` 번들.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import load_project_environment

CA_FILE_ENV_NAME = "NEO4J_TRUSTED_CA_FILE"
_VERIFIED_TLS_SCHEMES = {"neo4j+s": "neo4j", "bolt+s": "bolt"}
_UNVERIFIED_TLS_SCHEMES = {"neo4j+ssc", "bolt+ssc"}


# region 1. 검증된 TLS 연결 설정
def trusted_ca_file() -> str:
    """신뢰할 CA 번들 PEM 경로. 지정 파일이 없으면 오류(조용히 검증을 끄지 않는다)."""
    configured = os.getenv(CA_FILE_ENV_NAME)
    if configured:
        path = Path(configured).expanduser()
    else:
        import certifi

        path = Path(certifi.where())
    if not path.is_file():
        raise FileNotFoundError(f"Neo4j trusted CA file does not exist: {path}")
    return str(path)


def driver_arguments(uri: str) -> tuple[str, dict]:
    """``GraphDatabase.driver`` 에 넘길 URI와 TLS 설정. 검증하는 TLS 스킴만 CA 번들을 명시한다."""
    from neo4j import TrustCustomCAs

    scheme, separator, rest = uri.partition("://")
    if not separator:
        raise ValueError("NEO4J_URI must include a scheme such as neo4j+s://")
    scheme = scheme.lower()
    if scheme in _UNVERIFIED_TLS_SCHEMES:
        raise ValueError(f"{scheme}:// skips certificate verification; use neo4j+s:// (verified TLS)")
    if scheme in _VERIFIED_TLS_SCHEMES:
        return f"{_VERIFIED_TLS_SCHEMES[scheme]}://{rest}", {
            "encrypted": True,
            "trusted_certificates": TrustCustomCAs(trusted_ca_file()),
        }
    return uri, {}


# endregion
# region 2. Neo4j 드라이버 생성
# =========================================================
# Repository에 주입할 드라이버와 인증 정보 준비
# =========================================================
def create_neo4j_driver():
    """저장소 ``.env`` 의 ``NEO4J_URI`` / ``NEO4J_USERNAME`` / ``NEO4J_PASSWORD`` 로 드라이버를 만든다."""
    from neo4j import GraphDatabase

    load_project_environment()
    missing = [name for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not os.getenv(name)]
    if missing:
        raise ValueError("Missing Neo4j settings: " + ", ".join(missing))
    uri, settings = driver_arguments(os.environ["NEO4J_URI"])
    return GraphDatabase.driver(uri, auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]), **settings)

# endregion
