"""Establish the initial migration baseline; domain tables arrive in Phase 4+."""

from collections.abc import Sequence

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Initial schema baseline. No domain tables exist in Phase 3."""


def downgrade() -> None:
    """The baseline migration creates no tables to remove."""
