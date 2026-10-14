from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.config import DbConnectConfig


engine = create_async_engine(
    DbConnectConfig.DATABASE_URL,
    echo=False,
    connect_args={
        "command_timeout": 60,
    }
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass