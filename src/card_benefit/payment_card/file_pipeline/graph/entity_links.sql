-- DRAFT ONLY: review with the team before manual execution. This file is never run by the loader.
create table public.fp_entity_links (
  run_id text not null references public.fp_load_runs(run_id),
  group_id text not null,
  scope text not null check (scope in ('within_card', 'across_cards')),
  link_type text not null check (link_type in ('SAME_AS_STRONG', 'SIMILAR')),
  kind text not null,
  canonical_node_id text not null references public.fp_nodes(id),
  member_node_id text not null references public.fp_nodes(id),
  same_props boolean not null,
  distinct_pages integer not null check (distinct_pages >= 0),
  created_at timestamptz not null default now(),
  primary key (run_id, member_node_id, scope),
  check (length(group_id) > 0),
  check ((scope = 'within_card' and link_type = 'SAME_AS_STRONG') or
         (scope = 'across_cards' and link_type = 'SIMILAR'))
);

create index fp_entity_links_group_idx
  on public.fp_entity_links (run_id, scope, group_id);

alter table public.fp_entity_links enable row level security;

-- Choose and review real role names before enabling policies.
-- create policy fp_entity_links_service_select on public.fp_entity_links
--   for select to service_role using (true);
-- create policy fp_entity_links_reviewer_select on public.fp_entity_links
--   for select to reviewer_role using (true);

create schema if not exists fp_chat;

create or replace view fp_chat.entity_groups
with (security_invoker = true) as
select run_id, group_id, scope, link_type, kind, canonical_node_id,
       member_node_id, same_props, distinct_pages, created_at
from public.fp_entity_links;

-- Match the grants used by graph/chat_logs.sql; confirm service_role in the target project.
grant usage on schema fp_chat to service_role;
grant select on fp_chat.entity_groups to service_role;

-- Optional policy templates; RLS remains default-deny until approved policies are applied.
-- Rollback (manual review only):
-- drop view if exists fp_chat.entity_groups;
-- drop table if exists public.fp_entity_links;
-- drop schema if exists fp_chat; -- only if no other fp_chat objects depend on it
