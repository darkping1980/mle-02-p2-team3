# GraphRAG 오류·데이터 손실 수정 설계 및 단계별 실행 계획

- 작성일: 2026-11-06
- 작성: Claude (설계만 작성. 소스·DB·Neo4j 변경 없음, 유료 LLM 호출 없음)
- 선행 문서: [20261106_tier_value_none_typeerror.md](20261106_tier_value_none_typeerror.md), [20261106_postgresql_neo4j_mapping_query_audit.md](20261106_postgresql_neo4j_mapping_query_audit.md)
- 추가 조사(읽기 전용, 설계에 필요한 부분만): `fn_valid_item_data` 정의, `check_limit_tiers` 표 검증 규칙, 기존 행 등록 동작, 22·23·20 추출 원본·근거 위치·원문 표 순서, `card_evidence_link` 제약과 COND 연결 형식

---

## 1. 확정된 원인 요약

| ID | 원인 | 단계 | 근거 문서 |
|---|---|---|---|
| D3 | tier 계열 함수가 `value_num = NULL`을 숫자로 가정해 `float(None)` 발생(금액이 없는 문장도 해당) | 답변 검증 | 감사 9.3 |
| D1 | `build_rule()`·`normalize_benefit()`이 추출 결과의 `limits`·`rule.limit_keys`를 버리고, 등록부가 LIMIT 인용을 평문 `item_limit_txt`로만 저장 | 정규화·등록 | 감사 9.2 |
| D2 | `_links()`가 규칙 조건 안의 인용(구간+금액 인용)을 연결하지 않고, LIMIT 인용을 혜택 단위로만 연결 | 등록 | 감사 9.2 |
| D4 | `load_snapshot` benefits SELECT에 `item_data`가 없어 `limit_tiers`가 Neo4j에 없음 | 적재 | 감사 7.2 L1 |
| D5 | `neo4j_validate`가 같은 스냅샷으로 기대값을 만들어 D4를 감지하지 못함 | 검증 | 감사 7.2 L2 |
| D6 | 답변 검증이 한도 금액의 구간 배정을 검사하지 않음 | 답변 검증 | 감사 9.4 F |

### 이번 설계를 위해 새로 확인한 사실

1. **`item_data`(BENEFIT)의 DB 검사는 `schema_ver`뿐이다.** `fn_valid_item_data`의 BENEFIT 분기는 `NOT (p_data ? 'schema_ver') OR p_data->>'schema_ver' = 'BENEFIT_V1'` 하나다. 따라서 **DDL 없이** `item_data`에 키를 추가할 수 있다.
2. **기존 `SET_LIMIT_TIERS`의 표 검증(`check_limit_tiers`)은 22·23 원문에 그대로 쓸 수 없다.** 이 검증은 표 원문이 "열 이름들 → (구간 표기 → 그 구간 금액 칸들)" 순서라고 가정한다.
   - 22: 원문 순서가 `월 할인 한도 / 지난달 실적 / 10,000원 / 30만원 이상⏎80만원 미만 / 80만원 이상 / 15,000원`이다. 첫 금액이 구간 표기보다 앞에 있어 실패한다.
   - 23: 행마다 `구간 → 기본적립 → 적립한도 제한 없음 → 특별/추가 적립 → 금액` 순서다. 열 이름이 표 머리에 없어 실패한다. 구간 표기가 "30만원 이상"뿐이라 연속 구간 검사(`min_amt == 이전 max`)에서도 실패한다.
   - 저장 형태(`item_data.limit_tiers`)와 문장 생성(`limit_tiers_text`)은 재사용할 수 있다. 검증 경로는 따로 필요하다.
3. **이미 등록된 혜택은 등록 프로그램이 수정하지 않는다.** `product_benefit_service._register` 285~287행은 같은 `item_cd`가 있으면 `UNCHANGED`("등록된 혜택은 수정하지 않습니다")를 반환한다. 보정 대장을 고쳐 다시 실행해도 22·23·20은 바뀌지 않는다. 기존 데이터는 **ID를 보존하는 별도 보정 도구**가 있어야 고칠 수 있다(삭제 후 재등록은 ID가 바뀌어 근거·Neo4j key·임베딩이 깨지므로 금지).
4. **규칙 조건 근거 연결 형식은 이미 있다.** `card_evidence_link`에 `ev_subject_cd='RULE', ev_item_cd='COND', ev_item_key=<atom_key>` 행이 있다(예: card 2 `one_pick_100 / MIN_one_pick_100`). 자연 키(`card_evidence_link_natural_key`)가 있어 같은 연결을 다시 넣어도 중복이 생기지 않는다.
5. **`value_num`과 월 한도는 업무 의미가 다르다.** `build_rule` docstring에 따르면 `value_num`은 "답변의 수치 확인용 지급 값(율·금액)"이다. 한도는 기간 누적 상한이다. 22의 r1·r2는 "승인 금액만큼 할인"이라 지급 값이 정해져 있지 않다. **월 한도를 `value_num`에 저장하는 방안은 의미를 왜곡하므로 채택하지 않는다.**

---

## 2. 수정 대상과 제외 대상

### 수정 대상

| 단계 | 대상 |
|---|---|
| 1 (P0) | `card_graphrag.py`: tier 계열 함수의 지급값 nullable 계약 |
| 2 (P1 신규) | `extraction_service.py`(`normalize_benefit`, 신규 helper), `product_benefit_service.py`(`_register`의 item_data 구성, `_links`), `common_benefit_repository.sql`(COND 근거 연결 SQL 1건 추가) |
| 3 (P1 기존) | 신규 보정 도구 1개 + 보정 대장 1개. PG `card_product_item` 22/099·23/100·20/092의 `item_data`, `card_evidence_link` 7건 추가 |
| 4 (P2) | `neo4j_dry_run.py`(benefits SELECT), `neo4j_validate.py` + `neo4j_validation.sql`(컬럼 완전성·값 대조), `card_graphrag.py`(`benefit_context`가 한도 구조 전달, 한도 구간 검증) |
| 5 | 통합 회귀 |

### 제외 대상 (변경하지 않음)

- `dp_card_bnft` 라벨·노드 key·관계 구조, 그래프 재설계
- `rule_list` JSON 계약(6개 키)과 `fn_valid_rule_list`
- `value_num`·`value_unit_cd`의 의미
- `item_limit_txt`(기존 행): 바꾸면 `item_search_txt`·임베딩과 어긋난다. 구조는 `item_data`에만 추가한다.
- 임베딩 재생성, 검색 텍스트 재생성
- 새 테이블·컬럼·DDL
- DAILY 179 검색 품질 문제(8절에서 조사 계획만)
- Codex 소유 로그 파일(`streamlit_app.py`, `execution_log.py`, `card_search_execution_log.sql`): 8절의 로그 보강은 소유자와 협의 후 진행
- 23/100 규칙 atom의 `cond_max_amt_excl` 직접 수정(5.3절 결정 사항)

---

## 3. P0 상세 수정 설계 — `card_graphrag.py`

### 3.1 방식 비교와 선택

