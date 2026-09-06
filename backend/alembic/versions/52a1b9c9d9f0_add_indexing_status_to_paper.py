"""Add indexing status to paper

Revision ID: 52a1b9c9d9f0
Revises: 0ff8a78aba04
Create Date: 2026-09-04 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52a1b9c9d9f0'
down_revision: Union[str, Sequence[str], None] = '0ff8a78aba04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('papers', sa.Column('indexing_status', sa.String(length=50), server_default='not_indexed', nullable=False))
    op.add_column('papers', sa.Column('indexing_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('papers', 'indexing_error')
    op.drop_column('papers', 'indexing_status')
