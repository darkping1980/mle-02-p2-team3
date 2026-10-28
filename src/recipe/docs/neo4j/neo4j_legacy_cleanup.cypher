// =====================================================================
// [사용하지 않음 · 기록용] 이전(Sol) Rcp 그래프 → 목표 모델 선택적 정리안
// 2026-10-22 전체 초기화 후 재적재 방식으로 전환해 이 파일은 실행하지 않았다(neo4j_target_model_migration.md).
//
// 이 파일은 Named Mapper가 아니며(recipe_recommender/ 밖) 어떤 프로그램도 자동 실행하지 않는다.
// 사용자가 승인한 뒤 DBeaver 등에서 아래 순서대로 한 문장씩 실행한다.
// 대상은 Rcp 접두어 프로젝트 객체뿐이다. 다른 실습 제약조건(article_id, case_id, law_name,
// movie_title, person_name, rule_name)과 LOOKUP 인덱스는 건드리지 않는다. 전체 삭제·DETACH DELETE를 쓰지 않는다.
//
// 사전 백업(읽기 전용 내보내기, 2026-10-22):
//   D:\Bootcamp\vscode\workspace\graph-rag-db-backups\neo4j_20261022_legacy_rcp_objects\
//   (분류 노드 19, 분류 관계 275, 레시피 rcp_cat_id 1,156, 식재료 ingr_cat_id 275, rcp_ 제약 5·인덱스 7)
// 분류 원천은 PostgreSQL recipe_legacy_20261022.ingr_cat 에도 보존되어 있다.
// =====================================================================

// 1) 새 단독 키 제약 추가(추가만 함). 현재 rcp_id·ingr_id 중복 0건을 읽기 전용으로 확인했다.
CREATE CONSTRAINT rcp_recipe_key IF NOT EXISTS FOR (r:RcpRecipe) REQUIRE r.rcp_id IS UNIQUE;
CREATE CONSTRAINT rcp_ingredient_key IF NOT EXISTS FOR (i:RcpIngredient) REQUIRE i.ingr_id IS UNIQUE;

// 2) 이전 모델 제약조건 3개 제거(각각이 소유한 RANGE 인덱스도 함께 제거됨)
DROP CONSTRAINT rcp_recipe_composite_key IF EXISTS;
DROP CONSTRAINT rcp_ingredient_composite_key IF EXISTS;
DROP CONSTRAINT rcp_ingredient_category_key IF EXISTS;

// 3) 식재료 분류 관계 275개 삭제(라벨·관계 유형으로 범위를 한정)
MATCH (:RcpIngredient)-[e:RCP_IN_INGREDIENT_CATEGORY]->(:RcpIngredientCategory)
DELETE e;

// 4) 식재료 분류 노드 19개 삭제. 다른 관계가 남아 있으면 DELETE가 실패하므로 의도하지 않은 삭제를 막는다.
MATCH (c:RcpIngredientCategory)
DELETE c;

// 5) 분류 속성 제거(레시피 1,156, 식재료 275). 분류는 관계로만 표현한다.
MATCH (r:RcpRecipe) WHERE r.rcp_cat_id IS NOT NULL REMOVE r.rcp_cat_id;
MATCH (i:RcpIngredient) WHERE i.ingr_cat_id IS NOT NULL REMOVE i.ingr_cat_id;

// 6) 이후 프로젝트 폴더에서:
//    python -m recipe_recommender.setup.load_recipe_graph            (dry-run, 사전 점검 통과 확인)
//    python -m recipe_recommender.setup.load_recipe_graph --apply    (MERGE 2회·검증; 신규 노드·관계 0 예상)
//    python -m recipe_recommender.setup.load_recipe_graph --verify-only