| 방식 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. 제외 | `rule_conflicts()`에서 `value is None`인 규칙을 tier에서 뺀다 | 변경 최소 | 22의 r1·r2가 빠지면 conflict 자체가 사라지거나 r3만 남는다. 전월 실적 구간 정보가 검증·LLM 문맥(`rule_selection_unresolved`)에서 사라진다(요구 4 위반) |
| **B. 미확정 보존(선택)** | tier는 그대로 두고 지급값 상태를 `payout_known`으로 표시한다. 지급 비교는 `payout_known`인 tier만, 구간 기준액 검증은 모든 tier로 한다 | 구간 보존, 0원과 구분, 기존 정상 tier 동작 불변 | 호출부 6곳 수정 |
| C. 예외 포착 | `validate_answer`를 try/except로 감싼다 | 가장 간단 | 원인을 숨기고 검증을 통과시킬 위험이 있어 채택하지 않음 |

**선택: B.** 미확정 지급값은 `None` 그대로 두고, 판정 함수는 "모른다"를 "맞다/틀리다"로 바꾸지 않는다.

### 3.2 계약

- **지급 토큰**: `tier_token(tier) -> tuple[str, float] | None`
  - `tier["value"]`가 `int`/`float`(bool 제외)이고 `tier["unit"] in UNIT_KINDS`일 때만 `(kind, float(value))`를 반환한다. 그 밖에는 `None`이다.
  - `value == 0`은 숫자이므로 `("MONEY", 0.0)` 같은 **정상 토큰**이다. `None`과 구분된다.
  - 현재 데이터에서 `value` NULL과 `unit` NULL은 12건씩 정확히 겹친다. 단위 없이 값만 있는 규칙은 없으므로 이 조건을 추가해도 기존 동작에 영향이 없다.
- **tier dict**(`rule_conflicts` 출력): 기존 키에 `payout_known: bool`을 추가한다. `value`·`unit`은 원값(None 포함) 그대로 둔다. LLM 문맥에도 이 키가 전달된다.
- **판정 함수 원칙**
  - 구간 기준액(`min_amt`) 관련 판정은 모든 tier를 쓴다.
  - 지급액 관련 판정은 `payout_known`인 tier만 쓴다.
  - 비교할 지급값이 없으면 "왜곡 없음/언급 없음"으로 판정한다(통과). 단, 그 문장의 금액은 기존 `unknown_values()` 검사를 그대로 거친다. 근거에 없는 금액은 여전히 버려진다.
- **예외 정책**: tier 함수에 try/except를 추가하지 않는다. 형식이 잘못된 값은 `tier_token`이 `None`으로 거른다. 그 밖의 예외(키 누락 등 계약 위반)는 지금처럼 전파되게 해서 숨기지 않는다.

### 3.3 함수별 변경안 (diff 예시, 미적용)

```diff
@@ def tier_token(tier: dict) -> tuple[str | None, float]:
-def tier_token(tier: dict) -> tuple[str | None, float]:
-    """구간 지급액을 문장의 값과 비교할 ``(종류, 값)`` 으로 만든다."""
-    return UNIT_KINDS.get(tier["unit"]), float(tier["value"])
+def tier_token(tier: dict) -> tuple[str, float] | None:
+    """구간 지급액을 ``(종류, 값)`` 으로 만든다. 지급값·단위가 없으면 None(미확정). 0은 정상 값이다."""
+    value, kind = tier.get("value"), UNIT_KINDS.get(tier.get("unit"))
+    if kind is None or isinstance(value, bool) or not isinstance(value, (int, float)):
+        return None
+    return kind, float(value)
```

```diff
@@ def rule_conflicts(...)
-        tiers = sorted(({"rule_key": rule["rule_key"], "value": rule["value"], "unit": rule["unit"], "min_amt": ...,
-                         "max_amt": ..., "basis": ...} for rule in benefit["rules"]), key=...)
+        tiers = sorted(({"rule_key": rule["rule_key"], "value": rule["value"], "unit": rule["unit"], "min_amt": ...,
+                         "max_amt": ..., "basis": ...} for rule in benefit["rules"]), key=...)
+        for tier in tiers:
+            tier["payout_known"] = tier_token(tier) is not None   # None은 미확정. 0원과 구분한다.
```

```diff
@@ def tier_label(tier: dict) -> str:
-    kind, value = tier_token(tier)
-    payout = won(value) if kind == "MONEY" else f"{value:g}{UNIT_LABELS.get(kind, '')}"
+    token = tier_token(tier)
+    if token is None:
+        payout = "지급액 정보 없음"                      # 임의 금액을 만들지 않는다.
+    else:
+        kind, value = token
+        payout = won(value) if kind == "MONEY" else f"{value:g}{UNIT_LABELS.get(kind, '')}"
```

```diff
@@ def distorts_tier(text, conflicts):
     tiers = [tier for conflict in conflicts for tier in conflict["tiers"] if tier["min_amt"] is not None]
-    minimums, values = {float(tier["min_amt"]) for tier in tiers}, {tier_token(tier) for tier in tiers}
+    minimums = {float(tier["min_amt"]) for tier in tiers}            # 구간 기준은 모든 tier
+    paid = [tier for tier in tiers if tier_token(tier) is not None]  # 지급 비교는 값이 있는 tier만
+    values = {tier_token(tier) for tier in paid}
 ...
-                if not any(tier_token(tier) == token[:2] and (...) for tier in tiers):
+                if not any(tier_token(tier) == token[:2] and (...) for tier in paid):
```

`values`가 비면 두 지급 분기 조건(`token[:2] in values`)이 항상 거짓이 되므로 `False`를 반환한다(지급값을 모르는 구간으로 문장을 틀렸다고 단정하지 않음).

```diff
@@ def picks_single_tier(...)
-        mentioned = sum(tier_token(tier) in written or float(tier["min_amt"]) in minimums for tier in tiers)
-        if len(tiers) > 1 and sum(tier_token(tier) in written for tier in tiers) and mentioned < len(tiers):
+        mentioned = sum((tier_token(tier) is not None and tier_token(tier) in written)
+                        or (tier["min_amt"] is not None and float(tier["min_amt"]) in minimums) for tier in tiers)
+        if len(tiers) > 1 and sum(tier_token(tier) is not None and tier_token(tier) in written for tier in tiers) \
+                and mentioned < len(tiers):
```

현재 코드에서도 `None in written`은 예외가 아니지만, `float(tier["min_amt"])`는 적용 규칙의 `min_amt`가 None이면 예외가 날 수 있다. 같은 함수에서 함께 막는다.

```diff
@@ def tier_is_quoted(conflict, evidence):
     tiers = [tier for tier in conflict["tiers"] if tier["min_amt"] is not None]
-    needed = {("MONEY", float(tier["min_amt"])) for tier in tiers} | {tier_token(tier) for tier in tiers}
+    needed = {("MONEY", float(tier["min_amt"])) for tier in tiers} \
+             | {tier_token(tier) for tier in tiers if tier_token(tier) is not None}
```

지급값이 미확정인 tier는 "기준액이 원문에 있는가"만 확인한다. `tier_answer`의 문장은 `tier_label`이 "지급액 정보 없음"으로 쓴다.

```diff
@@ def validate_answer(...)  # 1299행 부근, 결제 금액이 여러 구간에 해당할 때의 시스템 문장
-        values = {(*tier_token(tier), None) for tier in conflict["tiers"]}
+        values = {(*tier_token(tier), None) for tier in conflict["tiers"] if tier_token(tier) is not None}
+        if not values:
+            warnings.append(f"{conflict['name']}의 구간 지급액이 조회 자료에 없어 금액 구간 문장을 만들지 않았습니다.")
+            continue
```

