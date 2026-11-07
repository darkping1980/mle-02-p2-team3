-- GraphRAG 챗봇용 Supabase(PostgreSQL) 스키마. Supabase 대시보드의 SQL Editor에서 실행하세요.
-- 테이블은 전용 스키마 graphrag 아래에 만듭니다. 팀의 card_benefit 등 다른 스키마와 이름이 겹치지 않습니다.
-- 아직 실제 Supabase에서 실행해 보지 않았습니다. 오류가 나면 메시지를 알려주세요.
-- 이미 예전 버전(public.nodes / public.edges)을 만들었다면 이 파일 대신 migrate_public_to_graphrag.sql을 먼저 보세요.

-- 1) 스키마와 테이블 ----------------------------------------------------------
create schema if not exists graphrag;

create table if not exists graphrag.nodes (
  id    uuid primary key default gen_random_uuid(),
  name  text not null,                      -- 화면과 검색에 쓰는 이름
  label text not null,                      -- 타입: Service, Team, Document ...
  props jsonb not null default '{}'::jsonb, -- 추가 속성 (예: {"summary": "..."})
  unique (label, name)
);

create table if not exists graphrag.edges (
  id     uuid primary key default gen_random_uuid(),
  source uuid not null references graphrag.nodes(id) on delete cascade,
  target uuid not null references graphrag.nodes(id) on delete cascade,
  type   text not null,                     -- 관계: OWNS, CALLS, NOTIFIES, DOCUMENTED_IN ...
  unique (source, target, type)
);

create index if not exists edges_source_idx on graphrag.edges (source);
create index if not exists edges_target_idx on graphrag.edges (target);
create index if not exists nodes_name_idx   on graphrag.nodes (name);

-- 2) 샘플 데이터 (미리보기와 같은 임의 예시. 실제 카드 데이터로 바꿀 때 지우세요) --
insert into graphrag.nodes (name, label, props) values
  ('결제팀',        'Team',     '{}'),
  ('결제 API',      'Service',  '{}'),
  ('주문 서비스',   'Service',  '{}'),
  ('정산 배치',     'Service',  '{}'),
  ('알림 서비스',   'Service',  '{}'),
  ('결제 운영 문서', 'Document', '{"summary": "결제 API 장애 대응 절차와 운영 기준"}')
on conflict (label, name) do nothing;

insert into graphrag.edges (source, target, type)
select s.id, t.id, v.type
from (values
  ('결제팀',      'OWNS',          '결제 API'),
  ('주문 서비스', 'CALLS',         '결제 API'),
  ('정산 배치',   'CALLS',         '결제 API'),
  ('주문 서비스', 'NOTIFIES',      '알림 서비스'),
  ('결제 API',    'DOCUMENTED_IN', '결제 운영 문서')
) as v(src, type, dst)
join graphrag.nodes s on s.name = v.src
join graphrag.nodes t on t.name = v.dst
on conflict (source, target, type) do nothing;

-- 3) 접근 제한 ------------------------------------------------------------
-- RLS를 켜고 정책을 만들지 않으면, Supabase의 공개 API 키(anon)로는 이 테이블을 읽을 수 없습니다.
-- 새 스키마는 기본적으로 공개 API(Exposed schemas)에 노출되지 않으므로 한 번 더 막혀 있습니다.
-- 챗봇은 서버(Streamlit)에서 DB 연결 문자열로 접속하므로 공개 API로 열 필요가 없습니다.
alter table graphrag.nodes enable row level security;
alter table graphrag.edges enable row level security;

-- (선택) 챗봇 전용 읽기 전용 계정. 비밀번호를 바꾼 뒤 주석을 풀고 실행하세요.
-- 풀러 주소로 접속할 때는 사용자 이름이 "chatbot_ro.<프로젝트 ref>" 형식일 수 있으니 연결 화면에서 확인하세요.
-- create role chatbot_ro login password '여기에-긴-비밀번호';
-- grant usage on schema graphrag to chatbot_ro;
-- grant select on graphrag.nodes, graphrag.edges to chatbot_ro;
-- create policy chatbot_read_nodes on graphrag.nodes for select to chatbot_ro using (true);
-- create policy chatbot_read_edges on graphrag.edges for select to chatbot_ro using (true);
