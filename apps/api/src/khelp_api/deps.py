from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from khelp_db import session_factory


def get_session() -> Iterator[Session]:
    with session_factory()() as s:
        yield s
