"""SQLAlchemy declarative base.

The final profile/contact tables are deliberately deferred until the database phase.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
