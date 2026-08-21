import asyncio
import asyncpg
import sys

async def fix_alembic():
    try:
        conn = await asyncpg.connect('postgresql://postgres:Aditya2310@localhost:5433/saira')
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        sys.exit(1)
        
    print("Connected to DB. Inspecting schema...")
    
    # 1. Get existing tables
    rows = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public';
    """)
    tables = [r['table_name'] for r in rows]
    print(f"Existing tables in public schema: {tables}")
    
    # 2. Get current alembic version in DB
    version_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'alembic_version'
        );
    """)
    
    if not version_exists:
        print("No alembic_version table found. The database is empty or not managed by Alembic.")
        await conn.close()
        return

    current_db_version = await conn.fetchval("SELECT version_num FROM alembic_version;")
    print(f"Current Alembic version in DB: {current_db_version}")
    
    if current_db_version == '3a24c8836524':
        print("\nConflict detected: DB is at '3a24c8836524', which is missing locally.")
        print("Checking if 'projects' and 'papers' tables already exist from this ghost migration...")
        
        has_new_tables = all(t in tables for t in ['projects', 'papers', 'project_papers'])
        
        if has_new_tables:
            print("The ghost migration '3a24c8836524' created the Project & Paper tables.")
            print("To safely repair:")
            print("  1. We will update the alembic_version in the DB to point to the last known good local migration ('ffffcae62153').")
            print("  2. We will drop the 'projects', 'papers', and 'project_papers' tables so Alembic can recreate them cleanly with your new models.")
            
            await conn.execute("UPDATE alembic_version SET version_num = 'ffffcae62153';")
            await conn.execute("DROP TABLE IF EXISTS project_papers, projects, papers CASCADE;")
            
            print("\nRepair complete! Database is now at 'ffffcae62153' and ready for the new migration.")
        else:
            print("The ghost migration did not create the expected tables. Reverting DB version to 'ffffcae62153'...")
            await conn.execute("UPDATE alembic_version SET version_num = 'ffffcae62153';")
            print("Repair complete!")
            
    else:
        print("The DB is not at '3a24c8836524'. No automated repair needed.")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_alembic())
