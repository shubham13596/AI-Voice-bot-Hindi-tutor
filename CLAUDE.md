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
- `GROQ_API_KEY` - Groq API key for Llama 3.1 8B conversation logic
- `OPENAI_API_KEY` - OpenAI GPT-4 API key (fallback, optional)
- `SARVAM_API_KEY` - Sarvam AI API for Hindi speech-to-text
- `GOOGLE_CLOUD_API_KEY` - Google Cloud Speech-to-Text API (optional, for google STT provider)
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
- **ResponseEvaluator**: Evaluates user responses for grammar, completeness, and contextual appropriateness using both user response and last talker response
- **TalkerModule**: Generates AI responses based on conversation type
- **CONVERSATION_TYPES**: Configuration dict defining different conversation modes (everyday, cartoons, adventure_story, mystery_story)

#### Speech Processing Pipeline
1. **Audio Input**: User records voice via browser MediaRecorder API
2. **STT**: Sarvam AI API converts Hindi speech to text
3. **LLM Processing**: Groq Llama 3.1 8B processes conversation (parallel evaluation + response generation)
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
- **conversation_type** field to track different conversation modes
- Support for conversation resumption with proper session data handling

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

#### Conversation History APIs
- `GET /api/conversation-history` - Fetch user's conversations from last 15 days
- `POST /api/resume_conversation` - Resume existing conversation by ID

### Frontend Architecture
- Mobile-first responsive design
- Vanilla JavaScript with audio recording capabilities
- Real-time audio visualization during recording
- Progress tracking with gamification (points, milestones, Captain America rewards)
- Multiple conversation types with different themes and prompts
- **Conversation History Sidebar**: Collapsible sidebar on conversation-select page showing last 15 days of conversations
- **Mobile Navigation System**: Reusable bottom navigation and profile avatar components

## Important Implementation Details

### Conversation History & Resume Functionality
The app includes a comprehensive conversation history system that allows users to view and resume previous conversations:

#### Key Features
- **Collapsible Sidebar**: Located on the conversation-select page with smooth animations
- **15-Day History**: Shows conversations from the last 15 days, sorted by most recent
- **Resume Capability**: Users can click on any previous conversation to resume exactly where they left off
- **Mobile-Responsive**: Optimized for mobile devices with touch-friendly interactions

#### Technical Implementation
- **Backend**: `/api/conversation-history` endpoint fetches conversations with proper authentication
- **Frontend**: JavaScript handles sidebar toggle, API calls, and conversation resumption
- **Session Management**: Proper session data structure preservation during resume operations
- **Database Integration**: conversation_type field tracks different conversation modes

#### Key Files
- `templates/conversation_select.html`: Sidebar HTML structure and JavaScript logic
- `static/js/mobile-navigation.js`: Mobile navigation components with content preservation
- `app.py`: API endpoints for history fetching and conversation resumption
- `models.py`: Enhanced Conversation model with conversation_type support

### Mobile Navigation System
Reusable navigation components for consistent mobile experience:

#### Components
- **MobileNavigation**: Bottom navigation with home and activity tabs
- **ProfileAvatar**: Animated profile dropdown with user information
- **MobilePageUtils**: Utility functions for page management and transitions

#### Features
- **Content Preservation**: Navigation components preserve existing page content
- **Responsive Design**: Optimized for mobile-first approach
- **User Avatars**: Fun animal avatars with cycling functionality
- **Smooth Transitions**: Page transition effects for better UX

### Conversation Types
Each conversation type has specific system prompts and focuses:
- **everyday**: Daily life conversations (school, family, activities)
- **cartoons**: Discussions about animated characters and shows
- **adventure_story**: Co-creating adventure narratives
- **mystery_story**: Solving child-friendly mysteries together

### Performance Optimizations
- Parallel API calls to Groq Llama 3.1 8B for evaluation and response generation (44% faster)
- Groq's fast inference for reduced LLM processing latency
- ElevenLabs streaming audio for reduced latency
- Redis session caching in production
- Optimized voice settings for child-friendly speech patterns

### Error Handling & Fallbacks
- Graceful degradation when external APIs fail
- File storage fallback when Redis unavailable
- Retry logic with exponential backoff for API calls
- Comprehensive logging for debugging
- **Authentication Handling**: Proper session credential handling for API calls
- **Field Name Consistency**: Resolved session data structure inconsistencies

### Security Considerations
- Google OAuth for secure authentication
- Environment variable protection for API keys
- Session security with Flask-Login
- File cleanup for temporary audio files

## Development Workflow

### Git Branching Strategy
**IMPORTANT**: Always create a new branch for any feature changes, functionality changes, or bug fixes:

```bash
# For new features
git checkout -b feature/feature-name

# For bug fixes  
git checkout -b fix/bug-description

# For enhancements to existing features
git checkout -b enhancement/improvement-description

# Examples:
git checkout -b feature/evaluator-context-enhancement
git checkout -b fix/session-timeout-issue
git checkout -b enhancement/mobile-navigation-improvements
```

**Branch Naming Convention**:
- `feature/` - New functionality or major additions
- `fix/` - Bug fixes and issue resolutions  
- `enhancement/` - Improvements to existing features
- `refactor/` - Code restructuring without functional changes
- `docs/` - Documentation updates

