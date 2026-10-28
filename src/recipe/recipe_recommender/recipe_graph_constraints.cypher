// PostgreSQL 목표 모델(rcp_id·ingr_id 단독 PK, rcp_cat_rel 다중 분류, 식재료 분류 없음)용 레시피 그래프 스키마.
// 노드 라벨은 PostgreSQL recipe 스키마 테이블명과 같다(rcp, ingr, rcp_cat).
// 재실행은 Python CLI --apply에서 사전 점검 후 수행한다. 이전 모델의 복합 키 제약
// (rcp_recipe_composite_key, rcp_ingredient_composite_key, rcp_ingredient_category_key)이나
// Rcp* 라벨 시절 제약·인덱스(rcp_recipe_key 등)가 남아 있으면
// 적재 서비스가 중단하므로, 이전 그래프 정리는 별도 승인 절차로 먼저 수행해야 한다.
// 유일성 제약이 만드는 RANGE 인덱스를 재사용하므로 같은 키의 일반 인덱스를 추가하지 않음.

// name: rcp_key
CREATE CONSTRAINT rcp_key IF NOT EXISTS
FOR (r:rcp) REQUIRE r.rcp_id IS UNIQUE;

// name: rcp_seq_key
CREATE CONSTRAINT rcp_seq_key IF NOT EXISTS
FOR (r:rcp) REQUIRE r.rcp_seq IS UNIQUE;

// name: ingr_key
CREATE CONSTRAINT ingr_key IF NOT EXISTS
FOR (i:ingr) REQUIRE i.ingr_id IS UNIQUE;

// name: rcp_cat_key
CREATE CONSTRAINT rcp_cat_key IF NOT EXISTS
FOR (c:rcp_cat) REQUIRE c.rcp_cat_id IS UNIQUE;

// 조리 단계 노드 키 = PostgreSQL recipe.rcp_step PK (rcp_id, step_no). step_no는 원본 MANUAL 번호(정수).
// name: rcp_step_key
CREATE CONSTRAINT rcp_step_key IF NOT EXISTS
FOR (s:rcp_step) REQUIRE (s.rcp_id, s.step_no) IS UNIQUE;

// 이름으로 찾는 질의용. 별칭 목록은 리스트라 이 RANGE 인덱스의 대상이 아님.
// name: rcp_nm_idx
CREATE RANGE INDEX rcp_nm_idx IF NOT EXISTS
FOR (r:rcp) ON (r.rcp_nm);

// name: ingr_nm_norm_idx
CREATE RANGE INDEX ingr_nm_norm_idx IF NOT EXISTS
FOR (i:ingr) ON (i.ingr_nm_norm);
