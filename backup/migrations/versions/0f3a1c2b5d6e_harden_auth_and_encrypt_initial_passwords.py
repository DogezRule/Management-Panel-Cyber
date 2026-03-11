"""harden auth and encrypt initial passwords

Revision ID: 0f3a1c2b5d6e
Revises: 719badf3f07c
Create Date: 2025-11-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f3a1c2b5d6e'
down_revision = '719badf3f07c'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Add lockout fields to users if not present
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'failed_login_attempts' not in cols:
        op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
        op.alter_column('users', 'failed_login_attempts', server_default=None)
    if 'locked_until' not in cols:
        op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))

    # Add encrypted initial password + lockout fields to students
    cols = [c['name'] for c in insp.get_columns('students')]
    if 'initial_password_enc' not in cols:
        op.add_column('students', sa.Column('initial_password_enc', sa.LargeBinary(), nullable=True))
    if 'failed_login_attempts' not in cols:
        op.add_column('students', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
        op.alter_column('students', 'failed_login_attempts', server_default=None)
    if 'locked_until' not in cols:
        op.add_column('students', sa.Column('locked_until', sa.DateTime(), nullable=True))

    # Migrate plaintext initial_password -> initial_password_enc when possible
    try:
        from cryptography.fernet import Fernet
        import os
        key = os.getenv('FERNET_KEY')
        f = Fernet(key.encode() if isinstance(key, str) else key) if key else None
    except Exception:
        f = None

    try:
        # Only proceed if the old column exists
        cols = [c['name'] for c in insp.get_columns('students')]
        if 'initial_password' in cols and f:
            students = sa.table(
                'students',
                sa.column('id', sa.Integer()),
                sa.column('initial_password', sa.String()),
            )
            res = bind.execute(sa.select(students.c.id, students.c.initial_password))
            for sid, pw in res:
                if pw:
                    token = f.encrypt(pw.encode('utf-8'))
                    bind.execute(sa.text(
                        'UPDATE students SET initial_password_enc = :tok WHERE id = :sid'
                    ), {'tok': token, 'sid': sid})
    except Exception:
        # Non-fatal; proceed without migrating
        pass

    # Drop old plaintext column if present
    cols = [c['name'] for c in insp.get_columns('students')]
    if 'initial_password' in cols:
        with op.batch_alter_table('students') as batch_op:
            batch_op.drop_column('initial_password')


def downgrade():
    # Recreate plaintext column (empty) on downgrade and remove new fields
    with op.batch_alter_table('students') as batch_op:
        batch_op.add_column(sa.Column('initial_password', sa.String(length=128), nullable=True))
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
        batch_op.drop_column('initial_password_enc')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
