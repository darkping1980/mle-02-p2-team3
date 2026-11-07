-- 실행 전 확인:
--   select count(*) from public.fp_nodes;
--   select count(*) from public.fp_edges;
-- 실행 후 확인:
--   select count(*) from fp_chat.nodes;
--   select count(*) from fp_chat.edges;
--   fp_chat.nodes 행 수는 fp_nodes 행 수 + distinct fp_evidence.doc_sha256 수,
--   fp_chat.edges 행 수는 fp_edges 행 수 + 제한 후 distinct SUPPORTED_BY 쌍 수와 같아야 합니다.
-- 되돌리기(뷰만 개별 삭제; 스키마나 원본 테이블은 삭제하지 않음):
--   drop view if exists fp_chat.edges;
--   drop view if exists fp_chat.nodes;
-- PostgreSQL 15+에서 생략된 security_invoker는 false(뷰 소유자 권한)입니다.
-- 따라서 RLS 활성화 및 정책 없음으로 fp_*가 일반 사용자에게 비어 있더라도,
-- 뷰 소유자가 RLS를 우회할 수 있는 소유자/서비스 계정 접속이면 조회될 수 있습니다.
-- 챗봇 DB_URL의 역할은 확인하지 않았으며 소유자/서비스 계정이라는 점은 추정입니다.
-- 권한은 Supabase service_role에 SELECT만 부여합니다. 실제 연결 역할은 별도 확인이 필요합니다.

create schema if not exists fp_chat;

create or replace view fp_chat.nodes as
with document_rows as (
  select
    e.doc_sha256,
    min(e.page_no) filter (where e.quote_status = 'located') as located_page
  from public.fp_evidence e
  group by e.doc_sha256
)
select
  md5(n.id)::uuid as id,
  left(btrim(regexp_replace(coalesce(n.props->>'name', n.props->>'text', n.props->>'product_name', n.id), '\s+', ' ', 'g')), 80) as name,
  n.node_type as label,
  coalesce(n.props, '{}'::jsonb) || jsonb_build_object(
    'fp_id', n.id,
    'run_id', n.run_id,
    'chunk_id', n.chunk_id
  ) as props
from public.fp_nodes n
union all
select
  md5('doc:' || d.doc_sha256)::uuid as id,
  '문서 ' || left(d.doc_sha256, 8) as name,
  'Document'::text as label,
  jsonb_build_object(
    'summary', '문서 해시 ' || left(d.doc_sha256, 8) || ', 쪽 ' || coalesce(d.located_page::text, '미상') || '…',
    'fp_id', 'doc:' || d.doc_sha256
  ) as props
from document_rows d;

create or replace view fp_chat.edges as
with document_rows as (
  select
    e.doc_sha256,
    min(e.page_no) filter (where e.quote_status = 'located') as located_page
  from public.fp_evidence e
  group by e.doc_sha256
), document_links as (
  -- 노드 자체 근거와 엣지 근거의 양 끝 노드를 문서 후보로 모읍니다.
  select e.node_id as fp_node_id, e.doc_sha256, e.quote_status
  from public.fp_evidence e
  where e.node_id is not null
  union all
  select endpoint.fp_node_id, e.doc_sha256, e.quote_status
  from public.fp_evidence e
  join public.fp_edges edge on edge.id = e.edge_id
  cross join lateral (values (edge.source_id), (edge.target_id)) endpoint(fp_node_id)
  where e.edge_id is not null
), ranked_links as (
  -- 노드별 최대 3개 문서. located 근거를 우선하고 해시로 결정적 정렬합니다.
  select distinct on (fp_node_id, doc_sha256)
    fp_node_id, doc_sha256,
    case when bool_or(quote_status = 'located') over (partition by fp_node_id, doc_sha256)
         then 'located' else quote_status end as preferred_status
  from document_links
  order by fp_node_id, doc_sha256,
           (quote_status = 'located') desc
), limited_links as (
  select fp_node_id, doc_sha256
  from (
    select rl.fp_node_id, rl.doc_sha256,
           row_number() over (
             partition by rl.fp_node_id
             order by (rl.preferred_status = 'located') desc, rl.doc_sha256
           ) as document_rank
    from ranked_links rl
  ) ranked
  where document_rank <= 3
)
select
  md5(edge.id)::uuid as id,
  md5(edge.source_id)::uuid as source,
  md5(edge.target_id)::uuid as target,
  edge.edge_type as type
from public.fp_edges edge
union all
select
  md5('supported:' || link.fp_node_id || ':' || link.doc_sha256)::uuid as id,
  md5(link.fp_node_id)::uuid as source,
  md5('doc:' || link.doc_sha256)::uuid as target,
  'SUPPORTED_BY'::text as type
from limited_links link;

-- 원본 fp_*는 읽기 전용으로 노출합니다. 뷰는 기본적으로 갱신 불가능한 union 뷰이며
-- 명시적으로 SELECT만 허용합니다. 다른 역할에 권한을 주려면 별도 검토가 필요합니다.
grant usage on schema fp_chat to service_role;
grant select on fp_chat.nodes, fp_chat.edges to service_role;