### Development Steps
1. **Create Branch**: Always start with a new branch for your changes
2. Set up environment variables in `.env` file
3. Install Python dependencies via `requirements.txt`
4. Run `python app.py` for local development
5. Application runs on port 5001 by default (configurable via PORT env var)
6. Database auto-initializes on first run
7. Use browser developer tools for debugging frontend audio issues
8. **Commit Changes**: Make frequent commits with descriptive messages
9. **Test Thoroughly**: Ensure all changes work as expected
10. **Create Pull Request**: When ready, merge back to main branch

## Deployment
- Configured for Heroku deployment via `Procfile`
- Uses Gunicorn WSGI server in production
- PostgreSQL database in production (SQLite for development)
- Redis session storage in production (file storage fallback)
- Python 3.11.9 runtime (specified in `runtime.txt`)

## Recent Updates & Bug Fixes

### v26 (Latest) - Groq Llama 3.1 8B Migration for Reduced Latency
- **Major Performance Improvement**: Migrated from OpenAI GPT-4o-mini to Groq Llama 3.1 8B for significantly reduced LLM processing latency
- **API Migration**: Complete replacement of all OpenAI API calls with Groq API calls
- **Maintained Functionality**: All conversation features (ResponseEvaluator, TalkerModule, initial conversation, translation) preserved
- **Enhanced Speed**: Leverages Groq's fast inference for better user experience
- **Environment Updates**: Added GROQ_API_KEY to required environment variables, kept OpenAI as optional fallback

### v25 - Enhanced Response Evaluator with Context Awareness
- **Major Enhancement**: ResponseEvaluator now uses both user response and last talker response for better contextual evaluation
- **Improved Corrections**: Evaluator provides more accurate corrected responses that properly answer questions in context
- **Example**: For tutor question "kya tum aaj school gaye?" and child response "nahi", evaluator now generates "aaj mein school nahi gaya" instead of just correcting grammar
- **Enhanced Completeness**: Better detection of incomplete responses based on conversational context
- **Git Workflow**: Added comprehensive branching guidelines to CLAUDE.md for all future development

### v24 - Conversation History Feature
- **Major Feature**: Added conversation history sidebar with resume functionality
- **Database Enhancement**: Added conversation_type field to Conversation model
- **Mobile Navigation**: Improved mobile navigation with content preservation
- **Authentication**: Fixed session credential handling for API calls
- **Session Management**: Resolved field name consistency issues (sentences_count vs sentence_count)
- **User Experience**: Enhanced dashboard UI with better navigation

### Key Technical Improvements
- **API Authentication**: All conversation history API calls include proper session credentials
- **Database Schema**: Conversation model now includes conversation_type tracking
- **Session Resume**: Proper handling of resumed conversations with complete session data
- **Mobile Responsiveness**: Enhanced mobile design with collapsible sidebar
- **Error Handling**: Improved error handling for conversation resumption scenarios

### Security & Maintenance
- **Environment Variables**: Added comprehensive .gitignore to protect sensitive data
- **Professional Footer**: Added informational pages and company footer
- **Dashboard Logic**: Improved weekly comparison logic and back button functionality

## STT Provider Testing & Evaluation

### Google Cloud Speech-to-Text Evaluation (September 2025)
- **Branch**: `enhancement/google-cloud-stt-integration`
- **Objective**: Test Google Cloud Speech-to-Text API as alternative to Sarvam AI for reduced ASR latency
- **Implementation**: Complete integration with Hindi language support (`hi-IN`)
- **Configuration**: Used `latest_short` model with enhanced mode for optimal performance
- **Result**: **REJECTED** - Latency remained high, no significant improvement over Sarvam AI
- **Technical Details**:
  - Added google-cloud-speech==2.21.0 dependency
  - Implemented feature flag (`STT_PROVIDER=google/sarvam`) for easy switching
  - Full integration with existing audio processing pipeline
  - Comprehensive error handling and logging
- **Conclusion**: Google Cloud STT does not solve the ASR latency bottleneck for real-time conversation
- **Status**: **REMOVED** - Google Cloud Speech dependency and code removed to reduce app size (~8MB savings)

### App Size Optimization (January 2025)
- **Objective**: Reduce Heroku app size from 52MB for faster deployments and reduced slug size
- **Actions Taken**:
  - Removed `google-cloud-speech==2.21.0` dependency (~8MB with grpcio dependencies)
  - Removed all related Google Cloud Speech STT code from app.py
  - Updated STT_PROVIDER options to support only `sarvam` and `groq`
- **Result**: Significant reduction in app size and dependency complexity

### Google Cloud Speech-to-Text Integration v2 (January 2025)
- **Branch**: `enhancement/google-cloud-stt-optimized`
- **Objective**: Re-implement Google Cloud Speech-to-Text with performance optimizations to address previous latency concerns
- **Key Optimizations**:
  - **Silence Trimming**: Removes dead air while preserving all speech content (10-40% size reduction)
  - **Connection Pooling**: Pre-established HTTP sessions for reduced latency
  - **Audio Format Optimization**: Optimal 16kHz WEBM_OPUS settings for Google Cloud
  - **Hindi Child Speech**: Specialized configuration with speech contexts for young learners
  - **Dual Authentication**: Supports both API key and service account methods
- **Performance Features**:
  - **Performance Logging**: Same detailed timing format as existing providers for A/B comparison
  - **Feature Flag**: `STT_PROVIDER=google` to enable (safe fallback to sarvam/groq)
  - **Error Handling**: Graceful degradation with comprehensive logging
- **Environment Setup**: Requires `GOOGLE_CLOUD_API_KEY` environment variable
- **Expected Benefits**: Reduced latency through optimizations, better Hindi accuracy with enhanced models