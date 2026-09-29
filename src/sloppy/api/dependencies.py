"""FastAPI dependency functions, injected via Depends(...) into router handlers so
handler bodies stay thin and dependencies could be overridden in tests if ever needed."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from sloppy.config import get_settings
from sloppy.db.session import session_scope
from sloppy.storage import get_s3_client


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def get_s3():
    return get_s3_client(get_settings())
