import logging
from typing import AsyncGenerator
from neo4j import AsyncGraphDatabase, AsyncDriver

from app.core.config import settings

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver: AsyncDriver | None = None

    async def connect(self):
        if not self._driver:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            try:
                await self._driver.verify_connectivity()
                logger.info("Successfully connected to Neo4j.")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise

    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Closed Neo4j connection.")

    async def get_session(self):
        if not self._driver:
            await self.connect()
        # We return an async session context manager
        return self._driver.session()


# Singleton instance
neo4j_client = Neo4jClient(
    uri=settings.NEO4J_URI,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD
)

async def get_neo4j_session() -> AsyncGenerator:
    """Dependency for FastAPI endpoints requiring a Neo4j session."""
    session = await neo4j_client.get_session()
    async with session:
        yield session
