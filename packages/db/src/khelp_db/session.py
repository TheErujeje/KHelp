from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=4)
def get_engine(url_env: str = "DATABASE_URL") -> Engine:
    url = os.environ.get(url_env)
    if not url:
        raise RuntimeError(f"{url_env} is not set")
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def session_factory(url_env: str = "DATABASE_URL") -> sessionmaker[Session]:
    return sessionmaker(get_engine(url_env), expire_on_commit=False)
