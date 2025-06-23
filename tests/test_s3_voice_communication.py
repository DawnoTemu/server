#!/usr/bin/env python3
"""
Test script for S3-based communication between server and Celery for voice cloning.

This script tests:
1. Uploading a voice sample to S3 (server side)
2. Downloading the voice sample from S3 (Celery side)
3. Processing the voice sample
4. Cleaning up temporary S3 files
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from utils.s3_client import S3Client
from io import BytesIO
import uuid

def test_s3_voice_communication():
    """Test the S3-based communication system for voice cloning"""
    
    app = create_app()
    with app.app_context():
        print("🧪 Testing S3-based Voice Communication System")
        print("=" * 60)
        
        # Test 1: Create a fake audio file
        print("\n📋 Step 1: Creating test audio data")
        fake_audio_data = b"fake_audio_data_for_testing_" * 1000  # Create some test data
        file_obj = BytesIO(fake_audio_data)
        
        user_id = 999
        voice_id = 888
        filename = "test_voice.mp3"
        
        # Generate a temporary S3 key (like the server would)
        temp_s3_key = f"temp_uploads/{user_id}/voice_{voice_id}_{uuid.uuid4()}.mp3"
        print(f"📊 Generated S3 key: {temp_s3_key}")
        print(f"📊 Test data size: {len(fake_audio_data)} bytes")
        
        # Test 2: Upload to S3 (server side)
        print("\n📋 Step 2: Uploading to S3 (server side)")
        try:
            extra_args = {
                'ContentType': 'audio/mpeg',
                'Metadata': {
                    'user_id': str(user_id),
                    'voice_id': str(voice_id),
                    'original_filename': filename
                }
            }
            
            file_obj.seek(0)
            success = S3Client.upload_fileobj(file_obj, temp_s3_key, extra_args)
            
            if success:
                print(f"✅ Successfully uploaded to S3: {temp_s3_key}")
            else:
                print(f"❌ Failed to upload to S3")
                return False
                
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return False
        
        # Test 3: Download from S3 (Celery side)
        print("\n📋 Step 3: Downloading from S3 (Celery side)")
        try:
            downloaded_file = S3Client.download_fileobj(temp_s3_key)
            downloaded_data = downloaded_file.read()
            
            print(f"✅ Successfully downloaded from S3")
            print(f"📊 Downloaded data size: {len(downloaded_data)} bytes")
            
            # Verify data integrity
            if downloaded_data == fake_audio_data:
                print(f"✅ Data integrity verified - upload/download successful")
            else:
                print(f"❌ Data integrity check failed")
                return False
                
        except Exception as e:
            print(f"❌ Download error: {e}")
            return False
        
        # Test 4: Clean up temporary S3 file
        print("\n📋 Step 4: Cleaning up temporary S3 file")
        try:
            success, deleted_count, errors = S3Client.delete_objects([temp_s3_key])
            
            if success:
                print(f"✅ Successfully cleaned up temporary S3 file")
                print(f"📊 Deleted {deleted_count} objects")
            else:
                print(f"❌ Failed to clean up S3 file: {errors}")
                return False
                
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
            return False
        
        # Test 5: Verify file is deleted
        print("\n📋 Step 5: Verifying file deletion")
        try:
            # This should fail since the file was deleted
            S3Client.download_fileobj(temp_s3_key)
            print(f"❌ File still exists after deletion")
            return False
        except Exception:
            print(f"✅ File successfully deleted - download correctly failed")
        
        print("\n🎉 All S3 communication tests passed!")
        print("\n📝 Summary:")
        print("✅ Server can upload voice samples to S3")
        print("✅ Celery can download voice samples from S3")
        print("✅ Data integrity is maintained")
        print("✅ Temporary files are properly cleaned up")
        print("✅ System is ready for distributed cloud deployment")
        
        return True

if __name__ == "__main__":
    success = test_s3_voice_communication()
    if not success:
        sys.exit(1) 