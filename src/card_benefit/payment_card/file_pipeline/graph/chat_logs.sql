-- 참고용, 실행 전 사용자 승인
create schema if not exists fp_chat;

create table if not exists public.fp_chat_logs (
  id uuid primary key,
  created_at timestamptz not null,
  session_id text,
  question text not null,
  answer text not null,
  answer_format_version text not null,
  model text,
  prompt_tokens integer,
  completion_tokens integer,
  cost_usd numeric,
  latency_ms jsonb not null default '{}'::jsonb,
  selected_entities text[] not null default '{}',
  retrieved_node_ids text[] not null default '{}',
  retrieved_node_count integer not null default 0,
  source_refs jsonb not null default '[]'::jsonb,
  source_refs_error text,
  graph_schema text not null,
  run_ids text[] not null default '{}',
  refusal boolean not null default false,
  ungrounded_numbers text[] not null default '{}',
  format_check jsonb not null default '{}'::jsonb,
  user_feedback text,
  app_version text
);

create index if not exists fp_chat_logs_created_at_idx on public.fp_chat_logs (created_at);
create index if not exists fp_chat_logs_session_id_idx on public.fp_chat_logs (session_id);

alter table public.fp_chat_logs enable row level security;

-- 정책 적용 전 실제 역할 이름으로 아래 자리표시자를 바꾸고 검토한다.
-- chatbot app role은 INSERT만 허용한다.
-- create policy fp_chat_logs_app_insert on public.fp_chat_logs
--   for insert to chatbot_app_role with check (true);
-- reviewer account는 SELECT만 허용한다.
-- create policy fp_chat_logs_reviewer_select on public.fp_chat_logs
--   for select to reviewer_role using (true);

comment on table public.fp_chat_logs is
  '질문 원문에 개인정보가 포함될 수 있음. 앱 역할은 INSERT 전용, 검토자 역할은 SELECT 전용 정책을 실제 역할명으로 설정한다.';
comment on column public.fp_chat_logs.source_refs is
  'fp_evidence에서 수집한 노드 ID, 문서 SHA-256, 쪽·위치·인용 상태 목록';

create or replace view fp_chat.log_review
with (security_invoker = true) as
select
  l.id,
  l.created_at,
  l.question,
  l.answer,
  l.latency_ms,
  l.cost_usd,
  l.refusal,
  jsonb_array_length(l.source_refs) as source_count,
  coalesce((
    select jsonb_agg(jsonb_build_object(
      'node_id', src.value->'node_id',
      'edge_id', src.value->'edge_id',
      'document', left(src.value->>'doc_sha256', 8),
      'page_no', src.value->'page_no',
      'start_pos', src.value->'start_pos',
      'end_pos', src.value->'end_pos',
      'quote_status', src.value->'quote_status'
    ))
    from jsonb_array_elements(l.source_refs) as src(value)
  ), '[]'::jsonb) as source_refs
from public.fp_chat_logs l;

-- 기존 chat_views.sql 과 같은 방식으로 서비스 역할이 읽을 수 있게 한다(실제 적용 전 역할명 확인).
grant usage on schema fp_chat to service_role;
grant select on fp_chat.log_review to service_role;
