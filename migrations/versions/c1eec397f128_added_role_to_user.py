"""Added role to user

Revision ID: c1eec397f128
Revises: 2df5aadb3912
Create Date: 2024-12-17 05:00:43.190287

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1eec397f128'
down_revision = '2df5aadb3912'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_role', sa.String(length=50), nullable=False, server_default='user'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('user_role')

    # ### end Alembic commands ###
