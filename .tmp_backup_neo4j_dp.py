import gzip
import hashlib
import json
from pathlib import Path
from dotenv import load_dotenv
from common.neo4j_connection import create_neo4j_driver
import os

load_dotenv(".env")
database = os.environ["NEO4J_DATABASE"]
out = Path("tmp/neo4j_dp_backup_20261106.json.gz")
out.parent.mkdir(parents=True, exist_ok=True)
with create_neo4j_driver() as driver, driver.session(database=database) as session:
    nodes = [r.data() for r in session.run("MATCH (n:dp_node) RETURN labels(n) AS labels,properties(n) AS props ORDER BY n.key")]
    relationships = [r.data() for r in session.run("MATCH (a:dp_node)-[r]->(b:dp_node) RETURN a.key AS start,type(r) AS type,properties(r) AS props,b.key AS end ORDER BY type,start,end")]
    indexes = [r.data() for r in session.run("SHOW INDEXES YIELD name,type,state,labelsOrTypes,properties,options RETURN name,type,state,labelsOrTypes,properties,options ORDER BY name")]
    constraints = [r.data() for r in session.run("SHOW CONSTRAINTS YIELD name,type,entityType,labelsOrTypes,properties RETURN name,type,entityType,labelsOrTypes,properties ORDER BY name")]
payload = {"database": database, "nodes": nodes, "relationships": relationships,
           "indexes": indexes, "constraints": constraints}
data = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
with gzip.open(out, "wb", compresslevel=9) as stream:
    stream.write(data)
print(json.dumps({"database": database, "nodes": len(nodes), "relationships": len(relationships),
                  "indexes": len(indexes), "constraints": len(constraints), "backup": str(out),
                  "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "bytes": out.stat().st_size}, ensure_ascii=False))