빈 `values`로 `all(...)`이 참이 되어 "이미 답했다"로 판정되는 것을 막는다. 현재 22는 기준이 `PREV_MONTH_SPEND`라 `applicable_rule_keys`가 늘 비어 이 분기에 들어오지 않지만, 같은 형태의 결제 건 기준 데이터를 대비한다.

`tier_text`, `tier_answer`, `fixed_conclusion`, `answer_text_problem`은 위 helper를 통해서만 지급값에 접근하므로 본문 변경이 필요 없다. `answer_text_problem`의 `same_tiers` 직렬화는 `None`을 그대로 JSON으로 쓰므로 안전하다.

### 3.4 LLM 지시문 (선택, 같은 단계)

`rule_selection_unresolved` 설명(247행)에 "`payout_known`이 false인 구간은 지급액을 쓰지 않고 구간 기준만 쓴다"를 한 줄 추가한다. 검증만으로도 안전하지만, 버려지는 문장을 줄여 답변 품질을 지킨다.

### 3.5 P0만으로 남는 한계 (요구 6)

P0는 월 한도를 tier의 지급값으로 쓰지 않는다. 다만 LLM이 `limit_text`의 10,000원·15,000원을 구간에 잘못 배정하는 것은 아직 막지 못한다(D6). 이 검증은 한도 구조가 전달되는 4단계(7.4절)에서 추가한다.

---

## 4. P1 정규화·등록 수정 설계 (신규 등록 데이터)

### 4.1 보존 구조 선택

| 안 | 내용 | 판단 |
|---|---|---|
| 1. `rule_list[].limit_keys` + 혜택에 `limits` 컬럼 | 규칙 JSON 계약 변경, 새 컬럼 | 제외: `rule_list` 계약·Neo4j 규칙 노드·계산 구조 정리 의도(2026-11-03)와 충돌 |
| 2. `value_num`에 한도 저장 | — | 금지: 업무 의미가 다름(1절 5번) |
| **3. `item_data`(BENEFIT_V1)에 추출 구조를 그대로 보존 + 구간 표가 명확한 경우만 `limit_tiers` 생성(선택)** | DDL 없음, 기존 `limit_tiers` 소비 코드 재사용 | **채택** |

### 4.2 `item_data` 확장 형식 (BENEFIT_V1, 하위 호환)

```json
{
  "schema_ver": "BENEFIT_V1",
  "limits": [
    {"limit_key": "l1", "limit_num": 10000, "cap_unit_cd": "KRW", "period_cd": "MONTH",
     "limit_raw_txt": "10,000원", "shared_scope_txt": "횟수 제한 없이 월 할인 한도 내에서 합산 할인",
     "evidence_ids": ["20261105_002681"]},
    {"limit_key": "l2", "limit_num": 15000, "cap_unit_cd": "KRW", "period_cd": "MONTH",
     "limit_raw_txt": "15,000원", "shared_scope_txt": "…", "evidence_ids": ["20261105_002682"]}
  ],
  "rule_limits": {"r1": ["l1"], "r2": ["l2"], "r3": ["l1", "l2"]},
  "limit_tiers": {
    "schema_ver": "LIMIT_TIERS_V1", "source": "EXTRACTION", "basis_cd": "PREV_MONTH_SPEND",
    "tiers": [
      {"tier_key": "r1", "rule_key": "r1", "label": "30만원 이상 80만원 미만", "min_amt": 300000, "max_amt_excl": 800000,
       "evidence_ids": ["20261105_002685"]},
      {"tier_key": "r2", "rule_key": "r2", "label": "80만원 이상", "min_amt": 800000, "max_amt_excl": null,
       "evidence_ids": ["20261105_002686"]}
    ],
    "own": {"column": "월 할인 한도", "merged_cell": false,
            "caps": {"r1": {"raw": "10,000원", "amount": 10000, "limit_key": "l1"},
                     "r2": {"raw": "15,000원", "amount": 15000, "limit_key": "l2"}}},
    "shared": []
  }
}
```

- `limits`·`rule_limits`: 추출 결과(`stg_raw_item.limits`, `rules[].limit_keys`)를 **해석 없이 복사**한다. 규칙과 한도는 `rule_key` ↔ `limit_key`로 연결된다. 이 단계에서 의미 손실이 끝난다.
- `limit_tiers`: 기존 키(`schema_ver, basis_cd, tiers[tier_key,label,min_amt,max_amt_excl], own{column,merged_cell,caps{raw,amount}}, shared`)를 유지한다. 추가하는 키는 모두 선택이다.
  - `source`: `"EXTRACTION"`. 없으면 기존 `SET_LIMIT_TIERS`(`TABLE_QUOTE`)다.
  - `tiers[].rule_key`: 구간 ↔ 규칙 식별자.
  - `tiers[].evidence_ids`, `caps[].limit_key`: 추적성.
  - `table_quote`: `source = EXTRACTION`일 때 생략할 수 있다.
  - 기존 소비 코드 `limit_tiers_text()`는 `own.column`, `caps[*].raw`, `tiers[*].label`, `shared`만 읽으므로 호환된다.
- 연결 식별자는 다음 순서로 정한다.
  1. **구간 ↔ 규칙**: `rule_key`(구간 하나 = 규칙 하나인 경우).
  2. 그 밖(DAILY처럼 규칙이 대상별이고 구간이 혜택 단위): `(basis_cd, min_amt, max_amt_excl)`로 규칙의 `SPEND_REQ` atom과 맞춘다.
  3. **한도 ↔ 규칙**: `rule_limits`.

### 4.3 `limit_tiers` 자동 생성 조건 (보수적)

새 helper `limit_tiers_from_extraction(item, rules, located_evidence) -> dict | None`(`extraction_service.py`)는 다음을 **모두** 만족할 때만 만든다. 하나라도 어기면 `None`이고, `limits`·`rule_limits`만 저장한다. 이 경우는 검토 대상(보정 대장 `SET_LIMIT_TIERS`)으로 남긴다.

1. `SPEND_REQ`가 있는 규칙이 2개 이상이고, 각 규칙의 `SPEND_REQ` atom이 정확히 1개이며 `cond_basis_cd`가 모두 같다(예: `PREV_MONTH_SPEND`).
2. 각 구간 규칙의 `limit_keys` 중 `cap_unit_cd='KRW'`이고 `limit_num`이 있는 한도가 정확히 1개다.
3. 구간끼리 `[min, max)`가 겹치지 않는다. `max_amt_excl`이 None인 구간은 가장 높은 구간 하나뿐이다.
   - **23/100처럼 상한이 없어 겹치면 생성하지 않는다**(5.3절).
4. 각 한도의 LIMIT 인용과 각 구간 조건의 COND 인용이 원문 위치가 확인된 근거(`card_source_evidence` start/end)로 존재한다.

생성할 때 금액 표기와 구간 표기는 추출 원본의 인용 문자열만 쓴다. 금액은 `limit_num`을 쓰고, 계산하거나 추론하지 않는다.

### 4.4 코드 변경안 (diff 예시, 미적용)

`extraction_service.normalize_benefit()` — 646행 주석 위치:

