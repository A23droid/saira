import asyncio
import asyncpg

async def inspect():
    conn = await asyncpg.connect('postgresql://postgres:Aditya2310@localhost:5433/saira')
    
    # Check tables
    rows = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public';
    """)
    print("Tables:", [r['table_name'] for r in rows])
    
    # Check alembic_version
    version_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'alembic_version'
        );
    """)
    if version_exists:
        version = await conn.fetchval("SELECT version_num FROM alembic_version;")
        print("Alembic Version:", version)
    else:
        print("Alembic Version table does not exist")
        
    await conn.close()

asyncio.run(inspect())
