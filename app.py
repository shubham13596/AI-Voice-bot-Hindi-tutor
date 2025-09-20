from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, Response
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
import openai
from groq import Groq
import logging
import logging.config
import requests
import base64
import os
import json
from dotenv import load_dotenv
from elevenlabs import ElevenLabs, VoiceSettings
import io
import redis
from datetime import datetime, timedelta
import json
import tempfile
import time
import concurrent.futures
import random

# Import our models and auth
from models import db, User, Conversation, AnalyticsHelper, PageView, UserAction, FunnelAnalytics
from auth import auth_bp, init_oauth


# Configure logging first so it's available throughout the application
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    }
})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis with Heroku Redis URL
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url)

# Load environment variables
load_dotenv()


# Configure Flask app with explicit static folder
app = Flask(__name__, 
    static_url_path='/static',  # URL path for static files
    static_folder='static'      # Physical folder name
)

# Configure Flask app
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
# Fix DATABASE_URL scheme for SQLAlchemy compatibility
database_url = os.getenv('DATABASE_URL', 'sqlite:///hindi_tutor.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)

# Initialize database
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'home'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize OAuth
oauth, google = init_oauth(app)

# Set the OAuth instances in auth module
import auth
auth.oauth = oauth
auth.google = google

# Register authentication blueprint
app.register_blueprint(auth_bp)

# Configure API keys from environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')  # Keep as fallback
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
SARVAM_API_KEY = os.getenv('SARVAM_API_KEY')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

STT_PROVIDER = os.getenv('STT_PROVIDER', 'sarvam')  # Default to sarvam (options: sarvam, groq)

# Initialize Groq client
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Groq client: {e}")
    raise

# Conversation type configurations
# Hindi affirmations for good responses - natural and encouraging
HINDI_AFFIRMATIONS = [
    "शाबाश!",
    "काफी अच्छे!",
    "बहुत अच्छे",
    "वाह!",
    "बहुत बढ़िया!",
    "शानदार!",
    "प्यारा जवाब!",
    "बहुत सही!",
    "कमाल है!",
    "लाजवाब!"
]

class AffirmationService:
    """Service to manage natural Hindi affirmations for good responses"""
    
    @staticmethod
    def should_affirm(session_data):
        """Decide if we should add an affirmation based on conversation context"""
        # Get consecutive good responses count
        good_count = session_data.get('good_response_count', 0)
        sentences_count = session_data.get('sentences_count', 0)
        
        # Strategy: Affirm on first good response, then every 2nd good response
        # But not too frequently to keep it natural
        if good_count == 1:  # First good response
            return True
        elif good_count % 2 == 0 and sentences_count > 2:  # Every 2nd good response
            return True
        elif good_count % 3 == 0 and sentences_count > 5:  # Every 3rd after more conversation
            return True
        
        return False
    
    @staticmethod
    def get_affirmation():
        """Get a random Hindi affirmation"""
        return random.choice(HINDI_AFFIRMATIONS)
    
    @staticmethod
    def add_affirmation_to_response(response, session_data):
        """Add affirmation to response if appropriate"""
        if AffirmationService.should_affirm(session_data):
            affirmation = AffirmationService.get_affirmation()
            return f"{affirmation} {response}"
        return response

CONVERSATION_TYPES = {
    'everyday': {
        'name': 'Everyday Life',
        'description': 'Daily activities, school, friends, and routine conversations',
        'system_prompts': {
            'initial': """
            You are a friendly Hindi female tutor starting a conversation with a 6-year-old child, named {child_name}.
            Create a warm, engaging greeting and ask if they went to school today or what they did today in Hindi.
            Guidelines:
            1. Keep it short
            2. Use simple Hindi words
            3. Make it cheerful and inviting
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi female tutor speaking with a 6-year-old child.
            Focus on everyday life topics: school, friends, family, daily activities, food, play, etc.
            Guidelines:
            1. Be curious about their daily life like a their grandmother would be. Choose to ask about the things that they did today; give advice, support, and guidance wherever necessary.
            2. Keep responses short (max 20 words)
            3. Ensure your Hindi response is grammatically correct and follows the correct sentence structure.
            4. Gently encourage them to give a longer, complete answer. For example, Ask a follow-up question to the child's single-word answer. If they say 'school', ask 'स्कूल में क्या किया?'."
            5. Basis the response of the kid, ask relevant follow-up questions. Make it fun and interesting for the kid.
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🏠',
        'tag': 'Easy'
    },
    'animals_nature': {
        'name': 'Animals and Nature',
        'description': 'Conversations about pets, zoo animals, and wildlife',
        'system_prompts': {
            'initial': """
            You are a friendly Hindi female tutor starting a conversation with a 6-year-old child, named {child_name}.
            Create a warm greeting and ask about their favorite animal in Hindi.
            Guidelines:
            1. Keep it short
            2. Use simple Hindi words
            3. Make it cheerful and inviting
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': 
            """
            You are a friendly, caring Hindi female tutor speaking with a 6-year-old child. Your goal is to guide a fun, Hindi-only conversation about animals and nature.
            Guidelines:
            1. Continue the natural conversation flow about animals
            2. Keep responses short (max 20 words)
            3. Ensure your Hindi response is grammatically correct and follows the correct sentence structure.
            4. Gently encourage them to give a longer, complete answer. For example, Ask a follow-up question to the child's single-word answer.
            5. Basis the response of the kid, ask relevant follow-up questions. Make it fun and interesting for the kid.
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🦊', 
        'tag': 'Fun'
    },
    'adventure_story': {
        'name': 'Adventure Story',
        'description': 'Create exciting adventure stories together in simple Hindi',
        'system_prompts': {
            'initial': """You are a friendly Hindi storytelling female tutor starting an adventure story with a 6-year-old child, named {child_name}.
            Begin by suggesting we create an adventure story together in Hindi, and ask them to choose a main character or setting.
            You will co-create an adventure story where they contribute ideas and you guide the narrative.
            Guidelines:
            1. Keep it very short (max 10 words)
            2. Use simple Hindi words
            3. Make it exciting and engaging
            4. Ask them to contribute ideas for the adventure story
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi storytelling female tutor co-creating an adventure story with a 6-year-old child.
            Help them build an exciting adventure story by asking for their input and expanding on their ideas.
            Guidelines:
            1. Continue the story based on their input and ask what happens next
            2. Keep responses short (max 20 words)
            3. Use simple Hindi vocabulary suitable for children
            4. Make the story exciting with simple adventures (finding treasure, helping animals, exploring places)
            5. Always ask for their input: "What should happen next?" or "Who should they meet?"
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🗺️',
        'tag': 'Creative'
    },
    'panchatantra_story': {
        'name': 'Co-create the "Thirsty Crow" Panchatantra Story',
        'description': 'Create the classic story of "The Thirsty Crow" together in simple Hindi',
        'system_prompts': {
            'initial': """
            You are a friendly, patient, and encouraging Hindi female tutor for a 6-year-old child, named {child_name}. Your task is to co-create the story of 'The Thirsty Crow' with the child. The child does not know the story. You must provide the main narrative points and then ask the child a question to move the story forward. Your goal is to help the child form complete sentences in Hindi.
            Start by narrating that a crow was very thirsty and was looking for water. Then ask the child, "कौआ कहाँ था और क्या कर रहा था?" (Where was the crow and what was he doing?)
            Important Rules for your response:
            - Keep your narrative parts simple and short (max 15 words).
            - Use very simple Hindi words and sentence structures.
            - Make it cheerful and engaging.
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': 
            """You are a friendly, patient, and encouraging Hindi female tutor for a 6-year-old child. Your task is to co-create the story of 'The Thirsty Crow' with the child. The child does not know the story. You must provide the main narrative points and then ask the child a question to move the story forward. Your goal is to help the child form complete sentences in Hindi.
            The story must follow these specific steps:
            1. **Start:** Narrate that a crow was very thirsty and was looking for water. Ask the child, "कौआ कहाँ था और क्या कर रहा था?" (Where was the crow and what was he doing?)
            2. **The Discovery:** Narrate that the crow found a pot of water but the water level was too low. Ask the child, "कौए को पानी का घड़ा कहाँ मिला?" (Where did the crow find the pot of water?)
            3. **The Problem:** Narrate that the crow's beak couldn't reach the water. Ask the child, "कौए ने पानी पीने के लिए क्या किया?" (What did the crow do to drink the water?)
            4. **The Solution:** Narrate that the crow saw pebbles nearby and started picking them up. Ask the child, "उसने उन पत्थरों को कहाँ डाला?" (Where did he put those stones?)
            5. **The Result:** Narrate that the water level rose and the crow drank it. Ask the child, "पानी पीने के बाद कौए ने क्या कहा?" (What did the crow say after drinking the water?)
            6. **The Moral:** Narrate the final lesson of the story. Ask the child, "इस कहानी से तुमने क्या सीखा?" (What did you learn from this story?)

            Important Rules for all your responses:
            - Keep your narrative parts simple and short (max 10 words).
            - Wait for the child's response before moving to the next step.
            - Use very simple Hindi words and sentence structures.
            - Reinforce the child's correct answer by repeating it in a full, grammatically correct sentence. For example, if the child says "glass mein," you say "हाँ! उसने पत्थर ग्लास में डाले।" (Yes! He put the stones in the glass.)
            - Encourage the child with positive phrases like "बहुत बढ़िया" (very good), "शाबाश" (bravo), or "वाह" (wow).
            - Guide the child to say a full sentence. If they give a single-word answer, repeat the sentence for them to practice.
            - The entire story, from start to finish, must be based on the provided plot points of 'The Thirsty Crow'.
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '📖',
        'tag': 'Indian fables'
    }
}


# Sarvam AI API endpoints
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
# Initialize ElevenLabs client
eleven_labs = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Get port from environment variable
port = int(os.getenv('PORT', 5001))

# Cache for storing user session data
user_sessions = {}


def get_initial_conversation(child_name="दोस्त", conversation_type="everyday"):
    """Generate initial conversation starter based on conversation type"""
    try:
        # Get the appropriate system prompt for the conversation type
        if conversation_type in CONVERSATION_TYPES:
            system_prompt = CONVERSATION_TYPES[conversation_type]['system_prompts']['initial'].format(child_name=child_name)
        else:
            # Fallback to everyday conversation
            system_prompt = CONVERSATION_TYPES['everyday']['system_prompts']['initial'].format(child_name=child_name)

        logger.info(f"Making Groq API call for initial {conversation_type} conversation")

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={ "type": "json_object" },
            temperature=0.2,
            max_tokens=100
        )
        
        logger.info("Groq API call successful")
        result = json.loads(response.choices[0].message.content)
        return result.get('response', "नमस्ते! कैसा है आपका दिन?")
        
    except Exception as e:
        logger.error(f"Error in initial conversation: {str(e)}")
        return "नमस्ते! कैसा है आपका दिन?"  # Fallback greeting


def calculate_rewards(evaluation_result, good_response_count):
    """Calculate reward points based on response quality"""
    points = 0
    
    # Award points only for good quality responses
    if evaluation_result.get('feedback_type') == 'green':
        points = 10  # Base points for good response
        
        # Bonus for milestones (every 4 good responses)
        if good_response_count % 4 == 0 and good_response_count > 0:
            points += 20  # Milestone bonus
    
    return points

class ResponseEvaluator:
    """Evaluates user responses for completeness and grammar"""
    
    @staticmethod
    def evaluate_response(user_text, last_talker_response=None):
        """Evaluate user response and return score + analysis"""
        try:
            
            # Build system prompt with context from last talker response
            if last_talker_response:
                context_section = f"""
                Context - Last question/statement from tutor: "{last_talker_response}"
                User response: "{user_text}"
                """
            else:
                context_section = f"""
                User response: "{user_text}"
                """
            
            system_prompt = f"""
            You are a Hindi tutor evaluating this Hindi response from a 6-year-old child ONLY for:
            1. Completeness (is it a sentence or just 1 word?)
            2. Grammar correctness in Hindi
            3. Evaluate from a CONVERSATIONAL Hindi perspective and not from a written Hindi perspective
            
            {context_section}
            
            Return JSON format:
            {{
                "score": 1-10,
                "is_complete": true/false,
                "is_grammatically_correct": true/false,
                "issues": ["incomplete", "grammar_error"],
                "corrected_response": "grammatically correct and complete version that responds to the context",
                "feedback_type": "green/amber"
            }}
            
            Score guide:
            - 8-10: Complete, grammatically correct = green
            - 1-7: Incomplete, grammar issues = amber
            
            For the corrected_response, provide a complete sentence in Hindi that:
            - Is 100% grammatically correct with proper sentence structure.
            - Properly answers the question or responds to the statement
            - Is appropriate for a 6-year-old's vocabulary
            """
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=100
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Error in response evaluation: {str(e)}")
            return {
                "score": 5,
                "is_complete": True,
                "is_grammatically_correct": True,
                "issues": [],
                "corrected_response": user_text,
                "feedback_type": "green"
            }

class TalkerModule:
    """Handles conversation responses based on evaluation context"""
    
    @staticmethod
    def get_response(conversation_history, user_text, sentence_count, conversation_type="everyday"):
        """Generate conversation response based on conversation type"""
        try:
            
            # Always use continue_conversation strategy for simplicity and speed
            strategy = "continue_conversation"
            
            # Get the appropriate system prompt for the conversation type
            if conversation_type in CONVERSATION_TYPES:
                system_prompt_template = CONVERSATION_TYPES[conversation_type]['system_prompts']['conversation']
            else:
                # Fallback to everyday conversation
                system_prompt_template = CONVERSATION_TYPES['everyday']['system_prompts']['conversation']
            
            system_prompt = system_prompt_template.format(strategy=strategy)
            
            messages = [
                {"role": "system", "content": system_prompt},
                *conversation_history,
                {"role": "user", "content": user_text}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=150
            )
            
            result = json.loads(response.choices[0].message.content)
            return result["response"]
            
        except Exception as e:
            logger.error(f"Error in talker response: {str(e)}")
            return "मैं समझ नहीं पाया। कृपया दोबारा बोलें।"

class ConversationController:
    """Main orchestrator for conversation flow"""
    
    def __init__(self):
        self.evaluator = ResponseEvaluator()
        self.talker = TalkerModule()
    
    def process_user_response(self, session_data, user_text):
        """Process user response through evaluation and conversation flow"""
        try:
            conversation_type = session_data.get('conversation_type', 'everyday')
            
            # Extract the last talker response from conversation history
            last_talker_response = None
            conversation_history = session_data.get('conversation_history', [])
            
            # Find the most recent assistant message
            for message in reversed(conversation_history):
                if message.get('role') == 'assistant':
                    last_talker_response = message.get('content')
                    break
            
            # Run evaluation and conversation response in PARALLEL
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both OpenAI API calls simultaneously
                eval_future = executor.submit(
                    self.evaluator.evaluate_response, 
                    user_text,
                    last_talker_response
                )
                
                conv_future = executor.submit(
                    self.talker.get_response,
                    session_data['conversation_history'],
                    user_text,
                    session_data['sentences_count'],
                    conversation_type
                )
                
                # Wait for both to complete
                evaluation = eval_future.result()
                conversation_response = conv_future.result()
            
            # Track good responses and handle amber responses
            if evaluation['feedback_type'] == 'green':
                session_data['good_response_count'] = session_data.get('good_response_count', 0) + 1
                # Add affirmation to conversation response for good responses
                conversation_response = AffirmationService.add_affirmation_to_response(
                    conversation_response, session_data
                )
            elif evaluation['feedback_type'] == 'amber':
                amber_entry = {
                    'user_response': user_text,
                    'corrected_response': evaluation['corrected_response'],
                    'issues': evaluation['issues']
                }
                session_data.setdefault('amber_responses', []).append(amber_entry)
            
            # Check if correction popup should trigger (every 4 interactions, and we have amber responses)
            should_show_popup = (
                session_data['sentences_count'] % 4 == 0 and
                session_data['sentences_count'] > 0 and
                len(session_data.get('amber_responses', [])) > 0
            )
            
            # Calculate milestone status for celebration
            is_milestone = (
                evaluation['feedback_type'] == 'green' and 
                session_data['good_response_count'] % 4 == 0 and
                session_data['good_response_count'] > 0
            )
            
            return {
                'response': conversation_response,
                'evaluation': evaluation,
                'should_show_popup': should_show_popup,
                'amber_responses': session_data.get('amber_responses', []) if should_show_popup else [],
                'is_milestone': is_milestone,
                'good_response_count': session_data.get('good_response_count', 0)
            }
            
        except Exception as e:
            logger.error(f"Error in conversation controller: {str(e)}")
            return {
                'response': "मैं समझ नहीं पाया। कृपया दोबारा बोलें।",
                'evaluation': {'feedback_type': 'green'},
                'should_show_popup': False,
                'amber_responses': []
            }

# Analytics Helper Functions
def track_page_view(page, url_path):
    """Track page view for analytics"""
    try:
        session_id = request.cookies.get('session', 'anonymous')
        user_id = current_user.id if current_user.is_authenticated else None
        referrer = request.referrer
        user_agent = request.headers.get('User-Agent')
        ip_address = request.remote_addr
        
        page_view = PageView(
            user_id=user_id,
            session_id=session_id,
            page=page,
            url_path=url_path,
            referrer=referrer,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        db.session.add(page_view)
        db.session.commit()
        logger.info(f"Tracked page view: {page} for {'user_' + str(user_id) if user_id else 'anonymous'}")
        
    except Exception as e:
        logger.error(f"Error tracking page view: {str(e)}")
        db.session.rollback()

def track_user_action(action, page, metadata=None):
    """Track user action for analytics"""
    try:
        session_id = request.cookies.get('session', 'anonymous')
        user_id = current_user.id if current_user.is_authenticated else None
        
        user_action = UserAction(
            user_id=user_id,
            session_id=session_id,
            action=action,
            page=page,
            action_metadata=json.dumps(metadata, ensure_ascii=False) if metadata else None
        )
        
        db.session.add(user_action)
        db.session.commit()
        logger.info(f"Tracked action: {action} on {page} for {'user_' + str(user_id) if user_id else 'anonymous'}")
        
    except Exception as e:
        logger.error(f"Error tracking user action: {str(e)}")
        db.session.rollback()

@app.route('/api/start_conversation', methods=['POST'])
@login_required
def start_conversation():
    """Endpoint to start the initial conversation"""
    try:
        logger.info("Starting new conversation")
        
        # Get conversation type from request
        data = request.get_json() or {}
        conversation_type = data.get('conversation_type', 'everyday')
        
        # Validate conversation type
        if conversation_type not in CONVERSATION_TYPES:
            conversation_type = 'everyday'
        
        # Use the authenticated user's child name
        child_name = current_user.child_name or 'दोस्त'
        
        initial_message = get_initial_conversation(child_name, conversation_type)
        
        logger.info("Converting text to speech")
        audio_response = text_to_speech_hindi(initial_message)

        if not audio_response:
            raise Exception("Failed to generate audio response")
        
        session_id = base64.b64encode(os.urandom(16)).decode('utf-8')

        # Create conversation record in database
        conversation = Conversation(
            user_id=current_user.id,
            session_id=session_id,
            conversation_type=conversation_type,
            sentences_count=0,
            good_response_count=0,
            reward_points=0
        )
        conversation.conversation_data = []
        conversation.amber_data = []
        
        db.session.add(conversation)
        db.session.commit()
        
        # Initialize complete session data with all required fields
        session_store = FileSessionStore()
        session_data = {
            'conversation_id': conversation.id,
            'user_id': current_user.id,
            'conversation_history': [],
            'sentences_count': 0,
            'good_response_count': 0,
            'reward_points': 0,
            'conversation_type': conversation_type,
            'amber_responses': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Add initial message to conversation history
        session_data['conversation_history'].append({
            'role': 'assistant',
            'content': initial_message
        })

        # Save session with complete data including initial message
        session_store.save_session(session_id, session_data)

        logger.info("Conversation started successfully")
        
        return jsonify({
            'text': initial_message,
            'audio': audio_response,
            'session_id': session_id,
            'corrections': None  # Explicitly include corrections as None
        })
        
    except Exception as e:
        logger.error(f"Error in start_conversation: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({'error': str(e)}), 500
    

def text_to_speech_hindi(text, output_filename="response.wav"):
    """Convert text to speech using ElevenLabs"""
    tts_function_start = time.time()
    logger.info(f"🔊 ELEVENLABS TTS: Starting synthesis for '{text[:50]}...'")
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                audio_stream = eleven_labs.text_to_speech.convert_as_stream(
                    text=text,
                    model_id="eleven_flash_v2_5",
                    language_code="hi",
                    voice_id="Sm1seazb4gs7RSlUVw7c", #
                    optimize_streaming_latency="4",
                    output_format="mp3_44100_128",
                    voice_settings=VoiceSettings(
                        stability=0.5,
                        similarity_boost=0.6,
                        style=0.0,
                        use_speaker_boost=True,
                        speed=0.8
                    )
                )
                
                audio_data = io.BytesIO()
                for chunk in audio_stream:
                    audio_data.write(chunk)
                
                audio_base64 = base64.b64encode(audio_data.getvalue()).decode('utf-8')
                
                if output_filename:
                    with open(output_filename, 'wb') as f:
                        f.write(audio_data.getvalue())
                
                tts_function_end = time.time()
                api_time = (tts_function_end - tts_function_start) * 1000
                logger.info(f"✅ ELEVENLABS TTS: Success in {api_time:.1f}ms")
                        
                return audio_base64
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"TTS attempt {attempt + 1} failed: {e}")
                time.sleep(0.1 * (attempt + 1))
        
    except Exception as e:
        print(f"TTS Error: {str(e)}")
        return None

def speech_to_text_hindi_sarvam(audio_data):
    """Convert Hindi speech to text using Sarvam AI"""
    stt_start_time = time.time()
    logger.info("🎙️ SARVAM STT: Starting transcription...")
    
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
    }

    # Create form data
    files = {
            'file': ('audio.wav', audio_data, 'audio/wav')
        }
    
    # Form data parameters
    data = {
            'language_code': 'hi-IN',
            'model': 'saarika:v2.5',
            'with_timestamps': False
        }
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                api_start_time = time.time()
                response = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data)
                api_end_time = time.time()
                api_latency = (api_end_time - api_start_time) * 1000
                logger.info(f"🌐 SARVAM API: Response received in {api_latency:.1f}ms")
                
                response.raise_for_status()
                result = response.json()
                transcript = result.get("transcript")
                
                stt_end_time = time.time()
                total_latency = (stt_end_time - stt_start_time) * 1000
                logger.info(f"✅ SARVAM STT: Success! Total time: {total_latency:.1f}ms")
                logger.info(f"📝 TRANSCRIPT: '{transcript}'")
                
                return transcript
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"❌ Sarvam STT attempt {attempt + 1} failed: {e}")
                time.sleep(0.1 * (attempt + 1))

    except Exception as e:
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000
        logger.error(f"❌ SARVAM STT: Failed after {total_latency:.1f}ms - {str(e)}")
        return None


def speech_to_text_hindi_groq(audio_data):
    """Convert Hindi speech to text using Groq Whisper-Large-V3"""
    stt_start_time = time.time()
    logger.info("🎙️ GROQ WHISPER STT: Starting transcription...")

    try:
        # Create a temporary file for the audio data
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_file.write(audio_data)
            temp_file_path = temp_file.name

        try:
            # Use Groq Whisper API for transcription
            api_start_time = time.time()
            with open(temp_file_path, 'rb') as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3", 
                    language="hi",  # Hindi language code
                    response_format="json",
                    prompt = "वक्ता एक 6 वर्षीय बालक है जो स्कूल, कहानियों, जानवरों आदि जैसे विभिन्न विषयों पर बोलकर अपने हिंदी बोलने के कौशल का अभ्यास कर रहा है।",
                    temperature=0.0  # For consistent results
                )
            api_end_time = time.time()
            api_latency = (api_end_time - api_start_time) * 1000
            logger.info(f"🌐 GROQ API: Response received in {api_latency:.1f}ms")

            # Extract transcript text
            transcript = transcription.text.strip()

            stt_end_time = time.time()
            total_latency = (stt_end_time - stt_start_time) * 1000
            logger.info(f"✅ GROQ WHISPER STT: Success! Total time: {total_latency:.1f}ms")
            logger.info(f"📝 TRANSCRIPT: '{transcript}'")

            return transcript

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass

    except Exception as e:
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000
        logger.error(f"❌ GROQ WHISPER STT: Failed after {total_latency:.1f}ms - {str(e)}")
        return None

