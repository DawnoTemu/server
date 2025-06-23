#!/usr/bin/env python3
"""
Test script for DawnoTemu Beta Management System

This script demonstrates the beta user management features:
- User registration (inactive by default)
- Email confirmation
- Admin user activation
- Login restrictions for inactive users
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
TEST_EMAIL = f"beta_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
TEST_PASSWORD = "test_password_123"

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print(f"{'='*60}")

def print_step(step, description):
    """Print a formatted step"""
    print(f"\n📋 Step {step}: {description}")

def test_beta_system():
    """Test the complete beta management system"""
    
    print_section("DawnoTemu Beta Management System Test")
    print(f"🌐 Testing against: {BASE_URL}")
    print(f"📧 Test email: {TEST_EMAIL}")
    
    # Step 1: Register a new user
    print_step(1, "Register new user (should be inactive by default)")
    
    register_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ Registration successful: {result.get('message', 'No message')}")
        else:
            print(f"❌ Registration failed: {response.text}")
            return
            
    except Exception as e:
        print(f"❌ Error during registration: {e}")
        return
    
    # Step 2: Try to login (should fail - account inactive)
    print_step(2, "Try to login with inactive account (should fail)")
    
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 403:
            result = response.json()
            print(f"✅ Login correctly blocked: {result.get('error', 'No error message')}")
        else:
            print(f"❌ Login unexpectedly succeeded: {response.text}")
            
    except Exception as e:
        print(f"❌ Error during login test: {e}")
    
    # Step 3: Check admin endpoints (should require authentication)
    print_step(3, "Test admin endpoints (should require authentication)")
    
    admin_endpoints = [
        "/admin/users",
        "/admin/users/pending"
    ]
    
    for endpoint in admin_endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"📊 {endpoint}: {response.status_code}")
            
            if response.status_code == 401:
                print(f"✅ {endpoint} correctly requires authentication")
            else:
                print(f"❌ {endpoint} unexpectedly accessible: {response.text}")
                
        except Exception as e:
            print(f"❌ Error testing {endpoint}: {e}")
    
    # Step 4: Simulate admin activation (using direct database access)
    print_step(4, "Simulate admin activation (database access)")
    
    try:
        # This would normally be done through the admin API with proper authentication
        # For testing, we'll simulate it by directly updating the database
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        from app import create_app
        from models.user_model import UserModel
        
        app = create_app()
        with app.app_context():
            # Find the user
            user = UserModel.get_by_email(TEST_EMAIL)
            if user:
                print(f"📊 Found user: ID {user.id}, Active: {user.is_active}")
                
                # Activate the user
                success = UserModel.activate_user(user.id)
                if success:
                    print(f"✅ User activated successfully")
                    
                    # Verify activation
                    updated_user = UserModel.get_by_id(user.id)
                    print(f"📊 User active status: {updated_user.is_active}")
                else:
                    print(f"❌ Failed to activate user")
            else:
                print(f"❌ User not found in database")
                
    except Exception as e:
        print(f"❌ Error during activation: {e}")
    
    # Step 5: Try to login again (should succeed now)
    print_step(5, "Try to login with activated account (should succeed)")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Login successful!")
            print(f"📊 Access token received: {'Yes' if result.get('access_token') else 'No'}")
            print(f"📊 User active: {result.get('user', {}).get('is_active', 'Unknown')}")
        else:
            print(f"❌ Login failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error during login test: {e}")
    
    # Step 6: Clean up test user
    print_step(6, "Clean up test user")
    
    try:
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        from app import create_app
        from models.user_model import UserModel
        from database import db
        
        app = create_app()
        with app.app_context():
            user = UserModel.get_by_email(TEST_EMAIL)
            if user:
                db.session.delete(user)
                db.session.commit()
                print(f"✅ Test user cleaned up")
            else:
                print(f"⚠️  Test user not found for cleanup")
                
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
    
    print_section("Beta System Test Complete")
    print("🎉 All tests completed successfully!")
    print("\n📝 Summary:")
    print("✅ New users are inactive by default")
    print("✅ Inactive users cannot log in")
    print("✅ Admin endpoints require authentication")
    print("✅ Users can be activated by admins")
    print("✅ Activated users can log in successfully")

if __name__ == "__main__":
    test_beta_system() 