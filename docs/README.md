# AI Hindi Tutor - Kiki, Your Hindi Friend 🌟

An AI-powered Hindi conversation partner designed to be a 24/7 companion for young children (ages 4-8) learning Hindi. Born from a family dinner conversation about maintaining heritage language skills while growing up abroad.

## 🎯 Project Overview

Created for my nephew in Singapore who was struggling to maintain his Hindi skills in a predominantly Chinese-speaking environment. Unlike traditional language learning apps that focus on structured lessons, Kiki creates natural, conversation-based learning experiences - like chatting with a caring older sister who's genuinely interested in what you have to say.

## 🔗 Try It Out
Experience Kiki here: **[hindispeakingtutor.in](https://www.hindispeakingtutor.in/)**

## ✨ Key Features

### Intelligent Conversation System
- **Natural Dialogue Flow**: Kiki responds like a warm, caring older sister - encouraging, patient, never critical
- **Child-Led Learning**: No rigid curriculum - conversations flow naturally based on child's interests
- **Structured Topics**: 6 thoughtfully designed modules covering everyday life:
  - 🙋 **Main aur Meri Baatein** (Me and My World)
  - 👨‍👩‍👧‍👦 **Mera Parivaar** (My Family)
  - 🍽️ **Khana-Peena** (Food & Eating)
  - 🎉 **Tyohaar** (Festivals & Celebrations)
  - 🦊 **Bahar ki Duniya** (The World Outside)
  - 📖 **Coming soon - Kahaniyan** (Stories & Tales)

### Smart Learning Experience
- **Real-time Grammar Evaluation**: Gentle correction with conversational examples (e.g., "हमने दिया जलाना" → "हमें दीये जलाना")
- **Contextual Hints**: 8-10 word suggestions that respond naturally to Kiki's last message
- **Progressive Difficulty**: Conversations adapt to the child's comfort level
- **Milestone Celebrations**: Visual rewards and encouragement for consistent practice

### Parent & Teacher Tools
- **Analytics Dashboard**: Track conversation frequency, sentence counts, and progress
- **Conversation Insights**: Review what topics your child enjoys discussing
  
## 🛠️ Technical Stack

### AI & Language Processing
- **LLM**: Google Gemini 2.0 Flash (optimized for fast, natural conversations)
- **Speech-to-Text**: Google Cloud Speech-to-Text (superior accuracy for child speech patterns)
- **Text-to-Speech**: ElevenLabs (emotional, natural-sounding voice)
- **Specialized Prompting**: Fine-tuned system prompts for encouraging, age-appropriate responses

### Infrastructure
- **Backend**: Flask (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Session Management**: Redis for distributed sessions
- **Authentication**: Google OAuth 2.0 via Authlib
- **Hosting**: Heroku with automatic scaling
- **Frontend**: Mobile-responsive HTML/CSS/JavaScript with Tailwind CSS

### Key Technical Improvements
- **JSON Validation**: Robust error handling for AI responses
- **Streaming Architecture**: Real-time text streaming for better UX
- **State Management**: Sophisticated recording state handling with cleanup

## 🔑 Technical Decisions & Why

### LLM Selection: Gemini 2.0 Flash
- **Speed**: 8-10x faster than GPT-4 for similar quality
- **Cost**: Significantly more economical for sustained conversations
- **JSON Mode**: Native support for structured responses
- **Streaming**: Built-in streaming capabilities for responsive UX

### STT Selection: Google Cloud Speech-to-Text
- **Child Speech**: Excellent at handling pauses, incomplete thoughts
- **Hindi Accuracy**: Superior Devanagari transcription
- **Latency**: Sub-2-second response times
- **Context Hints**: Supports custom vocabulary for better accuracy

### TTS Selection: ElevenLabs
- **Voice Quality**: Most natural-sounding Hindi voice available
- **Emotional Range**: Conveys warmth and encouragement effectively
- **Streaming**: Low-latency audio delivery
- **Consistency**: Reliable pronunciation across diverse vocabulary

### Architecture Decisions
- **Manual Recording**: Better accuracy than voice activity detection for children
- **Session Persistence**: Redis-backed sessions for seamless conversation resumption
- **Module-Based Topics**: Structured exploration while maintaining conversational flow
- **Correction Flow**: Non-intrusive grammar improvements that don't disrupt engagement

## 📊 Recent Enhancements

### v76 (Latest)
- ✅ Improved hints quality (8-10 words for better context)
- ✅ Fixed correction recording state management bugs
- ✅ Enhanced grammar evaluation with better examples
- ✅ Better error recovery in recording flow

### v75
- ✅ Fixed JSON parsing errors in AI responses
- ✅ Removed stop sequences in JSON mode (preventing truncation)
- ✅ Increased token limits for complete responses
- ✅ Enhanced error handling across all AI interactions

### Previous Updates
- ✅ Migrated from Groq Llama 3-70b to Gemini 2.0 Flash
- ✅ Implemented streaming text responses
- ✅ Added conversation history and resumption
- ✅ Built analytics dashboard
- ✅ Redesigned with heritage-focused messaging

## 🚀 Future Development Plans

### Near-Term
1. **Phoneme Practice Module**: Dedicated exercises for challenging Hindi sounds (ड़, ढ़, ज्ञ, क्ष)
2. **Festival Integration**: Interactive stories during Diwali, Holi, Raksha Bandhan
3. **Parent Reports**: Weekly summaries of conversation topics and progress
4. **Offline Mode**: Basic conversation capabilities without internet

### Long-Term
1. **Multi-Child Profiles**: Support for siblings with individual progress tracking
2. **Voice Customization**: Choose Kiki's voice style and personality
3. **Expanded Topics**: Sports, science, geography modules
4. **Accent Support**: Regional Hindi variations (Marathi-influenced, Punjabi-influenced)
5. **Other Languages**: Adapt architecture for Tamil, Telugu, Bengali, Gujarati
6. **Story Mode**: Interactive Hindi storytelling with comprehension checks

## 🌍 Impact

Helping the Indian diaspora maintain their connection with Hindi, creating a safe and engaging space for children to practice their heritage language through natural conversation.

**Current Reach**: Available globally, with users in Singapore, US, UK, and Canada.

## 🔒 Privacy & Safety

- **Data Security**: All conversations stored securely with encryption
- **Authentication**: Secure Google OAuth - no password storage
- **Child Safety**: No external links, advertisements, or user-generated content
- **Privacy**: Conversation data only accessible to authenticated parents/guardians

## 💻 Local Development

```bash
# Clone repository
git clone https://github.com/your-username/AI-Voice-bot-Hindi-tutor.git
cd AI-Voice-bot-Hindi-tutor

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Add your API keys: GEMINI_API_KEY, GOOGLE_CLOUD_API_KEY, ELEVENLABS_API_KEY

# Run locally
python app.py
```

## 🤝 Contributing

This is a personal project, but suggestions and feedback are always welcome! Feel free to:
- Open issues for bugs or feature requests
- Share your experience if you're using it with your children
- Suggest conversation topics or cultural elements to include

## 📫 Contact

For questions about the project, collaboration opportunities, or just to share your child's progress story, feel free to reach out!

## 🙏 Acknowledgments

- My nephew, for being the inspiration and first tester
- The Indian diaspora community, for invaluable feedback on cultural relevance
- Open source community, for the amazing tools that made this possible

*Built with love for heritage languages across generations* ❤️

---

**License**: MIT
**Status**: Active Development
**Version**: 1.0 (Production)
