# API Key Generation Guide 🔑

This guide shows you **multiple secure methods** to generate production-grade API keys for DawnoTemu.

## 🎯 Quick Start (Recommended)

### Method 1: Use Our Custom Generator (Best)

```bash
# Generate a secure production API key
python scripts/generate_api_key.py

# Generate with custom settings
python scripts/generate_api_key.py --method hex --length 64

# Generate multiple keys for rotation
python scripts/generate_api_key.py --multiple 3

# Show all available methods
python scripts/generate_api_key.py --show-methods
```

### Method 2: Command Line Tools

```bash
# Using OpenSSL (most secure)
openssl rand -hex 32

# Using Python one-liner
python -c "import secrets; print(secrets.token_hex(32))"

# Using uuidgen (simple but secure)
uuidgen | tr -d '-'
```

## 🔧 Detailed Methods

### 1. Our Custom API Key Generator

The custom script provides the most comprehensive solution:

```bash
# Default: 64-character hex key (256-bit entropy)
python scripts/generate_api_key.py

# UUID-based key (128-bit entropy)
python scripts/generate_api_key.py --method uuid

# Base64 URL-safe key
python scripts/generate_api_key.py --method base64 --length 48

# Alphanumeric key
python scripts/generate_api_key.py --method alphanumeric --length 64

# Custom prefix/suffix
python scripts/generate_api_key.py --prefix "DT_" --suffix "_PROD"

# Generate multiple keys for rotation
python scripts/generate_api_key.py --multiple 5
```

**Example Output:**
```
================================================================================
🔑 GENERATED API KEY
================================================================================
Method: hex
Key:    c056d5e480226761b4f2165e94c6d69df28b5766977f6ee4ec959bc66d094f93
Length: 64 characters
Entropy: 256.0 bits
Strength: EXCELLENT

📋 CONFIGURATION:
Add to your production .env file:
ADMIN_API_KEYS=c056d5e480226761b4f2165e94c6d69df28b5766977f6ee4ec959bc66d094f93
```

### 2. OpenSSL (Most Widely Available)

```bash
# Generate 32-byte (256-bit) hex key
openssl rand -hex 32
# Output: a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456

# Generate 32-byte base64 key
openssl rand -base64 32
# Output: kJ8NiobKV2bULcP8gzrR6QpW+vN4mFDx3hZwE2A=

# Generate 48-byte base64 key (stronger)
openssl rand -base64 48
# Output: R7P3mZ9Nf2vK8+Qn5WEt6Gc4JyL1Ds7XvY4CqA9nB2pW3hM8+
```

### 3. Python Built-in Methods

```bash
# Secure hex token (recommended)
python -c "import secrets; print(secrets.token_hex(32))"

# Secure URL-safe base64 token
python -c "import secrets; print(secrets.token_urlsafe(32))"

# UUID4 (good entropy, standardized)
python -c "import uuid; print(str(uuid.uuid4()).replace('-', ''))"

# Custom alphanumeric
python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))"
```

### 4. System Tools

```bash
# UUID generator (available on most systems)
uuidgen | tr -d '-'

# /dev/urandom (Linux/macOS)
head -c 32 /dev/urandom | xxd -p -c 32

# Random with base64 encoding
head -c 32 /dev/urandom | base64 | tr -d '='

# Using dd (Linux/macOS)
dd if=/dev/urandom bs=32 count=1 2>/dev/null | xxd -p -c 32
```

### 5. Node.js/JavaScript

```bash
# If you have Node.js available
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"

# UUID approach
node -e "console.log(require('crypto').randomUUID().replace(/-/g, ''))"
```

## 🎯 Recommended Settings by Use Case

### Production (High Security)
```bash
# Best: Custom generator with hex
python scripts/generate_api_key.py --method hex --length 64

# Alternative: OpenSSL
openssl rand -hex 32
```

### Development/Testing
```bash
# Simple UUID approach
python scripts/generate_api_key.py --method uuid

# Or command line
uuidgen | tr -d '-'
```

### Enterprise/Compliance
```bash
# Maximum entropy (384 bits)
python scripts/generate_api_key.py --method hex --length 96

# With organizational prefix
python scripts/generate_api_key.py --prefix "DAWNO_" --method hex --length 64
```

