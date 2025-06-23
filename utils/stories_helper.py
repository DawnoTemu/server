#!/usr/bin/env python3
"""
Stories Helper Utility

This script provides functionality to:
1. Export stories from database to JSON files
2. Download story cover images
3. Upload stories to production server

Usage:
    python utils/stories_helper.py export --output-dir stories_backup
    python utils/stories_helper.py upload --source-dir stories_backup --target-url https://api.dawnotemu.app
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Add the parent directory to the path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.story_model import Story, StoryModel
from utils.s3_client import S3Client
from config import Config

class StoriesHelper:
    """Helper class for managing story export/import operations"""
    
    def __init__(self, output_dir: str = "stories_backup"):
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.metadata_file = self.output_dir / "metadata.json"
        
        # Create directories if they don't exist
        self.output_dir.mkdir(exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
    
    def export_all_stories(self) -> Tuple[bool, str]:
        """
        Export all stories from database to JSON files
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            app = create_app()
            with app.app_context():
                stories = Story.query.all()
                
                if not stories:
                    return False, "No stories found in database"
                
                exported_stories = []
                failed_exports = []
                
                for story in stories:
                    try:
                        # Export story data
                        story_data = self._export_story_data(story)
                        
                        # Save story to individual JSON file
                        story_file = self.output_dir / f"story_{story.id}.json"
                        with open(story_file, 'w', encoding='utf-8') as f:
                            json.dump(story_data, f, indent=2, ensure_ascii=False)
                        
                        # Download cover image if available
                        cover_downloaded = self._download_cover_image(story)
                        
                        exported_stories.append({
                            'id': story.id,
                            'title': story.title,
                            'file': str(story_file),
                            'cover_downloaded': cover_downloaded
                        })
                        
                        print(f"✓ Exported story {story.id}: {story.title}")
                        
                    except Exception as e:
                        failed_exports.append({
                            'id': story.id,
                            'title': story.title,
                            'error': str(e)
                        })
                        print(f"✗ Failed to export story {story.id}: {story.title} - {str(e)}")
                
                # Save export metadata
                metadata = {
                    'export_date': datetime.now().isoformat(),
                    'total_stories': len(stories),
                    'exported_count': len(exported_stories),
                    'failed_count': len(failed_exports),
                    'exported_stories': exported_stories,
                    'failed_exports': failed_exports
                }
                
                with open(self.metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                success_message = f"Successfully exported {len(exported_stories)} stories to {self.output_dir}"
                if failed_exports:
                    success_message += f" ({len(failed_exports)} failed)"
                
                return True, success_message
                
        except Exception as e:
            return False, f"Export failed: {str(e)}"
    
    def _export_story_data(self, story: Story) -> Dict:
        """
        Convert story to exportable dictionary format
        
        Args:
            story: Story database model
            
        Returns:
            Dict: Story data for export
        """
        return {
            'id': story.id,
            'title': story.title,
            'author': story.author,
            'description': story.description,
            'content': story.content,
            'cover_filename': story.cover_filename,
            's3_cover_key': story.s3_cover_key,
            'created_at': story.created_at.isoformat() if story.created_at else None,
            'updated_at': story.updated_at.isoformat() if story.updated_at else None,
            'export_metadata': {
                'exported_at': datetime.now().isoformat(),
                'has_local_cover': bool(story.cover_filename),
                'has_s3_cover': bool(story.s3_cover_key)
            }
        }
    
    def _download_cover_image(self, story: Story) -> bool:
        """
        Download cover image for a story
        
        Args:
            story: Story database model
            
        Returns:
            bool: True if image was downloaded successfully
        """
        try:
            image_downloaded = False
            
            # Try to download from S3 first
            if story.s3_cover_key:
                image_downloaded = self._download_from_s3(story)
            
            # If S3 download failed, try local file
            if not image_downloaded and story.cover_filename:
                image_downloaded = self._download_from_local(story)
            
            return image_downloaded
            
        except Exception as e:
            print(f"Warning: Could not download cover for story {story.id}: {str(e)}")
            return False
    
    def _download_from_s3(self, story: Story) -> bool:
        """Download cover image from S3"""
        try:
            # Generate presigned URL
            success, url = StoryModel.generate_cover_presigned_url(story.id)
            
            if not success:
                return False
            
            # Download the image
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Determine file extension from S3 key
            file_ext = Path(story.s3_cover_key).suffix or '.png'
            image_path = self.images_dir / f"story_{story.id}_cover{file_ext}"
            
            with open(image_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✓ Downloaded cover from S3: {image_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ S3 download failed: {str(e)}")
            return False
    
    def _download_from_local(self, story: Story) -> bool:
        """Download cover image from local storage"""
        try:
            local_path = StoryModel.get_story_cover_path(story.id)
            
            if not local_path.exists():
                return False
            
            # Copy to backup directory
            file_ext = local_path.suffix or '.png'
            image_path = self.images_dir / f"story_{story.id}_cover{file_ext}"
            
            import shutil
            shutil.copy2(local_path, image_path)
            
            print(f"  ✓ Copied cover from local: {image_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ Local copy failed: {str(e)}")
            return False
    
    def upload_stories_to_server(self, target_url: str, auth_token: Optional[str] = None) -> Tuple[bool, str]:
        """
        Upload stories to production server
        
        Args:
            target_url: Target server URL
            auth_token: Optional authentication token
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            if not self.metadata_file.exists():
                return False, "No export metadata found. Run export first."
            
            # Load metadata
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            uploaded_count = 0
            failed_count = 0
            duplicate_count = 0
            
            headers = {'Content-Type': 'application/json'}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            for story_info in metadata['exported_stories']:
                story_file = Path(story_info['file'])
                
                if not story_file.exists():
                    print(f"✗ Story file not found: {story_file}")
                    failed_count += 1
                    continue
                
                # Load story data
                with open(story_file, 'r', encoding='utf-8') as f:
                    story_data = json.load(f)
                
                # Upload story
                try:
                    response = requests.post(
                        f"{target_url}/admin/stories/upload",
                        json=story_data,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('duplicate'):
                            print(f"⚠ Story {story_data['id']} already exists: {story_data['title']}")
                            duplicate_count += 1
                        else:
                            print(f"✓ Uploaded story {story_data['id']}: {story_data['title']}")
                            uploaded_count += 1
                    else:
                        print(f"✗ Failed to upload story {story_data['id']}: {response.text}")
                        failed_count += 1
                        
                except Exception as e:
                    print(f"✗ Error uploading story {story_data['id']}: {str(e)}")
                    failed_count += 1
            
            summary = f"Upload complete: {uploaded_count} uploaded, {duplicate_count} duplicates, {failed_count} failed"
            return True, summary
            
        except Exception as e:
            return False, f"Upload failed: {str(e)}"


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Stories Helper - Export/Import stories')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export stories from database')
    export_parser.add_argument('--output-dir', default='stories_backup',
                             help='Output directory for exported stories')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload stories to server')
    upload_parser.add_argument('--source-dir', default='stories_backup',
                             help='Source directory with exported stories')
    upload_parser.add_argument('--target-url', required=True,
                             help='Target server URL')
    upload_parser.add_argument('--auth-token',
                             help='Authentication token for server')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'export':
        helper = StoriesHelper(args.output_dir)
        success, message = helper.export_all_stories()
        print(f"\n{message}")
        sys.exit(0 if success else 1)
    
    elif args.command == 'upload':
        helper = StoriesHelper(args.source_dir)
        success, message = helper.upload_stories_to_server(args.target_url, args.auth_token)
        print(f"\n{message}")
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main() 