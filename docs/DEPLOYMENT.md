# DawnoTemu Deployment Guide

This guide covers deploying DawnoTemu in various environments, from local development to distributed cloud production.

## 🏗️ Architecture Overview

DawnoTemu uses a distributed architecture designed for cloud deployment:

- **Flask Server**: Handles API requests and user management
- **Celery Workers**: Process voice cloning and audio synthesis
- **PostgreSQL**: Database for user data and voice metadata
- **Redis**: Task queue and caching
- **AWS S3**: File storage and inter-service communication
- **Resend**: Email delivery service

### Key Features for Cloud Deployment

- **S3-Based Communication**: Server and Celery communicate via S3, not local files
- **Stateless Components**: All services can be scaled independently
- **Distributed Processing**: Celery workers can run on separate instances
- **Cloud Storage**: All audio files stored in AWS S3

## 🚀 Deployment Options

### 1. Local Development

Perfect for development and testing:

```bash
# Terminal 1 - Redis
redis-server

# Terminal 2 - Flask Server
flask run --host=0.0.0.0 --port=8000

# Terminal 3 - Celery Worker
celery -A celery_worker.celery_app worker --loglevel=info
```

### 2. Heroku Deployment (Recommended)

Heroku provides an excellent platform for DawnoTemu with built-in scaling:

#### Prerequisites
- Heroku CLI installed
- AWS account with S3 bucket
- Resend account for emails
- Cartesia/ElevenLabs API keys

#### Step-by-Step Deployment

1. **Create Heroku App**
   ```bash
   heroku create dawnotemu-app
   ```

2. **Add Required Add-ons**
   ```bash
   heroku addons:create heroku-postgresql:mini
   heroku addons:create heroku-redis:mini
   ```

3. **Configure Environment Variables**
   ```bash
   # API Keys
   heroku config:set CARTESIA_API_KEY=your_cartesia_api_key
   heroku config:set ELEVENLABS_API_KEY=your_elevenlabs_api_key
   heroku config:set RESEND_API_KEY=your_resend_api_key
   
   # AWS Configuration
   heroku config:set AWS_ACCESS_KEY_ID=your_aws_access_key
   heroku config:set AWS_SECRET_ACCESS_KEY=your_aws_secret_key
   heroku config:set AWS_REGION=eu-west-1
   heroku config:set S3_BUCKET_NAME=your_s3_bucket_name
   
   # Email Configuration
   heroku config:set RESEND_FROM_EMAIL=no-reply@dawnotemu.app
   heroku config:set FRONTEND_URL=https://dawnotemu.app
   heroku config:set BACKEND_URL=https://dawnotemu-api.herokuapp.com
   
   # Application Configuration
   heroku config:set SECRET_KEY=your_production_secret_key
   heroku config:set PREFERRED_VOICE_SERVICE=cartesia
   ```

4. **Deploy Application**
   ```bash
   git push heroku main
   ```

5. **Run Database Migrations**
   ```bash
   heroku run flask db upgrade
   ```

6. **Scale Dynos**
   ```bash
   # Scale web dynos for API
   heroku ps:scale web=2
   
   # Scale worker dynos for voice processing
   heroku ps:scale worker=2
   ```

### 3. Docker Deployment

For containerized deployments:

#### Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: dawnotemu
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/dawnotemu
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    command: gunicorn app:app --bind 0.0.0.0:8000

  worker:
    build: .
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/dawnotemu
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    command: celery -A celery_worker.celery_app worker --loglevel=info

volumes:
  postgres_data:
```

#### Dockerfile

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Default command
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
```

### 4. AWS ECS Deployment

For enterprise-grade deployment on AWS:

#### Task Definitions

