"""DB 연결과 테이블 상태를 읽기 전용으로 확인합니다. 실행: python check_db.py (이 폴더에서)"""
import db
import rag

print("SELECT 1 ->", db.run_query("select 1 as ok")[0]["ok"])
for table in (db.NODES, db.EDGES):
    count = db.run_query(f"select count(*) as n from {table}")[0]["n"]
    print(f"{table}: {count}행")
names = [e["name"] for e in rag.list_entities()]
print("엔티티 예시:", names[:10])