def speech_to_text_hindi(audio_data):
    """Convert Hindi speech to text using the configured STT provider"""
    if STT_PROVIDER.lower() == 'groq':
        return speech_to_text_hindi_groq(audio_data)
    else:
        return speech_to_text_hindi_sarvam(audio_data)

# COMMENTED OUT FOR SARVAM USAGE  
# def speech_to_text_hindi_deepgram(audio_data):
#     """Convert Hindi speech to text using Deepgram AI"""
#     stt_start_time = time.time()
#     logger.info("🎙️ DEEPGRAM STT: Starting transcription...")
#     
#     headers = {
#         "Authorization": f"Token {DEEPGRAM_API_KEY}",
#         "Content-Type": "audio/wav"
#     }
#     
#     # Query parameters for Deepgram
#     params = {
#         "language": "hi",
#         "model": "nova-2",
#         "smart_format": "true",
#         "punctuate": "true"
#     }
#     
#     try:
#         max_retries = 3
#         for attempt in range(max_retries):
#             try:
#                 api_start_time = time.time()
#                 response = requests.post(
#                     "https://api.deepgram.com/v1/listen",
#                     headers=headers,
#                     params=params,
#                     data=audio_data
#                 )
#                 api_end_time = time.time()
#                 api_latency = (api_end_time - api_start_time) * 1000
#                 logger.info(f"🌐 DEEPGRAM API: Response received in {api_latency:.1f}ms")
#                 
#                 response.raise_for_status()
#                 result = response.json()
#                 
#                 # Extract transcript from Deepgram response
#                 if "results" in result and "channels" in result["results"]:
#                     channels = result["results"]["channels"]
#                     if channels and "alternatives" in channels[0]:
#                         alternatives = channels[0]["alternatives"]
#                         if alternatives:
#                             transcript = alternatives[0].get("transcript")
#                             stt_end_time = time.time()
#                             total_latency = (stt_end_time - stt_start_time) * 1000
#                             logger.info(f"✅ DEEPGRAM STT: Success! Total time: {total_latency:.1f}ms")
#                             logger.info(f"📝 TRANSCRIPT: '{transcript}'")
#                             return transcript
#                 
#                 logger.warning("⚠️ DEEPGRAM: No transcript found in response")
#                 return None
#                 
#             except Exception as e:
#                 if attempt == max_retries - 1:
#                     raise
#                 logger.warning(f"❌ Deepgram STT attempt {attempt + 1} failed: {e}")
#                 time.sleep(0.1 * (attempt + 1))
#
#     except Exception as e:
#         stt_end_time = time.time()
#         total_latency = (stt_end_time - stt_start_time) * 1000
#         logger.error(f"❌ DEEPGRAM STT: Failed after {total_latency:.1f}ms - {str(e)}")
#         return None

