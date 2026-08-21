from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.token import Message, TokenPair
from app.schemas.user import UserRead, UserUpdateRequest
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectPaperCreate, ProjectPaperUpdate, ProjectPaperResponse
from app.schemas.paper import PaperCreate, PaperUpdate, PaperResponse
from app.schemas.reading_data import (
    NoteCreate, NoteUpdate, NoteResponse,
    HighlightCreate, HighlightUpdate, HighlightResponse,
    ReadingProgressCreate, ReadingProgressUpdate, ReadingProgressResponse,
    ProjectPaperReadingData
)

__all__ = [
    "LoginRequest",
    "Message",
    "RegisterRequest",
    "TokenPair",
    "UserRead",
    "UserUpdateRequest",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "ProjectPaperCreate",
    "ProjectPaperUpdate",
    "ProjectPaperResponse",
    "PaperCreate",
    "PaperUpdate",
    "PaperResponse",
    "NoteCreate",
    "NoteUpdate",
    "NoteResponse",
    "HighlightCreate",
    "HighlightUpdate",
    "HighlightResponse",
    "ReadingProgressCreate",
    "ReadingProgressUpdate",
    "ReadingProgressResponse",
    "ProjectPaperReadingData"
]
