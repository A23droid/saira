import asyncio
import os
from dotenv import load_dotenv
load_dotenv('backend/.env')
from groq import AsyncGroq
api_key = os.getenv('GROQ_API_KEY')

async def list_models():
    client = AsyncGroq(api_key=api_key)
    try:
        models = await client.models.list()
        print("Available models:")
        for m in models.data:
            print(f" - {m.id}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(list_models())