@app.route('/')
def home():
    """Landing page - shows login or redirects if authenticated"""
    # Track landing page visit
    track_page_view('landing', request.path)
    
    if current_user.is_authenticated:
        if not current_user.child_name:
            return redirect(url_for('profile_setup'))
        return redirect(url_for('conversation_select'))
    return render_template('index.html')

@app.route('/profile-setup')
@login_required
def profile_setup():
    """Profile setup page for setting child name"""
    return render_template('profile_setup.html')

@app.route('/conversation-select')
@login_required
def conversation_select():
    """Conversation type selection page - requires authentication and profile setup"""
    if not current_user.child_name:
        return redirect(url_for('profile_setup'))
    
    # Track conversation-select page visit
    track_page_view('conversation-select', request.path)
    
    return render_template('conversation_select.html')

@app.route('/conversation')
@login_required
def conversation():
    """Main conversation page - requires authentication and conversation type selection"""
    if not current_user.child_name:
        return redirect(url_for('profile_setup'))
    
    # Get conversation type from query parameter, default to 'everyday'
    conversation_type = request.args.get('type', 'everyday')
    
    # Validate conversation type
    if conversation_type not in CONVERSATION_TYPES:
        return redirect(url_for('conversation_select'))
    
    # Track conversation page visit
    track_page_view('conversation', request.path)
    
    # Track conversation start action
    track_user_action('conversation_start', 'conversation', {'conversation_type': conversation_type})
    
    return render_template('conversation.html', conversation_type=conversation_type)

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with analytics"""
    return render_template('dashboard.html')

@app.route('/mission')
def mission():
    """Mission page - accessible to all users"""
    return render_template('mission.html')

@app.route('/contact')
def contact():
    """Contact us page - accessible to all users"""
    return render_template('contact.html')

@app.route('/privacy')
def privacy():
    """Privacy policy and terms page - accessible to all users"""
    return render_template('privacy.html')

# Configure static files handling
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', 
                             mimetype='image/vnd.microsoft.icon',
                             as_attachment=False)

#Make sure process_audio.js is served correctly
# Optional: Add a specific route for process_audio.js if needed
@app.route('/static/js/process_audio.js')
def serve_js():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'),
        'process_audio.js',
        mimetype='application/javascript',
        as_attachment=False
    )

@app.route('/api/speak', methods=['POST'])
def speak_text():
    try:
        text = request.form.get('text')
        if not text:
            return jsonify({'error': 'No text provided'}), 400
            
        # Use the existing TTS function
        audio_response = text_to_speech_hindi(text)
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
            
        return jsonify({'audio': audio_response})
        
    except Exception as e:
        print(f"Speak Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/translate', methods=['POST'])
def translate_text():
    try:
        data = request.json
        text = data.get('text')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
            
        # Use Groq for translation
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a translator. Translate the given text to English. Provide only the translation, no additional text."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.2
        )
        
        translation = response.choices[0].message.content.strip()
        return jsonify({'translation': translation})
        
    except Exception as e:
        print(f"Translation Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/process_audio', methods=['POST'])
@login_required
def process_audio():
    request_start_time = time.time()
    logger.info("🚀 PROCESS AUDIO: Request started")
    
    temp_file = None
    try:
        # Log incoming request data
        logger.info(f"Files in request: {list(request.files.keys())}")
        logger.info(f"Form data in request: {list(request.form.keys())}")

        if 'audio' not in request.files:
            logger.error("No audio file in request")
            return jsonify({'error': 'No audio file'}), 400
        
        session_id = request.form.get('session_id')
        logger.info(f"Received session_id: {session_id}")
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400
        
        
        session_data = session_store.load_session(session_id)
        if not session_data:
            logger.error(f"Invalid session ID: {session_id}")
            return jsonify({'error': 'Invalid or expired session'}), 400
        
         # Log current session state
        logger.info(f"Current sentence count: {session_data['sentences_count']}")

        # Simply increment sentence count by 1 for each user interaction
        session_data['sentences_count'] += 1
        logger.info(f"Updated sentence count: {session_data['sentences_count']}")
        session_store.save_session(session_id, session_data)
        
        # Use tempfile for secure file handling
        # Step 1: Save audio file
        file_start_time = time.time()
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)

            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read())
        
        file_end_time = time.time()
        logger.info(f"📁 FILE PROCESSING: {(file_end_time - file_start_time) * 1000:.1f}ms")
        
        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        # Step 2: LLM Processing
        llm_start_time = time.time()
        logger.info("🤖 LLM PROCESSING: Starting conversation logic...")
        
        # Initialize conversation controller
        controller = ConversationController()
        
        # Process user response through controller
        controller_result = controller.process_user_response(session_data, transcript)
        
        llm_end_time = time.time()
        logger.info(f"✅ LLM PROCESSING: Complete in {(llm_end_time - llm_start_time) * 1000:.1f}ms")
        
        # Step 3: Rewards calculation
        rewards_start_time = time.time()
        new_rewards = calculate_rewards(
            controller_result['evaluation'], 
            controller_result['good_response_count']
        )
        
        if new_rewards > 0:
            session_data['reward_points'] += new_rewards
        
        rewards_end_time = time.time()
        logger.info(f"🎯 REWARDS: Calculated in {(rewards_end_time - rewards_start_time) * 1000:.1f}ms")
        
        if not controller_result['response']:
            return jsonify({'error': 'Failed to get conversation response'}), 500
        
        # Step 4: Convert response to speech
        tts_start_time = time.time()
        logger.info("🔊 TTS: Starting text-to-speech...")
        audio_response = text_to_speech_hindi(controller_result['response'])
        tts_end_time = time.time()
        logger.info(f"✅ TTS: Complete in {(tts_end_time - tts_start_time) * 1000:.1f}ms")
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
        
        # Update conversation history
        session_data['conversation_history'].extend([
            {"role": "user", "content": transcript},
            {"role": "assistant", "content": controller_result['response']}
        ])

        # Update database conversation record
        if 'conversation_id' in session_data:
            try:
                conversation = Conversation.query.get(session_data['conversation_id'])
                if conversation:
                    conversation.sentences_count = session_data['sentences_count']
                    conversation.good_response_count = controller_result['good_response_count']
                    conversation.reward_points = session_data['reward_points']
                    conversation.conversation_data = session_data['conversation_history']
                    conversation.amber_data = session_data.get('amber_responses', [])
                    conversation.updated_at = datetime.utcnow()
                    db.session.commit()
            except Exception as e:
                logger.error(f"Failed to update conversation in database: {e}")

        # Add this line to save all updates
        session_store.save_session(session_id, session_data)

        try:
            os.unlink(temp_file.name)
        except Exception as e:
                logger.error(f"Failed to delete temporary file: {e}")
        
        # Final timing
        request_end_time = time.time()
        total_time = (request_end_time - request_start_time) * 1000
        logger.info(f"🏁 TOTAL REQUEST TIME: {total_time:.1f}ms")
        
        return jsonify({
            'text': controller_result['response'],
            'audio': audio_response,
            'transcript': transcript,
            'evaluation': controller_result['evaluation'],
            'sentence_count': session_data['sentences_count'],
            'good_response_count': controller_result['good_response_count'],
            'reward_points': session_data['reward_points'],
            'new_rewards': new_rewards,
            'is_milestone': controller_result['is_milestone'],
            'should_show_popup': controller_result['should_show_popup'],
            'amber_responses': controller_result['amber_responses']
        })
        
    except Exception as e:
        logger.error(f"Process Error: {str(e)}")
        logger.exception("Full traceback:")  # Add full traceback logging
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/process_audio_stream', methods=['POST'])
@login_required
def process_audio_stream():
    """Enhanced process_audio with streaming text response for typewriter effect"""
    request_start_time = time.time()
    logger.info("🚀 PROCESS AUDIO STREAM: Request started")

    temp_file = None
    try:
        # Validate request data
        if 'audio' not in request.files:
            logger.error("No audio file in request")
            return jsonify({'error': 'No audio file'}), 400

        session_id = request.form.get('session_id')
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400

        session_data = session_store.load_session(session_id)
        if not session_data:
            logger.error(f"Invalid session ID: {session_id}")
            return jsonify({'error': 'Invalid or expired session'}), 400

        # Process audio file (same as original)
        session_data['sentences_count'] += 1
        session_store.save_session(session_id, session_data)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)
            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read())

        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        # Get conversation context
        conversation_type = session_data.get('conversation_type', 'everyday')
        conversation_history = session_data.get('conversation_history', [])

        # Extract last talker response for evaluation
        last_talker_response = None
        for message in reversed(conversation_history):
            if message.get('role') == 'assistant':
                last_talker_response = message.get('content')
                break

        # Run evaluation in parallel (same as original)
        controller = ConversationController()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            eval_future = executor.submit(
                controller.evaluator.evaluate_response,
                transcript,
                last_talker_response
            )
            evaluation = eval_future.result()

        # Streaming response generator
        def generate_streaming_response():
            try:
                # Send initial metadata
                yield f"data: {json.dumps({'type': 'metadata', 'transcript': transcript, 'evaluation': evaluation})}\n\n"

                # Get system prompt for conversation type
                if conversation_type in CONVERSATION_TYPES:
                    system_prompt_template = CONVERSATION_TYPES[conversation_type]['system_prompts']['conversation']
                else:
                    system_prompt_template = CONVERSATION_TYPES['everyday']['system_prompts']['conversation']

                system_prompt = system_prompt_template.format(strategy="continue_conversation")

                messages = [
                    {"role": "system", "content": system_prompt},
                    *conversation_history,
                    {"role": "user", "content": transcript}
                ]

                # Create streaming response
                response_stream = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    stream=True,  # Enable streaming
                    temperature=0.5,
                    max_tokens=150
                )

                # Word buffering for smooth display (2-3 words at a time)
                word_buffer = ""
                accumulated_text = ""
                word_count = 0

                for chunk in response_stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        word_buffer += content
                        accumulated_text += content

                        # Send buffered words (2-3 words or on punctuation)
                        if (' ' in word_buffer and word_count >= 2) or any(p in word_buffer for p in '.!?,।'):
                            # Clean and send the buffered words
                            words_to_send = word_buffer.strip()
                            if words_to_send:
                                yield f"data: {json.dumps({'type': 'words', 'content': words_to_send, 'accumulated': accumulated_text})}\n\n"
                            word_buffer = ""
                            word_count = 0
                        elif ' ' in word_buffer:
                            word_count += 1

                # Send any remaining buffered content
                if word_buffer.strip():
                    yield f"data: {json.dumps({'type': 'words', 'content': word_buffer.strip(), 'accumulated': accumulated_text})}\n\n"

                # Apply affirmation service if needed
                if evaluation['feedback_type'] == 'green':
                    session_data['good_response_count'] = session_data.get('good_response_count', 0) + 1
                    accumulated_text = AffirmationService.add_affirmation_to_response(accumulated_text, session_data)
                elif evaluation['feedback_type'] == 'amber':
                    amber_entry = {
                        'user_response': transcript,
                        'corrected_response': evaluation['corrected_response'],
                        'issues': evaluation['issues']
                    }
                    session_data.setdefault('amber_responses', []).append(amber_entry)

                # Calculate additional response data
                should_show_popup = (
                    session_data['sentences_count'] % 4 == 0 and
                    session_data['sentences_count'] > 0 and
                    len(session_data.get('amber_responses', [])) > 0
                )

                is_milestone = (
                    evaluation['feedback_type'] == 'green' and
                    session_data.get('good_response_count', 0) % 4 == 0 and
                    session_data.get('good_response_count', 0) > 0
                )

                new_rewards = calculate_rewards(evaluation, session_data.get('good_response_count', 0))
                if new_rewards > 0:
                    session_data['reward_points'] = session_data.get('reward_points', 0) + new_rewards

                # Send completion with final data
                completion_data = {
                    'type': 'complete',
                    'final_text': accumulated_text,
                    'should_show_popup': should_show_popup,
                    'amber_responses': session_data.get('amber_responses', []) if should_show_popup else [],
                    'is_milestone': is_milestone,
                    'good_response_count': session_data.get('good_response_count', 0),
                    'sentence_count': session_data['sentences_count'],
                    'reward_points': session_data.get('reward_points', 0),
                    'new_rewards': new_rewards
                }
                yield f"data: {json.dumps(completion_data)}\n\n"

                # Update conversation history and session
                session_data['conversation_history'].extend([
                    {"role": "user", "content": transcript},
                    {"role": "assistant", "content": accumulated_text}
                ])

                # Update database if conversation exists (with proper app context)
                if 'conversation_id' in session_data:
                    try:
                        with app.app_context():
                            conversation = Conversation.query.get(session_data['conversation_id'])
                            if conversation:
                                conversation.sentences_count = session_data['sentences_count']
                                conversation.good_response_count = session_data.get('good_response_count', 0)
                                conversation.reward_points = session_data.get('reward_points', 0)
                                conversation.conversation_data = session_data['conversation_history']
                                conversation.amber_data = session_data.get('amber_responses', [])
                                conversation.updated_at = datetime.utcnow()
                                db.session.commit()
                    except Exception as e:
                        logger.error(f"Failed to update conversation in database: {e}")

                session_store.save_session(session_id, session_data)

            except Exception as e:
                logger.error(f"Streaming error: {str(e)}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                if temp_file:
                    try:
                        os.unlink(temp_file.name)
                    except Exception as e:
                        logger.error(f"Failed to delete temporary file: {e}")

        return Response(
            generate_streaming_response(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            }
        )

    except Exception as e:
        logger.error(f"Process Stream Error: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/clear_amber_responses', methods=['POST'])
def clear_amber_responses():
    """Clear amber responses from session after correction popup"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400
        
        session_data = session_store.load_session(session_id)
        if not session_data:
            return jsonify({'error': 'Invalid session'}), 400
        
        # Clear amber responses
        session_data['amber_responses'] = []
        session_store.save_session(session_id, session_data)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error clearing amber responses: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/correction_stt', methods=['POST'])
