"""widen node status fields

Revision ID: 20260326_0001
Revises:
Create Date: 2026-03-26 20:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260326_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("docker_status", existing_type=sa.String(length=100), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("swarm_state", existing_type=sa.String(length=100), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("swarm_state", existing_type=sa.Text(), type_=sa.String(length=100), existing_nullable=True)
        batch_op.alter_column("docker_status", existing_type=sa.Text(), type_=sa.String(length=100), existing_nullable=True)
