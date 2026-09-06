import asyncio
import os
import logging
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import the app
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db.neo4j_client import neo4j_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "neo4j_migrations" / "migrations"

async def init_migration_tracking(session):
    await session.run("""
        CREATE CONSTRAINT migration_name IF NOT EXISTS FOR (m:Migration) REQUIRE m.name IS UNIQUE
    """)

async def run_migrations():
    await neo4j_client.connect()
    try:
        session = await neo4j_client.get_session()
        async with session:
            await init_migration_tracking(session)
            
            if not MIGRATIONS_DIR.exists():
                logger.warning(f"Migrations directory {MIGRATIONS_DIR} does not exist.")
                return

            migration_files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".cypher")])
            
            for migration_file in migration_files:
                # Check if already applied
                result = await session.run(
                    "MATCH (m:Migration {name: $name}) RETURN m", 
                    name=migration_file
                )
                record = await result.single()
                
                if not record:
                    logger.info(f"Applying migration: {migration_file}")
                    filepath = MIGRATIONS_DIR / migration_file
                    with open(filepath, "r") as f:
                        cypher_queries = f.read().split(";")
                        
                    for query in cypher_queries:
                        query = query.strip()
                        if query:
                            # Avoid executing comments as full statements if they are the only thing
                            if query.startswith("//") and "\n" not in query:
                                continue
                            try:
                                await session.run(query)
                            except Exception as e:
                                logger.error(f"Failed executing query in {migration_file}: {query}")
                                raise e
                    
                    # Record migration as applied
                    await session.run(
                        "CREATE (m:Migration {name: $name, applied_at: datetime()})",
                        name=migration_file
                    )
                    logger.info(f"Successfully applied {migration_file}")
                else:
                    logger.info(f"Migration {migration_file} already applied, skipping.")
                    
    finally:
        await neo4j_client.close()

if __name__ == "__main__":
    asyncio.run(run_migrations())
