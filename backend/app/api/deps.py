from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    """One session per request; the service explicitly commits its transaction."""
    with request.app.state.session_factory() as session:
        yield session
