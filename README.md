# StoryVoice: AI Voice-Cloned Bedtime Stories 🎙️✨

**Turn bedtime stories into personalized audio adventures using voice cloning technology**

StoryVoice is a web application that allows users to record a short audio sample of their voice and then uses AI to read children's stories in that voice. Perfect for parents who want to create personalized bedtime stories for their children, even when they can't be physically present.

[![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0.2-lightgrey?logo=flask)](https://flask.palletsprojects.com/)
[![ElevenLabs](https://img.shields.io/badge/Powered%20by-ElevenLabs-orange)](https://elevenlabs.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Heroku](https://img.shields.io/badge/Deployed%20on-Heroku-79589F?logo=heroku)](https://www.heroku.com)

![StoryVoice Demo](demo-screenshot.png)

## 🌟 Features

- **Voice Cloning**: Record or upload a 30-second audio sample to create your unique voice profile
- **AI-Powered Narration**: Generate natural-sounding story narration using ElevenLabs' voice synthesis API
- **Curated Story Library**: Classic tales and modern stories suitable for children
- **Interactive Audio Player**: Full playback controls with seek/scrub functionality
- **User-Friendly Interface**: Clean, intuitive design that works across devices
- **Progressive Web App (PWA)**: Install as a standalone app on mobile devices
- **Secure Storage**: Audio files stored in AWS S3 for reliability and scalability

## 🛠️ Technology Stack

### Backend
- **Python 3.10** - Core programming language
- **Flask 3.0.2** - Web framework
- **ElevenLabs API** - Text-to-speech with voice cloning capabilities
- **AWS S3** - Cloud storage for audio files

### Frontend
- **HTML5/CSS3** - Markup and styling
- **Tailwind CSS** - Utility-first CSS framework
- **Vanilla JavaScript** - Client-side interactivity
- **Progressive Web App (PWA)** - Mobile-friendly installable experience

### DevOps
- **Heroku** - Cloud hosting platform
- **Gunicorn** - WSGI HTTP Server
- **Environment Variables** - Configuration management

## 📋 Prerequisites

- Python 3.10 or higher
- ElevenLabs API key (get one at [elevenlabs.io](https://elevenlabs.io))
- AWS account with S3 bucket set up
- AWS credentials with S3 access permissions

## 🚀 Getting Started

### Environment Setup

1. Clone the repository
```bash
git clone https://github.com/yourusername/storyvoice.git
cd storyvoice
```

2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with the following variables:
```
ELEVENLABS_API_KEY=your_eleven_labs_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=your_aws_region
S3_BUCKET_NAME=your_s3_bucket_name
```

### Running Locally

Start the Flask development server:
```bash
python app.py
```

The application will be available at http://localhost:8000

### Deployment to Heroku

1. Create a new Heroku app
```bash
heroku create your-storyvoice-app
```

2. Add environment variables to Heroku
```bash
heroku config:set ELEVENLABS_API_KEY=your_eleven_labs_api_key
heroku config:set AWS_ACCESS_KEY_ID=your_aws_access_key
heroku config:set AWS_SECRET_ACCESS_KEY=your_aws_secret_key
heroku config:set AWS_REGION=your_aws_region
heroku config:set S3_BUCKET_NAME=your_s3_bucket_name
```

3. Deploy to Heroku
```bash
git push heroku main
```

## 📂 Project Structure

```
storyvoice/
├── app.py                 # Main Flask application
├── static/                # Frontend assets
│   ├── app.html           # Main application HTML
│   ├── scripts.js         # Client-side JavaScript
│   ├── styles.css         # Custom CSS styles
│   ├── sw.js              # Service Worker for PWA
│   └── manifest.json      # PWA manifest
├── stories/               # Story content in JSON format
│   ├── 1.json             # Hansel and Gretel
│   ├── 2.json             # Three Little Pigs
│   └── ...                # Other stories
├── Procfile               # Heroku deployment configuration
├── requirements.txt       # Python dependencies
├── runtime.txt            # Python version specification
└── README.md              # Project documentation
```

## 🔄 How It Works

1. **Voice Recording**: Users provide a voice sample through microphone recording or audio upload
2. **Voice Cloning**: The sample is sent to ElevenLabs API which creates a digital voice model
3. **Story Selection**: Users choose from available stories in the library
4. **Text-to-Speech**: The application sends the story text to ElevenLabs to generate audio with the cloned voice
5. **Storage**: Generated audio files are stored in AWS S3 for efficient delivery
6. **Playback**: Users can listen to stories with full audio player controls

## 🌐 API Endpoints

- `POST /api/clone` - Upload a voice sample and create a voice clone
- `DELETE /api/voices/<voice_id>` - Delete a voice profile
- `GET /api/stories` - List available stories
- `GET /api/stories/<story_id>` - Get a specific story's content
- `GET /api/audio/<voice_id>/<story_id>.mp3` - Stream generated audio
- `GET /api/audio/exists/<voice_id>/<story_id>` - Check if audio has been generated
- `POST /api/synthesize` - Generate audio for a story with a cloned voice

## 📱 PWA Support

StoryVoice can be installed as a Progressive Web App on mobile devices and desktop browsers:

1. Open the application in a browser
2. For mobile, tap "Add to Home Screen" in the browser menu
3. For desktop, look for the "Install" option in the address bar

## 🔒 Privacy & Data Storage

- Voice samples are processed securely via ElevenLabs API
- Generated audio files are stored in a private AWS S3 bucket
- No user data is shared with third parties beyond what's needed for core functionality

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 💭 Inspiration

Created for parents who want to:
- Preserve their voice for future generations
- Share stories even when physically apart
- Create lasting memories through technology

---

*"Because every child deserves to hear stories in the voice they love most."*