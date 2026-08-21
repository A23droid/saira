import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectPaperCreate,
    ProjectPaperUpdate,
)


class ProjectService:
    async def create_project(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        project_in: ProjectCreate,
    ) -> Project:
        project = Project(
            user_id=user_id,
            **project_in.model_dump(),
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def get_projects_by_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> Sequence[Project]:
        stmt = select(Project).where(Project.user_id == user_id)
        result = await session.scalars(stmt)
        return result.all()

    async def get_project_by_id(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
        )
        return await session.scalar(stmt)

    async def update_project(
        self,
        session: AsyncSession,
        db_project: Project,
        project_in: ProjectUpdate,
    ) -> Project:
        update_data = project_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_project, field, value)

        await session.commit()
        await session.refresh(db_project)
        return db_project

    async def delete_project(
        self,
        session: AsyncSession,
        db_project: Project,
    ) -> None:
        await session.delete(db_project)
        await session.commit()

    async def add_paper_to_project(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        project_paper_in: ProjectPaperCreate,
    ) -> ProjectPaper:
        project_paper = ProjectPaper(
            project_id=project_id,
            **project_paper_in.model_dump(),
        )

        session.add(project_paper)
        await session.commit()
        await session.refresh(project_paper)
        return project_paper

    async def get_project_paper(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        paper_id: uuid.UUID,
    ) -> ProjectPaper | None:
        stmt = select(ProjectPaper).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.paper_id == paper_id,
        )
        return await session.scalar(stmt)

    async def update_project_paper(
        self,
        session: AsyncSession,
        db_project_paper: ProjectPaper,
        project_paper_in: ProjectPaperUpdate,
    ) -> ProjectPaper:
        update_data = project_paper_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_project_paper, field, value)

        await session.commit()
        await session.refresh(db_project_paper)
        return db_project_paper

    async def remove_paper_from_project(
        self,
        session: AsyncSession,
        db_project_paper: ProjectPaper,
    ) -> None:
        await session.delete(db_project_paper)
        await session.commit()


project_service = ProjectService()