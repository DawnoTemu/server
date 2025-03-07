# StoryVoice: Magical Voice-Cloned Bedtime Stories 🎙️✨

**Transform bedtime stories into personalized audio adventures using AI voice cloning**  
*A web application that reads children's stories in your voice – perfect for parents, guardians, or anyone who wants to create magical moments.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Heroku](https://img.shields.io/badge/Deployed-Heroku-79589F?logo=heroku)](https://your-app-name.herokuapp.com)

![StoryVoice Demo](demo-screenshot.png)

## 🌟 Features
- **Voice Cloning Magic**: Record or upload 30s of audio to create a unique voiceprint
- **AI-Powered Storytelling**: Generates natural-sounding narration using ElevenLabs' API
- **Curated Story Library**: Classic tales and modern stories with child-friendly content
- **Responsive Audio Controls**: Beautiful player with seek/scrub functionality
- **Parent-Friendly UI**: Clean interface with quick recording/playback
- **Cross-Device Support**: Works perfectly on mobile, tablet, and desktop

## 🛠️ Tech Stack
**Frontend**  
📖 HTML5 · 🎨 Tailwind CSS · 📜 Vanilla JavaScript  

**Backend**  
🐍 Python · 🧪 Flask · 🌐 ElevenLabs API  

**Infrastructure**  
☁️ Heroku · 🔒 Environment Config · 📦 Git  

## 🚀 Quick Start

1. Clone repository
```bash
git clone https://github.com/yourusername/storyvoice.git
```

2. Configure environment
```bash
cp .env.example .env
# Add your ElevenLabs API key to .env
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Run locally
```bash
python api.py
```
Visit `http://localhost:8000` in your browser

## 📂 Project Structure
```
storyvoice/
├── static/
│   ├── index.html
│   └── scripts.js
├── stories/
│   ├── index.json
│   └── (story files)
├── api.py
├── Procfile
├── requirements.txt
├── runtime.txt
└── README.md
```

## 💡 Inspiration
Created for parents who want to:
- Preserve their voice for future generations 🕰️
- Share stories even when physically apart 🌍  
- Create lasting memories through technology 💖  


---

💬 *"Because every child deserves to hear stories in the voice they love most."*  

---
