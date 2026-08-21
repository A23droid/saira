"""Add project and paper models

Revision ID: 16ad66ff7efc
Revises: ffffcae62153
Create Date: 2026-08-17 06:30:19.476333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '16ad66ff7efc'
down_revision: Union[str, Sequence[str], None] = 'ffffcae62153'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create papers, projects, and project_papers tables from scratch."""
    # --- papers (global, not user-owned) ---
    op.create_table(
        'papers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('doi', sa.String(length=255), nullable=True),
        sa.Column('arxiv_id', sa.String(length=255), nullable=True),
        sa.Column('semantic_scholar_id', sa.String(length=255), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('publication_year', sa.Integer(), nullable=True),
        sa.Column('venue', sa.String(length=255), nullable=True),
        sa.Column('pdf_url', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('citation_count', sa.Integer(), nullable=True),
        sa.Column('reference_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('doi', name='uq_papers_doi'),
        sa.UniqueConstraint('arxiv_id', name='uq_papers_arxiv_id'),
        sa.UniqueConstraint('semantic_scholar_id', name='uq_papers_semantic_scholar_id'),
    )

    # --- projects (user-owned) ---
    op.create_table(
        'projects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)

    # --- project_papers (association: project ↔ paper, with per-project metadata) ---
    op.create_table(
        'project_papers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('paper_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('favorite', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_papers_project_id'), 'project_papers', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_papers_paper_id'), 'project_papers', ['paper_id'], unique=False)


def downgrade() -> None:
    """Drop project_papers, projects, and papers tables."""
    op.drop_index(op.f('ix_project_papers_paper_id'), table_name='project_papers')
    op.drop_index(op.f('ix_project_papers_project_id'), table_name='project_papers')
    op.drop_table('project_papers')
    op.drop_index(op.f('ix_projects_user_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_table('papers')
