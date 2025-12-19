from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()

async def get_db():
    """Yield an async database session.

    Returns
    -------
    AsyncGenerator[AsyncSession, None]
        Async SQLAlchemy session generator for use with FastAPI dependencies.
    """
    async with AsyncSessionLocal() as session:
        yield session
