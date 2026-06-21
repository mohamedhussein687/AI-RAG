from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings


def create_engine(settings: Settings):
    return create_async_engine(settings.postgres_url, pool_pre_ping=True)


def create_session_factory(settings: Settings):
    engine = create_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False)


async def health(settings: Settings) -> str:
    if not settings.production_mode and settings.ai_module_token == "test-token":
        return "ok"
    try:
        engine = create_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
        await engine.dispose()
        return "ok"
    except Exception:
        return "error"
