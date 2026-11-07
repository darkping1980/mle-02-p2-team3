-- Purpose: list a card's benefits and attached conditions, limits, and targets.
-- Parameters: :card_name is a partial card name. PostgreSQL JSONB syntax.
SELECT c.id AS card_id, b.id AS benefit_id, b.props ->> 'name' AS benefit_name,
       cond.id AS condition_id, cond.props AS condition_props,
       lim.id AS limit_id, lim.props AS limit_props,
       tgt.id AS target_id, tgt.props AS target_props
FROM fp_nodes AS c
JOIN fp_edges AS offers ON offers.source_id = c.id AND offers.edge_type = 'OFFERS'
JOIN fp_nodes AS b ON b.id = offers.target_id AND b.node_type = 'Benefit'
LEFT JOIN fp_edges AS hc ON hc.source_id = b.id AND hc.edge_type = 'HAS_CONDITION'
LEFT JOIN fp_nodes AS cond ON cond.id = hc.target_id
LEFT JOIN fp_edges AS hl ON hl.source_id = b.id AND hl.edge_type = 'HAS_LIMIT'
LEFT JOIN fp_nodes AS lim ON lim.id = hl.target_id
LEFT JOIN fp_edges AS at ON at.source_id = b.id AND at.edge_type = 'APPLIES_TO'
LEFT JOIN fp_nodes AS tgt ON tgt.id = at.target_id
WHERE c.node_type = 'Card'
  AND lower(COALESCE(c.props ->> 'name', c.props ->> 'product_name')) LIKE '%' || lower(:card_name) || '%'
ORDER BY b.id, cond.id, lim.id, tgt.id;

-- Purpose: find source locations for evidence attached to a benefit node.
-- Parameters: :benefit_id is a fp_nodes.id.
SELECT e.doc_sha256, e.page_no, e.start_pos, e.end_pos, e.quote_status
FROM fp_evidence AS e
WHERE e.node_id = :benefit_id
ORDER BY e.doc_sha256, e.page_no, e.start_pos;

-- Purpose: list benefit pairs connected by a MUTUALLY_EXCLUSIVE relation once.
-- Parameters: :card_name is a partial card name.
SELECT DISTINCT b1.id AS benefit_id, b1.props ->> 'name' AS benefit_name,
       b2.id AS exclusive_benefit_id, b2.props ->> 'name' AS exclusive_benefit_name
FROM fp_edges AS x
JOIN fp_nodes AS b1 ON b1.id = x.source_id AND b1.node_type = 'Benefit'
JOIN fp_nodes AS b2 ON b2.id = x.target_id AND b2.node_type = 'Benefit'
WHERE x.edge_type = 'MUTUALLY_EXCLUSIVE'
  AND EXISTS (
    SELECT 1 FROM fp_edges AS o
    JOIN fp_nodes AS c ON c.id = o.source_id
    WHERE o.target_id = b1.id AND o.edge_type = 'OFFERS'
      AND c.node_type = 'Card'
      AND lower(COALESCE(c.props ->> 'name', c.props ->> 'product_name')) LIKE '%' || lower(:card_name) || '%'
  )
ORDER BY b1.id, b2.id;

-- Purpose: list shared limits and benefits that use them for a card.
-- Parameters: :card_name is a partial card name.
SELECT DISTINCT b.id AS benefit_id, b.props ->> 'name' AS benefit_name,
       lim.id AS limit_id, lim.props AS limit_props
FROM fp_nodes AS c
JOIN fp_edges AS o ON o.source_id = c.id AND o.edge_type = 'OFFERS'
JOIN fp_nodes AS b ON b.id = o.target_id AND b.node_type = 'Benefit'
JOIN fp_edges AS hl ON hl.source_id = b.id AND hl.edge_type = 'HAS_LIMIT'
JOIN fp_nodes AS lim ON lim.id = hl.target_id AND lim.node_type = 'Limit'
WHERE c.node_type = 'Card'
  AND lower(COALESCE(c.props ->> 'name', c.props ->> 'product_name')) LIKE '%' || lower(:card_name) || '%'
  AND CAST(lim.props ->> 'shared' AS TEXT) IN ('true', '1')
ORDER BY lim.id, b.id;

-- Purpose: traverse outgoing graph edges from a node up to the requested hop limit.
-- Parameters: :start_node_id is a fp_nodes.id; :max_hops is a nonnegative integer.
WITH RECURSIVE walk(node_id, hop) AS (
  SELECT n.id, 0
  FROM fp_nodes AS n WHERE n.id = :start_node_id
  UNION ALL
  SELECT e.target_id, w.hop + 1
  FROM walk AS w
  JOIN fp_edges AS e ON e.source_id = w.node_id
  WHERE w.hop < :max_hops
)
SELECT w.hop, n.id, n.node_type, n.props
FROM walk AS w JOIN fp_nodes AS n ON n.id = w.node_id
ORDER BY w.hop, n.id;
