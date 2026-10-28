# COOKRCP01.csv 원본 및 코드 매핑

`src/data/COOKRCP01.csv`는 UTF-8(BOM) 1,156행·55열이며 따옴표 안 줄바꿈을 포함합니다. `rcp_raw`는 55개 원본 헤더를 소문자 이름의 TEXT 컬럼으로 보존합니다(빈 문자열만 NULL, 그 외는 공백 포함 원형). 원본에 없는 식별 컬럼은 두 개입니다.

- `rcp_raw_id`: 수집 회차 ID. 적재 시작 시 `recipe.fn_get_biz_id('import_batch')`로 한 번 발급하고 그 회차의 1,156행이 공유합니다.
- `rcp_raw_seq`: 회차 내 원본 행 순번. CSV 데이터 행 순서대로 `000001`~`001156`을 Python이 만듭니다.

## 원본 55개 헤더

```text
RCP_SEQ, RCP_NM, RCP_WAY2, RCP_PAT2, INFO_WGT, INFO_ENG, INFO_CAR, INFO_PRO, INFO_FAT, INFO_NA, HASH_TAG, ATT_FILE_NO_MAIN, ATT_FILE_NO_MK, RCP_PARTS_DTLS, MANUAL01, MANUAL_IMG01, MANUAL02, MANUAL_IMG02, MANUAL03, MANUAL_IMG03, MANUAL04, MANUAL_IMG04, MANUAL05, MANUAL_IMG05, MANUAL06, MANUAL_IMG06, MANUAL07, MANUAL_IMG07, MANUAL08, MANUAL_IMG08, MANUAL09, MANUAL_IMG09, MANUAL10, MANUAL_IMG10, MANUAL11, MANUAL_IMG11, MANUAL12, MANUAL_IMG12, MANUAL13, MANUAL_IMG13, MANUAL14, MANUAL_IMG14, MANUAL15, MANUAL_IMG15, MANUAL16, MANUAL_IMG16, MANUAL17, MANUAL_IMG17, MANUAL18, MANUAL_IMG18, MANUAL19, MANUAL_IMG19, MANUAL20, MANUAL_IMG20, RCP_NA_TIP
```

## 정제 매핑

| CSV 필드 | 대상 | 변환 정책 |
|---|---|---|
| `RCP_SEQ` | `rcp_raw.rcp_seq`, `rcp.rcp_seq` | 원본 문자열 유지. 내부 레시피 ID `rcp_id`와 별개 |
| `RCP_PAT2` | `rcp_cat.rcp_cat_nm` → `rcp.rcp_cat_id` | 원본 라벨과 요리 종류명을 정확 매핑 |
| `RCP_WAY2` | `common_cd(common_code_grp_id='COOK_MTHD')` 의 `common_cd_nm` 으로 조회한 `common_cd` → `rcp.cook_mthd_cd` | 원본은 한글 명칭. 6자리 코드로 바꿔 저장(예: 찌기 → `000004`). 코드표에 없는 명칭은 검증 오류(코드 임의 부여 금지) |
| `RCP_NM` | `rcp.rcp_nm` | 앞뒤 공백 제거 |
| `INFO_WGT` | `rcp.rcp_serving_weight_value` | 숫자 변환 후보; 단위 미확정 |
| `INFO_ENG`, `INFO_CAR`, `INFO_PRO`, `INFO_FAT`, `INFO_NA` | 영양 컬럼(kcal, g, g, g, mg) | 변환 실패·열량 불일치는 `REVIEW_REQUIRED`; 값 보정 금지 |
| `HASH_TAG` | `rcp.rcp_hash_tag` | 식재료 목록으로 해석하지 않음 |
| `ATT_FILE_NO_MAIN`, `ATT_FILE_NO_MK` | 대표 이미지 URL 컬럼 | 원본 주소 유지 |
| `RCP_PARTS_DTLS` | `rcp_ingr_stg` (부모: `rcp_raw`) | 항목 원문·등장 순번·수량·단위·구획·검토 상태 보존 |
| `MANUALnn`, `MANUAL_IMGnn` | `rcp_step.step_no = nn` | 설명이 있는 단계만; 번호 재부여 없음; 앞의 "nn. " 번호만 제거 |
| `RCP_NA_TIP` | `rcp.rcp_sodium_reduction_tip_txt` | 앞뒤 공백 제거 |

## 실제 고유값과 참조 마스터

`RCP_PAT2`, `RCP_WAY2` 모두 공란 없이 6개 고유값입니다. 요리 종류는 적재기가 CSV 값으로 `rcp_cat`에 등록합니다.
조리 방법은 CSV 값으로 코드를 만들지 않고, 확정 코드표 `recipe_recommender/data/cook_mthd_cd_seed.csv`를 등록한 뒤
`RCP_WAY2`(명칭)로 코드를 찾습니다(2026-10-23 코드·명칭 분리, `cook_mthd_code_migration_20261023.md`).

| 요리 종류 (`rcp_cat`) | 건수 | 조리 방법 `common_cd` | `common_cd_nm` (= `RCP_WAY2`) | 건수 |
|---|---:|---|---|---:|
| 국&찌개 | 103 | `000001` | 굽기 | 259 |
| 기타 | 37 | `000002` | 끓이기 | 326 |
| 반찬 | 574 | `000003` | 볶기 | 108 |
| 밥 | 119 | `000004` | 찌기 | 82 |
| 일품 | 181 | `000005` | 튀기기 | 71 |
| 후식 | 142 | `000006` | 기타 | 310 |

같은 행의 요리 종류와 조리 방법은 서로 관계가 없습니다(두 목록을 나란히 적은 것).

## Staging에서 최종 관계로 변환

`rcp_ingr_stg`의 부모는 `rcp_raw (rcp_raw_id, rcp_raw_seq)`입니다. 같은 재료가 원문에 반복되면 staging에서 각각 보존합니다. 최종 변환은 선택 회차의 `AUTO_APPROVED`/`MANUAL_APPROVED` 행만 대상으로, `rcp_raw.rcp_seq`로 같은 회차의 `rcp`를 찾아 `rcp_id`를 얻고, `ingr (ingr_id)` 존재를 확인한 뒤 PK `(rcp_id, ingr_id)`로 중복을 제거합니다. 요리 분류는 원본 `RCP_PAT2`를 `rcp_cat`에 대응시켜 `rcp_cat_rel (rcp_id, rcp_cat_id)` 관계로 등록합니다(목표 모델, `recipe_target_schema.sql`).
