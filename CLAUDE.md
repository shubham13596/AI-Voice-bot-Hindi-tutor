# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered Hindi language tutor Flask web application designed for children (ages 4-8) learning Hindi. The app provides conversational learning experiences through voice interactions, with features like speech-to-text, text-to-speech, progress tracking, and gamification elements.

## Development Commands

### Running the Application
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally for development
python app.py

# Run with Gunicorn (production-like)
gunicorn app:app

# Deploy to Heroku (configured via Procfile)
git push heroku main
```

### Database Operations
```bash
# The app auto-initializes SQLite database on startup
# Database file: hindi_tutor.db (SQLite for development)
# Tables are created automatically via models.py
```

### Environment Setup
Required environment variables in `.env`:
- `OPENAI_API_KEY` - OpenAI GPT-4 API key for conversation logic
- `SARVAM_API_KEY` - Sarvam AI API for Hindi speech-to-text
- `ELEVENLABS_API_KEY` - ElevenLabs API for text-to-speech
- `GOOGLE_CLIENT_ID` - Google OAuth authentication
- `GOOGLE_CLIENT_SECRET` - Google OAuth authentication
- `SECRET_KEY` - Flask session security
- `DATABASE_URL` - Database connection (PostgreSQL for production, SQLite for dev)
- `REDIS_URL` - Redis session storage (optional, falls back to file storage)

## Architecture Overview

### Core Application Structure
- **app.py**: Main Flask application with all routes and conversation logic
- **models.py**: SQLAlchemy database models (User, Conversation, Analytics)
- **auth.py**: Google OAuth authentication blueprint
- **templates/**: HTML templates for web interface
- **static/**: CSS, JavaScript, images, and audio assets

### Key Components

#### Conversation System
The conversation flow is managed by several classes in `app.py`:
- **ConversationController**: Main orchestrator for conversation flow
- **ResponseEvaluator**: Evaluates user responses for grammar and completeness
- **TalkerModule**: Generates AI responses based on conversation type
- **CONVERSATION_TYPES**: Configuration dict defining different conversation modes (everyday, cartoons, adventure_story, mystery_story)

#### Speech Processing Pipeline
1. **Audio Input**: User records voice via browser MediaRecorder API
2. **STT**: Sarvam AI API converts Hindi speech to text
3. **LLM Processing**: OpenAI GPT-4 processes conversation (parallel evaluation + response generation)
4. **TTS**: ElevenLabs converts Hindi response to speech
5. **Audio Output**: Browser plays generated audio response

#### Session Management
- **FileSessionStore**: File-based session storage for development
- **RedisSessionStore**: Redis-based session storage for production
- Sessions track conversation history, response quality metrics, and reward points

#### Authentication Flow
- Google OAuth integration for user authentication
- User profile setup (child name) required before conversations
- Flask-Login manages user sessions

### Database Schema

#### User Model
- Basic profile information (email, name, child_name)
- Google OAuth integration
- One-to-many relationship with conversations

#### Conversation Model
- Session tracking with metrics (sentences_count, good_response_count, reward_points)
- JSON storage for conversation_history and amber_responses (corrections needed)
- Analytics helpers for weekly stats and comparisons

### API Endpoints

#### Core Conversation APIs
- `POST /api/start_conversation` - Initialize new conversation session
- `POST /api/process_audio` - Main audio processing pipeline
- `POST /api/correction_stt` - STT-only for correction attempts
- `POST /api/clear_amber_responses` - Clear correction popup data

#### Utility APIs
- `POST /api/speak` - Text-to-speech only
- `POST /api/translate` - Hindi to English translation
- `GET /api/dashboard` - User analytics and progress
- `GET /api/user` - Current user information

### Frontend Architecture
- Mobile-first responsive design
- Vanilla JavaScript with audio recording capabilities
- Real-time audio visualization during recording
- Progress tracking with gamification (points, milestones, Captain America rewards)
- Multiple conversation types with different themes and prompts

## Important Implementation Details

### Conversation Types
Each conversation type has specific system prompts and focuses:
- **everyday**: Daily life conversations (school, family, activities)
- **cartoons**: Discussions about animated characters and shows
- **adventure_story**: Co-creating adventure narratives
- **mystery_story**: Solving child-friendly mysteries together

### Performance Optimizations
- Parallel API calls to OpenAI for evaluation and response generation (44% faster)
- ElevenLabs streaming audio for reduced latency
- Redis session caching in production
- Optimized voice settings for child-friendly speech patterns

### Error Handling & Fallbacks
- Graceful degradation when external APIs fail
- File storage fallback when Redis unavailable
- Retry logic with exponential backoff for API calls
- Comprehensive logging for debugging

### Security Considerations
- Google OAuth for secure authentication
- Environment variable protection for API keys
- Session security with Flask-Login
- File cleanup for temporary audio files

## Development Workflow
1. Set up environment variables in `.env` file
2. Install Python dependencies via `requirements.txt`
3. Run `python app.py` for local development
4. Application runs on port 5001 by default (configurable via PORT env var)
5. Database auto-initializes on first run
6. Use browser developer tools for debugging frontend audio issues

## Deployment
- Configured for Heroku deployment via `Procfile`
- Uses Gunicorn WSGI server in production
- PostgreSQL database in production (SQLite for development)
- Redis session storage in production (file storage fallback)
- Python 3.11.9 runtime (specified in `runtime.txt`)