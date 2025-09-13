from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
import openai
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

# Import our models and auth
from models import db, User, Conversation, AnalyticsHelper
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
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///hindi_tutor.db')
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
openai.api_key = os.getenv('OPENAI_API_KEY')
SARVAM_API_KEY = os.getenv('SARVAM_API_KEY')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

# Conversation type configurations
CONVERSATION_TYPES = {
    'everyday': {
        'name': 'Everyday Life',
        'description': 'Daily activities, school, friends, and routine conversations',
        'system_prompts': {
            'initial': """You are a friendly Hindi tutor starting a conversation with a 6-year-old child, named {child_name}.
            Create a warm, engaging greeting and ask if they went to school today or what they did today in Hindi.
            Guidelines:
            1. Keep it short
            2. Use simple Hindi words
            3. Make it cheerful and inviting
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi tutor speaking with a 6-year-old child.
            Focus on everyday life topics: school, friends, family, daily activities, food, play, etc.
            Strategy: {strategy}
            Guidelines:
            1. If strategy is 'nudge_for_completeness': Gently encourage them to give a longer, complete answer
            2. If strategy is 'continue_conversation': Continue the natural conversation flow about everyday topics
            3. Keep responses short (max 20 words)
            4. Be curious about their daily life like a caring mother would.
            5. Ensure your Hindi response is grammatically correct and follows the correct sentence structure.
            6. Gently encourage them to give a longer, complete answer. For example, Ask a follow-up question to the child's single-word answer. If they say 'school', ask 'स्कूल में क्या किया?'."
            7. Basis the response of the kid, ask relevant follow-up questions. Make it fun and interesting for the kid.
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🏠',
        'tag': 'Popular'
    },
    'cartoons': {
        'name': 'Favorite Cartoons',
        'description': 'Talk about cartoon characters, shows, stories, and animated movies',
        'system_prompts': {
            'initial': """You are a friendly Hindi tutor starting a conversation with a 6-year-old child, named {child_name}.
            Create a warm, engaging greeting and ask about their favorite cartoons or animated characters in Hindi.
            Focus on cartoons, animated shows, characters, and stories.
            Guidelines:
            1. Keep it very short (max 10 words)
            2. Use simple Hindi words
            3. Make it cheerful and fun
            4. Ask about their favorite cartoon character or show
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi tutor speaking with a 6-year-old child.
            Focus on cartoon and animation topics: favorite characters, shows, stories, what they like about cartoons, etc.
            Strategy: {strategy}
            Guidelines:
            1. If strategy is 'nudge_for_completeness': Gently encourage them to give a longer, complete answer
            2. If strategy is 'continue_conversation': Continue the natural conversation flow about cartoons and characters
            3. Keep responses short (max 20 words)
            4. Be enthusiastic about their favorite cartoons
            5. Ask follow-up questions about characters, stories, what they like
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🎭',
        'tag': 'Fun'
    },
    'adventure_story': {
        'name': 'Adventure Story',
        'description': 'Create exciting adventure stories together in simple Hindi',
        'system_prompts': {
            'initial': """You are a friendly Hindi storytelling tutor starting an adventure story with a 6-year-old child, named {child_name}.
            Begin by suggesting we create an adventure story together in Hindi, and ask them to choose a main character or setting.
            You will co-create an adventure story where they contribute ideas and you guide the narrative.
            Guidelines:
            1. Keep it very short (max 10 words)
            2. Use simple Hindi words
            3. Make it exciting and engaging
            4. Ask them to contribute ideas for the adventure story
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi storytelling tutor co-creating an adventure story with a 6-year-old child.
            Help them build an exciting adventure story by asking for their input and expanding on their ideas.
            Strategy: {strategy}
            Guidelines:
            1. If strategy is 'nudge_for_completeness': Encourage them to add more details to the story
            2. If strategy is 'continue_conversation': Continue the story based on their input and ask what happens next
            3. Keep responses short (max 20 words)
            4. Use simple Hindi vocabulary suitable for children
            5. Make the story exciting with simple adventures (finding treasure, helping animals, exploring places)
            6. Always ask for their input: "What should happen next?" or "Who should they meet?"
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🗺️',
        'tag': 'Creative'
    },
    'mystery_story': {
        'name': 'Mystery Story',
        'description': 'Solve fun mysteries and create detective stories in simple Hindi',
        'system_prompts': {
            'initial': """You are a friendly Hindi storytelling tutor starting a mystery story with a 6-year-old child, named {child_name}.
            Begin by suggesting we solve a fun mystery together in Hindi, like finding a missing toy or solving a simple puzzle.
            You will co-create a child-friendly mystery where they help solve clues.
            Guidelines:
            1. Keep it very short (max 10 words)
            2. Use simple Hindi words
            3. Make it intriguing but not scary
            4. Ask them to help solve a simple mystery
            Return response in JSON format: {{"response": "Your Hindi greeting here"}}""",
            'conversation': """You are a friendly Hindi storytelling tutor co-creating a mystery story with a 6-year-old child.
            Help them solve a fun, child-friendly mystery by giving simple clues and asking for their detective ideas.
            Strategy: {strategy}
            Guidelines:
            1. If strategy is 'nudge_for_completeness': Encourage them to explain their detective thinking more
            2. If strategy is 'continue_conversation': Give them a clue and ask what they think happened or what to do next
            3. Keep responses short (max 20 words)
            4. Use simple Hindi vocabulary suitable for children
            5. Keep mysteries light and fun (missing toys, hidden treats, simple puzzles)
            6. Always ask for their detective input: "What clue should we look for?" or "What do you think happened?"
            Return JSON format: {{"response": "Your Hindi response here"}}"""
        },
        'icon': '🔍',
        'tag': 'Detective'
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
        client = openai.OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url="https://api.openai.com/v1",
            http_client=None
        )
        
        # Get the appropriate system prompt for the conversation type
        if conversation_type in CONVERSATION_TYPES:
            system_prompt = CONVERSATION_TYPES[conversation_type]['system_prompts']['initial'].format(child_name=child_name)
        else:
            # Fallback to everyday conversation
            system_prompt = CONVERSATION_TYPES['everyday']['system_prompts']['initial'].format(child_name=child_name)

        logger.info(f"Making OpenAI API call for initial {conversation_type} conversation")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={ "type": "json_object" },
            temperature=0.7,
            max_tokens=50
        )
        
        logger.info("OpenAI API call successful")
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
    def evaluate_response(user_text):
        """Evaluate user response and return score + analysis"""
        try:
            client = openai.OpenAI(
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url="https://api.openai.com/v1",
                http_client=None
            )
            
            system_prompt = f"""
            Evaluate this Hindi response from a 6-year-old child for:
            1. Completeness (is it a full sentence or just 1-2 words?)
            2. Grammar correctness in Hindi
            
            User response: "{user_text}"
            
            Return JSON format:
            {{
                "score": 1-10,
                "is_complete": true/false,
                "is_grammatically_correct": true/false,
                "issues": ["incomplete", "grammar_error"],
                "corrected_response": "grammatically correct version if needed",
                "feedback_type": "green/amber"
            }}
            
            Score guide:
            - 8-10: Complete, grammatically correct = green
            - 1-7: Incomplete or grammar issues = amber
            """
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=150
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
            client = openai.OpenAI(
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url="https://api.openai.com/v1",
                http_client=None
            )
            
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
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=100
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
            
            # Run evaluation and conversation response in PARALLEL
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both OpenAI API calls simultaneously
                eval_future = executor.submit(
                    self.evaluator.evaluate_response, 
                    user_text
                )
                
                conv_future = executor.submit(
                    self.talker.get_response,
                    session_data['conversation_history'],
                    user_text,
                    session_data['sentence_count'],
                    conversation_type
                )
                
                # Wait for both to complete
                evaluation = eval_future.result()
                conversation_response = conv_future.result()
            
            # Track good responses and handle amber responses
            if evaluation['feedback_type'] == 'green':
                session_data['good_response_count'] = session_data.get('good_response_count', 0) + 1
            elif evaluation['feedback_type'] == 'amber':
                amber_entry = {
                    'user_response': user_text,
                    'corrected_response': evaluation['corrected_response'],
                    'issues': evaluation['issues']
                }
                session_data.setdefault('amber_responses', []).append(amber_entry)
            
            # Check if correction popup should trigger (every 4 interactions, and we have amber responses)
            should_show_popup = (
                session_data['sentence_count'] % 4 == 0 and
                session_data['sentence_count'] > 0 and
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
            'sentence_count': 0,
            'good_response_count': 0,
            'reward_points': 0,
            'conversation_type': conversation_type,
            'amber_responses': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Save session once with complete data
        session_store.save_session(session_id, session_data)

        # Add initial message
        session_data['conversation_history'].append({
            'role': 'assistant',
            'content': initial_message
        })

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

def speech_to_text_hindi(audio_data):
    """Convert Hindi speech to text using Sarvam AI"""
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
            
        # Use GPT-4 for translation
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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
        logger.info(f"Current sentence count: {session_data['sentence_count']}")

        # Simply increment sentence count by 1 for each user interaction
        session_data['sentence_count'] += 1
        logger.info(f"Updated sentence count: {session_data['sentence_count']}")
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
                    conversation.sentences_count = session_data['sentence_count']
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
            'sentence_count': session_data['sentence_count'],
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
            with open(self.filename, 'w') as f:
                json.dump(sessions, f)
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
                with open(self.filename, 'r') as f:
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
            with open(self.filename, 'w') as f:
                json.dump(sessions, f)
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
                json.dumps(data_copy)
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