import asyncio
import asyncpg

async def check_db():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/saira')
    val = await conn.fetchval('SELECT COUNT(*) FROM papers')
    print(f'Papers in DB: {val}')
    await conn.close()

asyncio.run(check_db())
