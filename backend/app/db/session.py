# Module purpose: Implement session behavior for the database domain.

import sys

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


# Purpose: Handle engine options for the database workflow.
def engine_options() -> dict:
    if "pytest" in sys.modules:
        return {
            "poolclass": NullPool,
        }

    return {
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout_seconds,
        "pool_recycle": settings.database_pool_recycle_seconds,
        "pool_pre_ping": settings.database_pool_pre_ping,
    }


engine = create_async_engine(
    settings.database_url,
    echo=False,
    **engine_options(),
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Purpose: Return db for the database workflow.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
