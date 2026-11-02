"""혜택 검색 텍스트와 임베딩을 저장한다. 혜택 원본 컬럼은 바꾸지 않는다.

순서는 텍스트 저장 → 임베딩 생성 → 벡터 저장이다. 텍스트가 바뀌면 벡터를 먼저 비우므로, 벡터가 있으면 항상
현재 텍스트에서 만든 값이다. 임베딩이 실패해도 혜택과 텍스트는 남고 다음 실행이 비어 있는 벡터만 다시 처리한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from time import sleep
from typing import Protocol

from psycopg.types.json import Jsonb

from .benefit_search_text import SEARCH_TEXT_RULE_VER, build_card_bnft_text, build_common_bnft_text

embedding_logger = logging.getLogger("card_benefit.embedding")

DEFAULT_MODEL = "text-embedding-3-small"
DIMENSIONS = 1536                       # 컬럼 vector(1536)와 같아야 한다.
BATCH_SIZE = 64
API_TIMEOUT_SECONDS = 30
SYSTEM_USER_ID = "SYSTEM"
EMBEDDING_LOG_KEYS = ("BNFT_EMBEDDING", "QUERY_EMBEDDING")      # SQL 로그에서 가릴 벡터 파라미터
TABLES = ("card_bnft", "card_common_bnft")


class EmbeddingError(Exception):
    """임베딩 실행을 시작할 수 없는 경우."""


class Embedder(Protocol):
    """임베딩 클라이언트 계약. 실제 구현과 Mock이 같은 형태를 따른다."""

    model_nm: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """입력 순서대로 벡터를 반환한다."""


def embedding_model() -> str:
    """사용할 모델을 한 곳에서 정한다. 저장과 질문 임베딩이 같은 값을 쓴다."""
    return os.getenv("CARD_EMBEDDING_MODEL") or DEFAULT_MODEL


class OpenAIEmbedder:
    """OpenAI 임베딩 호출. 재시도는 ``EmbeddingService`` 가 맡는다."""

    def __init__(self, client=None, model_nm: str | None = None, dimensions: int = DIMENSIONS):
        if client is None:
            from common.query_log_config import load_project_environment
            from openai import OpenAI

            load_project_environment()
            client = OpenAI(max_retries=0, timeout=API_TIMEOUT_SECONDS)
        self.client = client
        self.model_nm = model_nm or embedding_model()
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model_nm, input=texts, dimensions=self.dimensions)
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts) or any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingError("임베딩 응답의 건수 또는 차원이 다릅니다")
        return vectors


def vector_literal(vector: list[float]) -> str:
    """pgvector 입력 문자열."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


class EmbeddingRepository:
    """``embedding_repository.*`` statement를 실행한다."""

    def __init__(self, sql_session):
        self.sql_session = sql_session

    def rows(self, name: str, **params) -> list[dict]:
        return self.sql_session.select_list("embedding_repository." + name, params)

    def one(self, name: str, **params) -> dict | None:
        return self.sql_session.select_one("embedding_repository." + name, params)

    def write(self, name: str, **params):
        return self.sql_session.execute("embedding_repository." + name, params)


@dataclass(frozen=True)
class TableSpec:
    """테이블마다 다른 부분. ``owner_key`` 는 복합 PK의 부모 키다."""

    statement: str
    owner_key: str
    id_key: str
    build: object


SPECS = {
    "card_bnft": TableSpec("card_bnft", "card_id", "card_bnft_id", build_card_bnft_text),
    "card_common_bnft": TableSpec("common_bnft", "card_common_id", "card_common_bnft_id", build_common_bnft_text),
}


@dataclass
class TableReport:
    """테이블별 처리 건수."""

    table: str
    targets: int = 0
    text_changed: int = 0
    embedded: int = 0
    skipped: int = 0
    failed: list[dict] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)


@dataclass
class SyncResult:
    """실행 결과. ``run_id`` 는 임베딩 API를 호출한 실행에만 있다."""

    reports: list[TableReport]
    run_id: str | None = None
    applied: bool = False

    @property
    def ok(self) -> bool:
        return not any(report.failed for report in self.reports)


