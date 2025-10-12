# DawnoTemu: AI-Powered Personalized Bedtime Stories 🎙️✨

**Twój głos opowiada baśnie, zawsze gdy potrzebujesz**

DawnoTemu is an AI-powered platform that creates personalized bedtime stories using voice cloning technology. Parents can record their voice and have Polish fairy tales narrated in their own voice, creating magical moments even when they can't be physically present.

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0.2-lightgrey?logo=flask)](https://flask.palletsprojects.com/)
[![Cartesia](https://img.shields.io/badge/Powered%20by-Cartesia-purple)](https://cartesia.ai)
[![ElevenLabs](https://img.shields.io/badge/Powered%20by-ElevenLabs-orange)](https://elevenlabs.io)
[![Resend](https://img.shields.io/badge/Email%20by-Resend-green)](https://resend.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

![DawnoTemu Demo](demo-screenshot.png)

## 🌟 Features

### Core Functionality
- **🎤 Voice Cloning**: Record a 1-minute audio sample to create your unique voice profile
- **🤖 AI-Powered Narration**: Generate natural-sounding Polish story narration using Cartesia and ElevenLabs APIs
- **📚 Curated Polish Story Library**: Classic Polish fairy tales and bedtime stories
- **🎵 Interactive Audio Player**: Full playback controls with seek/scrub functionality
- **📱 Responsive Design**: Beautiful, mobile-first interface with DawnoTemu branding
- **🔐 User Authentication**: Secure account system with email confirmation and beta approval
- **📧 Professional Email System**: Branded emails using Resend API with beautiful templates
- **👨‍💼 Beta Management**: Admin-controlled user activation system for beta phase

### Advanced Features
- **⚡ Background Processing**: Celery-powered asynchronous voice synthesis
- **🌐 Multi-Service Support**: Cartesia (primary) and ElevenLabs voice services
- **☁️ Cloud Storage**: AWS S3 integration for audio file storage
- **🔄 Voice Quality Comparison**: Built-in testing system for voice quality optimization
- **👨‍💼 Admin Interface**: Flask-Admin dashboard for content management
- **🚀 Production Ready**: Comprehensive logging, error handling, and monitoring
- **🪄 Story Points (Punkty Magii)**: Credit system to control story generation costs (1 point per 1,000 characters; rounded up)

## 🏗️ Architecture

### Backend Stack
- **Python 3.13** - Core programming language
- **Flask 3.0.2** - Web framework with blueprints architecture
- **SQLAlchemy + PostgreSQL** - Database ORM and relational database
- **Celery + Redis** - Asynchronous task processing
- **Flask-Admin** - Administrative interface
- **Flask-Migrate** - Database migrations
- **Cartesia API** - Primary voice synthesis service
- **ElevenLabs API** - Secondary voice synthesis service
- **Resend API** - Email delivery service
- **AWS S3** - Cloud storage for audio files

### Frontend Technologies
- **HTML5/CSS3** - Modern web standards
- **Tailwind CSS** - Utility-first CSS framework
- **Vanilla JavaScript** - Client-side interactivity
- **DawnoTemu Design System** - Custom branded components

### Infrastructure
- **Heroku** - Cloud hosting platform
- **PostgreSQL** - Production database
- **Redis** - Task queue and caching
- **AWS S3** - File storage
- **Gunicorn** - WSGI HTTP Server

## 📋 Prerequisites

- Python 3.13 or higher
- PostgreSQL database
- Redis server
- Cartesia API key (get one at [cartesia.ai](https://cartesia.ai))
- ElevenLabs API key (get one at [elevenlabs.io](https://elevenlabs.io))
- Resend API key (get one at [resend.com](https://resend.com))
- AWS account with S3 bucket set up

## 🚀 Getting Started

### 1. Environment Setup

Clone the repository:
```bash
git clone https://github.com/yourusername/dawnotemu.git
cd dawnotemu/server
```

Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the server directory:
```bash
# Database Configuration
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/dawnotemu

# API Keys
CARTESIA_API_KEY=your_cartesia_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
RESEND_API_KEY=your_resend_api_key

# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=eu-west-1
S3_BUCKET_NAME=your_s3_bucket_name

# Email Configuration
RESEND_FROM_EMAIL=no-reply@dawnotemu.app
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

# Application Configuration
SECRET_KEY=your_secret_key_here
FLASK_ENV=development
FLASK_DEBUG=True

# Redis / Voice Slot Queue
REDIS_URL=redis://localhost:6379/0

# Voice Slot Management
ELEVENLABS_SLOT_LIMIT=30
VOICE_WARM_HOLD_SECONDS=900
VOICE_QUEUE_POLL_INTERVAL=60

# Credits Configuration
CREDITS_UNIT_LABEL="Story Points (Punkty Magii)"
CREDITS_UNIT_SIZE=1000
INITIAL_CREDITS=10
# Optional: override consumption order if needed
CREDIT_SOURCES_PRIORITY=event,monthly,referral,add_on,free

### 5. Credits & Billing

- How it works: see `docs/CREDITS.md`.
- Estimating cost: Story payloads now include a `required_credits` field; you can still call `GET /stories/{id}/credits` → `{ required_credits }` when you need to revalidate.
- Checking balance: `GET /me/credits` (Bearer) → `{ balance, lots, recent_transactions }`.
- Insufficient funds: endpoints may return `402 Payment Required`.
- Admin grants: `POST /admin/users/{user_id}/credits/grant` with `{ amount, reason?, source?, expires_at? }`.

# Celery Configuration
REDIS_URL=redis://localhost:6379/0

# Voice Service Configuration
PREFERRED_VOICE_SERVICE=cartesia  # or "elevenlabs"
```

# Voice Slot Allocation Workflow
- Voice recordings are stored encrypted in S3 immediately after upload; remote ElevenLabs voices are allocated just-in-time during the first synthesis request.
- `POST /voices/{voice_id}/stories/{story_id}/audio` may return `queued_for_slot`, `allocating_voice`, `processing`, or `ready`. Queue metadata is exposed in the payload (`voice.queue_position`, `voice.queue_length`) and mirrored in `X-Voice-Queue-*` response headers for inline UI hints.
- Celery workers poll allocation progress; once a slot is ready, they synthesise audio, update `Voice.last_used_at`, and release the lock after the warm-hold window.
- Admins can inspect `/admin/voice-slots/status` or trigger `/admin/voice-slots/process-queue` to nudge background processing.
- Full lifecycle details, fairness policy, and troubleshooting guidance live in [`docs/ElasticVoiceSlots.md`](docs/ElasticVoiceSlots.md).

# UX Messaging Guidance
- **Queued for slot**: “Twoja prośba jest w kolejce. Przydzielimy slot głosowy w ciągu kilku chwil.”
- **Allocating voice**: “Twój głos jest aktywowany w ElevenLabs… odtwarzanie rozpocznie się automatycznie.”
- **Processing**: “Generujemy opowieść w Twoim głosie. To zwykle trwa ok. 30–90 sekund.”
- **Ready**: “Nagranie jest gotowe – możesz teraz odtworzyć historię.”
- For retries or timeouts, show a CTA that re-issues the POST request; credits są już zarezerwowane, więc użytkownik nie zapłaci podwójnie.

### 3. Database Setup

Initialize the database:
```bash
flask db upgrade
```

### 4. Running the Application

#### Development Mode

**Terminal 1 - Flask Application:**
```bash
flask run --host=0.0.0.0 --port=8000
```

**Terminal 2 - Celery Worker:**
```bash
celery -A celery_worker.celery_app worker --loglevel=info
```

**Terminal 3 - Redis Server:**
```bash
redis-server
```

The application will be available at http://localhost:8000

#### Production Mode

```bash
# Start the web server
gunicorn app:app --bind 0.0.0.0:$PORT

# Start Celery worker (in separate process/container)
celery -A celery_worker.celery_app worker --loglevel=info
```

## 📂 Project Structure

```
dawnotemu/server/
├── app.py                          # Main Flask application
├── celery_worker.py               # Celery configuration and tasks
├── config.py                      # Application configuration
├── database.py                    # Database initialization
├── admin.py                       # Flask-Admin configuration
├── requirements.txt               # Python dependencies
├── runtime.txt                    # Python version for Heroku
├── Procfile                       # Heroku deployment configuration
├── pytest.ini                     # Test configuration
├── migrations/                    # Database migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/                  # Migration files
├── models/                        # SQLAlchemy models
│   ├── __init__.py
│   ├── user_model.py              # User authentication
│   ├── voice_model.py             # Voice profiles
│   ├── story_model.py             # Story content
│   └── audio_model.py             # Audio files
├── controllers/                   # Business logic
│   ├── __init__.py
│   ├── auth_controller.py         # Authentication logic
│   ├── voice_controller.py        # Voice management
│   ├── story_controller.py        # Story management
│   └── audio_controller.py        # Audio processing
├── routes/                        # API endpoints
│   ├── __init__.py
│   ├── auth_routes.py             # Authentication endpoints
│   ├── voice_routes.py            # Voice management endpoints
│   ├── story_routes.py            # Story endpoints
│   ├── audio_routes.py            # Audio processing endpoints
│   ├── static_routes.py           # Static file serving
│   └── task_routes.py             # Task status endpoints
├── utils/                         # Utility modules
│   ├── __init__.py
│   ├── auth_middleware.py         # JWT authentication
│   ├── email_service.py           # Email functionality
│   ├── email_template_helper.py   # Email template utilities
│   ├── cartesia_service.py        # Cartesia API integration
│   ├── cartesia_sdk_service.py    # Cartesia SDK integration
│   ├── elevenlabs_service.py      # ElevenLabs API integration
│   ├── voice_service.py           # Voice service abstraction
│   ├── s3_client.py               # AWS S3 client
│   ├── audio_splitter.py          # Audio processing
│   └── helpers.py                 # General utilities
├── tasks/                         # Celery tasks
│   ├── __init__.py
│   ├── voice_tasks.py             # Voice processing tasks
│   └── audio_tasks.py             # Audio synthesis tasks
├── templates/                     # Email templates
│   ├── admin/                     # Admin interface templates
│   └── email/                     # Email templates
│       └── base_template.html     # Base email template
├── static/                        # Static assets
│   └── icons/                     # Application icons
├── stories/                       # Story content
├── uploads/                       # Temporary file uploads
├── tests/                         # Test suite
│   ├── conftest.py               # Test configuration
│   ├── fixtures/                 # Test fixtures
│   ├── test_models/              # Model tests
│   ├── test_controllers/         # Controller tests
│   ├── test_routes/              # Route tests
│   └── test_*.py                 # Various test files
└── docs/                         # Documentation
    ├── openapi.yaml              # API documentation
    ├── EMAIL_SETUP.md            # Email system documentation
    ├── README_cartesia.md        # Cartesia integration guide
    └── api.doc.md                # API documentation guide
```

## 🔄 How It Works

### Voice Cloning Process
1. **Recording**: User records 1-minute voice sample via web interface
2. **Upload**: Audio file uploaded to AWS S3 for distributed processing
3. **Processing**: Celery task downloads from S3 and processes voice cloning via Cartesia/ElevenLabs
4. **Storage**: Voice profile stored in database with status tracking

### Story Synthesis Process
1. **Selection**: User chooses story from Polish fairy tale library
2. **Queue**: Synthesis request queued via Celery
3. **Generation**: AI generates audio using cloned voice
4. **Storage**: Generated audio stored in S3
5. **Delivery**: Audio streamed to user with full player controls

### Email System
1. **Templates**: Modular email templates with DawnoTemu branding
2. **Delivery**: Resend API for reliable email delivery
3. **Types**: Account confirmation, password reset, notifications

## 🌐 API Documentation

### Authentication Endpoints
- `POST /auth/register` - User registration with email confirmation
- `POST /auth/login` - User authentication with JWT tokens
- `POST /auth/refresh` - Refresh access token
- `GET /auth/confirm-email/<token>` - Email confirmation
- `POST /auth/resend-confirmation` - Resend confirmation email
- `POST /auth/reset-password-request` - Request password reset
- `POST /auth/reset-password/<token>` - Reset password

### Voice Management
- `POST /voices/clone` - Upload voice sample and start cloning
- `GET /voices` - List user's voice profiles
- `GET /voices/<voice_id>` - Get voice profile details
- `DELETE /voices/<voice_id>` - Delete voice profile

### Story Management
- `GET /stories` - List available stories
- `GET /stories/<story_id>` - Get story content
- `POST /stories/<story_id>/synthesize` - Generate audio for story

### Audio Endpoints
- `GET /audio/<voice_id>/<story_id>` - Stream generated audio
- `GET /audio/exists/<voice_id>/<story_id>` - Check audio availability

### Task Management
- `GET /tasks/<task_id>/status` - Check background task status

### Admin Endpoints (Beta Management)
- `GET /admin/users` - List all users (admin only)
- `GET /admin/users/pending` - List pending (inactive) users
- `GET /admin/users/<user_id>` - Get user details
- `POST /admin/users/<user_id>/activate` - Activate user account
- `POST /admin/users/<user_id>/deactivate` - Deactivate user account

## 🧪 Beta Management System

DawnoTemu is currently in beta phase with controlled user access:

### User Registration Flow
1. **Registration**: Users register with email and password
2. **Email Confirmation**: Users must confirm their email address
3. **Beta Approval**: Account remains inactive until admin approval
4. **Activation**: Admin manually activates approved users
5. **Access**: Only activated users can log in and use the platform

### Admin Management
- **Pending Users**: View all users waiting for beta approval
- **User Activation**: Manually activate approved users
- **User Deactivation**: Deactivate users if needed
- **User Management**: Full user list and details

### Beta Features
- All new users are inactive by default
- Email confirmation required before activation
- Admin-controlled access during beta phase
- Secure API endpoints for user management

## 🚀 Deployment

### Heroku Deployment

1. **Create Heroku App:**
```bash
heroku create dawnotemu-app
```

2. **Add Required Add-ons:**
```bash
heroku addons:create heroku-postgresql:mini
heroku addons:create heroku-redis:mini
```

3. **Set Environment Variables:**
```bash
heroku config:set CARTESIA_API_KEY=your_cartesia_api_key
heroku config:set ELEVENLABS_API_KEY=your_elevenlabs_api_key
heroku config:set RESEND_API_KEY=your_resend_api_key
heroku config:set AWS_ACCESS_KEY_ID=your_aws_access_key
heroku config:set AWS_SECRET_ACCESS_KEY=your_aws_secret_key
heroku config:set AWS_REGION=eu-west-1
heroku config:set S3_BUCKET_NAME=your_s3_bucket_name
heroku config:set RESEND_FROM_EMAIL=no-reply@dawnotemu.app
heroku config:set FRONTEND_URL=https://dawnotemu.app
heroku config:set SECRET_KEY=your_production_secret_key
heroku config:set PREFERRED_VOICE_SERVICE=cartesia
heroku config:set SENTRY_DSN=your_sentry_dsn
```

4. **Deploy:**
```bash
git push heroku main
```

5. **Run Database Migrations:**
```bash
heroku run flask db upgrade
```

### Production Considerations

- **Scaling**: Use Heroku's dyno scaling for web and worker processes
- **Monitoring**: Implement application monitoring (e.g., Sentry)
- **Logging**: Centralized logging with structured logs
- **Security**: Environment-based configuration, secure API keys
- **Performance**: Redis caching, S3 CDN, database optimization

## 🧪 Testing

Run the test suite:
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_voice_controller.py

# Run with verbose output
pytest -v
```

Test categories:
- **Unit Tests**: Models, controllers, utilities
- **Integration Tests**: API endpoints, database operations
- **Service Tests**: External API integrations
- **Email Tests**: Template rendering and delivery

## 🔧 Development Tools

### Email Testing
```bash
python tests/test_resend_email.py
```

### Voice Quality Testing
```bash
python tests/test_voice_quality_comparison.py
```

### API Testing
```bash
python tests/test_endpoints.py
```

### Beta System Testing
```bash
python tests/test_beta_system.py
```

## 📧 Email System

DawnoTemu uses a modular email system with:

- **Resend API**: Reliable email delivery
- **Template System**: Reusable HTML templates with DawnoTemu branding
- **Email Types**: 
  - Account confirmation
  - Password reset
  - System notifications

Email templates are located in `templates/email/` with helper utilities in `utils/email_template_helper.py`.

## 🔒 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Email Verification**: Required email confirmation for new accounts
- **Password Security**: Bcrypt hashing with salt
- **API Rate Limiting**: Protection against abuse
- **Environment Variables**: Secure configuration management
- **CORS Configuration**: Proper cross-origin resource sharing
- **Input Validation**: Comprehensive request validation

## 🌍 Internationalization

- **Polish Language**: Primary language for stories and interface
- **Unicode Support**: Full UTF-8 support for Polish characters
- **Localized Content**: Polish fairy tales and cultural content

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the existing code style and architecture
4. Add tests for new functionality
5. Update documentation as needed
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write comprehensive tests
- Use type hints where appropriate
- Document new functions and classes
- Keep commits atomic and well-described

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Cartesia AI** - Primary voice synthesis technology
- **ElevenLabs** - Voice cloning capabilities
- **Resend** - Email delivery infrastructure
- **Flask Community** - Excellent web framework
- **Polish Folklore** - Inspiration for story content

## 💭 Mission

DawnoTemu exists to strengthen family bonds through technology. We believe that a parent's voice telling bedtime stories creates lasting memories and emotional connections that transcend physical distance.

Perfect for:
- **Working Parents**: Share stories even during business trips
- **Military Families**: Stay connected across deployments  
- **Grandparents**: Create lasting voice memories for grandchildren
- **Divorced Parents**: Maintain bedtime story traditions
- **Anyone**: Who wants to preserve their voice for future generations

---

*"Twój głos opowiada baśnie, zawsze gdy potrzebujesz"*

**DawnoTemu Sp. z o.o.**  
ul. Żywiczna 38A, 03-179 Warszawa  
zespol.dawnotemu@gmail.com
