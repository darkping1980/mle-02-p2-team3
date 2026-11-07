-- 실행 전 확인용 조회 (아래 결과에 pf_ 테이블만 있고 fp_ 테이블은 없는지 확인)
-- select tablename from pg_tables where schemaname = 'public' and (tablename like 'pf\_%' escape '\' or tablename like 'fp\_%' escape '\') order by tablename;
-- select schemaname, tablename from pg_tables where schemaname = 'public' and (tablename like 'pf\_%' escape '\' or tablename like 'fp\_%' escape '\') order by tablename;

begin;

do $$ begin
  if to_regclass('public.pf_load_runs') is not null and to_regclass('public.fp_load_runs') is null then alter table public.pf_load_runs rename to fp_load_runs; end if;
  if to_regclass('public.pf_nodes') is not null and to_regclass('public.fp_nodes') is null then alter table public.pf_nodes rename to fp_nodes; end if;
  if to_regclass('public.pf_edges') is not null and to_regclass('public.fp_edges') is null then alter table public.pf_edges rename to fp_edges; end if;
  if to_regclass('public.pf_evidence') is not null and to_regclass('public.fp_evidence') is null then alter table public.pf_evidence rename to fp_evidence; end if;
end $$;

alter index if exists public.pf_nodes_type_idx rename to fp_nodes_type_idx;
alter index if exists public.pf_nodes_run_idx rename to fp_nodes_run_idx;
alter index if exists public.pf_edges_source_idx rename to fp_edges_source_idx;
alter index if exists public.pf_edges_target_idx rename to fp_edges_target_idx;
alter index if exists public.pf_edges_type_idx rename to fp_edges_type_idx;
alter index if exists public.pf_edges_run_idx rename to fp_edges_run_idx;
alter index if exists public.pf_evidence_node_idx rename to fp_evidence_node_idx;
alter index if exists public.pf_evidence_edge_idx rename to fp_evidence_edge_idx;
alter index if exists public.pf_evidence_document_page_idx rename to fp_evidence_document_page_idx;

do $$ declare r record; new_name text; begin
  for r in
    select t.relname as table_name, c.conname
    from pg_constraint c join pg_class t on t.oid = c.conrelid
    where c.conrelid in (
      to_regclass('public.fp_load_runs'), to_regclass('public.fp_nodes'),
      to_regclass('public.fp_edges'), to_regclass('public.fp_evidence')
    )
      and c.conname like 'pf\_%' escape '\'
  loop
    new_name := 'fp_' || substr(r.conname, 4);
    if not exists (
      select 1 from pg_constraint
      where conrelid = to_regclass('public.' || r.table_name) and conname = new_name
    ) then
      execute format('alter table %I.%I rename constraint %I to %I', 'public', r.table_name, r.conname, new_name);
    end if;
  end loop;
end $$;

-- Identity 시퀀스도 일반 시퀀스처럼 이름 변경을 시도할 수 있으나, 권한/상태에 따라 실패할 수 있어 예외를 격리한다.
do $$ begin
  if to_regclass('public.pf_evidence_id_seq') is not null and to_regclass('public.fp_evidence_id_seq') is null then
    begin
      alter sequence if exists public.pf_evidence_id_seq rename to fp_evidence_id_seq;
    exception when others then
      raise notice 'Could not rename public.pf_evidence_id_seq: %', SQLERRM;
    end;
  end if;
end $$;

create or replace function public.fp_check_edge_endpoint_types()
returns trigger language plpgsql set search_path = public as $fp_body$
declare source_type text; target_type text; allowed boolean := false;
begin
  select node_type into source_type from public.fp_nodes where id = new.source_id;
  select node_type into target_type from public.fp_nodes where id = new.target_id;
  if source_type is null or target_type is null then raise exception 'fp_edges endpoint is missing'; end if;
  allowed := case new.edge_type
    when 'HAS_CONDITION' then source_type = 'Benefit' and target_type = 'Condition'
    when 'HAS_LIMIT' then source_type = 'Benefit' and target_type = 'Limit'
    when 'APPLIES_TO' then source_type = 'Benefit' and target_type = 'Target'
    when 'EXCLUDES' then source_type = 'Benefit' and target_type = 'Target'
    when 'MUTUALLY_EXCLUSIVE' then source_type = 'Benefit' and target_type = 'Benefit' and new.source_id <> new.target_id
    when 'OFFERS' then source_type = 'Card' and target_type = 'Benefit'
    else false end;
  if not allowed then raise exception 'fp_edges disallowed endpoint types for %: % -> %', new.edge_type, source_type, target_type; end if;
  return new;
end
$fp_body$;

do $$ begin
  if to_regclass('public.fp_edges') is not null then
    drop trigger if exists pf_edges_endpoint_types_trg on public.fp_edges;
    drop trigger if exists fp_edges_endpoint_types_trg on public.fp_edges;
    create trigger fp_edges_endpoint_types_trg before insert or update of source_id, target_id, edge_type on public.fp_edges for each row execute function public.fp_check_edge_endpoint_types();
  end if;
end $$;
drop function if exists public.pf_check_edge_endpoint_types();

alter table public.fp_load_runs enable row level security;
alter table public.fp_nodes enable row level security;
alter table public.fp_edges enable row level security;
alter table public.fp_evidence enable row level security;

commit;

-- 검증용 조회 (실행 후 public에 pf_ 객체가 남았는지 확인)
-- select tablename from pg_tables where schemaname = 'public' and tablename like 'pf\_%' escape '\' order by tablename;
-- select indexname from pg_indexes where schemaname = 'public' and indexname like 'pf\_%' escape '\' order by indexname;
-- select conname, conrelid::regclass from pg_constraint where connamespace = 'public'::regnamespace and conname like 'pf\_%' escape '\' order by conname;
-- select 'tables' as object_type, count(*) from pg_tables where schemaname = 'public' and tablename like 'fp\_%' escape '\'
-- union all select 'indexes', count(*) from pg_indexes where schemaname = 'public' and indexname like 'fp\_%' escape '\'
-- union all select 'constraints', count(*) from pg_constraint where connamespace = 'public'::regnamespace and conname like 'fp\_%' escape '\'
-- union all select 'sequences', count(*) from pg_class where relnamespace = 'public'::regnamespace and relkind = 'S' and relname like 'fp\_%' escape '\';