def correction_speech_to_text():
    """STT-only endpoint for correction attempts (doesn't affect conversation)"""
    correction_start_time = time.time()
    logger.info("🔄 CORRECTION STT: Request started")
    
    temp_file = None
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file'}), 400
        
        # Use tempfile for secure file handling
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)

            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read())
        
        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        correction_end_time = time.time()
        total_time = (correction_end_time - correction_start_time) * 1000
        logger.info(f"✅ CORRECTION STT: Complete in {total_time:.1f}ms")

        return jsonify({
            'transcript': transcript
        })
        
    except Exception as e:
        logger.error(f"Correction STT Error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        if temp_file:
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.error(f"Failed to delete temporary file: {e}")

@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard_data():
    """API endpoint for dashboard analytics"""
    try:
        # Get week parameter (0 = this week, 1 = last week)
        week = request.args.get('week', '0')
        weeks_ago = int(week)
        
        # Get analytics for the specified week
        stats = AnalyticsHelper.get_weekly_stats(current_user.id, weeks_ago)
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"Dashboard API error: {e}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500

@app.route('/api/dashboard/comparison', methods=['GET'])
@login_required
def get_dashboard_comparison():
    """API endpoint for week-to-week comparison"""
    try:
        comparison = AnalyticsHelper.get_comparison_stats(current_user.id)
        return jsonify({
            'success': True,
            'data': comparison
        })
        
    except Exception as e:
        logger.error(f"Dashboard comparison API error: {e}")
        return jsonify({'error': 'Failed to fetch comparison data'}), 500

@app.route('/api/conversation-history', methods=['GET'])
@login_required
def get_conversation_history():
    """API endpoint to fetch conversation history for last 15 days"""
    try:
        # Calculate date 15 days ago
        fifteen_days_ago = datetime.now() - timedelta(days=15)
        
        # Query conversations from last 15 days for current user
        conversations = Conversation.query.filter(
            Conversation.user_id == current_user.id,
            Conversation.created_at >= fifteen_days_ago
        ).order_by(Conversation.created_at.desc()).all()
        
        # Format conversation data for frontend
        conversation_list = []
        for conv in conversations:
            # Get last message preview from conversation history
            last_message = ""
            if conv.conversation_history:
                try:
                    history = json.loads(conv.conversation_history)
                    if history and len(history) > 0:
                        # Get the last user message
                        for msg in reversed(history):
                            if msg.get('role') == 'user':
                                last_message = msg.get('content', '')[:50] + "..." if len(msg.get('content', '')) > 50 else msg.get('content', '')
                                break
                except:
                    last_message = "Conversation started"
            
            # Map conversation type to display info
            type_info = {
                'everyday': {'name': 'Everyday Life', 'icon': '🏠'},
                'animals_nature': {'name': 'Animals and Nature', 'icon': '🦊'},
                'adventure_story': {'name': 'Adventure Story', 'icon': '🗺️'},
                'panchatantra_story': {'name': 'Co-create the "Thirsty Crow" Panchatantra Story', 'icon': '📖'}
            }
            
            conv_type = type_info.get(conv.conversation_type, {'name': 'Conversation', 'icon': '💬'})
            
            conversation_list.append({
                'id': conv.id,
                'conversation_type': conv.conversation_type,
                'type_name': conv_type['name'],
                'type_icon': conv_type['icon'],
                'created_at': conv.created_at.isoformat(),
                'last_message_preview': last_message or "New conversation",
                'sentence_count': conv.sentences_count or 0,
                'reward_points': conv.reward_points or 0
            })
        
        return jsonify({
            'success': True,
            'conversations': conversation_list
        })
        
    except Exception as e:
        logger.error(f"Conversation history API error: {e}")
        return jsonify({'error': 'Failed to fetch conversation history'}), 500

@app.route('/api/resume_conversation', methods=['POST'])
@login_required
def resume_conversation():
    """API endpoint to resume an existing conversation"""
    try:
        data = request.json
        conversation_id = data.get('conversation_id')
        
        if not conversation_id:
            return jsonify({'error': 'Conversation ID is required'}), 400
        
        # Find the conversation and verify ownership
        conversation = Conversation.query.filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
        
        # Load conversation history
        conversation_history = []
        if conversation.conversation_history:
            try:
                conversation_history = json.loads(conversation.conversation_history)
            except:
                logger.error(f"Failed to parse conversation history for conversation {conversation_id}")
        
        # Create session ID for this resumed conversation
        session_id = f"resume_{conversation_id}_{int(time.time())}"
        
        # Store session data with all required fields
        session_data = {
            'conversation_id': conversation_id,
            'conversation_type': conversation.conversation_type,
            'conversation_history': conversation_history,
            'sentences_count': conversation.sentences_count or 0,
            'good_response_count': conversation.good_response_count or 0,
            'reward_points': conversation.reward_points or 0,
            'amber_responses': json.loads(conversation.amber_responses) if conversation.amber_responses else [],
            'created_at': datetime.now().isoformat()  # Add required created_at field
        }
        
        session_store.save_session(session_id, session_data)
        
        # For resumed conversations, we don't need to send a new message
        # The frontend will load the existing history and be ready for user input
        return jsonify({
            'session_id': session_id,
            'conversation_id': conversation_id,
            'conversation_type': conversation.conversation_type,
            'conversation_history': conversation_history,
            'text': None,  # No continuation message to avoid duplication
            'sentences_count': conversation.sentences_count or 0,
            'reward_points': conversation.reward_points or 0
        })
        
    except Exception as e:
        logger.error(f"Resume conversation API error: {e}")
        return jsonify({'error': 'Failed to resume conversation'}), 500

@app.route('/api/track', methods=['POST'])
def track_analytics():
    """API endpoint for frontend analytics tracking"""
    try:
        data = request.get_json() or {}
        action = data.get('action')
        page = data.get('page')
        metadata = data.get('metadata')
        
        if not action or not page:
            return jsonify({'error': 'Missing required fields: action, page'}), 400
        
        track_user_action(action, page, metadata)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error in analytics tracking: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard for analytics - basic auth protection"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != os.getenv('ADMIN_PASSWORD', 'admin123'):
        return authenticate()
    
    return render_template('admin_dashboard.html')

@app.route('/api/admin/funnel-stats')
def admin_funnel_stats():
    """API endpoint for funnel analytics data"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != os.getenv('ADMIN_PASSWORD', 'admin123'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)
        end_date = datetime.utcnow()
        
        stats = FunnelAnalytics.get_funnel_stats(start_date, end_date)
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting funnel stats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/user-activity/<int:user_id>')
def admin_user_activity(user_id):
    """API endpoint for specific user activity data"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != os.getenv('ADMIN_PASSWORD', 'admin123'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        stats = FunnelAnalytics.get_user_activity_stats(user_id)
        if not stats:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting user activity: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/all-users')
def admin_all_users():
    """API endpoint for all users list"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != os.getenv('ADMIN_PASSWORD', 'admin123'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        users = User.query.all()
        users_data = []
        
        for user in users:
            conversation_count = Conversation.query.filter(Conversation.user_id == user.id).count()
            last_conversation = Conversation.query.filter(Conversation.user_id == user.id).order_by(Conversation.created_at.desc()).first()
            
            users_data.append({
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'child_name': user.child_name,
                'created_at': user.created_at.isoformat(),
                'conversation_count': conversation_count,
                'last_conversation': last_conversation.created_at.isoformat() if last_conversation else None
            })
        
        return jsonify({'users': users_data})
        
    except Exception as e:
        logger.error(f"Error getting all users: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def authenticate():
    """Send a 401 response with WWW-Authenticate header"""
    return jsonify({'error': 'Unauthorized'}), 401, {'WWW-Authenticate': 'Basic realm="Admin Login Required"'}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check Redis connection if using Redis
        if hasattr(session_store, 'redis'):
            session_store.redis.ping()
        
        # Check database connection
        db.session.execute('SELECT 1')
        
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# Session storage interface
class SessionStore:
    def save_session(self, session_id, data):
        pass
    
    def load_session(self, session_id):
        pass
    
    def cleanup_old_sessions(self):
        pass

# File-based session storage for development
class FileSessionStore(SessionStore):
    def __init__(self):
        self.filename = 'sessions.json'
    
    def save_session(self, session_id, data):
        try:
            sessions = self.load_all_sessions()
            sessions[session_id] = {
                **data,
                'created_at': data['created_at'].isoformat() if isinstance(data.get('created_at'), datetime) else data.get('created_at')
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(sessions, f, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save session to file: {e}")

    def load_session(self, session_id):
        try:
            sessions = self.load_all_sessions()
            data = sessions.get(session_id)
            if data and 'created_at' in data:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            return data
        except Exception as e:
            logging.error(f"Failed to load session from file: {e}")
            return None

    def load_all_sessions(self):
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"Failed to load sessions from file: {e}")
            return {}

    def cleanup_old_sessions(self):
        try:
            sessions = self.load_all_sessions()
            current_time = datetime.now()
            sessions = {
                sid: data for sid, data in sessions.items()
                if current_time - datetime.fromisoformat(data['created_at']) < timedelta(hours=24)
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(sessions, f, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to cleanup sessions: {e}")


# Update your Redis connection in app.py
# Replace the existing RedisSessionStore class with this SSL-enabled version:
# Replace your existing RedisSessionStore class with this fixed version:

class RedisSessionStore(SessionStore):
    def __init__(self, redis_url):
        import redis
        
        # Parse the URL to determine if SSL is needed
        if redis_url.startswith('rediss://'):
            # Heroku Redis uses rediss:// for SSL connections
            # Use redis.from_url which handles SSL automatically
            self.redis = redis.from_url(redis_url, decode_responses=False)
        elif 'amazonaws.com' in redis_url or 'heroku' in redis_url:
            # For redis:// URLs that require SSL (older Heroku format)
            # Convert redis:// to rediss:// for SSL
            if redis_url.startswith('redis://'):
                redis_url = redis_url.replace('redis://', 'rediss://', 1)
            self.redis = redis.from_url(redis_url, decode_responses=False)
        else:
            # Local Redis without SSL
            self.redis = redis.from_url(redis_url, decode_responses=False)
    
    def save_session(self, session_id, data):
        try:
            data_copy = {
                **data,
                'created_at': data['created_at'].isoformat() if isinstance(data.get('created_at'), datetime) else data.get('created_at')
            }
            self.redis.setex(
                f"session:{session_id}",
                timedelta(hours=24),
                json.dumps(data_copy, ensure_ascii=False)
            )
            logger.info(f"Session saved successfully: {session_id}")
        except Exception as e:
            logger.error(f"Failed to save session to Redis: {e}")
            # Fallback to file storage if Redis fails
            fallback_store = FileSessionStore()
            fallback_store.save_session(session_id, data)

    def load_session(self, session_id):
        try:
            data = self.redis.get(f"session:{session_id}")
            if data:
                session_data = json.loads(data)
                if 'created_at' in session_data:
                    session_data['created_at'] = datetime.fromisoformat(session_data['created_at'])
                logger.info(f"Session loaded successfully: {session_id}")
                return session_data
            logger.warning(f"No session found for ID: {session_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to load session from Redis: {e}")
            # Try fallback to file storage
            fallback_store = FileSessionStore()
            return fallback_store.load_session(session_id)

    def cleanup_old_sessions(self):
        # Redis automatically handles expiration
        pass

# Also update your get_session_store function:
def get_session_store():
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        try:
            import redis
            logger.info(f"Attempting to connect to Redis...")
            store = RedisSessionStore(redis_url)
            # Test the connection
            store.redis.ping()
            logger.info("Redis connection successful")
            return store
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            logger.warning("Falling back to file storage")
            return FileSessionStore()
    return FileSessionStore()


# Initialize the appropriate session store
session_store = get_session_store()


def init_database():
    """Initialize database tables"""
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")


if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    app.run(host='0.0.0.0', port=port)