### API Key Rotation
```bash
# Generate multiple keys for rotation
python scripts/generate_api_key.py --multiple 5

# Or batch generation
for i in {1..5}; do echo "Key $i: $(openssl rand -hex 32)"; done
```

## 📊 Security Comparison

| Method | Entropy (bits) | Strength | Use Case |
|--------|---------------|----------|----------|
| `hex --length 64` | 256 | Excellent | Production |
| `base64 --length 48` | 256 | Excellent | Production |
| `uuid` | 122 | Good | Development |
| `alphanumeric --length 64` | 380 | Excellent | High Security |
| `openssl rand -hex 32` | 256 | Excellent | Production |

## 🔍 Key Validation

Validate existing keys:

```bash
# Validate an existing key
python scripts/generate_api_key.py --validate "your_existing_key_here"

# Example output:
# Length: 64 characters
# Entropy: 256.0 bits
# Strength: EXCELLENT
```

## 📋 Configuration Examples

### Single API Key
```bash
# .env file
ADMIN_API_KEYS=c056d5e480226761b4f2165e94c6d69df28b5766977f6ee4ec959bc66d094f93
```

### Multiple API Keys (for rotation)
```bash
# .env file
ADMIN_API_KEYS=key1_here,key2_here,key3_here
```

### With Environment-specific Prefixes
```bash
# Production
ADMIN_API_KEYS=PROD_c056d5e480226761b4f2165e94c6d69df28b5766977f6ee4ec959bc66d094f93

# Staging
ADMIN_API_KEYS=STAGING_a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

## 🔒 Security Best Practices

### Generation
✅ **Use cryptographically secure random generators** (`secrets`, `openssl`, `/dev/urandom`)  
✅ **Minimum 32 characters (128-bit entropy)**  
✅ **Prefer 64 characters (256-bit entropy) for production**  
✅ **Use our validator to check key strength**  

### Storage
✅ **Store in environment variables, not code**  
✅ **Use secure secret management (AWS Secrets Manager, Azure Key Vault)**  
✅ **Keep in password managers for team access**  
✅ **Encrypt at rest in production systems**  

### Management
✅ **Rotate keys regularly (monthly/quarterly)**  
✅ **Generate multiple keys for zero-downtime rotation**  
✅ **Monitor key usage and access logs**  
✅ **Revoke compromised keys immediately**  

### Don'ts
❌ **Never commit API keys to git repositories**  
❌ **Never log API keys in application logs**  
❌ **Never send API keys via email or chat**  
❌ **Never use predictable patterns or weak generators**  

## 🚀 Production Setup Workflow

1. **Generate secure API key:**
   ```bash
   python scripts/generate_api_key.py --method hex --length 64
   ```

2. **Add to production environment:**
   ```bash
   # In your production deployment
   export ADMIN_API_KEYS="your_generated_key_here"
   
   # Or in .env file
   echo "ADMIN_API_KEYS=your_generated_key_here" >> .env
   ```

3. **Test the key:**
   ```bash
   python scripts/upload_stories_to_production.py \
     --server https://api.dawnotemu.app \
     --api-key your_generated_key_here \
     --test-only
   ```

4. **Use in production:**
   ```bash
   python scripts/upload_stories_to_production.py \
     --server https://api.dawnotemu.app \
     --api-key your_generated_key_here \
     --source stories_backup
   ```

## 🔄 Key Rotation Example

```bash
# 1. Generate new keys
python scripts/generate_api_key.py --multiple 3

# 2. Add new key to environment (keep old one temporarily)
ADMIN_API_KEYS=old_key,new_key1,new_key2

# 3. Test with new key
python scripts/upload_stories_to_production.py \
  --api-key new_key1 --test-only

# 4. Remove old key after successful deployment
ADMIN_API_KEYS=new_key1,new_key2

# 5. Store backup key securely for emergency access
```

## 🆘 Emergency Access

If you lose your API keys:

1. **Access production server directly**
2. **Generate new key on server:**
   ```bash
   python scripts/generate_api_key.py
   ```
3. **Update environment variables**
4. **Test new key immediately**
5. **Update team with new key securely**

---

**🔐 Remember: A strong API key is your first line of defense!** 