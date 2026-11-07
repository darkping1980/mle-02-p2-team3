-- 이미 예전 버전으로 public.nodes / public.edges를 만들어 두었을 때만 실행하세요. (한 번만)
-- 테이블을 새로 만들지 않고 스키마만 옮기므로 데이터, 인덱스, 외래 키, RLS 설정이 그대로 따라갑니다.
-- 실행 전에 public.nodes / public.edges가 이 챗봇이 만든 것인지 확인하세요. 다른 사람이 같은 이름으로 만든 테이블이면 실행하지 마세요.
-- 아직 실제 Supabase에서 실행해 보지 않았습니다. 오류가 나면 메시지를 알려주세요.

begin;
create schema if not exists graphrag;
alter table public.nodes set schema graphrag;
alter table public.edges set schema graphrag;
commit;

-- 확인: 두 줄 모두 graphrag가 나와야 합니다.
-- select schemaname, tablename from pg_tables where tablename in ('nodes', 'edges');
