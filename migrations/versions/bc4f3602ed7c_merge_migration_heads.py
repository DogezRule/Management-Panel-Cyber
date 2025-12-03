"""merge migration heads

Revision ID: bc4f3602ed7c
Revises: 0f3a1c2b5d6e, 9b3c2d4e5f60
Create Date: 2025-11-18 02:13:51.953013

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc4f3602ed7c'
down_revision = ('0f3a1c2b5d6e', '9b3c2d4e5f60')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
