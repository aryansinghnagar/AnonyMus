"""add_profiles_abuse_and_supporter_badges

Revision ID: 698e812f0dfc
Revises: 780ce35d17d9
Create Date: 2026-07-14 09:39:32.195810

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "698e812f0dfc"
down_revision: Union[str, Sequence[str], None] = "780ce35d17d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "abuse_reports" not in existing_tables:
        op.create_table(
            "abuse_reports",
            sa.Column("report_id", sa.String(length=64), nullable=False),
            sa.Column("message_hash", sa.String(length=256), nullable=False),
            sa.Column("reporter_onion", sa.String(length=128), nullable=False),
            sa.Column("reason", sa.String(length=1024), nullable=True),
            sa.Column("signature", sa.String(length=512), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("report_id"),
        )
    if "profiles" not in existing_tables:
        op.create_table(
            "profiles",
            sa.Column("profile_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("hidden", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("passphrase_hash", sa.String(length=256), nullable=True),
            sa.PrimaryKeyConstraint("profile_id"),
        )
        # Insert default profile
        op.execute(
            "INSERT OR IGNORE INTO profiles (profile_id, display_name, hidden) VALUES ('default', 'Default Profile', 0)"
        )

    if "supporter_badges" not in existing_tables:
        op.create_table(
            "supporter_badges",
            sa.Column("onion_address", sa.String(length=128), nullable=False),
            sa.Column("badge_signature", sa.String(length=512), nullable=False),
            sa.Column("signed_by_key", sa.String(length=256), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("onion_address"),
        )

    contact_cols = [col["name"] for col in inspector.get_columns("contacts")]
    with op.batch_alter_table("contacts", schema=None) as batch_op:
        if "my_onion_address" not in contact_cols:
            batch_op.add_column(
                sa.Column("my_onion_address", sa.String(length=128), nullable=True)
            )
        if "disappearing_ttl" not in contact_cols:
            batch_op.add_column(
                sa.Column(
                    "disappearing_ttl", sa.Integer(), nullable=False, server_default="0"
                )
            )
        if "display_name" not in contact_cols:
            batch_op.add_column(
                sa.Column("display_name", sa.String(length=64), nullable=True)
            )
        if "dr_state" not in contact_cols:
            batch_op.add_column(sa.Column("dr_state", sa.Text(), nullable=True))
        if "peer_kem_public_key" not in contact_cols:
            batch_op.add_column(
                sa.Column("peer_kem_public_key", sa.Text(), nullable=True)
            )
        if "my_kem_private_key" not in contact_cols:
            batch_op.add_column(
                sa.Column("my_kem_private_key", sa.Text(), nullable=True)
            )
        if "preferred_file_relay" not in contact_cols:
            batch_op.add_column(
                sa.Column("preferred_file_relay", sa.String(length=512), nullable=True)
            )
        if "send_receipts" not in contact_cols:
            batch_op.add_column(
                sa.Column(
                    "send_receipts", sa.Boolean(), nullable=False, server_default="1"
                )
            )
        if "profile_id" not in contact_cols:
            batch_op.add_column(
                sa.Column(
                    "profile_id",
                    sa.String(length=64),
                    nullable=False,
                    server_default="default",
                )
            )
            batch_op.create_foreign_key(
                "fk_contacts_profile",
                "profiles",
                ["profile_id"],
                ["profile_id"],
                ondelete="CASCADE",
            )

    group_cols = [col["name"] for col in inspector.get_columns("groups")]
    with op.batch_alter_table("groups", schema=None) as batch_op:
        if "profile_id" not in group_cols:
            batch_op.add_column(
                sa.Column(
                    "profile_id",
                    sa.String(length=64),
                    nullable=False,
                    server_default="default",
                )
            )
            batch_op.create_foreign_key(
                "fk_groups_profile",
                "profiles",
                ["profile_id"],
                ["profile_id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("groups", schema=None) as batch_op:
        batch_op.drop_constraint("fk_groups_profile", type_="foreignkey")
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("contacts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_contacts_profile", type_="foreignkey")
        batch_op.drop_column("profile_id")
        batch_op.drop_column("send_receipts")
        batch_op.drop_column("preferred_file_relay")
        batch_op.drop_column("my_kem_private_key")
        batch_op.drop_column("peer_kem_public_key")
        batch_op.drop_column("dr_state")
        batch_op.drop_column("display_name")
        batch_op.drop_column("disappearing_ttl")
        batch_op.drop_column("my_onion_address")

    op.drop_table("supporter_badges")
    op.drop_table("profiles")
    op.drop_table("abuse_reports")
