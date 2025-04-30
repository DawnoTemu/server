"""Add voice status fields

Revision ID: e0e59f1eaa8e
Revises: c2fe7b01cb66
Create Date: 2025-04-30 07:50:33.466748

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e0e59f1eaa8e'
down_revision = 'c2fe7b01cb66'
branch_labels = None
depends_on = None

def upgrade():
    # Add status and error_message to voices table if not already present
    # Use batch_alter_table to handle SQLite compatibility if needed
    with op.batch_alter_table('voices', schema=None) as batch_op:
        # Check if status column already exists (migration-safe approach)
        conn = op.get_bind()
        insp = sa.inspect(conn)
        columns = insp.get_columns('voices')
        column_names = [col['name'] for col in columns]
        
        # Add status column if it doesn't exist
        if 'status' not in column_names:
            batch_op.add_column(sa.Column('status', sa.String(20), nullable=True))
        
        # Add error_message column if it doesn't exist
        if 'error_message' not in column_names:
            batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True))

    # Update existing voices to "ready" status
    # Make elevenlabs_voice_id nullable (for pending status)
    try:
        # Set default status for existing records
        op.execute("UPDATE voices SET status = 'ready' WHERE status IS NULL AND elevenlabs_voice_id IS NOT NULL")
        
        # Make status not nullable with default
        with op.batch_alter_table('voices', schema=None) as batch_op:
            # Use a single transaction for multiple alterations
            # First make elevenlabs_voice_id nullable
            batch_op.alter_column('elevenlabs_voice_id',
                       existing_type=sa.String(255),
                       nullable=True)
            
            # Then make status not nullable with default
            batch_op.alter_column('status',
                       existing_type=sa.String(20),
                       nullable=False,
                       server_default='pending')
            
            # Remove server default after migration
            batch_op.alter_column('status',
                       existing_type=sa.String(20),
                       server_default=None)
    except Exception as e:
        print(f"Error updating columns: {e}")
        # Continue with migration even if column update fails
        # This allows the migration to work on databases where the schema might already be partially updated


def downgrade():
    # Revert the changes - make elevenlabs_voice_id not nullable again
    # and remove status/error_message columns
    with op.batch_alter_table('voices', schema=None) as batch_op:
        # First make elevenlabs_voice_id not nullable again
        batch_op.alter_column('elevenlabs_voice_id',
                   existing_type=sa.String(255),
                   nullable=False)
        
        # Then drop the new columns
        batch_op.drop_column('error_message')
        batch_op.drop_column('status')