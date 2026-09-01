"""
Declarative base shared by every ORM model.

Kept in its own module (rather than alongside the engine) so that Alembic's
`env.py` can import `Base.metadata` without also importing the engine /
session machinery.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

from app.models.user import User
from app.models.project import Project
from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.models.note import Note
from app.models.highlight import Highlight
from app.models.reading_progress import ReadingProgress
from app.models.comparison import Comparison
from app.models.chat import ChatSession, ChatMessage
from app.models.literature_review import LiteratureReview
from app.models.saved_artifact import SavedArtifact
