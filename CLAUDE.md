# CLAUDE.md

AI-powered Hindi tutor for children (ages 4-8). Voice conversations with "Kiki" character. Flask + vanilla JS.

## Commands
```bash
python app.py                    # Local dev (port 5001)
git push heroku main             # Deploy to Heroku
```

## Git Workflow
Always use feature branches + worktrees for new work:
```bash
git worktree add ../worktrees/<name> -b feature/<name>   # Create
# work, commit, test in the worktree...
git merge feature/<name>                                  # From main repo
git worktree remove ../worktrees/<name>                   # Cleanup
git branch -d feature/<name>
```
Keep commits small and focused — one feature or fix per commit.

## Architecture
- **Backend**: `app.py` (Flask, Gemini API, ElevenLabs TTS, Google Cloud STT), `s3_audio.py` (AWS S3 uploads)
- **Frontend**: `templates/conversation.html` + `static/js/process_audio.js` + `static/js/mobile-navigation.js`
- **Auth**: `auth.py` (Google OAuth), `models.py` (User, Conversation, analytics models)
- **Config**: `conversation_config.py` (Kiki personality/response styles), `sticker_config.py` (reward stickers)
- **State machine**: `appState` in `process_audio.js` — `IDLE | KIKI_SPEAKING | LISTENING | PROCESSING`
- **STT**: Google Cloud Speech — Chirp 3 V2 (primary) with V1 fallback
- **Conversations**: `MAX_CONVERSATION_TURNS = 6`, tracked via `sentences_count` in session

## Key Files
- `process_audio.js`: recording, streaming SSE responses, TTS playback, waveform viz, correction popup, transliteration engine
- `conversation.html`: header, conversation bubbles, hints, waveform + Kiki avatar, progress bar, record button
- `app.py`: Flask routes, `ResponseEvaluator` (Gemini grammar eval), `TalkerModule`, `FileSessionStore`/`RedisSessionStore`
- `s3_audio.py`: Background ThreadPoolExecutor S3 uploads. Behind `ENABLE_AUDIO_STORAGE` feature flag
- `conversation_config.py`: Kiki personality — varied response styles, anti-robotic-opener patterns

## Key Patterns
- `transitionTo(state)` is the single source of truth for all UI state changes
- `generateAndPlayAudio()` awaits TTS + playback, then calls `scheduleAutoStartRecording()`
- SSE streaming: backend yields `data:` events (transcript → evaluation → text chunks → complete), frontend processes in `processAudioStreaming()`
- Recording flow: mic auto-opens after Kiki speaks, child taps "Send Reply" to send
- `initializeRecording()` does NOT request mic — `showStartOverlay()` button click → `getUserMedia()` → `startConversation()`

## Gotchas
- iOS requires user gesture for audio — `warmUpAudioElement()` must be called from click handler
- iOS MediaRecorder must be created fresh each recording; non-iOS reuses one instance
- `hideThinkingLoader` should NOT auto-show the record button (state machine manages it)
- Reward points: `base_reward_points` seeds from lifetime total; only per-conversation deltas stored in DB
- Chirp 3 STT falls back to V1 API on failure — don't assume V2 always available
- `.env` file is gitignored — worktrees need their own copy or symlink

## Environment Variables
Required in `.env`:
- `GEMINI_API_KEY` — Google Gemini for conversation + grammar eval
- `ELEVENLABS_API_KEY` — Text-to-speech
- `GOOGLE_APPLICATION_CREDENTIALS` — Google Cloud STT service account JSON
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — OAuth
- `SECRET_KEY` — Flask sessions
- `DATABASE_URL` — PostgreSQL (prod) / SQLite (dev)
- `REDIS_URL` — Session storage (optional, falls back to file)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET_NAME` — Audio storage (optional)
- `SENTRY_DSN` — Error tracking (optional)