```diff
         "relation_list": relations,
-        # 한도는 원문 인용(bnft_limit_txt)으로 보관한다. 한도 풀(limit_list·pool_refs) 정규화는 제거했다.
+        # 한도 원문 인용은 bnft_limit_txt로 보관하고, 추출 구조(limits·규칙별 limit_keys)는 해석 없이 item_data 후보로 넘긴다.
+        # 한도 풀(limit_list·pool_refs) 계산 구조는 계속 쓰지 않는다. rule_list 계약은 바꾸지 않는다.
+        "limit_struct": {"limits": [limit.model_dump(mode="json") for limit in item.limits],
+                         "rule_limits": {rule.rule_key: list(rule.limit_keys) for rule in item.rules if rule.limit_keys}},
         "verification_status_cd": "PENDING_REVIEW",
```

`limit_struct`는 정규화 결과(`stg_normalized_item` 대체 메모리 구조)에만 있다. `rule_list`에는 들어가지 않는다. `build_rule()`은 **변경하지 않는다**(규칙 계약 유지).

`product_benefit_service._register()` — 325~338행:

```diff
         limit_txt = quote_text(evidence_items, 'LIMIT')
 ...
         data = {}
         if candidate.get('review_patch'):
             data = {'schema_ver': 'BENEFIT_V1', 'review_patch': candidate['review_patch']}
+        struct = norm.get('limit_struct') or {}
+        if struct.get('limits'):
+            # 추출 한도 구조 보존(2026-11-xx). limit_key마다 위치가 확인된 LIMIT 근거 ID를 붙인다.
+            data = {**data, 'schema_ver': 'BENEFIT_V1',
+                    'limits': attach_limit_evidence(struct['limits'], raw, evidence),
+                    'rule_limits': {k: v for k, v in struct['rule_limits'].items() if k in {r['rule_key'] for r in rules}}}
+            derived = limit_tiers_from_extraction(norm, rules, data['limits'], raw, evidence)
+            if derived and not candidate.get('limit_tiers'):
+                data['limit_tiers'] = derived          # 사람 보정(SET_LIMIT_TIERS)이 있으면 그것이 우선
         if candidate.get('limit_tiers'):
             data = {**data, 'schema_ver': 'BENEFIT_V1', 'limit_tiers': candidate['limit_tiers']}
             limit_txt = limit_tiers_text(candidate['limit_tiers'])
```

자동 생성한 `limit_tiers`로는 `item_limit_txt`를 바꾸지 않는다. 원문 인용 텍스트 계약을 유지하기 위해서다. 사람 보정이 있는 경우만 기존처럼 바꾼다.

`product_benefit_service._links()` — 규칙 조건 인용 연결:

```diff
         unique = list(dict.fromkeys(links))
         if not any(key is None for key, _ in unique) or not rule_keys <= {key for key, _ in unique}:
             return [], '혜택 또는 계산 규칙을 뒷받침하는 근거가 없습니다'
+        # 규칙 조건 안의 인용(구간 표기 등)을 RULE/COND로 연결한다. 위치를 못 찾으면 건너뛴다(기존 등록 판정을 바꾸지 않음).
+        for rule in raw.get('rules', []):
+            if rule.get('rule_key') not in rule_keys:
+                continue
+            for cond in rule.get('conditions', []):
+                for item in cond.get('evidence', []):
+                    match = next((e for e in located if compact(e['quote_txt']) == compact(item.get('quote_txt') or '')), None)
+                    if match:
+                        unique.append((('COND', rule['rule_key'], cond['cond_key']), match['evidence_id']))
+        unique = list(dict.fromkeys(unique))
         return unique, None
```

등록 루프에 분기 하나를 추가한다. `('COND', rule_key, cond_key)` 키는 신규 SQL `insert_rule_cond_evidence_link`로 넣는다.

```sql
-- name: insert_rule_cond_evidence_link   (common_benefit_repository.sql)
INSERT INTO db_pipeline.card_evidence_link (card_doc_id,page_no,card_doc_chunk_id,evidence_id,card_id,ev_subject_cd,card_product_item_id,rule_key,ev_item_cd,ev_item_key)
SELECT e.card_doc_id,e.page_no,e.card_doc_chunk_id,e.evidence_id,CAST(:CARD_ID AS bigint),'RULE',CAST(:BNFT_ID AS varchar),
       CAST(:RULE_KEY AS varchar),'COND',CAST(:ATOM_KEY AS varchar)
FROM db_pipeline.card_source_evidence e WHERE e.evidence_id=:EVIDENCE_ID
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING evidence_link_id;
```

`ev_item_key`는 atom key다. `build_cond_expr`가 `atom_key = cond_key`로 만들기 때문에 같은 값이다. CHECK `card_evidence_link_ck_1`(COND면 `ev_item_key <> '-'`)을 만족한다. `limits[].evidence_ids`는 `link_basis`와 관계없이 `support_key = limit_key`인 LIMIT 인용 중 위치가 확인된 것으로 채운다.

### 4.5 정합성 검증 (추출 ↔ 등록)

등록 직후 같은 트랜잭션에서 검사하고, 실패하면 REVIEW로 롤백한다. 신규 함수 `check_limit_struct(raw, data, rules)`가 다음을 확인한다.

1. 추출 `limits`의 `limit_key` 집합 = `item_data.limits`의 키 집합.
2. 규칙마다 `rule_limits[rule_key]` = 추출 `rules[].limit_keys`(등록된 규칙에 한함).
3. `limit_tiers`가 있으면 `caps[*].amount` = 대응 `limits[].limit_num`, `tiers[*].min/max` = 대응 규칙 atom `cond_min_amt/cond_max_amt_excl`.

### 4.6 기존 등록 데이터 영향

- 기존 행은 `UNCHANGED` 경로라 이 변경의 영향을 받지 않는다(1절 3번).
- 기존 run을 다시 실행해도 기존 행은 바뀌지 않는다.
- 신규 등록분만 `item_data`에 키가 늘어난다. `fn_valid_item_data` 통과(schema_ver만 검사).
- `limits`가 없는 혜택은 `item_data`가 지금과 같다(`{}` 또는 review_patch만).
- `shared_limit_problems`(공유 한도 검사)은 `candidate`의 추출 원본을 읽는 기존 로직이라 영향이 없다. 테스트로 확인한다.

---

## 5. P1 기존 데이터 보정 설계

### 5.1 도구

- **신규 스크립트** `payment_card/db_pipeline/limit_struct_backfill.py`
  - 기본은 읽기 전용 미리보기다. `--apply --confirm APPROVED_LIMIT_STRUCT_BACKFILL`일 때만 쓴다.
- **입력** 보정 대장 `docs/identity_registry/benefit_patch/LIMIT_STRUCT_BACKFILL_20261106.json`
  - 대상별 `card_id, card_product_item_id, card_extr_stg_id, expected_item_data, rule_fingerprint, item_data_patch, evidence_links[]`.
  - `status`가 `APPROVED`인 항목만 쓴다.
- **도구가 하는 일**: 4.3~4.5의 helper를 재사용해 추출 원본에서 `item_data_patch`를 **다시 계산**하고 대장 값과 같아야 진행한다(사람이 적은 값과 프로그램 계산이 같은지 이중 확인).
- **쓰기**(한 트랜잭션)
  - `UPDATE db_pipeline.card_product_item SET item_data = :new, update_date = now(), update_user_id = 'limit_struct_backfill' WHERE card_id = :c AND card_product_item_id = :id AND item_data = :expected AND md5(rule_list::text) = :rule_fp` — 1행이 아니면 롤백.
  - `insert_rule_cond_evidence_link` × N(자연 키로 재실행에 안전).
  - 사후 검사(4.5) + 대상 외 행 지문 불변 검사.
