"""Populate stories

Revision ID: a36a09dda7c8
Revises: 96fdb828fe76
Create Date: 2025-03-10 23:16:42.802462

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, Text, DateTime
from datetime import datetime
import json
import os
from pathlib import Path



# revision identifiers, used by Alembic.
revision = 'a36a09dda7c8'
down_revision = '96fdb828fe76'
branch_labels = None
depends_on = None

def get_stories_dir():
    """Get the stories directory path from app config"""
    # Try to get the path from the app config
    from app import app
    with app.app_context():
        from config import Config
        return Config.STORIES_DIR
    
    # Fallback to a reasonable default if that doesn't work
    return Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'stories'))


def upgrade():
    """Migrate stories from JSON files to database"""
    print("Starting to populate stories...")
    
    # Define the stories table structure for raw SQL operations
    stories_table = table('stories',
        column('id', Integer),
        column('title', String),
        column('author', String),
        column('description', Text),
        column('content', Text),
        column('cover_filename', String),
        column('created_at', DateTime),
        column('updated_at', DateTime)
    )
    
    # Get stories directory
    stories_dir = get_stories_dir()
    print(f"Looking for stories in: {stories_dir}")
    
    # Count of stories migrated
    count = 0
    
    # Process each JSON file
    for file_path in stories_dir.glob('*.json'):
        # Skip non-numeric filenames (might be metadata files)
        if not file_path.stem.isdigit():
            continue
            
        try:
            print(f"Processing file: {file_path}")
            
            # Read the JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if story already exists
            connection = op.get_bind()
            result = connection.execute(
                sa.text("SELECT id FROM stories WHERE id = :id"),
                {"id": data.get('id')}
            ).fetchone()
            
            if result:
                print(f"Story with ID {data.get('id')} already exists, skipping...")
                continue
            
            # Prepare cover_filename
            cover_filename = None
            cover_path = stories_dir / f"cover{data.get('id')}.png"
            if cover_path.exists():
                cover_filename = f"cover{data.get('id')}.png"
                print(f"Found cover image: {cover_filename}")
            
            # Insert the story
            now = datetime.utcnow()
            op.bulk_insert(
                stories_table,
                [{
                    'id': data.get('id'),
                    'title': data.get('title', 'Untitled'),
                    'author': data.get('author', 'Unknown'),
                    'description': data.get('description', ''),
                    'content': data.get('content', ''),
                    'cover_filename': cover_filename,
                    'created_at': now,
                    'updated_at': now
                }]
            )
            
            count += 1
            print(f"Added story: {data.get('title')}")
            
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
    
    print(f"Successfully migrated {count} stories to the database.")


def downgrade():
    """Remove migrated stories"""
    # Get stories directory to find IDs
    stories_dir = get_stories_dir()
    
    # Find all story IDs from JSON files
    story_ids = []
    for file_path in stories_dir.glob('*.json'):
        if file_path.stem.isdigit():
            story_ids.append(int(file_path.stem))
    
    if not story_ids:
        print("No stories to remove.")
        return
    
    # Convert list to string for SQL IN clause
    ids_str = ','.join(str(id) for id in story_ids)
    
    # Delete stories with matching IDs
    connection = op.get_bind()
    result = connection.execute(
        sa.text(f"DELETE FROM stories WHERE id IN ({ids_str})")
    )
    
    print(f"Removed {result.rowcount} stories from the database.")