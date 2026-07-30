"""
Declarative base shared by every ORM model.

Kept in its own module (rather than alongside the engine) so that Alembic's
`env.py` can import `Base.metadata` without also importing the engine /
session machinery.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
