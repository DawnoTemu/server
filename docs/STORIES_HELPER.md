# Stories Helper System Documentation

The Stories Helper System provides comprehensive tools for exporting stories from your local database and uploading them to production servers. This system handles story backup, image downloads, and production deployment with **enterprise-grade security** and duplicate detection.

## 🔒 SECURITY FIRST

**🚨 CRITICAL SECURITY UPDATE**: The system now implements proper admin authentication:

- ✅ **API Keys**: Required for production story uploads
- ✅ **Admin Tokens**: Required for admin operations  
- ✅ **Role-Based Access**: Only admin users can access admin endpoints
- ❌ **Email/Password**: DEPRECATED for production use (development only)

## 🎯 Overview

The system consists of three main components:

1. **Stories Export Tool** (`utils/stories_helper.py`) - Exports stories from local database to JSON files
2. **Secure Admin API** (`routes/admin_routes.py`) - Role-based admin endpoints with API key authentication
3. **Production Upload Script** (`scripts/upload_stories_to_production.py`) - Secure production deployment

## 📁 File Structure

When you export stories, the following structure is created:

```
stories_backup/
├── metadata.json              # Export metadata and summary
├── story_1.json              # Individual story files
├── story_2.json
├── story_N.json
└── images/                   # Downloaded cover images
    ├── story_1_cover.png
    ├── story_2_cover.jpg
    └── story_N_cover.png
```

## 🔧 Setup and Prerequisites

### Environment Setup

Ensure you have all required dependencies:

```bash
# Install required packages (already in requirements.txt)
pip install requests flask sqlalchemy
```

### Configuration

Make sure your `.env` file contains:

```bash
# Database connection
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/dawnotemu

# AWS S3 credentials (for image downloads)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
S3_BUCKET_NAME=your_s3_bucket_name

# Security configuration
SECRET_KEY=your_super_secret_key_here

# Admin API Keys for production (comma-separated)
ADMIN_API_KEYS=your_production_api_key_1,your_production_api_key_2
```

### 🔑 Admin User Setup

First, you need to create an admin user and get proper credentials:

```bash
# Run migration to add admin role
flask db upgrade

# Create admin user (via Flask shell)
flask shell
>>> from models.user_model import UserModel
>>> admin_user = UserModel.create_user("admin@dawnotemu.app", "secure_password", is_admin=True)
>>> admin_user.is_active = True
>>> admin_user.email_confirmed = True
>>> from database import db
>>> db.session.commit()
>>> exit()
```

## 📤 Exporting Stories from Local Database

### Basic Export

Export all stories to the default directory:

```bash
python utils/stories_helper.py export
```

### Custom Export Directory

Export to a specific directory:

```bash
python utils/stories_helper.py export --output-dir my_stories_backup
```

### What Gets Exported

For each story, the system exports:

- **Story Data**: Title, author, description, content, metadata
- **Cover Images**: Downloaded from S3 or copied from local storage
- **Export Metadata**: Export timestamp, success/failure tracking

### Export Output Example

```bash
✓ Exported story 1: Kopciuszek
  ✓ Downloaded cover from S3: stories_backup/images/story_1_cover.png
✓ Exported story 2: Czerwony Kapturek
  ✓ Copied cover from local: stories_backup/images/story_2_cover.jpg
✗ Failed to export story 3: Królewna Śnieżka - Database error

Successfully exported 2 stories to stories_backup (1 failed)
```

## 🔐 Secure Authentication for Production

### Method 1: API Key (RECOMMENDED for Production)

1. **Generate API Key**: Add to your production environment:
   ```bash
   # In production .env
   ADMIN_API_KEYS=your_secure_api_key_here
   ```

2. **Upload with API Key**:
   ```bash
   python scripts/upload_stories_to_production.py \
     --server https://api.dawnotemu.app \
     --api-key your_secure_api_key_here
   ```

### Method 2: Admin Token (For Testing)

1. **Login as Admin** and get token:
   ```bash
   curl -X POST https://api.dawnotemu.app/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@dawnotemu.app", "password": "your_password"}'
   ```

2. **Generate Admin Token**:
   ```bash
   curl -X POST https://api.dawnotemu.app/admin/auth/generate-token \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -H "Content-Type: application/json"
   ```

### ⚠️ Method 3: Email/Password (DEVELOPMENT ONLY)

```bash
# ONLY for development - shows security warnings
python scripts/upload_stories_to_production.py \
  --server http://localhost:8000 \
  --email admin@dawnotemu.app
```

## 📤 Uploading Stories to Production

### Secure Production Upload

```bash
# RECOMMENDED: Use API key
python scripts/upload_stories_to_production.py \
  --server https://api.dawnotemu.app \
  --api-key your_production_api_key

# Custom source directory
python scripts/upload_stories_to_production.py \
  --server https://api.dawnotemu.app \
  --api-key your_production_api_key \
  --source my_stories_backup
```

### Test Connection

```bash
python scripts/upload_stories_to_production.py \
  --server https://api.dawnotemu.app \
  --api-key your_production_api_key \
  --test-only
```