class EmbeddingService:
    """검색 텍스트 재생성과 임베딩 저장을 처리한다."""

    def __init__(self, sql_session, embedder: Embedder | None = None, max_attempts: int = 3, retry_seconds: float = 1.0):
        self.repository = EmbeddingRepository(sql_session)
        self.embedder = embedder
        self.max_attempts = max_attempts
        self.retry_seconds = retry_seconds

    def sync(self, table: str = "all", ids: list[str] | None = None, force: bool = False,
             text_only: bool = False, apply: bool = False) -> SyncResult:
        """대상 행을 처리한다. 같은 텍스트에 벡터가 있으면 ``force`` 없이는 API를 호출하지 않는다.

        Raises:
            EmbeddingError: 모델이 지난 실행과 다르거나 임베딩 클라이언트가 없는 경우.
        """
        tables = list(TABLES) if table == "all" else [table]
        if table != "all" and table not in SPECS:
            raise EmbeddingError(f"대상 테이블이 아닙니다: {table}")
        plans = [self._plan(name, ids, force) for name in tables]
        result = SyncResult([report for report, _ in plans], applied=apply)
        if not apply:
            return result
        for report, work in plans:
            self._save_texts(report.table, work)
        pending = [(name.table, row) for name, work in plans for row in work if row["needs_embedding"]]
        if text_only or not pending:
            return result
        if self.embedder is None:
            raise EmbeddingError("임베딩 클라이언트가 없습니다")
        self._check_model(force)
        result.run_id = self._start_run(table, ids, force, len(pending))
        try:
            by_table = {report.table: report for report in result.reports}
            for start in range(0, len(pending), BATCH_SIZE):
                self._embed_batch(pending[start:start + BATCH_SIZE], by_table)
        except Exception:
            self._finish_run(result, "FAILED", "처리 중 오류")
            raise
        failed = sum(len(report.failed) for report in result.reports)
        status = "SUCCEEDED" if not failed else ("PARTIAL" if failed < len(pending) else "FAILED")
        self._finish_run(result, status, f"실패 {failed}건" if failed else None)
        return result

    def embed_new(self, table: str, ids: list[str]) -> SyncResult | None:
        """등록 직후 호출한다. 실패해도 등록을 되돌리지 않으며 ``embedding_main`` 으로 복구한다."""
        try:
            return self.sync(table, ids, apply=True)
        except Exception as error:      # 등록은 이미 커밋됐다. 키나 응답이 섞이지 않도록 유형만 남긴다.
            embedding_logger.error("EMBED FAILED table=%s ids=%s: %s", table, ids, type(error).__name__)
            return None

    def status(self) -> list[dict]:
        return self.repository.rows("select_embedding_status", DIMENSIONS=DIMENSIONS)

    def _plan(self, table: str, ids: list[str] | None, force: bool) -> tuple[TableReport, list[dict]]:
        spec = SPECS[table]
        report, work = TableReport(table), []
        for row in self.repository.rows(f"select_{spec.statement}_rows", IDS=ids):
            built = spec.build(row)
            bnft_id = row[spec.id_key]
            if built.review:
                report.review.append({"id": bnft_id, "items": built.review})
            changed = built.text != row["bnft_search_txt"]
            needs_embedding = force or changed or not row["has_embedding"]
            report.targets += 1
            report.text_changed += changed
            report.skipped += not needs_embedding
            if changed or needs_embedding:
                work.append({"owner_id": row[spec.owner_key], "id": bnft_id, "text": built.text,
                             "changed": changed, "needs_embedding": needs_embedding})
        return report, work

    def _save_texts(self, table: str, work: list[dict]) -> None:
        statement = f"update_{SPECS[table].statement}_text"
        for row in work:
            if row["changed"]:
                self.repository.write(statement, OWNER_ID=row["owner_id"], BNFT_ID=row["id"],
                                      BNFT_SEARCH_TXT=row["text"], USER_ID=SYSTEM_USER_ID)

    def _check_model(self, force: bool) -> None:
        """한 컬럼에 다른 모델의 벡터가 섞이면 유사도가 무의미하다. 모델을 바꾸려면 전체를 ``force`` 로 다시 만든다."""
        last = self.repository.one("select_last_embedding_run")
        if last and last["run_model_nm"] != self.embedder.model_nm and not force:
            raise EmbeddingError(f"저장된 모델({last['run_model_nm']})과 현재 모델({self.embedder.model_nm})이 다릅니다. --force로 다시 생성하세요")

    def _embed_batch(self, batch: list[tuple[str, dict]], reports: dict[str, TableReport]) -> None:
        """한 묶음을 호출하고 저장한다. 호출이 끝내 실패하면 묶음 전체를 실패로 기록하고 다음으로 넘어간다."""
        texts = [row["text"] for _, row in batch]
        try:
            vectors = self._call_with_retry(texts)
        except Exception as error:
            for table, row in batch:
                reports[table].failed.append({"id": row["id"], "error": type(error).__name__})
            return
        for (table, row), vector in zip(batch, vectors):
            updated = self.repository.write(f"update_{SPECS[table].statement}_embedding", OWNER_ID=row["owner_id"],
                                            BNFT_ID=row["id"], BNFT_SEARCH_TXT=row["text"],
                                            BNFT_EMBEDDING=vector_literal(vector), USER_ID=SYSTEM_USER_ID)
            if updated:
                reports[table].embedded += 1
            else:
                reports[table].failed.append({"id": row["id"], "error": "TEXT_CHANGED"})

    def _call_with_retry(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.embedder.embed(texts)
            except Exception as error:
                embedding_logger.warning("EMBED RETRY %d/%d: %s", attempt, self.max_attempts, type(error).__name__)
                if attempt == self.max_attempts:
                    raise
                sleep(self.retry_seconds * attempt)
        raise EmbeddingError("재시도 횟수가 올바르지 않습니다")

    def _start_run(self, table: str, ids: list[str] | None, force: bool, targets: int) -> str:
        rows = self.repository.write(
            "insert_embedding_run", RUN_MODEL_NM=self.embedder.model_nm, RUN_PROMPT_VER=SEARCH_TEXT_RULE_VER,
            RUN_PROMPT_TXT="혜택명 + 혜택 유형 + 이용처 또는 서비스 대상 + 핵심 혜택 내용",
            RUN_PARAM=Jsonb({"table": table, "ids": ids, "force": force, "targets": targets, "dimensions": DIMENSIONS}),
            USER_ID=SYSTEM_USER_ID)
        return rows[0]["card_ai_run_id"]

    def _finish_run(self, result: SyncResult, status: str, note: str | None) -> None:
        summary = {report.table: {"embedded": report.embedded, "failed": report.failed} for report in result.reports}
        self.repository.write("finish_embedding_run", CARD_AI_RUN_ID=result.run_id, RUN_STATUS=status,
                              RUN_RESULT=Jsonb({"result": summary}), RUN_NOTE=note, USER_ID=SYSTEM_USER_ID)
