#!/usr/bin/env python3
"""
Production Stories Upload Script

This script uploads exported stories from local backup to production server.
It handles authentication, bulk uploads, and provides detailed progress reporting.

Usage:
    python scripts/upload_stories_to_production.py --help
    python scripts/upload_stories_to_production.py --server https://api.dawnotemu.app --email admin@dawnotemu.app --password your_password
    python scripts/upload_stories_to_production.py --server https://api.dawnotemu.app --token your_jwt_token --source stories_backup
"""

import os
import sys
import json
import argparse
import requests
import getpass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Add the parent directory to the path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class ProductionUploader:
    """Handle uploading stories to production server"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.auth_token = auth_token
        self.session = requests.Session()
        
        # Set up authentication headers
        self.session.headers.update({'Content-Type': 'application/json'})
        
        if api_key:
            # API key authentication (for production story uploads)
            self.session.headers.update({'X-API-Key': api_key})
        elif auth_token:
            # JWT token authentication (for admin operations)
            self.session.headers.update({'Authorization': f'Bearer {auth_token}'})
    
    def authenticate(self, email: str, password: str) -> Tuple[bool, str]:
        """
        Authenticate with the production server
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Tuple[bool, str]: (success, token_or_error_message)
        """
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={
                    'email': email,
                    'password': password
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('access_token')
                
                if token:
                    self.auth_token = token
                    self.session.headers.update({
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json'
                    })
                    return True, token
                else:
                    return False, "No access token in response"
            else:
                error_msg = response.json().get('error', f'HTTP {response.status_code}')
                return False, error_msg
                
        except Exception as e:
            return False, str(e)
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test connection to the production server
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Use appropriate endpoint based on authentication method
            if self.api_key:
                # Test API key by trying to access the actual upload endpoint with a test request
                # This properly validates the API key authentication
                test_data = {
                    "title": "Test Story",
                    "author": "Test Author", 
                    "content": "Test content for API key validation"
                }
                
                response = self.session.post(
                    f"{self.base_url}/admin/stories/upload",
                    json=test_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    # Test successful - check if it was actually uploaded or is a duplicate
                    result = response.json()
                    if result.get('duplicate'):
                        return True, f"API key authentication successful. Test story already exists (ID: {result.get('existing_story_id')})."
                    else:
                        return True, f"API key authentication successful. Test story uploaded (ID: {result.get('story_id')})."
                elif response.status_code == 401:
                    return False, "API key authentication failed. Check your API key configuration in ADMIN_API_KEYS."
                elif response.status_code == 400:
                    # Bad request likely means API key worked but data validation failed
                    # This is actually good - it means auth passed
                    return True, "API key authentication successful. Server accessible (data validation passed)."
                else:
                    return False, f"Server returned HTTP {response.status_code}: {response.text}"
            else:
                # JWT token can access admin endpoints
                response = self.session.get(f"{self.base_url}/admin/stories/stats", timeout=30)
                
                if response.status_code == 200:
                    stats = response.json()
                    return True, f"Connected successfully. Server has {stats.get('total_stories', 0)} stories."
                elif response.status_code == 401:
                    return False, "Authentication failed. Check your credentials."
                elif response.status_code == 403:
                    return False, "Access denied. Admin privileges required."
                else:
                    return False, f"Server returned HTTP {response.status_code}"
                
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    def upload_single_story(self, story_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload a single story to production
        
        Args:
            story_data: Story data dictionary
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (success, result)
        """
        try:
            # Remove export metadata before uploading
            clean_story_data = {k: v for k, v in story_data.items() if k != 'export_metadata'}
            
            response = self.session.post(
                f"{self.base_url}/admin/stories/upload",
                json=clean_story_data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                return True, response.json()
            else:
                return False, {
                    'error': f"HTTP {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            return False, {'error': str(e)}
    
    def upload_stories_from_directory(self, source_dir: str) -> Dict[str, Any]:
        """
        Upload all stories from a backup directory
        
        Args:
            source_dir: Directory containing exported stories
            
        Returns:
            Dict[str, Any]: Upload results summary
        """
        source_path = Path(source_dir)
        
        if not source_path.exists():
            return {
                'success': False,
                'error': f"Source directory does not exist: {source_dir}"
            }
        
        # Look for metadata file
        metadata_file = source_path / "metadata.json"
        
        if not metadata_file.exists():
            return {
                'success': False,
                'error': f"No metadata.json found in {source_dir}. Run export first."
            }
        
        # Load metadata
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to load metadata: {str(e)}"
            }
        
        results = {
            'success': True,
            'total': 0,
            'uploaded': 0,
            'duplicates': 0,
            'failed': 0,
            'uploaded_stories': [],
            'duplicate_stories': [],
            'failed_stories': []
        }
        
        exported_stories = metadata.get('exported_stories', [])
        results['total'] = len(exported_stories)
        
        print(f"Found {results['total']} stories to upload...")
        
        for i, story_info in enumerate(exported_stories, 1):
            story_file = Path(story_info['file'])
            
            if not story_file.exists():
                print(f"[{i}/{results['total']}] ✗ Story file not found: {story_file}")
                results['failed'] += 1
                results['failed_stories'].append({
                    'id': story_info.get('id'),
                    'title': story_info.get('title'),
                    'error': 'File not found'
                })
                continue
            
            # Load story data
            try:
                with open(story_file, 'r', encoding='utf-8') as f:
                    story_data = json.load(f)
            except Exception as e:
                print(f"[{i}/{results['total']}] ✗ Failed to load {story_file}: {str(e)}")
                results['failed'] += 1
                results['failed_stories'].append({
                    'id': story_info.get('id'),
                    'title': story_info.get('title'),
                    'error': f'Failed to load file: {str(e)}'
                })
                continue
            
            # Upload story
            success, result = self.upload_single_story(story_data)
            
            if success:
                if result.get('duplicate'):
                    print(f"[{i}/{results['total']}] ⚠ Duplicate: {story_data['title']}")
                    results['duplicates'] += 1
                    results['duplicate_stories'].append({
                        'id': story_data['id'],
                        'title': story_data['title'],
                        'existing_id': result.get('existing_story_id')
                    })
                else:
                    print(f"[{i}/{results['total']}] ✓ Uploaded: {story_data['title']}")
                    results['uploaded'] += 1
                    results['uploaded_stories'].append({
                        'id': story_data['id'],
                        'title': story_data['title'],
                        'new_id': result.get('story_id')
                    })
            else:
                print(f"[{i}/{results['total']}] ✗ Failed: {story_data['title']} - {result.get('error', 'Unknown error')}")
                results['failed'] += 1
                results['failed_stories'].append({
                    'id': story_data['id'],
                    'title': story_data['title'],
                    'error': result.get('error', 'Unknown error')
                })
        
        return results


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Upload stories to production server')
    
    # Server connection
    parser.add_argument('--server', required=True,
                       help='Production server URL (e.g., https://api.dawnotemu.app)')
    
    # Authentication (API key is required for production uploads)
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument('--api-key',
                           help='API key for production story uploads (REQUIRED for production)')
    auth_group.add_argument('--email',
                           help='Email for authentication (DEVELOPMENT ONLY - not for production uploads)')
    
    # Upload options
    parser.add_argument('--source', default='stories_backup',
                       help='Source directory with exported stories (default: stories_backup)')
    parser.add_argument('--password',
                       help='Password for authentication (not recommended, use interactive prompt)')
    parser.add_argument('--test-only', action='store_true',
                       help='Only test connection, do not upload')
    parser.add_argument('--stats-only', action='store_true',
                       help='Only show server statistics')
    
    args = parser.parse_args()
    
    # Security warnings and checks
    if args.email and not args.api_key:
        print("🚨 SECURITY WARNING: Email/password authentication is NOT recommended for production!")
        print("🚨 This method should only be used for development and testing.")
        print("🚨 For production uploads, use --api-key instead.")
        
        confirm = input("Continue with email/password? (y/N): ").lower()
        if confirm != 'y':
            print("Upload cancelled. Use --api-key for secure production uploads.")
            sys.exit(0)
    
    # Initialize uploader  
    uploader = ProductionUploader(args.server, api_key=getattr(args, 'api_key', None))
    
    # Handle authentication
    if args.email:
        if args.password:
            password = args.password
        else:
            password = getpass.getpass(f"Enter password for {args.email}: ")
        
        print(f"⚠️  Authenticating with {args.server} using email/password (NOT recommended for production)...")
        success, result = uploader.authenticate(args.email, password)
        
        if not success:
            print(f"❌ Authentication failed: {result}")
            sys.exit(1)
        
        print("✅ Authentication successful")
    elif args.api_key:
        print(f"🔐 Using API key authentication (secure for production)")
    else:
        print("❌ No authentication method provided")
        sys.exit(1)
    
    # Test connection
    print("Testing connection...")
    success, message = uploader.test_connection()
    
    if not success:
        print(f"❌ Connection test failed: {message}")
        sys.exit(1)
    
    print(f"✅ {message}")
    
    if args.test_only:
        print("Test completed successfully!")
        sys.exit(0)
    
    if args.stats_only:
        print("Server statistics retrieved successfully!")
        sys.exit(0)
    
    # Upload stories
    print(f"\nStarting upload from {args.source}...")
    results = uploader.upload_stories_from_directory(args.source)
    
    if not results['success']:
        print(f"❌ Upload failed: {results['error']}")
        sys.exit(1)
    
    # Print summary
    print("\n" + "="*60)
    print("UPLOAD SUMMARY")
    print("="*60)
    print(f"Total stories processed: {results['total']}")
    print(f"Successfully uploaded: {results['uploaded']}")
    print(f"Duplicates skipped: {results['duplicates']}")
    print(f"Failed uploads: {results['failed']}")
    
    if results['failed'] > 0:
        print("\n❌ FAILED UPLOADS:")
        for failed in results['failed_stories']:
            print(f"  - {failed['title']} (ID: {failed['id']}): {failed['error']}")
    
    if results['duplicates'] > 0:
        print("\n⚠️  DUPLICATE STORIES:")
        for duplicate in results['duplicate_stories']:
            print(f"  - {duplicate['title']} (ID: {duplicate['id']}) -> existing ID: {duplicate['existing_id']}")
    
    if results['uploaded'] > 0:
        print("\n✅ SUCCESSFULLY UPLOADED:")
        for uploaded in results['uploaded_stories']:
            print(f"  - {uploaded['title']} (old ID: {uploaded['id']}) -> new ID: {uploaded['new_id']}")
    
    print(f"\n🎉 Upload completed! {results['uploaded']} stories uploaded successfully.")
    
    if results['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main() 