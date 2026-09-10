"""Add the LLM-Wiki / OKF knowledge layer.

Creates the index over the Markdown knowledge store (`knowledge_entries`),
the concept graph tables that replace Neo4j (`paper_concepts`,
`concept_relations`), and the citation edges that replace the `:CITES`
relationships (`paper_citations`).

`knowledge_entries.search_vector` is a Postgres GENERATED column rather than
something the application writes: making it derived means the index can never
drift from the body text, and a bulk insert cannot forget to populate it.
Weighting puts the title above the section heading above the body, so a
question matching a paper's title outranks one matching a passing mention.

Also indexes `project_papers(project_id)` and `project_papers(paper_id)`.
These were always missing, but scope resolution now runs on every knowledge
query rather than only on chat, so the sequential scan became hot.

Revision ID: d1a7c4e90b21
Revises: 52a1b9c9d9f0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1a7c4e90b21"
down_revision: Union[str, Sequence[str], None] = "52a1b9c9d9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept as one expression so the CREATE and the docstring cannot disagree.
_SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(section, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(body, '')), 'C')"
)


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_key", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("slug", sa.String(255), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("section", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provenance", postgresql.JSONB(), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_SEARCH_VECTOR_SQL, persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("entry_key", name="uq_knowledge_entries_entry_key"),
    )
    op.create_index("ix_knowledge_entries_paper_id", "knowledge_entries", ["paper_id"])
    op.create_index("ix_knowledge_entries_kind", "knowledge_entries", ["kind"])
    op.create_index("ix_knowledge_entries_slug", "knowledge_entries", ["slug"])
    op.create_index(
        "ix_knowledge_entries_search",
        "knowledge_entries",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "paper_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_key", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="concept"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("pages", postgresql.JSONB(), nullable=True),
        sa.Column("entry_keys", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("paper_id", "concept_key", name="uq_paper_concepts_paper_key"),
    )
    op.create_index("ix_paper_concepts_paper_id", "paper_concepts", ["paper_id"])
    op.create_index("ix_paper_concepts_concept_key", "paper_concepts", ["concept_key"])

    op.create_table(
        "concept_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("target_key", sa.String(255), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False, server_default="RELATES_TO"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "paper_id", "source_key", "target_key", "relation_type",
            name="uq_concept_relations_edge",
        ),
    )
    op.create_index("ix_concept_relations_paper_id", "concept_relations", ["paper_id"])

    op.create_table(
        "paper_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("other_id", sa.String(64), nullable=False),
        sa.Column("other_title", sa.String(1024), nullable=True),
        sa.Column("other_year", sa.Integer(), nullable=True),
        sa.Column("other_doi", sa.String(255), nullable=True),
        sa.Column("other_arxiv_id", sa.String(255), nullable=True),
        sa.Column("other_semantic_scholar_id", sa.String(255), nullable=True),
        sa.Column("other_has_pdf", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("paper_id", "direction", "other_id", name="uq_paper_citations_edge"),
    )
    op.create_index("ix_paper_citations_paper_id", "paper_citations", ["paper_id"])

    # Hot path for every scope resolution.
    op.create_index("ix_project_papers_project_id", "project_papers", ["project_id"])
    op.create_index("ix_project_papers_paper_id", "project_papers", ["paper_id"])


def downgrade() -> None:
    op.drop_index("ix_project_papers_paper_id", table_name="project_papers")
    op.drop_index("ix_project_papers_project_id", table_name="project_papers")

    op.drop_index("ix_paper_citations_paper_id", table_name="paper_citations")
    op.drop_table("paper_citations")

    op.drop_index("ix_concept_relations_paper_id", table_name="concept_relations")
    op.drop_table("concept_relations")

    op.drop_index("ix_paper_concepts_concept_key", table_name="paper_concepts")
    op.drop_index("ix_paper_concepts_paper_id", table_name="paper_concepts")
    op.drop_table("paper_concepts")

    op.drop_index("ix_knowledge_entries_search", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_slug", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_kind", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_paper_id", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