**Web Service Task Definition:**
```json
{
  "family": "dawnotemu-web",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "dawnotemu-web",
      "image": "your-registry/dawnotemu:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "DATABASE_URL", "value": "your-rds-url"},
        {"name": "REDIS_URL", "value": "your-elasticache-url"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/dawnotemu-web",
          "awslogs-region": "eu-west-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

**Worker Service Task Definition:**
```json
{
  "family": "dawnotemu-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "dawnotemu-worker",
      "image": "your-registry/dawnotemu:latest",
      "command": ["celery", "-A", "celery_worker.celery_app", "worker", "--loglevel=info"],
      "environment": [
        {"name": "DATABASE_URL", "value": "your-rds-url"},
        {"name": "REDIS_URL", "value": "your-elasticache-url"}
      ]
    }
  ]
}
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `REDIS_URL` | Redis connection string | Yes | - |
| `CARTESIA_API_KEY` | Cartesia API key | Yes | - |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Yes | - |
| `RESEND_API_KEY` | Resend email API key | Yes | - |
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes | - |
| `AWS_REGION` | AWS region | Yes | - |
| `S3_BUCKET_NAME` | S3 bucket name | Yes | - |
| `SECRET_KEY` | Flask secret key | Yes | - |
| `FRONTEND_URL` | Frontend application URL | No | `http://localhost:3000` |
| `BACKEND_URL` | Backend API URL | No | `http://localhost:8000` |
| `ELEVENLABS_SLOT_LIMIT` | Maximum concurrent remote voices | No | `30` |
| `VOICE_WARM_HOLD_SECONDS` | Warm-hold window before eviction | No | `900` |
| `VOICE_QUEUE_POLL_INTERVAL` | Interval for processing queued allocations (seconds) | No | `60` |
| `PREFERRED_VOICE_SERVICE` | Voice service preference | No | `cartesia` |

### AWS S3 Bucket Configuration

Your S3 bucket should have the following structure:
```
your-bucket/
├── voice_samples/          # Permanent voice samples
│   └── {user_id}/
│       └── {voice_id}.mp3
├── temp_uploads/           # Temporary uploads for processing
│   └── {user_id}/
│       └── voice_{voice_id}_{uuid}.mp3
└── audio_stories/          # Generated story audio
    └── {voice_id}/
        └── {story_id}.mp3
```

### S3 Bucket Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR-ACCOUNT:user/dawnotemu-user"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::your-bucket/*"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR-ACCOUNT:user/dawnotemu-user"
      },
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::your-bucket"
    }
  ]
}
```

## 📊 Scaling Considerations

### Horizontal Scaling

- **Web Dynos**: Scale based on API traffic
- **Worker Dynos**: Scale based on voice processing queue length
- **Database**: Use connection pooling and read replicas
- **Redis**: Use Redis Cluster for high availability

### Performance Optimization

1. **Database Optimization**
   - Use connection pooling (configured in `config.py`)
   - Index frequently queried columns
   - Use database migrations for schema changes

2. **S3 Optimization**
   - Use multipart uploads for large files
   - Implement CloudFront CDN for audio delivery
   - Set appropriate cache headers

3. **Celery Optimization**
   - Use multiple worker processes
   - Implement task routing for different queues
   - Monitor queue lengths and processing times

## 🔒 Security Best Practices

### Environment Security
- Store all secrets in environment variables
- Use IAM roles instead of access keys when possible
- Rotate API keys regularly
- Enable S3 bucket versioning and encryption

### Application Security
- Use HTTPS in production
- Implement rate limiting
- Enable CORS properly
- Use secure session configurations

### Database Security
- Use SSL connections
- Implement regular backups
- Use database connection encryption
- Monitor for suspicious activity

## 📈 Monitoring and Logging

### Application Monitoring
- Use Heroku metrics or CloudWatch
- Monitor API response times
- Track voice processing queue lengths
- Set up alerts for errors

### Logging Configuration
```python
# Production logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
        },
    },
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
}
```

## 🚨 Troubleshooting

### Common Issues

1. **Voice Processing Fails**
   - Check S3 permissions
   - Verify API keys are valid
   - Monitor Celery worker logs

2. **Database Connection Issues**
   - Check connection pooling settings
   - Verify DATABASE_URL format
   - Monitor connection counts

3. **S3 Upload/Download Failures**
   - Verify AWS credentials
   - Check bucket permissions
   - Monitor S3 request metrics

### Health Checks

Implement health check endpoints:
```python
@app.route('/health')
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.route('/health/detailed')
def detailed_health_check():
    # Check database, Redis, S3 connectivity
    pass
```

## 📋 Deployment Checklist

- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] S3 bucket created and configured
- [ ] DNS records configured
- [ ] SSL certificates installed
- [ ] Monitoring and alerting set up
- [ ] Backup procedures in place
- [ ] Load testing completed
- [ ] Security audit performed

## 🔄 Continuous Deployment

### GitHub Actions Example

```yaml
name: Deploy to Heroku

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: akhileshns/heroku-deploy@v3.12.12
        with:
          heroku_api_key: ${{secrets.HEROKU_API_KEY}}
          heroku_app_name: "dawnotemu-app"
          heroku_email: "your-email@example.com"
```

This deployment guide ensures your DawnoTemu application can scale from development to enterprise production environments while maintaining reliability and performance. 
