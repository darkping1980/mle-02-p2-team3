import json
import os
from dotenv import load_dotenv
from neo4j import READ_ACCESS
from common.neo4j_connection import create_neo4j_driver

load_dotenv(".env")
database = os.getenv("NEO4J_DATABASE")
if not database:
    raise SystemExit("NEO4J_DATABASE is not configured")
with create_neo4j_driver() as driver, driver.session(database=database, default_access_mode=READ_ACCESS) as session:
    dbinfo = session.run("CALL db.info()").single().data()
    identity = session.run("RETURN $database AS database", database=database).single().data()
    labels = [r.data() for r in session.run("MATCH (n) UNWIND labels(n) AS label WITH label,count(*) AS n RETURN label,n ORDER BY label")]
    relationships = [r.data() for r in session.run("MATCH ()-[r]->() RETURN type(r) AS type,count(*) AS n ORDER BY type")]
    external = [r.data() for r in session.run("""MATCH (n)-[r]-(m)
       WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_')
         AND none(label IN labels(m) WHERE label STARTS WITH 'dp_')
       RETURN labels(n) AS dp_labels,labels(m) AS external_labels,type(r) AS rel,count(*) AS n LIMIT 100""")]
    constraints = [r.data() for r in session.run("SHOW CONSTRAINTS YIELD name,type,entityType,labelsOrTypes,properties RETURN name,type,entityType,labelsOrTypes,properties ORDER BY name")]
    indexes = [r.data() for r in session.run("SHOW INDEXES YIELD name,type,state,labelsOrTypes,properties,options RETURN name,type,state,labelsOrTypes,properties,options ORDER BY name")]
    counts = session.run("MATCH (n) WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_') WITH count(n) AS nodes MATCH ()-[r]->() WHERE type(r) STARTS WITH 'dp_' RETURN nodes,count(r) AS relationships").single().data()
print(json.dumps({"identity": identity, "dbinfo": dbinfo, "configured_database": database, "counts": counts,
                  "labels": labels, "relationships": relationships, "external_links": external,
                  "constraints": constraints, "indexes": indexes}, ensure_ascii=False, default=str, indent=2))
