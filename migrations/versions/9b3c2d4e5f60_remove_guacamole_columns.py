"""Remove Guacamole-related columns

Revision ID: 9b3c2d4e5f60
Revises: 719badf3f07c
Create Date: 2025-11-17 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9b3c2d4e5f60'
down_revision = '719badf3f07c'
branch_labels = None
depends_on = None


def upgrade():
    # Drop legacy Guacamole columns no longer represented in models
    with op.batch_alter_table('users', schema=None) as batch_op:
        try:
            batch_op.drop_column('guacamole_username')
        except Exception:
            pass
    with op.batch_alter_table('classrooms', schema=None) as batch_op:
        try:
            batch_op.drop_column('guacamole_group_id')
        except Exception:
            pass
    with op.batch_alter_table('students', schema=None) as batch_op:
        for col in ['guacamole_username', 'guacamole_password']:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
    with op.batch_alter_table('virtual_machines', schema=None) as batch_op:
        try:
            batch_op.drop_column('guacamole_connection_id')
        except Exception:
            pass


def downgrade():
    # Recreate columns (best-effort) for downgrade compatibility
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guacamole_username', sa.String(length=120), nullable=True))
    with op.batch_alter_table('classrooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guacamole_group_id', sa.String(length=120), nullable=True))
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guacamole_username', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('guacamole_password', sa.String(length=256), nullable=True))
    with op.batch_alter_table('virtual_machines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guacamole_connection_id', sa.String(length=120), nullable=True))
