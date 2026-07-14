"""add_sealed_sender_column

Revision ID: 075354cafd1e
Revises: 698e812f0dfc
Create Date: 2026-07-14 10:24:28.971931

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "075354cafd1e"
down_revision: Union[str, Sequence[str], None] = "698e812f0dfc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("messages")]
    if "sealed_sender" not in columns:
        op.add_column("messages", sa.Column("sealed_sender", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("messages")]
    if "sealed_sender" in columns:
        # op.drop_column is generally supported but SQLite drop_column requires alembic >= 1.4.0
        # If it fails, we can catch it or do raw query
        try:
            op.drop_column("messages", "sealed_sender")
        except Exception:
            pass