- **바꾸지 않는 것**: `item_limit_txt`, `rule_list`, `item_cond_expr`, 검색 텍스트, 임베딩, ID.

### 5.2 22 / 20261105_000099 월납 요금 청구할인

| 항목 | 내용 |
|---|---|
| 복구 원천 | `card_extr_stg 20261105_000619`(run `20261105_000042`, 문서 `20261105_000042` p1, 청크 `20261105_000173`) |
| 근거 ID | 한도 `002681 "10,000원"`(3719–3725, 연결됨), `002682 "15,000원"`(3751–3757, 연결됨). 구간 `002685 "30만원 이상⏎80만원 미만"`(3727–3741, **미연결**), `002686 "80만원 이상⏎15,000원"`(3743–3757, **미연결**) |
| 현재 구조 | `rule_list` r1(300000~800000)·r2(800000~)·r3(ETC), `value_num`·`unit` null, `item_data = {}`, `item_limit_txt` 평문 |
| 누락 구조 | `limits`(l1=10000, l2=15000, MONTH, KRW), `rule_limits`(r1→l1, r2→l2, r3→l1,l2), `limit_tiers` |
| 복구 JSON | 4.2절 예시 그대로. 자동 생성 조건(4.3) 4개 모두 충족: 구간 규칙 2개, `PREV_MONTH_SPEND`, 각 KRW 한도 1개, 구간이 겹치지 않음, 근거 위치 확인 |
| 근거 연결 추가 | `(RULE, r1, COND, c1, 002685)`, `(RULE, r2, COND, c2, 002686)` → 2건 |
| 기존 함수 사용 | `limit_tiers_text`는 사용할 수 있다. `check_limit_tiers`는 표 순서 때문에 **사용할 수 없다**(1절 2번) → 4.3 경로 사용 |
| r3 | 규칙 변경 없음(제외 대상). `rule_limits.r3 = [l1, l2]`로 "한도 안에서 승인 금액만큼"이라는 관계만 보존 |

### 5.3 23 / 20261105_000100 주요 간편결제 모아포인트 추가적립 — 두 문제를 분리

| 항목 | (a) 월 적립 한도 누락 | (b) 구간 상한 누락 |
|---|---|---|
| 현상 | 추출 `l1=1만, l2=2만, l3=5만`(MONTH, KRW)과 `r1→l1, r2→l2, r3→l3`가 등록에서 사라짐 | 규칙 atom이 `30만원 이상`, `60만원 이상`, `120만원 이상`이고 `cond_max_amt_excl`이 모두 null이라 구간이 겹침 |
| 원문 | 청크 `20261105_000176`: `전월 국내가맹점 이용실적⏎30만원 이상⏎기본적립⏎적립한도 제한 없음⏎특별/추가 적립⏎1만원⏎… 60만원 이상 … 2만원 … 120만원 이상 … 5만원` | 원문 구간 표기에 상한이 없다(표의 사다리 구조로만 암시) |
| 성격 | 추출에 있던 구조의 손실 → **복구 가능** | 원문에 적히지 않은 값 → **해석이 필요**(복구가 아님) |
| 복구 | `limits`(근거 `002739/002740/002741`, 연결됨), `rule_limits`, 구간 근거 연결 `(RULE,r1,COND,c1,002744)`, `(r2,c2,002745)`, `(r3,c3,002746)` → 3건 | 아래 결정 필요 |
| `limit_tiers` | 4.3 조건 3번(겹침)에 걸려 **자동 생성 안 함** | (b) 결정 후 생성 |

**(b) 처리 방안**

| 안 | 내용 | 판단 |
|---|---|---|
| B1 | 규칙 atom에 `cond_max_amt_excl` 추가(30만~60만 등) | 비권장: 원문 조건 인용(`cond_raw_txt`)에 없는 값을 조건에 넣는다. 조건 표시·검증 근거와 어긋난다 |
| **B2(권장)** | 규칙은 그대로 두고, `limit_tiers.tiers[].max_amt_excl`에 다음 구간 하한을 넣는다. 여기에 `max_basis: "NEXT_TIER_MIN"`과 승인 기록을 남긴다 | 원문 조건은 보존하고, 사다리 해석은 근거와 함께 표시된다. **사용자 승인 필요** |
| B3 | 상한 없이 둔다 | 현재와 같다. GraphRAG가 "60만 원 실적이면 30만·60만 구간 모두 해당"으로 혼동할 수 있다 |

(a)는 B2 승인과 관계없이 먼저 보정할 수 있다. `limit_tiers`는 B2를 승인한 뒤 추가한다.

### 5.4 20 / 20261105_000092 골프/프리미엄 아울렛 50% 청구 할인

| 항목 | 내용 |
|---|---|
| 복구 원천 | `card_extr_stg 20261105_000571`(문서 `20261105_000040` p3, 청크 `20261105_000159`) |
| 원문 | `서비스 실적 기간 내 2,400만원 이상 이용 시 보너스 할인 한도 10만원 제공 / 3,600만원 이상 이용 시 보너스 할인 한도 10만원 추가 제공` |
| 성격 | **배타적 구간이 아니라 누적 추가**("추가 제공"). `limit_tiers`(구간마다 하나의 한도)로 표현하면 의미가 왜곡된다 |
| 복구 | `limits`(bonus_base_cap 100000, bonus_additional_cap 100000, `period_cd = UNKNOWN`, 근거 `002447`, `002448` 연결됨)와 `rule_limits`(bonus_base_discount→bonus_base_cap, bonus_additional_cap_discount→bonus_additional_cap)만 보존. **`limit_tiers`는 만들지 않음**. 합계(20만 원)를 계산해 저장하지 않음 |
| 근거 연결 추가 | `(RULE, bonus_base_discount, COND, bonus_spend_24m, 002453)`, `(RULE, bonus_additional_cap_discount, COND, bonus_spend_36m, 002454)` → 2건. atom key가 같은지는 실행 전 미리보기에서 확인 |
| 우선순위 | 낮음(두 한도 금액이 같아 오답 위험이 작음). 22·23 다음에 진행 |

### 5.5 전후 비교와 롤백

- **사전**
  - `backup_db_pipeline.py`로 백업한다(메모리 기준 `stg_normalized_item` 지문 문제로 래퍼가 필요할 수 있음. 실행 전 확인).
  - 미리보기 출력: 대상 3행의 현재 `item_data`·`md5(rule_list)`, 추가 예정 연결 7건, 대상 외 `card_product_item` 전체 지문.
- **사후**
  - 대상 3행 `item_data`가 대장 값과 같은지 확인한다.
  - `item_limit_txt`·`rule_list`·`item_search_txt`·`item_embedding` 지문이 바뀌지 않았는지 확인한다.
  - `card_evidence_link`가 정확히 +7건인지 확인한다.
  - 대상 외 행 지문이 바뀌지 않았는지 확인한다.
  - `v_card_integrity_issue`가 늘지 않았는지 확인한다.
- **롤백**: 도구가 `--rollback <실행 결과 파일>`을 제공한다.
  - `item_data`를 실행 전 값으로 되돌린다(조건: 현재 값 = 보정 값).
  - 기록된 `evidence_link_id`를 DELETE한다.
  - 같은 트랜잭션에서 사후 지문을 다시 검사한다.

---

## 6. P2 Neo4j 적재 수정 설계

### 6.1 변경

