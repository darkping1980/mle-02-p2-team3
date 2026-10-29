"""DB 연결과 테이블 상태를 읽기 전용으로 확인합니다. 실행: python check_db.py"""
import rag

print("SELECT 1 ->", rag.run_query("select 1 as ok")[0]["ok"])
for table in ("nodes", "edges"):
    count = rag.run_query(f"select count(*) as n from {table}")[0]["n"]
    print(f"{table}: {count}행")
names = [e["name"] for e in rag.list_entities()]
print("엔티티 예시:", names[:10])
