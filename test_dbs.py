import asyncio
import os
import sys

try:
    import asyncpg
    from neo4j import GraphDatabase
except ImportError:
    print('Missing driver libraries, exiting.')
    sys.exit(0)

async def test_pg():
    try:
        conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/saira')
        print('Postgres: OK')
        await conn.close()
    except Exception as e:
        print(f'Postgres: FAILED - {e}')

def test_neo4j():
    try:
        driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
        driver.verify_connectivity()
        print('Neo4j: OK')
        driver.close()
    except Exception as e:
        print(f'Neo4j: FAILED - {e}')

asyncio.run(test_pg())
test_neo4j()
