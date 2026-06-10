from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy models."""


def import_models() -> None:
    import backend.app.models  # noqa: F401
