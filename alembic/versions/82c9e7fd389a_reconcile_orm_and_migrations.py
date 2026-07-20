"""reconcile_orm_and_migrations

Revision ID: 82c9e7fd389a
Revises: 71b9e6fd267b
Create Date: 2026-07-20 08:32:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "82c9e7fd389a"
down_revision: Union[str, Sequence[str], None] = "075354cafd1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema idempotently."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Reconcile users table columns
    if inspector.has_table("users"):
        user_cols = [c["name"] for c in inspector.get_columns("users")]
        with op.batch_alter_table("users", schema=None) as batch_op:
            if "last_seen" not in user_cols:
                batch_op.add_column(
                    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True)
                )
            if "is_blocked" not in user_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_blocked", sa.Boolean(), server_default="0", nullable=True
                    )
                )

    # Reconcile contacts table columns
    if inspector.has_table("contacts"):
        contact_cols = [c["name"] for c in inspector.get_columns("contacts")]
        with op.batch_alter_table("contacts", schema=None) as batch_op:
            if "is_blocked" not in contact_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_blocked", sa.Boolean(), server_default="0", nullable=True
                    )
                )

    # Reconcile messages table columns
    if inspector.has_table("messages"):
        msg_cols = [c["name"] for c in inspector.get_columns("messages")]
        with op.batch_alter_table("messages", schema=None) as batch_op:
            if "is_deleted" not in msg_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_deleted", sa.Boolean(), server_default="0", nullable=True
                    )
                )


def downgrade() -> None:
    """Downgrade schema."""
    pass