`neo4j_dry_run.load_snapshot()`의 benefits SELECT에 `item_data`를 추가한다(별칭 없음, items SELECT와 같은 이름).

```diff
             "benefits": ("SELECT card_id, card_product_item_id AS card_bnft_id, item_cd AS bnft_cd, item_nm AS bnft_nm, "
                          ...
                          "item_rule_txt AS bnft_rule_txt, item_limit_txt AS bnft_limit_txt, item_search_txt AS bnft_search_txt, "
-                         "item_embedding AS bnft_embedding "
+                         "item_embedding AS bnft_embedding, item_data "
                          "FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT' ...
```

- `item_data`는 dict라 `node_properties`의 스칼라 조건에 걸리지 않는다. 노드 속성은 생기지 않고 **`source_json`에만** 들어간다. 연회비·TERMS와 같은 계약이다.
- 별도 속성 투영(`limit_tiers` JSON 속성)은 하지 않는다. Cypher 필터에 쓰지 않으므로 필요 없다.

### 6.2 호환성과 접근 경로

- `card.context`는 `apoc.map.removeKeys(properties(b), …)`로 `source_json`을 그대로 돌려준다. 그래서 **Cypher 변경 없이** Python `source(detail["context"]["benefit"])["item_data"]["limit_tiers"]`로 읽을 수 있다. hybrid·catalog 쿼리는 `item_data`를 쓰지 않는다.
- 규칙 노드, 조건 노드, 관계, key, 제약, 벡터 인덱스는 변경이 없다.
- 영향 받는 테스트: `test_neo4j_dry_run.py`, `test_neo4j_load_draft.py`의 fixture에 `item_data`를 추가한다. `test_neo4j_load_draft`의 기존 4건 실패(2026-11-04부터)는 이번 변경과 분리해 기록한다.

### 6.3 재적재 방식 비교

| 방식 | 동작 | 안전성 | 판단 |
|---|---|---|---|
| **전체 MERGE 재적재(`neo4j_load_draft --apply`)** | 같은 key로 MERGE. 혜택 34개의 `source_json`만 바뀌고, 임베딩·검색 텍스트는 스냅샷의 **기존 저장값**으로 같은 값을 다시 SET(임베딩 재생성 없음). 원천에 없는 노드가 있으면 중단. 사후 key 검사 실패 시 롤백 | 검증된 경로. 한 트랜잭션 | **채택** |
| 대상만 갱신(신규 Cypher) | 혜택 노드 `source_json`만 SET | 새 쓰기 코드가 필요하고 검증 경로가 따로 생김 | 비채택 |
| 투영 동기화(`neo4j_search_projection_sync`) | 투영 속성·공통 근거만 허용 | `source_json` 변경을 차단 항목으로 보고 중단 | 사용 불가 |

3단계(PG 보정)의 근거 연결 7건은 `dp_supported_by` 관계 7개와 `dp_card_source_evidence` 노드 7개(002685·002686·002744~002746·002453·002454)를 추가로 만든다. 전체 MERGE 재적재가 함께 반영한다. 예상 결과는 노드 1,642, 관계 2,716(근거 노드 7 + `in_chunk` 7 + `supported_by` 7)이며, 미리보기 수치로 확정한다.

순서: 3단계 COMMIT → `neo4j_dry_run --dry-run` 오류 0 → `neo4j_load_draft` 미리보기 → 승인 → `--apply` → `neo4j_validate`(7절 개선판) 차이 0 → `neo4j_search_projection_sync` 미리보기에서 차단 0.

---

## 7. P2 정합성 검증 개선 설계

### 7.1 문제

`neo4j_validate.run()`의 기대값은 `build(load_snapshot(conn))`이다. SELECT에서 빠진 컬럼은 기대값에도 없어서 "차이 0"이 된다.

### 7.2 추가 검사 1 — 컬럼 매핑 완전성 (스냅샷과 독립)

`neo4j_dry_run.py`에 원천 컬럼별 처리 방식을 명시한 표를 둔다.

```python
# 원천 컬럼 → 그래프 처리. 새 컬럼이 생기면 여기 분류하지 않는 한 검증이 실패한다.
SOURCE_COLUMNS = {
    "card_product_item": {
        "graph":      {"card_id", "card_product_item_id", "item_cd", "item_nm", "item_subtype_cd", "item_origin_cd",
                       "item_scope_cd", "item_brand_opt_cds", "item_cond_expr", "rule_list", "relation_list", "item_data",
                       "verification_status_cd", "item_valid_from", "item_valid_to_excl", "item_rule_txt", "item_limit_txt",
                       "item_type_cd"},
        "projection": {"item_search_txt", "item_embedding"},
        "excluded":   {"item_ref", "create_date", "create_user_id", "update_date", "update_user_id"},
    },
    # card_product, card_common_bnft 등도 같은 형식(1차는 card_product_item만, 2차 확대)
}
```

`neo4j_validate`가 `information_schema.columns`(신규 named query `neo4j_validation.source_columns`)를 읽어 다음 두 가지를 실패로 처리한다.

1. **분류되지 않은 컬럼**이 있으면 실패한다.
2. `graph`로 분류된 컬럼이 benefits/items SELECT 결과 행의 키(별칭 역매핑 포함)에 **실제로 없으면** 실패한다. 별칭 역매핑 표(`bnft_limit_txt → item_limit_txt` 등)는 SELECT 옆에 함께 둔다.

현재 코드에 이 검사를 넣으면 `item_data`(BENEFIT)가 2번 조건으로 실패한다. 즉 이번 결함을 잡는다.

### 7.3 추가 검사 2 — PG 직접 값 대조

신규 SQL `neo4j_validation.benefit_item_data`로 `SELECT card_id, card_product_item_id, item_data, md5(rule_list::text) FROM card_product_item WHERE item_type_cd='BENEFIT'`를 **스냅샷 함수를 거치지 않고** 직접 읽는다. Neo4j에서는 `apoc.convert.fromJsonMap(b.source_json).item_data`를 읽는다. 혜택마다 JSON이 같아야 하고, 키 누락(`null` vs 키 없음)도 차이로 본다. 같은 방식으로 `item_limit_txt` ↔ `limit_text` 속성도 대조한다. 기존 `COMPARED` 5종과 같은 `sql_cypher` 보고 형식을 쓴다.

### 7.4 GraphRAG 소비 (4단계 후반, D6)

1. `benefit_context()`에 `"limit_tiers"`와 `"rule_limits"` 요약을 추가한다(있을 때만). LLM 문맥에서 구간 ↔ 한도가 구조로 전달된다.

   ```diff
   +    data = benefit.get("item_data") or {}
   +    tiers = (data.get("limit_tiers") or {})
   +    limit_tiers = [{"label": t["label"], "min_amt": t["min_amt"], "max_amt": t["max_amt_excl"], "rule_key": t.get("rule_key"),
   +                    "cap": tiers["own"]["caps"][t["tier_key"]]["raw"]} for t in tiers.get("tiers", [])] if tiers else []
        return {..., "limits": limits,
   +            "limit_tiers": limit_tiers}
   ```

2. 신규 검증 `distorts_limit_tier(text, context)`: 문장의 "N원 이상(구간 기준)" 뒤에 나온 기간 한도 금액(`월`·`한도` 표현이 붙은 MONEY 토큰)이 그 구간의 `cap`이 아니고 **다른 구간의 cap**이면 문장을 버린다. `distorts_tier` 바로 뒤에 같은 방식으로 호출하고, `answer_text_problem`에도 추가한다.
3. `limit_tiers`가 없는 혜택은 지금과 같다. 검증을 추가하지 않으므로 오탐이 없다.

