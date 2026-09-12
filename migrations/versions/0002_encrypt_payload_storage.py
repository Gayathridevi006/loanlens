"""Make legacy JSON payload columns compatible with application encryption."""
from alembic import op
import sqlalchemy as sa

revision="0002_encrypt_payload_storage"
down_revision="0001_initial"

def upgrade():
    connection=op.get_bind()
    columns={column["name"]: column for column in sa.inspect(connection).get_columns("applications")}
    raw_type=columns.get("raw_data", {}).get("type")
    if raw_type is not None and not isinstance(raw_type, (sa.Text, sa.String)):
        if connection.dialect.name == "postgresql":
            op.alter_column("applications","raw_data",type_=sa.Text(),postgresql_using="raw_data::text")
        else:
            with op.batch_alter_table("applications") as batch:
                batch.alter_column("raw_data",type_=sa.Text())

def downgrade():
    # Encrypted ciphertext is intentionally not coerced back to a JSON database type.
    pass
