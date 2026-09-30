"""Mark simulated demo incidents explicitly."""
from alembic import op
import sqlalchemy as sa

revision = "0002_demo_incident"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("incidents", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE incidents SET is_demo = true WHERE id IN (SELECT incident_id FROM incident_events WHERE idempotency_key = 'demo-initial-claim')"))


def downgrade():
    op.drop_column("incidents", "is_demo")