### Upload Process

The upload script provides detailed progress information:

```bash
🔐 Using API key authentication (secure for production)
Testing connection...
✅ API key authentication successful. Server accessible.

Starting upload from stories_backup...
Found 3 stories to upload...

[1/3] ✓ Uploaded: Kopciuszek
[2/3] ⚠ Duplicate: Czerwony Kapturek
[3/3] ✗ Failed: Królewna Śnieżka - Missing required fields

============================================================
UPLOAD SUMMARY  
============================================================
Total stories processed: 3
Successfully uploaded: 1
Duplicates skipped: 1
Failed uploads: 1

🎉 Upload completed! 1 stories uploaded successfully.
```

## 🔗 Secure API Endpoints

### Story Upload Endpoints (API Key Required)

```http
POST /admin/stories/upload
X-API-Key: your_production_api_key
Content-Type: application/json

{
  "title": "Story Title",
  "author": "Author Name",
  "content": "Story content...",
  "description": "Optional description"
}
```

### Admin Management Endpoints (Admin Token Required)

```http
GET /admin/users
Authorization: Bearer admin_token

POST /admin/auth/generate-token
Authorization: Bearer admin_token
Content-Type: application/json

{
  "expires_in": 3600
}
```

## 🛡️ Enhanced Security Features

### Authentication Layers

1. **API Key Authentication**: For production story uploads
   - Server-side validation against `ADMIN_API_KEYS`
   - No user context required
   - Perfect for automated deployments

2. **Admin Token Authentication**: For admin operations
   - JWT tokens with admin privileges
   - Role-based access control
   - User context and activity tracking

3. **Role-Based Access Control**: 
   - `is_admin` field in user model
   - Admin-only endpoints protected
   - Prevents privilege escalation

### Security Validations

- ✅ **Admin Role Verification**: All admin endpoints check `user.is_admin`
- ✅ **Email Confirmation**: Required before admin access
- ✅ **Account Status**: Active account required
- ✅ **Token Expiration**: All tokens have expiration times
- ✅ **Input Validation**: Comprehensive request validation
- ✅ **Error Handling**: Secure error messages

## 🚨 Security Warnings

### Production Don'ts

❌ **NEVER use email/password for production uploads**  
❌ **NEVER commit API keys to version control**  
❌ **NEVER use development tokens in production**  
❌ **NEVER ignore the security warnings in the scripts**

### Production Do's

✅ **Use API keys for automated story uploads**  
✅ **Rotate API keys regularly**  
✅ **Use environment variables for secrets**  
✅ **Monitor admin endpoint access**  
✅ **Use HTTPS for all production communication**

## 🔧 Admin User Management

### Create Admin User

```python
# Flask shell
from models.user_model import UserModel
from database import db

# Create admin user
admin = UserModel.create_user("admin@example.com", "secure_password", is_admin=True)
admin.is_active = True
admin.email_confirmed = True
db.session.commit()
```

### Promote Existing User

```bash
curl -X POST https://api.dawnotemu.app/admin/users/123/promote \
  -H "Authorization: Bearer admin_token"
```

### Generate Admin Token

```bash
curl -X POST https://api.dawnotemu.app/admin/auth/generate-token \
  -H "Authorization: Bearer admin_token" \
  -H "Content-Type: application/json" \
  -d '{"expires_in": 3600}'
```

## 🎯 Best Practices

### Security

1. **API Key Management**:
   - Generate strong, unique API keys
   - Store in secure environment variables
   - Rotate keys regularly
   - Monitor usage

2. **Admin Access**:
   - Limit admin users to essential personnel
   - Use strong passwords
   - Enable 2FA when available
   - Regular access reviews

3. **Production Deployment**:
   - Use HTTPS only
   - Validate SSL certificates
   - Monitor for unauthorized access
   - Log all admin operations

### Development vs Production

| Feature | Development | Production |
|---------|-------------|------------|
| Authentication | Email/Password OK | API Key REQUIRED |
| SSL/HTTPS | Optional | REQUIRED |
| API Keys | Not required | MANDATORY |
| Logging | Basic | Comprehensive |
| Access Control | Relaxed | Strict |

## 📊 Migration Guide

### From Old System

If you were using the old email/password system:

1. **Add admin role to existing users**:
   ```python
   # Flask shell
   from models.user_model import UserModel
   user = UserModel.get_by_email("admin@example.com")
   user.is_admin = True
   from database import db
   db.session.commit()
   ```

2. **Generate API keys**:
   ```bash
   # Add to production environment
   ADMIN_API_KEYS=generate_secure_api_key_here
   ```

3. **Update deployment scripts**:
   ```bash
   # Old (INSECURE)
   --email admin@example.com

   # New (SECURE)
   --api-key your_secure_api_key
   ```

## 📝 Support

For security issues or questions:

1. **Review this documentation**
2. **Check server logs for authentication errors**
3. **Verify API key configuration**
4. **Test with `--test-only` flag**
5. **Contact the security team for production issues**

---

**🔐 Security First, Stories Second! 🎭📚** 