---

## 8. 검색 품질 후속 조사 항목 (42/179) — 수정하지 않음

| 항목 | 내용 |
|---|---|
| 확정 사실 | 키워드 채널만으로 179가 top_k 5 안(3위)에 있다. 실패 요청은 상세 조회에서 179를 조회하지 않았다(`app_log` 198 `detail_batch` keys) |
| 미확인 | 벡터 채널을 포함한 실제 순위, interpret LLM이 고른 ID와 이유 |
| 필요한 로그 지점 | ① `Neo4jBenefitSearch.search` 결과 `hits[*].key, rrf, channels, own_card`와 `last_trace` ② `CardGraphRAG.interpret` 출력(선택 ID·의도·버린 후보) ③ `resolve_fee_choice`·`filter_by_payment`·`drop_duplicate_benefits`가 제외한 ID와 사유. 모두 `CARD_LOG.log_summary` 수준. `app_log` 저장은 Codex 소유 파일이라 협의 후 진행 |
| 테스트 입력 | 원래 질문, "카드의정석2 DAILY 휴대전화 요금 할인과 통합 한도", "카드의정석2 DAILY 통신요금 할인", 대조군 "카드의정석2 DAILY 정기결제 할인" |
| 관찰 방법 | `verify_view`의 단계 실행(`verify_interpret` → `verify_retrieve`)으로 후보와 선택을 비교한다. interpret에는 LLM이 필요하므로 승인을 받고 2~4회만 실행한다. 벡터 채널은 질문 임베딩 1회(학원 제공 키, 사용자 확인) |
| 판단 기준 | 후보에 있는데 선택에서 빠지면 interpret 지시문·후보 표시 문제, 후보에 없으면 검색 순위 문제. "휴대전화"↔"통신(SKT·KT·LG U+)" 동의어 부재가 관계 보정에 미치는 영향은 키워드 실행으로 따로 확인 |

---

## 9. 단계별 변경 파일·함수 목록

| 단계 | 파일 | 함수·객체 | 변경 이유 |
|---|---|---|---|
| 1 | `db_pipeline_origin_search/card_graphrag.py` | `tier_token`, `rule_conflicts`, `tier_label`, `distorts_tier`, `picks_single_tier`, `tier_is_quoted`, `validate_answer`(1299행 블록), 지시문 247행(선택) | D3 |
| 1 | `tests/test_card_graphrag.py` | 신규 테스트 클래스 | 회귀 |
| 2 | `db_pipeline/extraction_service.py` | `normalize_benefit`(limit_struct), 신규 `limit_tiers_from_extraction`, `check_limit_struct` | D1 |
| 2 | `db_pipeline/product_benefit_service.py` | `_register`(item_data 구성·COND 연결 분기), `_links`, 신규 `attach_limit_evidence` | D1, D2 |
| 2 | `db_pipeline/common_benefit_repository.sql` | `insert_rule_cond_evidence_link` | D2 |
| 2 | 테스트: 정규화·등록 단위 테스트(기존 `tests/` 내 등록 테스트 파일에 추가) | — | 회귀 |
| 3 | 신규 `db_pipeline/limit_struct_backfill.py`, 대장 `docs/identity_registry/benefit_patch/LIMIT_STRUCT_BACKFILL_20261106.json` | — | 기존 데이터 |
| 3 | PG `card_product_item`(22/099, 23/100, 20/092 `item_data`), `card_evidence_link`(+7) | — | 기존 데이터 |
| 4 | `db_pipeline/neo4j_dry_run.py` | benefits SELECT, `SOURCE_COLUMNS`, 별칭 역매핑 | D4, D5 |
| 4 | `db_pipeline/neo4j_validate.py`, `neo4j_validation.sql` | 컬럼 완전성·`benefit_item_data` 대조 | D5 |
| 4 | `test_neo4j_dry_run.py`, `test_neo4j_load_draft.py`, `test_neo4j_validate.py` | fixture | 회귀 |
| 4 | Neo4j `dp_` 그래프 | 전체 MERGE 재적재 | D4 반영 |
| 4 | `card_graphrag.py` | `benefit_context`(limit_tiers), 신규 `distorts_limit_tier`, `validate_answer`·`answer_text_problem` 호출 | D6 |

---

## 10. 단계별 테스트 시나리오

모든 단위 테스트는 오프라인이다(LLM·DB 없음, fixture는 감사에서 확인한 실제 값의 형태).

