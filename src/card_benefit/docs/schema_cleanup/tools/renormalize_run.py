"""읽기 전용: 저장된 추출 원본(stg_raw_item)으로 실제 공통 등록 로직(CommonBenefitService.register_run)을 시뮬레이션한다.

정제본(stg_normalized_item)을 읽지 않는다. 등록 SQL(write)은 실행하지 않고 가로채며, 트랜잭션은 READ ONLY다. API 호출 없음.
사용법(프로젝트 루트): python src/card_benefit/docs/schema_cleanup/tools/renormalize_run.py 20261103_000031 [--detail]
"""
import collections
from contextlib import contextmanager
import sys
from pathlib import Path

CARD = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CARD.parent), str(CARD)]
sys.stdout.reconfigure(encoding='utf-8')
from common.query_log_config import load_project_environment  # noqa: E402
load_project_environment()
from common.postgres_db_session import PostgresDbSession  # noqa: E402
from payment_card.db_pipeline.document_repository import MAPPER_ROOT  # noqa: E402
from payment_card.db_pipeline.common_benefit_service import CommonBenefitService  # noqa: E402



class OuterSession(PostgresDbSession):
    """서비스 내부 트랜잭션을 바깥 READ ONLY 트랜잭션에 합친다."""
    @contextmanager
    def transaction(self):
        if self._active_connection is not None:
            yield self
        else:
            with super().transaction():
                yield self


run_id = sys.argv[1]
detail = '--detail' in sys.argv
session = OuterSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode='none')
svc = CommonBenefitService(session)
writes = collections.Counter()


def fake_write(name, **params):          # 등록 SQL 대신 기록만 한다
    writes[name] += 1
    return [{'card_common_bnft_id': f'SIM{writes[name]}'}]


real_one = svc.repo.one
svc.repo.write = fake_write
svc.repo.one = lambda name, **p: None if name == 'lock_common' else real_one(name, **p)   # FOR UPDATE는 READ ONLY에서 불가
try:
    with session.transaction():
        session._active_connection.execute('SET TRANSACTION READ ONLY')
        candidates = svc.candidates(run_id)
        identities = {c['card_extr_stg_id']: 'SIM:' + c['card_extr_stg_id'] for c in candidates}
        decisions = svc.register_run(run_id, identities)
        session._active_connection.rollback()
finally:
    session.database_manager.close()

by_id = {c['card_extr_stg_id']: c for c in candidates}
print('candidates', len(candidates), '| check_cd(stored→effective)',
      dict(collections.Counter((c['stg_sql_check_cd'], c['check_cd']) for c in candidates)))
print('decisions', dict(collections.Counter(d.status for d in decisions)), '| simulated writes', dict(writes))
for reason, n in collections.Counter(d.reason for d in decisions).most_common():
    print(f'  {n:3d}  {reason}')
if detail:
    for d in decisions:
        c = by_id[d.stg_id]
        name = (c.get('normalized') or {}).get('bnft_nm') or c['stg_raw_item'].get('bnft_nm')
        print(f'  {d.status:9s} {d.stg_id} {c["stg_sql_check_cd"]}→{c["check_cd"]} | {str(name)[:40]} | {d.reason[:50]}')
