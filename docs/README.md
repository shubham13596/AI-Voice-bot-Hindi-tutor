# AI Hindi Tutor - Your Hindi Friend

An AI-powered Hindi language tutor designed to be a 24/7 conversation partner for young children (ages 4-8) learning Hindi. Born from a family dinner conversation about maintaining heritage language skills while growing up abroad.

## Project Overview

Created for my nephew in Singapore who was struggling to maintain his Hindi skills in a predominantly Chinese-speaking environment. Unlike traditional language learning apps that focus on structured lessons, this application creates natural, conversation-based learning experiences - like chatting with a friend.

## Link 
You can try the tutor here: https://hindi-voice-tutor-f63a2d6e31a7.herokuapp.com/

## Key Features

- **Natural Conversations**: Acts like a motherly figure who's curious about the child's day
- **Child-Led Learning**: No rigid curriculum - conversations flow naturally based on child's interests (school, dinosaurs, cartoons)
- **Smart Error Correction**: Gentle correction of English-Hindi code-switching (e.g., "मैं school जा रहा हूं" → "मैं विद्यालय जा रहा हूं")
- **Engaging Rewards**: Point system with visual rewards, including Captain America's shield animations
- **Mobile-First Design**: Optimized for smartphone access with an intuitive interface
- **Visual Recording Cues**: Animated microphone for clear recording indicators

## Technical Stack

- **Speech-to-Text**: Sarvam API (chosen specifically for handling children's speech patterns and pauses)
- **Text-to-Speech**: ElevenLabs (selected for superior voice quality and emotional range)
- **Conversation Logic**: GPT-4 with specialized prompting
- **Hosting**: Heroku
- **Interface**: Mobile-first web application
- **Recording**: Manual recording button with visual cues

## Technical Decisions

- Chose Sarvam API over Chromium STT for better handling of long pauses in children's speech
- Selected ElevenLabs over Sarvam TTS for enhanced emotional expression and engagement
- Implemented manual recording over voice activity detection for improved accuracy
- GPT-4 prompt engineered to "be like a mother who is curious about their child"

## Future Development Plans

1. Age-specific response modeling using different GPT prompts
2. Dedicated module for challenging Hindi phonemes
3. Integration of Indian cultural elements and festivals
4. Parent mode for sharing conversation transcripts
5. Analytics for tracking engagement patterns
6. Expansion to support various accents
7. Potential adaptation for other Indian languages

## Impact

Helping the Indian diaspora maintain their connection with Hindi, creating a safe and engaging space for children to practice their heritage language through natural conversation.

## Note

This is a personal project aimed at bridging the language gap for children growing up in non-Hindi speaking environments. While currently focused on Hindi, the architecture could be adapted for other heritage language learning needs.

## 📫 Contact

For questions about the project or development process, feel free to reach out!

---

*Built with love for heritage languages across generations* ❤️
