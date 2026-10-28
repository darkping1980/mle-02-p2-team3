"""식약처 ``COOKRCP01.csv`` 를 recipe 스키마에 적재하는 Service 모듈.

CSV 한 개를 받아 다음을 수행한다.
    - CSV 구조 검증(UTF-8 BOM, 55개 헤더, 중복 헤더, RCP_SEQ 중복·공란, 행 수 999,999 한도)
    - 참조 마스터 등록: rcp_cat(RCP_PAT2), common_code_grp/common_cd(COOK_MTHD, data/cook_mthd_cd_seed.csv 확정 코드표)
    - 조리 방법: 원본 RCP_WAY2(한글 명칭)를 COOK_MTHD의 common_cd_nm으로 찾아 6자리 코드를 rcp.cook_mthd_cd에 저장
      (코드표에 없는 명칭은 코드를 만들지 않고 검증 오류)
    - 식재료 마스터 등록: data/ingr_seed.csv(검토된 표준명·별칭 사전, 식재료 분류 없음)
    - 영양정보 수치 변환과 자동 검증 상태 결정(원본 값은 보정하지 않음)
    - 조리 단계(원본 번호 보존)와 재료 원문 파싱 후보 생성
    - 하나의 DB 트랜잭션으로 마스터 → rcp_raw → rcp → rcp_cat_rel → rcp_step → rcp_ingr_stg → rcp_ingr 등록

식별자:
    rcp_raw_id  : 원본 수집 회차 ID. DB 함수 fn_get_biz_id('import_batch')로 회차당 한 번 발급.
    rcp_raw_seq : 회차 내 원본 행 순번. CSV 전체 행 순서로 Python이 000001부터 만든다.
    rcp_seq     : 식약처 원본 레시피 번호(일반 속성).
    rcp_id      : 정제 레시피 내부 ID(rcp 단독 PK). 처음 등록할 때 DB가 발급하고, 재실행 시 rcp_seq로 찾아 재사용.
    rcp_cat_rel : 레시피·요리 분류 N:M. 원본 RCP_PAT2 분류만 관계로 만들고 다른 분류를 추론하지 않는다.

트랜잭션 정책:
    전체 적재를 ``PostgresDbSession.transaction()`` 하나로 묶는다. 1,156건 규모는 한 번에 처리해도
    수십 초 이내이며, 원본·정제·단계·staging이 서로 다른 회차로 일부만 남는 상태를 막는 것이
    단계별 commit보다 중요하다. 오류가 나면 예외를 삼키지 않고 전파하므로 전체가 ROLLBACK된다.

재실행 정책:
    가장 최근 원본 회차의 모든 행이 현재 CSV의 같은 위치(rcp_raw_seq)·같은 RCP_SEQ 행과 55개 컬럼까지
    같으면 같은 수집 회차의 반복 실행으로 보고 그 rcp_raw_id를 재사용한다(예: --limit 10 후 --full).
    비교할 때만 CRLF/CR을 LF로 맞춘다. Windows의 Git 자동 줄바꿈 변환(core.autocrlf)으로 같은 파일이
    CRLF로 체크아웃되어도 새 회차로 오인하지 않기 위해서다. rcp_raw에는 CSV 값을 그대로 저장한다.
    정제 컬럼(rcp·rcp_step·staging 원문)은 줄바꿈을 LF로 통일해 체크아웃 방식과 관계없이 같은 값을 만든다.
    하나라도 다르면 새 수집 회차로 보고 새 rcp_raw_id를 발급한다. 업무 ID DEFAULT는 INSERT 때마다
    시퀀스를 소비하므로, 기존 키를 먼저 조회해 새 행만 INSERT한다. 기존 데이터는 삭제하지 않는다.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common.database_manager import snake_to_camel
from common.postgres_db_session import PostgresDbSession

from .recipe_ingredient_parser import RecipeIngredientParser
from ..recipe_repository import SYSTEM_USER_ID, RecipeRepository


# region 1. CSV·시드 파일 및 검증 규칙
register_logger = logging.getLogger("recipe_recommender.register")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INGR_SEED_PATH = DATA_DIR / "ingr_seed.csv"
INGR_SEED_COLUMNS = ("ingr_nm", "ingr_als_nms")
COOK_MTHD_SEED_PATH = DATA_DIR / "cook_mthd_cd_seed.csv"
COOK_MTHD_SEED_COLUMNS = ("common_cd", "common_cd_nm")
COOK_MTHD_CODE_PATTERN = re.compile(r"[0-9]{6}")    # 6자리 문자열 코드(VARCHAR(20) 유지, 숫자형 아님)

STEP_COUNT = 20
MAX_RAW_ROWS_PER_BATCH = 999_999                # rcp_raw_seq VARCHAR(6) 한도
SOURCE_COLUMNS: tuple[str, ...] = (
    "RCP_SEQ", "RCP_NM", "RCP_WAY2", "RCP_PAT2",
    "INFO_WGT", "INFO_ENG", "INFO_CAR", "INFO_PRO", "INFO_FAT", "INFO_NA",
    "HASH_TAG", "ATT_FILE_NO_MAIN", "ATT_FILE_NO_MK", "RCP_PARTS_DTLS",
    *(name for step in range(1, STEP_COUNT + 1) for name in (f"MANUAL{step:02d}", f"MANUAL_IMG{step:02d}")),
    "RCP_NA_TIP",
)
EXPECTED_SOURCE_ROW_COUNT = 1156
NEW_ID_PLACEHOLDER = "(new)"                    # dry-run에서 아직 없는 마스터 ID 자리

# (CSV 컬럼, rcp mapper 파라미터) — 영양정보는 원본 문자열을 Decimal로만 변환하고 보정하지 않는다.
NUTRITION_FIELDS: tuple[tuple[str, str], ...] = (
    ("INFO_WGT", "RCP_SERVING_WEIGHT_VALUE"),
    ("INFO_ENG", "RCP_ENERGY_KCAL"),
    ("INFO_CAR", "RCP_CARBS_G"),
    ("INFO_PRO", "RCP_PROTEIN_G"),
    ("INFO_FAT", "RCP_FAT_G"),
    ("INFO_NA", "RCP_SODIUM_MG"),
)
_NUMERIC_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
_NUMERIC_10_2_LIMIT = Decimal("100000000")     # numeric(10,2) 정수부 8자리 한도
ENERGY_TOLERANCE_KCAL = Decimal("50")           # 4C+4P+9F 추정 열량과의 절대 오차 허용치
ENERGY_TOLERANCE_RATIO = Decimal("0.5")         # 그리고 상대 오차 허용치(둘 다 넘으면 검토)


# endregion
# region 2. 적재 계획과 실행 결과 DTO
# =========================================================
# 쓰기 전 계획·검토 사유와 쓰기 후 집계 구분
# =========================================================
class RecipeLoadError(Exception):
    """적재를 중단해야 하는 데이터·구조 오류. 메시지에 원인 목록을 담는다."""


class RehearsalRollback(Exception):
    """리허설 적재 마지막에 던져 전체 트랜잭션을 ROLLBACK시키는 표식 예외."""


@dataclass(frozen=True)
class IngredientSeed:
    """검토된 식재료 사전. ingredients: [(표준명, (별칭...))]."""

    ingredients: tuple[tuple[str, tuple[str, ...]], ...]  # 검토된 표준명과 별칭 묶음; 등록 전 사전 검증에 쓴다.

    @property
    def alias_count(self) -> int:
        """검토된 식재료 사전에 포함된 별칭 총수를 계산한다."""
        return sum(len(aliases) for _, aliases in self.ingredients)


@dataclass
class RecipeLoadPlan:
    """CSV에서 만든 DB 등록 후보와 검증 결과. DB에는 아직 아무것도 쓰지 않은 상태다."""

    source_row_count: int = 0  # 읽은 CSV 데이터 행 수.
    raw_rows: list[dict] = field(default_factory=list)  # 원본 테이블 등록 후보.
    recipes: list[dict] = field(default_factory=list)  # 정제 레시피 등록 후보.
    steps: list[dict] = field(default_factory=list)  # 조리 단계 등록 후보.
    stagings: list[dict] = field(default_factory=list)  # 재료 원문 파싱 staging 후보.
    category_relations: list[dict] = field(default_factory=list)  # 레시피·분류 관계 후보.
    blocking_errors: list[str] = field(default_factory=list)  # 쓰기를 중단해야 할 검증 오류.
    category_conflicts: list[str] = field(default_factory=list)  # 분류 매핑 충돌 보고.
    nutrition_reviews: list[str] = field(default_factory=list)  # 영양값 검토 필요 사유.
    step_issues: list[str] = field(default_factory=list)  # 단계 원문 누락·불일치 문제.
    recipes_without_parts: list[str] = field(default_factory=list)  # 재료 원문이 없는 레시피.
    parse_status_counts: dict[str, int] = field(default_factory=dict)  # 파싱 상태별 후보 건수.


@dataclass
class RecipeLoadResult:
    """적재 실행 결과. dry-run이면 DB 관련 값은 비어 있다."""

    plan: RecipeLoadPlan  # 실행에 사용한 사전 검증·등록 후보.
    dry_run: bool  # True면 DB에 쓰지 않고 후보와 검증 결과만 반환한다.
    rcp_raw_id: str | None = None  # 사용한 수집 회차 ID; dry-run이면 None.
    batch_mode: str | None = None               # NEW_BATCH / SAME_BATCH_RERUN
    written: dict[str, int] = field(default_factory=dict)  # 테이블별 실제 등록 건수.
    ingredient_conflicts: list[str] = field(default_factory=list)  # 표준 재료 충돌 목록.
    batch_counts: dict | None = None  # 현재 수집 회차의 테이블별 건수; 미실행 시 None.
    table_counts_before: dict | None = None  # 쓰기 전 전체 테이블 건수.
    table_counts_after: dict | None = None  # 쓰기 후 전체 테이블 건수.
    integrity: dict | None = None  # 참조 정합성 검사 결과; 미실행 시 None.
    stale_steps: list[str] = field(default_factory=list)  # 재실행 때 원본과 어긋난 기존 단계.
    rolled_back: bool = False                   # --rehearse: 쓰기·검증 후 ROLLBACK됨


# endregion
# region 3. 원문 정규화와 검토된 시드 파일 로딩
def normalize_newlines(value: str | None) -> str | None:
    """CRLF·CR을 LF로 바꾼다. 원본 저장값은 바꾸지 않고 비교·정제 값에만 쓴다."""
    return None if value is None else value.replace("\r\n", "\n").replace("\r", "\n")


def _null_if_empty(value: str | None) -> str | None:
    """CSV에는 NULL 개념이 없으므로 빈 문자열만 NULL로 저장한다. 그 외 값은 공백 포함 원형 그대로."""
    return None if value is None or value == "" else value


def _clean_text(value: str | None) -> str | None:
    """정제 컬럼용: 줄바꿈을 LF로 맞추고 앞뒤 공백만 제거하며 비면 NULL."""
    if value is None:
        return None
    stripped = normalize_newlines(value).strip()
    return stripped or None


def raw_seq_for(position: int) -> str:
    """CSV 행 위치(1부터)를 회차 내 원본 행 순번 문자열로 만든다. 999,999 초과는 오류."""
    if not 1 <= position <= MAX_RAW_ROWS_PER_BATCH:
        raise RecipeLoadError(f"원본 행 순번 범위 초과: {position} (1~{MAX_RAW_ROWS_PER_BATCH})")
    return f"{position:06d}"


def strip_step_prefix(text: str, step_no: int) -> str:
    """조리 설명 앞의 '1. ' 같은 번호가 단계 번호와 같을 때만 제거한다. 나머지 원문은 유지한다."""
    return re.sub(rf"^{step_no}\s*\.\s*", "", text, count=1)


def evaluate_nutrition(row: dict[str, str]) -> tuple[dict[str, Decimal | None], str, str | None]:
    """영양정보를 Decimal로 변환하고 자동 검증 상태를 정한다.

    Returns:
        ``(rcp 파라미터 dict, 상태, 검토 메모)``. 상태는 ``VALID`` 또는 ``REVIEW_REQUIRED``.
        변환에 실패한 값은 None으로 두고 원본은 rcp_raw에 남는다. 이상값을 추정치로 덮어쓰지 않는다.
    """
    values: dict[str, Decimal | None] = {}
    issues: list[str] = []
    infos: list[str] = []
    for source, target in NUTRITION_FIELDS:
        raw = (row.get(source) or "").strip()
        if not raw:
            values[target] = None
            if source == "INFO_WGT":
                infos.append("INFO_WGT 원본 공란")
            else:
                issues.append(f"{source} 원본 공란")
            continue
        if not _NUMERIC_PATTERN.match(raw):
            values[target] = None
            issues.append(f"{source} 숫자 변환 실패 '{raw}'")
            continue
        try:
            number = Decimal(raw)
        except InvalidOperation:
            values[target] = None
            issues.append(f"{source} 숫자 변환 실패 '{raw}'")
            continue
        if number >= _NUMERIC_10_2_LIMIT or number.as_tuple().exponent < -2:
            values[target] = None
            issues.append(f"{source} numeric(10,2) 범위 초과 '{raw}'")
            continue
        values[target] = number

    energy = values["RCP_ENERGY_KCAL"]
    carbs, protein, fat = values["RCP_CARBS_G"], values["RCP_PROTEIN_G"], values["RCP_FAT_G"]
    if None not in (energy, carbs, protein, fat):
        estimated = 4 * carbs + 4 * protein + 9 * fat
        difference = abs(estimated - energy)
        base = max(energy, estimated, Decimal(1))
        if difference > ENERGY_TOLERANCE_KCAL and difference / base > ENERGY_TOLERANCE_RATIO:
            issues.append(f"열량 불일치 INFO_ENG={energy} vs 4C+4P+9F={estimated}")

    status = "REVIEW_REQUIRED" if issues else "VALID"
    note = "; ".join(["auto-check=nutrition-v1", *issues, *infos])
    return values, status, note


def load_ingredient_seed(ingredient_path: Path = INGR_SEED_PATH) -> IngredientSeed:
    """식재료 표준명·별칭 사전을 읽고 모순을 검사한다.

    Raises:
        RecipeLoadError: 헤더 불일치, 표준명 중복, 별칭이 다른 표준명/별칭과 겹치는 경우.
    """
    with ingredient_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != INGR_SEED_COLUMNS:
            raise RecipeLoadError(f"식재료 사전 헤더 {reader.fieldnames} != {list(INGR_SEED_COLUMNS)}")
        ingredients = tuple(
            (row["ingr_nm"].strip(),
             tuple(alias.strip() for alias in (row["ingr_als_nms"] or "").split("|") if alias.strip()))
            for row in reader
        )
    errors = []
    owner: dict[str, str] = {}
    for name, aliases in ingredients:
        for text in (name, *aliases):
            if text in owner and owner[text] != name:
                errors.append(f"'{text}' 가 '{owner[text]}' 와 '{name}' 에 중복 지정됨")
            elif text in owner and text == name:
                errors.append(f"표준명 중복 '{name}'")
            owner.setdefault(text, name)
    if errors:
        raise RecipeLoadError("식재료 사전 오류: " + "; ".join(errors))
    return IngredientSeed(ingredients=ingredients)


def load_cook_method_seed(path: Path = COOK_MTHD_SEED_PATH) -> dict[str, str]:
    """조리 방법 확정 코드표를 읽는다. Returns ``{common_cd: common_cd_nm}`` (파일 순서).

    Raises:
        RecipeLoadError: 헤더 불일치, 6자리 숫자 문자열이 아닌 코드, 코드·명칭 공란·중복.
    """
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != COOK_MTHD_SEED_COLUMNS:
            raise RecipeLoadError(f"조리 방법 코드표 헤더 {reader.fieldnames} != {list(COOK_MTHD_SEED_COLUMNS)}")
        rows = [(row["common_cd"].strip(), row["common_cd_nm"].strip()) for row in reader]
    errors = [f"코드 형식 오류 '{code}'" for code, _ in rows if not COOK_MTHD_CODE_PATTERN.fullmatch(code)]
    errors += [f"명칭 공란 '{code}'" for code, name in rows if not name]
    codes, names = [code for code, _ in rows], [name for _, name in rows]
    errors += [f"코드 중복 '{code}'" for code in sorted({c for c in codes if codes.count(c) > 1})]
    errors += [f"명칭 중복 '{name}'" for name in sorted({n for n in names if names.count(n) > 1})]
    if errors:
        raise RecipeLoadError("조리 방법 코드표 오류: " + "; ".join(errors))
    return dict(rows)


def resolve_cook_method_map(db_codes: dict[str, str], seed: dict[str, str]) -> dict[str, str]:
    """DB의 COOK_MTHD 코드와 확정 코드표를 합쳐 ``{common_cd_nm: common_cd}`` 를 만든다.

    기존 코드는 재번호화·개명하지 않는다. DB 코드가 코드표와 다른 명칭이거나, 6자리 형식이 아니거나
    (예: 이전 방식의 한글 코드값), 한 명칭이 두 코드에 걸리면 적재하지 않고 오류로 보고한다.
    """
    errors = [f"DB 코드 '{code}' 명칭 '{db_codes[code]}' != 코드표 '{name}'"
              for code, name in seed.items() if code in db_codes and db_codes[code] != name]
    merged = {**db_codes, **seed}
    errors += [f"6자리 형식이 아닌 COOK_MTHD 코드 '{code}'"
               for code in sorted(merged) if not COOK_MTHD_CODE_PATTERN.fullmatch(code)]
    by_name: dict[str, str] = {}
    for code, name in sorted(merged.items()):
        if name in by_name:
            errors.append(f"명칭 '{name}' 이 코드 '{by_name[name]}', '{code}' 에 중복")
        by_name.setdefault(name, code)
    if errors:
        raise RecipeLoadError("COOK_MTHD 코드 체계 오류: " + "; ".join(errors))
    return by_name


# endregion
# region 4. CSV 검증·계획·PostgreSQL 등록 Service
# =========================================================
# read_csv → build_plan → register의 단일 트랜잭션
# =========================================================
class RecipeRegisterService:
    """레시피 CSV 적재 파이프라인을 실행하는 Service.

    의존 관계: ``RecipeRepository`` (SQL), ``RecipeIngredientParser`` (재료 원문 파싱).
    진입점은 ``register()`` 이며 단계별 메서드는 테스트할 수 있게 공개한다.
    """

    sql_session: PostgresDbSession  # 등록 트랜잭션과 Named SQL 실행 세션.
    repository: RecipeRepository  # 테이블별 등록·조회 DAO.
    ingredient_parser: RecipeIngredientParser  # 원문 재료의 staging 후보 생성기.

    def __init__(self, sql_session, user_id=SYSTEM_USER_ID):
        """PostgreSQL 세션을 받아 등록 DAO와 재료 파서를 준비한다."""
        self.sql_session = sql_session
        self.repository = RecipeRepository(sql_session=sql_session, user_id=user_id)
        self.ingredient_parser = RecipeIngredientParser()

    # =========================================================
    # CSV 읽기 / 구조 검증
    # =========================================================
    @staticmethod
    def read_csv(csv_path: str | Path) -> list[dict[str, str]]:
        """CSV를 읽어 행 dict 목록을 돌려준다. 파일은 읽기만 하고 변경하지 않는다.

        ``utf-8-sig`` 로 BOM을 제거하고 ``newline=""`` 로 따옴표 안 줄바꿈을 보존한다.
        각 행에는 CSV 순서대로 만든 ``RCP_RAW_SEQ`` (000001~)를 함께 담는다.

        Raises:
            RecipeLoadError: 헤더 누락·중복·추가, 행 길이 불일치, 999,999행 초과.
        """
        path = Path(csv_path)
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            header = next(reader, None)
            if header is None:
                raise RecipeLoadError(f"CSV is empty: {path}")
            errors = []
            duplicates = sorted({name for name in header if header.count(name) > 1})
            if duplicates:
                errors.append(f"중복 헤더: {duplicates}")
            missing = [name for name in SOURCE_COLUMNS if name not in header]
            if missing:
                errors.append(f"누락 헤더: {missing}")
            extra = [name for name in header if name not in SOURCE_COLUMNS]
            if extra:
                errors.append(f"정의되지 않은 헤더: {extra}")
            rows = []
            for line_no, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    errors.append(f"CSV 레코드 {line_no}: 컬럼 수 {len(values)} != {len(header)}")
                    continue
                rows.append(dict(zip(header, values)))
            if errors:
                raise RecipeLoadError("; ".join(errors))
        for position, row in enumerate(rows, start=1):
            row["RCP_RAW_SEQ"] = raw_seq_for(position)
        return rows

    @staticmethod
    def validate_rows(rows: list[dict[str, str]], expected_count: int | None = EXPECTED_SOURCE_ROW_COUNT) -> list[str]:
        """행 수, RCP_SEQ 공란·중복, 레시피명·분류·조리 방법 공란을 검사한다. Returns 차단 오류 목록."""
        errors = []
        if expected_count is not None and len(rows) != expected_count:
            errors.append(f"CSV 행 수 {len(rows)} != 예상 {expected_count}")
        seen: dict[str, int] = {}
        for index, row in enumerate(rows, start=1):
            seq = row["RCP_SEQ"]
            if not seq.strip():
                errors.append(f"{index}번째 행 RCP_SEQ 공란")
                continue
            if seq != seq.strip():
                errors.append(f"RCP_SEQ '{seq}' 앞뒤 공백")
            if seq in seen:
                errors.append(f"RCP_SEQ 중복 '{seq}' ({seen[seq]}번째, {index}번째 행)")
            seen.setdefault(seq, index)
            for column in ("RCP_NM", "RCP_PAT2", "RCP_WAY2"):
                if not row[column].strip():
                    errors.append(f"RCP_SEQ {seq}: {column} 공란")
        return errors

    # =========================================================
    # 등록 후보 생성 (DB 쓰기 없음)
    # =========================================================
    # =========================================================
    # CSV 행을 원본·레시피·단계·관계 등록 후보로 변환
    # =========================================================
    def build_plan(self, rows, category_map, cook_method_map, existing_recipe_keys,
                   existing_category_relations=None) -> RecipeLoadPlan:
        """CSV 행을 테이블별 등록 후보로 바꾸고 매핑·충돌·품질 문제를 분류한다.

        Args:
            rows: 적재 대상 CSV 행(``--limit`` 적용 후, ``RCP_RAW_SEQ`` 포함).
            category_map: 요리 종류명 → rcp_cat_id.
            cook_method_map: 조리 방법명(common_cd_nm) → COOK_MTHD 코드(common_cd).
            existing_recipe_keys: 이미 등록된 rcp_seq → (rcp_id, rcp_raw_id).
            existing_category_relations: 이미 등록된 rcp_id → 요리 분류 ID 집합.

        Note:
            조리 단계·분류 관계의 ``RCP_ID`` 는 레시피 등록 후 ``write_plan()`` 이 채운다.
            기존 레시피의 원본 분류(RCP_PAT2)가 등록된 관계에 없으면 관계를 추가·삭제하지 않고
            ``category_conflicts`` 로 보고한다(레시피 본문은 갱신한다).
        """
        existing_category_relations = existing_category_relations or {}
        plan = RecipeLoadPlan(source_row_count=len(rows))
        parse_counts: dict[str, int] = {}
        for row in rows:
            seq = row["RCP_SEQ"]
            raw_seq = row["RCP_RAW_SEQ"]
            plan.raw_rows.append({"RCP_RAW_SEQ": raw_seq,
                                  **{column: _null_if_empty(row[column]) for column in SOURCE_COLUMNS}})

            # 재료 원문은 rcp_raw 행의 자식이므로 레시피 반영 여부와 관계없이 staging 후보로 만든다.
            parsed_items = self.ingredient_parser.parse(normalize_newlines(row["RCP_PARTS_DTLS"]), row["RCP_NM"])
            if not parsed_items:
                plan.recipes_without_parts.append(f"RCP_SEQ {seq} {row['RCP_NM'].strip()}")
            for item in parsed_items:
                parse_counts[item.parse_status] = parse_counts.get(item.parse_status, 0) + 1
                plan.stagings.append({
                    "RCP_RAW_SEQ": raw_seq,
                    "RCP_INGR_LINE_NO": item.line_no,
                    "RCP_INGR_RAW_TXT": item.raw_txt,
                    "RCP_INGR_PARSED_NM": item.parsed_nm,
                    "RCP_INGR_QTY": item.qty,
                    "RCP_INGR_UNIT_NM": item.unit_nm,
                    "RCP_INGR_SECTION_TXT": item.section_txt,
                    "RCP_INGR_REVIEW_NOTE": item.review_note,
                    "RCP_INGR_PARSER_VERSION": self.ingredient_parser.version,
                })

            category_id = category_map.get(row["RCP_PAT2"])
            if category_id is None:
                plan.blocking_errors.append(f"RCP_SEQ {seq}: 요리 종류 '{row['RCP_PAT2']}' 가 rcp_cat에 없음")
            cook_method_cd = cook_method_map.get(row["RCP_WAY2"])
            if cook_method_cd is None:
                plan.blocking_errors.append(f"RCP_SEQ {seq}: 조리 방법 '{row['RCP_WAY2']}' 가 COOK_MTHD 코드표에 없음"
                                            "(코드를 임의로 부여하지 않음)")
            if category_id is None or cook_method_cd is None:
                continue

            existing = existing_recipe_keys.get(seq)
            registered = existing_category_relations.get(existing[0], set()) if existing else set()
            if registered and category_id not in registered:
                # 원본 분류가 바뀐 기존 레시피: 관계를 임의로 추가·삭제하지 않고 검토 대상으로 남긴다.
                plan.category_conflicts.append(
                    f"RCP_SEQ {seq}: 등록 분류 {sorted(registered)} / 현재 CSV '{row['RCP_PAT2']}'={category_id}"
                )
            else:
                plan.category_relations.append({"RCP_SEQ": seq, "RCP_CAT_ID": category_id})

            nutrition, status, note = evaluate_nutrition(row)
            if status == "REVIEW_REQUIRED":
                plan.nutrition_reviews.append(f"RCP_SEQ {seq} {row['RCP_NM'].strip()}: {note}")
            plan.recipes.append({
                "RCP_SEQ": seq,
                "RCP_NM": _clean_text(row["RCP_NM"]),
                "COOK_MTHD_CD": cook_method_cd,
                **nutrition,
                "RCP_NUTRITION_STATUS": status,
                "RCP_NUTRITION_REVIEW_NOTE": note,
                "RCP_HASH_TAG": _clean_text(row["HASH_TAG"]),
                "RCP_IMAGE_URL": _clean_text(row["ATT_FILE_NO_MAIN"]),
                "RCP_IMAGE_LARGE_URL": _clean_text(row["ATT_FILE_NO_MK"]),
                "RCP_SODIUM_REDUCTION_TIP_TXT": _clean_text(row["RCP_NA_TIP"]),
            })

            present_steps = []
            for step_no in range(1, STEP_COUNT + 1):
                text = normalize_newlines(row[f"MANUAL{step_no:02d}"]).strip()
                image = _clean_text(row[f"MANUAL_IMG{step_no:02d}"])
                if not text:
                    if image:
                        plan.step_issues.append(f"RCP_SEQ {seq} 단계 {step_no}: 이미지만 있고 설명 없음(미등록)")
                    continue
                present_steps.append(step_no)
                plan.steps.append({
                    "RCP_SEQ": seq,
                    "STEP_NO": step_no,
                    "RCP_STEP_INSTRUCTION_TXT": strip_step_prefix(text, step_no),
                    "RCP_STEP_IMAGE_URL": image,
                })
            if present_steps and present_steps != list(range(1, max(present_steps) + 1)):
                plan.step_issues.append(f"RCP_SEQ {seq}: 단계 번호 공백 {present_steps} (원본 번호 유지)")
            if not present_steps:
                plan.step_issues.append(f"RCP_SEQ {seq}: 조리 단계 없음")
        plan.parse_status_counts = dict(sorted(parse_counts.items()))
        return plan

    # =========================================================
    # 마스터 등록 (transaction 안에서 호출)
    # =========================================================
    def cook_method_map(self, seed: dict[str, str] | None = None) -> dict[str, str]:
        """현재 DB 코드와 확정 코드표를 검증해 합친 조리 방법명 → 코드 dict."""
        return resolve_cook_method_map(self.repository.list_cook_method_codes(), seed or load_cook_method_seed())

    def register_reference_masters(self, source_rows, cook_method_seed: dict[str, str] | None = None) -> dict[str, int]:
        """CSV 실제 고유값으로 요리 종류를, 확정 코드표로 조리 방법 공통코드를 등록한다. 기존 행은 지우지 않는다.

        조리 방법 코드는 CSV 값으로 만들지 않는다. 코드표와 DB가 충돌하면 쓰기 전에 오류를 낸다.
        """
        cook_method_seed = cook_method_seed or load_cook_method_seed()
        self.cook_method_map(cook_method_seed)
        existing = self.repository.list_recipe_category_map()
        categories = sorted({row["RCP_PAT2"] for row in source_rows} - set(existing))
        group_count, code_count = self.repository.upsert_cook_method_codes(cook_method_seed)
        return {
            "rcp_cat": self.repository.insert_recipe_categories(categories) if categories else 0,
            "common_code_grp": group_count,
            "common_cd": code_count,
        }

    def register_ingredient_master(self, seed: IngredientSeed) -> tuple[dict[str, int], list[str]]:
        """식재료 사전을 ingr → ingr_als 순서로 등록한다. 새 행만 INSERT하고 기존 ID는 그대로 둔다.

        DB에서 이미 다른 표준 식재료의 이름·별칭으로 쓰이는 별칭은 등록하지 않고 충돌로 보고한다.
        Returns: ``(테이블별 등록 수, 충돌 목록)``.
        """
        ingredient_map = self.repository.list_ingredient_map()
        new_ingredients = [{"INGR_NM": name} for name, _ in seed.ingredients if name not in ingredient_map]
        written = {"ingr": self.repository.insert_ingredients(new_ingredients) if new_ingredients else 0}
        ingredient_map = self.repository.list_ingredient_map()

        alias_keys = self.repository.list_ingredient_alias_keys()
        name_owner = {name: ingredient_id for name, ingredient_id in ingredient_map.items()}
        name_owner.update({alias: ingredient_id for ingredient_id, alias in alias_keys})
        conflicts, new_aliases = [], []
        for name, aliases in seed.ingredients:
            ingredient_id = ingredient_map[name]
            for alias in aliases:
                owner = name_owner.get(alias)
                if owner is not None and owner != ingredient_id:
                    conflicts.append(f"별칭 '{alias}': DB에서 다른 식재료 {owner} 의 이름·별칭(미등록)")
                elif (ingredient_id, alias) not in alias_keys:
                    new_aliases.append({"INGR_ID": ingredient_id, "INGR_ALS_NM": alias})
        written["ingr_als"] = self.repository.insert_ingredient_aliases(new_aliases) if new_aliases else 0
        return written, conflicts

    # =========================================================
    # 회차 결정 / DB 쓰기 (transaction 안에서 호출)
    # =========================================================
    def resolve_batch(self, source_rows) -> tuple[str, str]:
        """같은 수집 회차 재실행이면 기존 rcp_raw_id를, 아니면 새 rcp_raw_id를 돌려준다.

        Returns: ``(rcp_raw_id, "SAME_BATCH_RERUN" | "NEW_BATCH")``.
        """
        latest = self.repository.find_latest_raw_batch()
        if latest is not None:
            # 최신 회차의 저장 행이 CSV 같은 순번의 원문과 모두 같으면 ID를 재사용한다.
            # 저장된 범위에서 차이가 있으면 새 회차 ID를 발급한다. 저장 범위 밖은 비교하지 않는다.
            source_by_raw_seq = {row["RCP_RAW_SEQ"]: row for row in source_rows}
            stored_rows = self.repository.list_raw_rows_by_batch(latest["rcpRawId"])
            if all(self._raw_row_matches(stored, source_by_raw_seq.get(stored["rcpRawSeq"])) for stored in stored_rows):
                return latest["rcpRawId"], "SAME_BATCH_RERUN"
        return self.repository.find_next_rcp_raw_id(), "NEW_BATCH"

    @staticmethod
    def _raw_row_matches(stored: dict, source: dict | None) -> bool:
        """저장된 원본 행이 같은 행 순번의 CSV 행과 55개 컬럼까지 같은지 확인한다(줄바꿈 종류만 무시)."""
        if source is None:
            return False
        return all(normalize_newlines(stored[snake_to_camel(column.lower())])
                   == normalize_newlines(_null_if_empty(source[column])) for column in SOURCE_COLUMNS)

    # =========================================================
    # 기존 키를 재사용하며 Repository에 등록·갱신 위임
    # =========================================================
    def write_plan(self, plan: RecipeLoadPlan, rcp_raw_id: str) -> dict[str, int]:
        """등록 후보를 순서대로 DB에 쓴다. 반드시 ``sql_session.transaction()`` 안에서 호출한다.

        Returns: 테이블별로 이번 실행에서 등록(또는 갱신)된 행 수.
        """
        if self.sql_session._active_connection is None:
            raise RuntimeError("write_plan() must run inside sql_session.transaction()")
        written = {"rcp_raw": self.repository.insert_recipe_raws(rcp_raw_id, plan.raw_rows)}

        # rcp: 원본 번호로 기존 rcp_id를 찾아 재사용하고, 없는 레시피만 새로 발급한다.
        existing = self.repository.list_recipe_key_map()
        new_recipes = [recipe for recipe in plan.recipes if recipe["RCP_SEQ"] not in existing]
        known_recipes = [{**recipe, "RCP_ID": existing[recipe["RCP_SEQ"]][0]}
                         for recipe in plan.recipes if recipe["RCP_SEQ"] in existing]
        written["rcp_insert"] = self.repository.insert_recipes(rcp_raw_id, new_recipes) if new_recipes else 0
        written["rcp_update"] = self.repository.update_recipes(rcp_raw_id, known_recipes) if known_recipes else 0

        key_map = self.repository.list_recipe_key_map()
        missing = [recipe["RCP_SEQ"] for recipe in plan.recipes if recipe["RCP_SEQ"] not in key_map]
        if missing:
            raise RecipeLoadError(f"rcp_seq → rcp_id 매핑 실패: {missing[:10]}")
        relations = [{"RCP_ID": key_map[item["RCP_SEQ"]][0], "RCP_CAT_ID": item["RCP_CAT_ID"]}
                     for item in plan.category_relations]
        written["rcp_cat_rel"] = self.repository.insert_recipe_category_relations(relations) if relations else 0
        steps = [{**step, "RCP_ID": key_map[step["RCP_SEQ"]][0]} for step in plan.steps]
        written["rcp_step"] = self.repository.upsert_recipe_steps(steps) if steps else 0

        # staging: 같은 (회차, 원본 행, 등장 순번)이 이미 있으면 ID를 새로 발급하지 않는다.
        staged = self.repository.list_staging_keys(rcp_raw_id)
        stagings = [staging for staging in plan.stagings
                    if (staging["RCP_RAW_SEQ"], staging["RCP_INGR_LINE_NO"]) not in staged]
        written["rcp_ingr_stg"] = (self.repository.insert_recipe_ingredient_stagings(rcp_raw_id, stagings)
                                   if stagings else 0)
        written["rcp_ingr_stg_auto_approved"] = self.repository.update_staging_verified_matches(rcp_raw_id)
        written["rcp_ingr"] = self.repository.insert_recipe_ingredient_relations(rcp_raw_id)
        self._verify_written(plan, rcp_raw_id)
        return written

    def _verify_written(self, plan: RecipeLoadPlan, rcp_raw_id: str) -> None:
        """트랜잭션 안에서 이번 회차 결과를 다시 세어 기대치보다 적으면 예외로 ROLLBACK시킨다."""
        counts = self.repository.count_batch_rows(rcp_raw_id)
        problems = []
        for key, expected, label in (("rawCount", len(plan.raw_rows), "rcp_raw"),
                                     ("recipeCount", len(plan.recipes), "rcp"),
                                     ("stepCount", len(plan.steps), "rcp_step"),
                                     ("categoryRelationCount", len(plan.category_relations), "rcp_cat_rel"),
                                     ("stagingCount", len(plan.stagings), "rcp_ingr_stg")):
            if counts[key] < expected:
                problems.append(f"{label} {counts[key]} < {expected}")
        if problems:
            raise RecipeLoadError("적재 후 검증 실패: " + "; ".join(problems))

    # =========================================================
    # 메인 파이프라인
    # =========================================================
    def check_target_model(self) -> None:
        """연결 스키마가 목표 모델인지 확인한다. 기존 모델 스키마에 새 SQL로 쓰지 않기 위한 가드."""
        model = self.repository.find_schema_model()
        if not model["hasRcpCatRel"] or model["hasIngrCat"]:
            raise RecipeLoadError("대상 스키마가 목표 모델(rcp_cat_rel 있음, ingr_cat 없음)이 아님 — "
                                  "tools/recipe_rebuild.py 로 재구축한 스키마를 지정해야 함")

    # =========================================================
    # dry-run·리허설·실제 적재를 구분하는 호출 진입점
    # =========================================================
    def register(self, csv_path, *, limit: int | None = None, dry_run: bool = True,
                 seed: IngredientSeed | None = None, rehearse: bool = False) -> RecipeLoadResult:
        """CSV 검증부터 DB 등록과 사후 정합성 검사까지 실행한다.

        Args:
            csv_path: 원본 CSV 경로.
            limit: 앞에서부터 N건만 적재. None이면 전체.
            dry_run: True면 읽기 전용 조회만 하고 DB를 변경하지 않는다.
            seed: 식재료 사전. None이면 ``data/`` 의 기본 사전을 읽는다.
            rehearse: True면 실제와 같이 쓰고 집계·정합성 검사까지 한 뒤 전체를 ROLLBACK한다.

        Raises:
            RecipeLoadError: 구조·매핑 오류가 있어 적재하면 안 되는 경우(dry-run 포함).
        """
        self.check_target_model()
        all_rows = self.read_csv(csv_path)
        errors = self.validate_rows(all_rows)
        if errors:
            raise RecipeLoadError("; ".join(errors))
        rows = all_rows[:limit] if limit is not None else all_rows
        seed = seed or load_ingredient_seed()
        cook_method_seed = load_cook_method_seed()
        cook_method_map = self.cook_method_map(cook_method_seed)
        unknown_methods = sorted({row["RCP_WAY2"] for row in all_rows} - set(cook_method_map))
        if unknown_methods:
            raise RecipeLoadError(f"COOK_MTHD 코드표에 없는 조리 방법 {unknown_methods} — 코드표 등록 후 다시 실행")

        # dry-run: 아직 없는 마스터는 CSV 값으로 등록될 예정이므로 자리표시 ID로 매핑을 검사한다.
        category_map = self.repository.list_recipe_category_map()
        category_map.update({row["RCP_PAT2"]: NEW_ID_PLACEHOLDER
                             for row in all_rows if row["RCP_PAT2"] not in category_map})
        plan = self.build_plan(rows, category_map, cook_method_map, self.repository.list_recipe_key_map(),
                               self.repository.list_recipe_category_relations())
        if plan.blocking_errors:
            raise RecipeLoadError("; ".join(plan.blocking_errors[:20]))

        result = RecipeLoadResult(plan=plan, dry_run=dry_run)
        result.table_counts_before = self.repository.count_recipe_tables()
        if dry_run:
            return result

        try:
            with self.sql_session.transaction():
                # Java의 @Transactional 경계에 해당한다. 예외가 밖으로 나가면 세션이 ROLLBACK한다.
                written = self.register_reference_masters(all_rows, cook_method_seed)
                ingredient_written, result.ingredient_conflicts = self.register_ingredient_master(seed)
                written.update(ingredient_written)
                result.rcp_raw_id, result.batch_mode = self.resolve_batch(all_rows)
                register_logger.info("rcp_raw_id=%s mode=%s", result.rcp_raw_id, result.batch_mode)

                # 실제 마스터 ID와 현재 레시피 키로 등록 후보를 다시 만든다.
                existing_keys = self.repository.list_recipe_key_map()
                plan = self.build_plan(rows, self.repository.list_recipe_category_map(),
                                       self.cook_method_map(cook_method_seed), existing_keys,
                                       self.repository.list_recipe_category_relations())
                if plan.blocking_errors:
                    raise RecipeLoadError("; ".join(plan.blocking_errors[:20]))
                result.plan = plan
                planned_steps = {(step["RCP_SEQ"], step["STEP_NO"]) for step in plan.steps}
                planned_seqs = {recipe["RCP_SEQ"] for recipe in plan.recipes}
                seq_by_rcp_id = {rcp_id: seq for seq, (rcp_id, _) in existing_keys.items()}
                result.stale_steps = sorted(
                    f"RCP_SEQ {seq_by_rcp_id[rcp_id]} 단계 {step_no}: DB에는 있으나 현재 CSV에는 없음(삭제하지 않음)"
                    for rcp_id, step_no in self.repository.list_recipe_step_keys()
                    if seq_by_rcp_id.get(rcp_id) in planned_seqs and (seq_by_rcp_id[rcp_id], step_no) not in planned_steps
                )
                written.update(self.write_plan(plan, result.rcp_raw_id))
                result.written = written
                # 집계와 정합성은 같은 트랜잭션에서 확인한다(리허설은 이 결과를 남기고 ROLLBACK).
                result.batch_counts = self.repository.count_batch_rows(result.rcp_raw_id)
                result.table_counts_after = self.repository.count_recipe_tables()
                result.integrity = self.repository.count_integrity_violations()
                if rehearse:
                    raise RehearsalRollback
        except RehearsalRollback:
            result.rolled_back = True
        return result

# endregion
