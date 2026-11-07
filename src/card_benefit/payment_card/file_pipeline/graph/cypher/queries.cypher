// 1) Count nodes by Fp label.
MATCH (n:FpIssuer) RETURN 'FpIssuer' AS label, count(n) AS count
UNION ALL MATCH (n:FpCard) RETURN 'FpCard' AS label, count(n) AS count
UNION ALL MATCH (n:FpBenefit) RETURN 'FpBenefit' AS label, count(n) AS count
UNION ALL MATCH (n:FpCondition) RETURN 'FpCondition' AS label, count(n) AS count
UNION ALL MATCH (n:FpLimit) RETURN 'FpLimit' AS label, count(n) AS count
UNION ALL MATCH (n:FpTarget) RETURN 'FpTarget' AS label, count(n) AS count;

// 2) Find benefits offered by cards with a matching name.
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
WHERE toLower(coalesce(c.name, c.product_name, '')) CONTAINS '우리'
RETURN c.product_name AS card, b.name AS benefit, b.method AS method, b.rate AS rate
ORDER BY benefit LIMIT 30;

// 3) Explore benefit conditions, limits, and targets.
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
WHERE toLower(coalesce(c.name, c.product_name, '')) CONTAINS '우리'
OPTIONAL MATCH (b)-[:FP_HAS_CONDITION]->(condition:FpCondition)
OPTIONAL MATCH (b)-[:FP_HAS_LIMIT]->(limit:FpLimit)
OPTIONAL MATCH (b)-[:FP_APPLIES_TO]->(target:FpTarget)
RETURN c.product_name AS card, b.name AS benefit,
       collect(DISTINCT condition.text) AS conditions,
       collect(DISTINCT limit.text) AS limits,
       collect(DISTINCT target.text) AS targets
ORDER BY card, benefit LIMIT 30;

// 4) Find benefits that apply to coffee targets.
MATCH (b:FpBenefit)-[:FP_APPLIES_TO]->(t:FpTarget)
WHERE toLower(coalesce(t.name, t.text, '')) CONTAINS '커피'
RETURN b.name AS benefit, t.name AS target_name, t.text AS target_text
ORDER BY benefit LIMIT 30;

// 5) Find nodes with ambiguous evidence.
MATCH (n:FpIssuer|FpCard|FpBenefit|FpCondition|FpLimit|FpTarget)-[:FP_HAS_EVIDENCE]->(e:FpEvidence)
WHERE e.quote_status = 'ambiguous'
RETURN labels(n) AS labels, n.id AS node_id, e.doc_sha256 AS document,
       e.edge_id AS edge_id, e.quote_status AS status
ORDER BY document, node_id LIMIT 50;

// 6) Find mutually exclusive benefit pairs on the same card.
MATCH (c:FpCard)-[:FP_OFFERS]->(a:FpBenefit)-[:FP_MUTUALLY_EXCLUSIVE]-(b:FpBenefit)<-[:FP_OFFERS]-(c)
RETURN DISTINCT c.product_name AS card, a.name AS benefit_a, b.name AS benefit_b
ORDER BY card, benefit_a LIMIT 50;

// 7) Trace from a card to its benefit details.
MATCH path = (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
             -[:FP_HAS_CONDITION|FP_HAS_LIMIT|FP_APPLIES_TO*0..1]->(detail:FpCondition|FpLimit|FpTarget)
RETURN path LIMIT 50;

// 샘플 확인용
// 1) 카드에서 혜택과 조건·한도·대상까지 두 단계 시각화
MATCH path=(c:FpCard {id: $card_id})-[:FP_OFFERS]->(b:FpBenefit)
OPTIONAL MATCH (b)-[:FP_HAS_CONDITION|FP_HAS_LIMIT|FP_APPLIES_TO|FP_EXCLUDES]->(detail:FpCondition|FpLimit|FpTarget)
RETURN path, detail LIMIT 100;

// 2) 카드별 혜택 수
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
RETURN c.id AS card_id, coalesce(c.product_name, c.productName, c.name, c.card_name, c.title) AS product_name, count(DISTINCT b) AS benefits
ORDER BY benefits DESC, card_id;

// 3) 같은 이름을 가진 Benefit 노드가 여러 개인 경우
MATCH (b:FpBenefit)
WITH coalesce(b.name, b.product_name, b.title) AS benefit_name, collect(b.id) AS ids, count(*) AS copies
WHERE benefit_name IS NOT NULL AND copies > 1
RETURN benefit_name, ids, copies ORDER BY copies DESC, benefit_name;

// 4) 여러 카드에 연결된 Benefit
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
WITH b, collect(DISTINCT c.id) AS card_ids, count(DISTINCT c) AS card_count
WHERE card_count > 1
RETURN b.id AS benefit_id, coalesce(b.name, b.product_name, b.title) AS benefit_name, card_ids, card_count
ORDER BY card_count DESC, benefit_id;

// 5) 근거가 ambiguous 또는 missing인 Fp 노드 수
MATCH (n:FpIssuer|FpCard|FpBenefit|FpCondition|FpLimit|FpTarget)
OPTIONAL MATCH (node)-[:FP_HAS_EVIDENCE]->(e:FpEvidence)
WITH n AS node, collect(e.quote_status) AS statuses
WHERE size(statuses) = 0 OR any(status IN statuses WHERE status IN ['ambiguous', 'missing'])
RETURN count(node) AS nodes_with_ambiguous_or_missing_evidence;

// 한국어 보기 쿼리: 캡션 속성 생성 후 실행
// 혜택, 관계, 조건 종류와 한도·대상 내용을 함께 확인
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
OPTIONAL MATCH (b)-[r:FP_HAS_CONDITION]->(condition:FpCondition)
OPTIONAL MATCH (b)-[:FP_HAS_LIMIT]->(limit:FpLimit)
OPTIONAL MATCH (b)-[:FP_APPLIES_TO|FP_EXCLUDES]->(target:FpTarget)
RETURN coalesce(c.caption_ko, c.name) AS 카드,
       coalesce(b.caption_ko, b.name) AS 혜택,
       coalesce(r.label_ko, type(r)) AS 관계,
       condition.cond_kind_ko AS 조건종류, condition.text AS 조건내용,
       limit.period_ko AS 한도주기, limit.text AS 한도내용,
       target.text AS 대상내용
ORDER BY 카드, 혜택 LIMIT 50;

// 혜택별 조건과 한도 수. 한도와 조건 사이의 연결 관계는 모델에 없음.
MATCH (c:FpCard)-[:FP_OFFERS]->(b:FpBenefit)
OPTIONAL MATCH (b)-[:FP_HAS_CONDITION]->(condition:FpCondition)
WITH c, b, count(DISTINCT condition) AS 조건수
OPTIONAL MATCH (b)-[:FP_HAS_LIMIT]->(limit:FpLimit)
RETURN coalesce(c.caption_ko, c.name) AS 카드,
       coalesce(b.caption_ko, b.name) AS 혜택,
       조건수, count(DISTINCT limit) AS 한도수
ORDER BY 카드, 혜택 LIMIT 50;