| # | 시나리오 | 단계 | 입력 | 기대 결과 |
|---|---|---|---|---|
| T1 | NULL 지급값 규칙 | 1 | 22형 tier(r1 300000~800000, r2 800000~, r3 min None, value·unit None) | `distorts_tier("자동납부 시 할인됩니다.")`·`("전월 실적 30만원 이상이면 할인됩니다.")` → False, 예외 없음. `tier_text` → "30만원 이상 시 지급액 정보 없음, 80만원 이상 시 지급액 정보 없음 구간이 기재되어 있습니다." `tier_is_quoted` → 근거에 30만·80만이 있으면 True |
| T2 | 0원과 NULL 구분 | 1 | value 0·unit KRW tier와 value None tier | `tier_token` → `("MONEY", 0.0)` / `None`. `payout_known` True / False |
| T3 | 정상 숫자 지급값 | 1 | 기존 `test_card_graphrag.py` 827~847행 케이스(3,000원 이상 100원 / 10,000원 이상 500원) | 기존 기대값 그대로 |
| T4 | 혼합 tier | 1 | 한 conflict에 값 있는 tier 2개 + None tier 1개 | 값 있는 tier 사이 지급액 뒤바꿈 문장은 True(버림). None tier는 판정에 쓰이지 않음 |
| T5 | 결제 건 기준·적용 구간 2개 이상·지급값 None | 1 | basis TXN_AMT, amount가 두 구간에 해당 | `validate_answer`가 시스템 구간 문장을 만들지 않고 경고. 예외 없음. `fixed_conclusion` → `tier_answer`가 "지급액 정보 없음"으로 작성 |
| T6 | 실제 데이터 재현 | 1 | 감사 재현 스크립트와 같은 Neo4j 읽기 전용 상세 행(22/099, 42/180, 42/179) | `rule_conflicts` → 22만 conflict, `payout_known` 모두 False, 모든 helper 예외 없음 |
| T7 | 실적 구간 2개 이상 → limit_tiers 생성 | 2 | 22 `stg_raw_item` fixture + 근거 위치 | `limits` 2, `rule_limits` 3, `limit_tiers` 구간 2·caps 10000/15000·rule_key r1/r2 |
| T8 | 최상위 구간 상한 없음 | 2 | 22의 r2(max None) | 정상 생성(최상위 1개만 None 허용) |
| T9 | 상한 누락으로 겹친 구간 | 2 | 23 fixture(30만~·60만~·120만~, max 모두 None) | `limit_tiers` 생성 안 함, `limits`·`rule_limits`는 저장, 검토 사유 기록 |
| T10 | 누적 한도(배타 구간 아님) | 2 | 20 fixture(ROLLING_MONTHS, 같은 금액 2개, "추가 제공") | `limit_tiers` 생성 안 함(구간이 겹침), `limits`·`rule_limits` 저장 |
| T11 | 한도 ≠ 지급액 | 2 | 22 등록 결과 | `rule_list[*].value_num`은 여전히 null, 한도는 `item_data`에만 |
| T12 | 근거 연결 보존 | 2 | 22 raw(조건 인용 2건 위치 확인) | `_links` 결과에 `('COND','r1','c1')→002685`, `('COND','r2','c2')→002686` 포함. 위치 없는 조건 인용은 건너뛰고 등록 판정은 기존과 동일 |
| T13 | 기존 등록 불변 | 2 | 기존 run 재실행 시나리오(가짜 repo) | 기존 행 `UNCHANGED`, 쓰기 0 |
| T14 | 사람 보정 우선 | 2 | DAILY 179 후보 + SET_LIMIT_TIERS | 기존과 같은 `limit_tiers`·`item_limit_txt`(자동 생성이 덮어쓰지 않음) |
| T15 | 보정 도구 미리보기·멱등 | 3 | 실제 PG 읽기 전용 | 대상 3행·연결 7건 계획 출력. 계산값 = 대장 값. 적용 후 재실행 → 변경 0 |
| T16 | 보정 롤백 | 3 | 격리 테스트 DB 또는 트랜잭션 롤백 시험 | 실행 전 지문과 같아짐 |
| T17 | PG ↔ Neo4j 필드 정합성 | 4 | 현재 코드 + 새 검증기 | 개선 전 코드에서 `item_data` 누락으로 **실패**, 개선 후 통과 |
| T18 | 분류되지 않은 컬럼 | 4 | `SOURCE_COLUMNS`에서 한 컬럼 제거한 fixture | 검증 실패 |
| T19 | 재적재 결과 | 4 | 미리보기 | 노드·관계 증가가 근거 7건분과 일치, 혜택 34 `node_properties_changed`는 `source_json`만 |
| T20 | limit_tiers GraphRAG 전달 | 4 | 22·42 상세 행 | `benefit_context`에 구간·cap 포함. "30만원 이상 80만원 미만 구간은 월 10,000원 한도"는 통과, "80만원 이상은 월 10,000원 한도"는 `distorts_limit_tier`로 버림 |
| T21 | 기존 정상 질문 회귀 | 5 | stub LLM 질문 세트: 연회비(카드 2·5·6), ONE PICK 결제 건 구간, DAILY 정기결제·고정소비, 넷플릭스, 공통 혜택(라운지) | 이전 기대 출력과 같은 status·포인트 수(허용 차이는 문서화) |
| T22 | 원래 실패한 비교 질문 | 5 | 원 질문, stub LLM(22·42 포인트 포함) | 예외 없음. 22 구간이 "지급액 정보 없음 + 월 한도 10,000원/15,000원(구간별)"로 표현, 임의 금액 없음 |
| T23 | 실제 LLM 확인(승인 시) | 5 | 원 질문 + 22 단일 질문 + DAILY 통합 한도 질문(3회) | 오류 없음, 구간↔한도 일치 |

---

## 11. 단계별 승인 및 롤백 계획

| 단계 | 선행 조건 | DB 변경 | 승인 필요 | 완료 판정 | 실패 시 롤백 |
|---|---|---|---|---|---|
| 1 P0 | 없음 | 없음 | 코드 리뷰 | T1~T6 통과, 기존 `test_card_graphrag.py` 전체 통과, 로컬 Streamlit에서 원 질문 재현 시 예외 없음(LLM 1회는 승인 시) | Git 되돌리기(커밋 1개) |
| 2 P1 신규 | 1 완료 권장(독립 가능) | 없음(신규 등록 시에만 반영) | 코드 리뷰 | T7~T14 통과, 기존 등록 테스트 통과 | Git 되돌리기. 이미 신규 등록된 행이 있으면 3단계 도구의 롤백으로 `item_data` 복구 |
| 3 P1 기존 | 2의 helper 병합, 백업 | **PG UPDATE 3행, INSERT 7행** | **사용자 승인**(대장 APPROVED, 확인 문구), 23 B2 방안 별도 승인 | T15·T16 통과, 사후 지문 검사 통과 | 도구 `--rollback` + 백업 |
| 4 P2 | 3 COMMIT(또는 3 없이 SELECT 변경만 먼저) | **Neo4j 전체 MERGE 재적재** | **사용자 승인**(`APPROVED_DP_HANA_CARD`) | T17~T20 통과, `neo4j_validate` 차이 0(고아 문서 1건 제외), 투영 동기화 미리보기 차단 0 | 재적재 전 Neo4j 백업(`neo4j_dp_pre_reload_*` 방식)으로 복원. MERGE는 노드를 지우지 않으므로 SELECT를 되돌리고 다시 적재하면 `source_json`이 원복된다 |
| 5 통합 | 1~4 | 없음 | 실제 LLM 호출 수 승인 | T21~T23 통과 | 해당 단계 롤백 |

---

## 12. 최종 구현 순서 및 완료 기준

1. **1단계(P0)를 바로 구현한다.** 데이터 변경 없이 장애를 없애고 다른 단계와 독립적이다.
2. **2단계 helper(`limit_tiers_from_extraction`, `check_limit_struct`, `attach_limit_evidence`)를 먼저 만들고 단위 테스트를 통과시킨다.** 3단계 도구가 이 helper를 재사용한다.
3. 2단계 등록부 연결(`_register`, `_links`, SQL)을 붙인다.
4. 3단계: 대장 작성 → 미리보기 → 승인 → 22·23(a) 적용 → (승인 시) 23 B2 → 20 적용.
5. 4단계: SELECT·검증기 개선 → dry-run → 미리보기 → 승인 → 재적재 → 검증 → `benefit_context`·`distorts_limit_tier`.
6. 5단계 통합 회귀.

**최종 완료 기준**

- 원 질문과 22 단일 질문이 예외 없이 답변되고, 구간별 월 한도(30만 원 이상~80만 원 미만 10,000원, 80만 원 이상 15,000원)가 원문과 일치한다.
- 22·23·20의 추출 한도 구조가 PG `item_data`와 Neo4j `source_json`에 같은 값으로 있다.
- 구간 인용 근거가 규칙에 연결되어 그래프에 있다.
- `neo4j_validate`가 컬럼 누락을 감지할 수 있고, 현재 상태에서 차이 0이다.
- 기존 정상 질문 회귀에 차이가 없다.
- `value_num`·`rule_list`·노드 key·임베딩은 변경되지 않았다.

### 미확정 사항 (구현 전 결정 필요)

1. 23/100 구간 상한 처리 방안(B2 권장, 사용자 승인).
2. 20/092 atom key(`bonus_spend_24m/36m`)가 등록본 `rule_list`의 atom key와 같은지. 보정 도구 미리보기에서 확인한다.
3. 23/100의 `limits.applies_to_benefit_nms`가 비어 있고 `shared_scope_txt`가 "특별/추가 적립"이다. 이 한도가 이 혜택 전용인지, 카드 내 다른 특별 적립과 공유하는지(공유라면 `shared` 그룹 필요). 원문 "통합 월 적립 한도"(002742) 해석은 사람이 확인해야 한다.
4. `backup_db_pipeline.py`를 현재 스키마에서 그대로 실행할 수 있는지(래퍼 필요 여부).
5. 8절 로그 보강을 Codex 소유 파일에 넣을지(소유자 협의).
