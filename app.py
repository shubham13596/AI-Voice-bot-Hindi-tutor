from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, Response
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
import openai
from groq import Groq
import google.generativeai as genai
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
import numpy as np
from google.cloud import speech
from datetime import datetime, timedelta
import json
import tempfile
import time
import concurrent.futures
import random
from conversation_config import CONVERSATION_TYPES, MODULES, TOPICS

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
GOOGLE_CLOUD_API_KEY = os.getenv('GOOGLE_CLOUD_API_KEY')

# Setup Google Cloud credentials from environment variable
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS')
if GOOGLE_CREDENTIALS_JSON:
    try:
        # Write credentials to a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(GOOGLE_CREDENTIALS_JSON)
            credentials_path = f.name
        # Set the environment variable for Google Cloud SDK
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        logger.info(f"Google Cloud credentials configured from environment variable")
    except Exception as e:
        logger.error(f"Failed to configure Google Cloud credentials: {e}")

STT_PROVIDER = os.getenv('STT_PROVIDER', 'sarvam')  # Default to sarvam (options: sarvam, groq, google)

# Initialize Groq client
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Groq client: {e}")
    raise

# Initialize Gemini client
try:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables")

    genai.configure(api_key=GEMINI_API_KEY)

    # Configure safety settings to be less restrictive for educational content
    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE",
        },
    ]

    # Create Gemini model instance
    gemini_model = genai.GenerativeModel(
        model_name='gemini-2.0-flash-lite',
        safety_settings=safety_settings
    )
    logger.info("Gemini client initialized successfully with model: gemini-2.0-flash-lite")
except Exception as e:
    logger.error(f"Failed to initialize Gemini client: {e}")
    raise


# Module metadata with Hindi names, English names, taglines, and colors
MODULES = {
    'main_aur_meri_baatein': {
        'name_hindi': 'मैं और मेरी बातें ',
        'name_english': 'Me and My World',
        'tagline': 'Because every conversation starts with "me"',
        'color': '#EEF4FA'
    },
    'mera_parivaar': {
        'name_hindi': 'मेरा परिवार ',
        'name_english': 'My Family',
        'tagline': 'Because Hindi has words for family that English doesn\'t',
        'color': '#FDEEE9'
    },
    'khana_peena': {
        'name_hindi': 'खाना-पीना',
        'name_english': 'Food & Eating',
        'tagline': 'Because food is how we carry culture across oceans',
        'color': '#F0F5F1'
    },
    'tyohaar': {
        'name_hindi': 'त्योहार',
        'name_english': 'Festivals & Celebrations',
        'tagline': 'Celebrate the joy and colors of our culture',
        'color': '#FEF3E2'
    },
    'bahar_ki_duniya': {
        'name_hindi': 'बाहर की दुनिया',
        'name_english': 'The World Outside',
        'tagline': 'From peacocks to monsoons - the world in Hindi',
        'color': '#E8F5F0'
    },
    'kahaniyan': {
        'name_hindi': 'कहानियाँ',
        'name_english': 'Stories & Tales',
        'tagline': 'Timeless wisdom wrapped in enchanting tales',
        'color': '#F5F3F9'
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

# Farewell keywords for early termination detection
FAREWELL_KEYWORDS = [
    'bye', 'goodbye', 'bye bye', 'byebye',
    'अलविदा', 'बाय', 'टाटा', 'फिर मिलेंगे', 'चलता हूँ', 'चलती हूँ',
    'बाय बाय', 'गुडबाय'
]

def detect_farewell(transcript):
    """Check if the user's message contains farewell keywords"""
    if not transcript:
        return False
    transcript_lower = transcript.lower().strip()
    for keyword in FAREWELL_KEYWORDS:
        if keyword in transcript_lower:
            logger.info(f"👋 Farewell detected! Keyword '{keyword}' found in transcript: '{transcript}'")
            return True
    return False

def get_phase_instruction(sentences_count, is_farewell=False):
    """Get phase-appropriate instruction based on conversation progress"""
    
    if is_farewell:
        return """
IMPORTANT - FINAL RESPONSE:
The child is saying goodbye. This is your FINAL response.
- Give a warm, affectionate goodbye
- Summarize one thing you enjoyed talking about
- Keep it short and sweet
- Do NOT ask any new questions
"""
    
    if sentences_count >= 10:
        return """
IMPORTANT - FINAL RESPONSE:
This is your FINAL response in this conversation.
- Give a warm, affectionate goodbye
- Briefly mention something nice from the conversation
- Give them a fun "homework": something to ask Mummy/Papa basis the discussion you had; for example: if the discussion was about favorite colors, the homework to the child can be to ask mom what her favorite color is.
- Do NOT ask any new questions
- Make the child feel proud and successful
"""
    
    if sentences_count == 9:
        return f"""
CONVERSATION PHASE - WRAPPING UP:
You are nearing the end of this conversation.
- Start wrapping up warmly over the next 1-2 exchanges
- You can still ask one small follow-up question
- Begin transitioning toward a natural conclusion
- Think about what parent connection you'll suggest at the end
"""
    
    # Early/mid conversation - no special instruction needed
    return ""

def gemini_generate_content(system_prompt, conversation_history=None, response_format="json"):
    """
    Generate content using Gemini with optional JSON formatting

    Args:
        system_prompt: The system prompt
        conversation_history: Optional list of previous messages
        response_format: "json" or "text"
    """
    try:
        # Build the prompt with conversation history
        full_prompt = system_prompt

        if conversation_history:
            full_prompt += "\n\nConversation history:\n"
            for msg in conversation_history:
                role = "Child" if msg["role"] == "user" else "Tutor"
                full_prompt += f"{role}: {msg['content']}\n"

        # Configure generation settings
        generation_config = {
            "temperature": 0.7,
            "max_output_tokens": 1000,
        }

        # Add JSON mode if requested
        if response_format == "json":
            generation_config["response_mime_type"] = "application/json"
            # IMPORTANT: Don't use stop_sequences with JSON mode as they can truncate the JSON
        else:
            # Only use stop_sequences for non-JSON responses
            generation_config["stop_sequences"] = ["Child:", "User:", "Tutor:", "Assistant:"]

        # Generate content
        response = gemini_model.generate_content(
            full_prompt,
            generation_config=generation_config
        )

        # Validate JSON response if in JSON mode
        if response_format == "json":
            # Try to parse to ensure it's valid JSON
            try:
                json.loads(response.text)
            except json.JSONDecodeError as json_err:
                logger.error(f"Invalid JSON from Gemini: {response.text[:200]}")
                raise ValueError(f"Gemini returned invalid JSON: {json_err}")

        return response.text

    except Exception as e:
        logger.error(f"Gemini generation error: {e}")
        raise

def gemini_stream_content(system_prompt, conversation_history=None):
    """
    Stream content using Gemini (for plain text responses, not JSON)

    Args:
        system_prompt: The system prompt
        conversation_history: Optional list of previous messages

    Yields:
        Text chunks from Gemini
    """
    try:
        # Build the prompt with conversation history
        full_prompt = system_prompt

        if conversation_history:
            full_prompt += "\n\nConversation history:\n"
            for msg in conversation_history:
                role = "Child" if msg["role"] == "user" else "Tutor"
                full_prompt += f"{role}: {msg['content']}\n"

        # Configure generation settings for streaming
        generation_config = {
            "temperature": 0.6,
            "max_output_tokens": 1000,
            "stop_sequences": ["Child:", "User:", "Tutor:", "Assistant:"]
        }

        # Generate content with streaming
        response = gemini_model.generate_content(
            full_prompt,
            generation_config=generation_config,
            stream=True
        )

        # Yield chunks
        for chunk in response:
            if chunk.text:
                yield chunk.text

    except Exception as e:
        logger.error(f"Gemini streaming error: {e}")
        raise

def get_streaming_system_prompt(base_prompt, sentences_count, child_name, child_age, child_gender, is_farewell=False):
    """
    Transform the base conversation prompt for streaming:
    1. Remove JSON format requirement
    2. Add phase-appropriate instructions
    """
    
    # Remove the JSON format instruction (after .format() is called, {{ becomes {)
    json_instruction = """RESPONSE FORMAT (CRITICAL - FOLLOW EXACTLY):
Return a JSON object with this exact structure:
{
  "response": "Your Devanagari Hindi response here",
  "hints": ["हिंट"],
  "should_end": false
}

Fields:
- "response": Your conversational response in Devanagari Hindi only (max 20 words)
- "hints": A possible response the child could say next (in Devanagari)
- "should_end": Set to true ONLY when conversation should naturally conclude"""
    
    streaming_instruction = """RESPONSE FORMAT:
Respond ONLY with your conversational response in Devanagari Hindi (max 15 words).
Do NOT use JSON format. Do NOT include any metadata or field names.
Just write the Hindi text directly - nothing else."""

    # IMPORTANT: Format first (to convert {{ to {), then replace
    # Format with child details
    formatted_prompt = base_prompt.format(
        strategy="continue_conversation",
        child_name=child_name,
        child_gender=child_gender,
        child_age=child_age,
        exchange_number=sentences_count
    )

    # Now replace JSON instruction with streaming instruction
    modified_prompt = formatted_prompt.replace(json_instruction, streaming_instruction)

    # Debug: Log if replacement worked
    if json_instruction in formatted_prompt:
        logger.info("✅ Found and replaced JSON instruction for streaming")
    else:
        logger.warning("❌ JSON instruction NOT found - replacement didn't work!")

    # Log a sample of the final prompt to verify
    logger.info(f"📝 Streaming prompt sample (first 500 chars): {modified_prompt[:500]}...")

    # Get phase-specific instruction
    phase_instruction = get_phase_instruction(sentences_count, is_farewell)

    # Add phase instruction if we have one
    if phase_instruction:
        modified_prompt = phase_instruction + "\n\n" + modified_prompt
    
    return modified_prompt

def generate_hints(conversation_history, conversation_type, child_name, child_age):
    """Generate hint suggestions for what the child could say next using Gemini"""
    try:
        hints_prompt = f"""You are helping a {child_age}-year-old child learning Hindi.
Based on the conversation so far, suggest ONLY 1 simple Hindi sentence the child could say next.

Rules:
- Use Devanagari script ONLY (no romanized Hindi)
- Keep sentence simple (8-10 words max)
- Make them age-appropriate for a {child_age}-year-old
- Sentence should be a NATURAL RESPONSE to the LAST ASSISTANT message

RESPONSE FORMAT (CRITICAL - FOLLOW EXACTLY):
Return a JSON object with this exact structure:
{{
  "hint": "Your Devanagari Hindi hint here"
}}

Example: {{"hint": "मुझे पिज़्ज़ा पसंद है"}}
"""

        # Get last few exchanges for context
        recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history

        # Use Gemini for hint generation
        result = gemini_generate_content(
            system_prompt=hints_prompt,
            conversation_history=recent_history,
            response_format="json"
        )

        logger.info(f"Raw hints response: {result[:200]}")

        # Parse the JSON response
        hints_data = json.loads(result)

        # Simplified parsing logic to match the structure
        if "hint" in hints_data:
            hint_text = hints_data["hint"]
            # Validate that the hint is not empty
            if hint_text and hint_text.strip():
                return [hint_text]
            else:
                logger.warning("Empty hint returned from Gemini")
                return []
        elif "hints" in hints_data and isinstance(hints_data["hints"], list):
             # Fallback if model decides to use a list anyway
            return hints_data["hints"][:1]
        else:
            logger.warning(f"Unexpected hints response structure: {hints_data}")
            return []

    except json.JSONDecodeError as json_err:
        logger.error(f"Error parsing hints JSON: {json_err}")
        logger.error(f"Raw response was: {result if 'result' in locals() else 'No result'}")
        return []
    except Exception as e:
        logger.error(f"Error generating hints: {e}")
        return []


def get_initial_conversation(child_name="दोस्त", child_age=6, child_gender="neutral", conversation_type="everyday"):
    """Generate initial conversation starter based on conversation type"""
    try:
        # Get the appropriate system prompt for the conversation type
        if conversation_type in CONVERSATION_TYPES:
            system_prompt = CONVERSATION_TYPES[conversation_type]['system_prompts']['initial'].format(
                child_name=child_name,
                child_age=child_age,
                child_gender=child_gender,
                exchange_number=1
            )
        else:
            # Fallback to everyday conversation
            system_prompt = CONVERSATION_TYPES['everyday']['system_prompts']['initial'].format(
                child_name=child_name,
                child_age=child_age,
                child_gender=child_gender,
                exchange_number=1
            )

        logger.info(f"Making Gemini API call for initial {conversation_type} conversation")

        # Use Gemini to generate initial greeting with JSON format
        raw_content = gemini_generate_content(
            system_prompt=system_prompt,
            conversation_history=None,
            response_format="json"
        )

        logger.info("Gemini API call successful")
        logger.info(f"Raw LLM response: {raw_content[:200]}")
        result = json.loads(raw_content)
        return result.get('response', "नमस्ते! कैसा है आपका दिन?")
        
    except Exception as e:
        logger.error(f"Error in initial conversation: {str(e)}")
        return "नमस्ते! कैसा है आपका दिन?"  # Fallback greeting


def show_completion_page():
    """Function to be called when structured conversation is complete"""
    return {
        "action": "redirect",
        "page": "completion_celebration",
        "message": "बहुत बढ़िया! तुमने सभी सवालों के जवाब दिए!"
    }


def calculate_rewards(evaluation_result, good_response_count):
    """Calculate reward points based on response quality"""
    points = 0
    
    # Award points only for good quality responses
    if evaluation_result.get('feedback_type') == 'green':
        points = 10  # Base points for good response
        
        # Bonus for milestones (every 5 good responses)
        if good_response_count % 5 == 0 and good_response_count > 0:
            points += 20  # Milestone bonus
    
    return points

class ResponseEvaluator:
    """Evaluates user responses for completeness and grammar"""
    
    @staticmethod
    def evaluate_response(user_text, last_talker_response=None):
        """Evaluate user response and return corrected answer using Gemini"""
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
            1. Completeness (is it a sentence or just 1 word?) and grammar correctness in Hindi from a CONVERSATIONAL perspective; NOT from a WRITTEN Hindi perspective.
            2. Don't evaluate from an answer correctness point of view. If the kid says he doesn't know or gives the wrong answer to the question, but the sentece is conversationally correct, then feedback_type should be green.
            3. EXAMPLES:
            हमने दिया जलाना अच्छा लगता है। -> This sentence should be given a low score since the correct form is हमें दीये जलाना अच्छा लगता है।

            {context_section}

            Return JSON format:
            {{{{
                "score": 1-10,
                "is_complete": true/false,
                "is_grammatically_correct": true/false,
                "issues": ["incomplete", "grammar_error"],
                "corrected_response": "grammatically correct answer - keep this short and crisp",
                "feedback_type": "green/amber"
            }}}}

            Score guide:
            - 7-10: Complete, grammatically correct = green
            - 1-6: Incomplete, grammar issues = amber

            For the corrected_response, provide a short, crisp sentence in Hindi that is appropriate for a 6-8 year-old's vocabulary
            """

            # Use Gemini for evaluation
            result = gemini_generate_content(
                system_prompt=system_prompt,
                conversation_history=None,
                response_format="json"
            )

            evaluation_data = json.loads(result)

            # Validate that all required fields are present
            required_fields = ["score", "is_complete", "is_grammatically_correct", "issues", "corrected_response", "feedback_type"]
            if not all(field in evaluation_data for field in required_fields):
                logger.warning(f"Incomplete evaluation data, missing fields. Got: {evaluation_data.keys()}")
                raise ValueError("Incomplete evaluation response from Gemini")

            return evaluation_data

        except json.JSONDecodeError as json_err:
            logger.error(f"Error parsing evaluation JSON: {json_err}")
            logger.error(f"Raw response was: {result if 'result' in locals() else 'No result'}")
            return {
                "score": 5,
                "is_complete": True,
                "is_grammatically_correct": True,
                "issues": [],
                "corrected_response": user_text,
                "feedback_type": "green"
            }
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
    def get_response(conversation_history, user_text, sentence_count, conversation_type="everyday", child_name="दोस्त", child_age=6, child_gender="neutral"):
        """Generate conversation response based on conversation type using Gemini"""
        try:

            # Always use continue_conversation strategy for simplicity and speed
            strategy = "continue_conversation"

            # Get the appropriate system prompt for the conversation type
            if conversation_type in CONVERSATION_TYPES:
                system_prompt_template = CONVERSATION_TYPES[conversation_type]['system_prompts']['conversation']
            else:
                # Fallback to everyday conversation
                system_prompt_template = CONVERSATION_TYPES['everyday']['system_prompts']['conversation']

            system_prompt = system_prompt_template.format(
                strategy=strategy,
                child_name=child_name,
                child_gender=child_gender,
                child_age=child_age,
                exchange_number=sentence_count
            )

            # Prepare history with user message
            history_with_user = conversation_history + [{"role": "user", "content": user_text}]

            # Use Gemini for conversation response
            result = gemini_generate_content(
                system_prompt=system_prompt,
                conversation_history=history_with_user,
                response_format="json"
            )

            return json.loads(result)  # Return full object with response, hints, should_end

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
            child_name = session_data.get('child_name', 'दोस्त')
            child_age = session_data.get('child_age', 6)
            child_gender = session_data.get('child_gender', 'Male')

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
                    conversation_type,
                    child_name,
                    child_age,
                    child_gender
                )
                
                # Wait for both to complete
                evaluation = eval_future.result()
                conversation_response = conv_future.result()

            # Check if conversation should end
            should_end = conversation_response.get('should_end', False) if isinstance(conversation_response, dict) else False

            # If conversation should end, return completion page
            if should_end:
                return show_completion_page()

            # Extract just the text response for backwards compatibility
            response_text = conversation_response.get('response') if isinstance(conversation_response, dict) else conversation_response

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
                session_data['sentences_count'] % 4 == 0 and
                session_data['sentences_count'] > 0 and
                len(session_data.get('amber_responses', [])) > 0
            )

            # Calculate milestone status for celebration
            is_milestone = (
                evaluation['feedback_type'] == 'green' and
                session_data['good_response_count'] % 5 == 0 and
                session_data['good_response_count'] > 0
            )

            result = {
                'response': response_text,
                'evaluation': evaluation,
                'should_show_popup': should_show_popup,
                'amber_responses': session_data.get('amber_responses', []) if should_show_popup else [],
                'is_milestone': is_milestone,
                'good_response_count': session_data.get('good_response_count', 0),
                'should_end': should_end
            }

            return result
            
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
        
        # Use the authenticated user's child data
        child_name = current_user.child_name or 'दोस्त'
        child_age = current_user.child_age or 6
        child_gender = current_user.child_gender or 'neutral'

        initial_message = get_initial_conversation(child_name, child_age, child_gender, conversation_type)
        
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
            'child_name': child_name,
            'child_age': child_age,
            'child_gender': child_gender,
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
                        stability=0.8,
                        similarity_boost=0.7,
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


def validate_audio_duration(audio_data, min_duration=0.05, max_duration=15.0):
    """Validate audio duration to filter out noise and incomplete recordings"""
    try:
        # Estimate duration: 16-bit mono audio at 44.1kHz (standard WAV)
        # Each sample is 2 bytes, so duration = bytes / (2 * sample_rate)
        estimated_duration = len(audio_data) / (2 * 44100)

        if estimated_duration < min_duration:
            logger.info(f"🔇 AUDIO VALIDATION: Too short ({estimated_duration:.2f}s < {min_duration}s) - likely noise")
            return False
        elif estimated_duration > max_duration:
            logger.info(f"🔇 AUDIO VALIDATION: Too long ({estimated_duration:.2f}s > {max_duration}s) - likely incomplete")
            return False
        else:
            logger.info(f"✅ AUDIO VALIDATION: Duration OK ({estimated_duration:.2f}s)")
            return True

    except Exception as e:
        logger.warning(f"⚠️ AUDIO VALIDATION: Could not estimate duration - {str(e)}")
        return True  # Default to allowing audio if validation fails


# Audio optimization functions for Google Cloud STT
def trim_audio_silence(audio_data):
    """
    Remove silence from beginning and end of audio to reduce processing time
    """
    try:
        # Convert audio data to numpy array for processing
        audio_array = np.frombuffer(audio_data, dtype=np.uint8)

        # Find first and last non-zero bytes (rough silence detection)
        # Use a threshold to identify "silence" (low amplitude)
        silence_threshold = 10
        non_silence_indices = np.where(audio_array > silence_threshold)[0]

        if len(non_silence_indices) > 0:
            # Keep small buffer around speech to avoid cutting off words
            buffer_size = 100
            start_idx = max(0, non_silence_indices[0] - buffer_size)
            end_idx = min(len(audio_data), non_silence_indices[-1] + buffer_size)

            trimmed_audio = audio_data[start_idx:end_idx]

            # Log reduction if significant
            original_size = len(audio_data) / 1024
            trimmed_size = len(trimmed_audio) / 1024
            reduction_percent = ((original_size - trimmed_size) / original_size) * 100

            if reduction_percent > 10:  # Only log if significant reduction
                logger.info(f"🔇 Audio trimmed: {original_size:.1f}KB → {trimmed_size:.1f}KB ({reduction_percent:.1f}% reduction)")
                return trimmed_audio

        return audio_data

    except Exception as e:
        logger.warning(f"⚠️ Audio trimming failed, using original: {e}")
        return audio_data

def optimize_audio_for_google_cloud(audio_data):
    """
    Apply optimizations for Google Cloud Speech-to-Text
    """
    try:
        # Apply silence trimming
        optimized_audio = trim_audio_silence(audio_data)

        # Additional optimizations to be added here
        # (e.g., audio format conversion, noise reduction)

        return optimized_audio

    except Exception as e:
        logger.warning(f"⚠️ Audio optimization failed, using original: {e}")
        return audio_data

# Initialize Google Cloud Speech client with connection pooling
google_speech_client = None
if GOOGLE_CLOUD_API_KEY:
    try:
        # Initialize client for connection pooling (SDK handles API key authentication automatically)
        google_speech_client = speech.SpeechClient()
        logger.info("Google Cloud Speech client initialized successfully")
    except Exception as e:
        logger.warning(f"Google Cloud Speech client initialization failed: {e}")
        logger.info("Will fallback to REST API with API key")

def speech_to_text_hindi_google(audio_data):
    """Convert Hindi speech to text using Google Cloud Speech-to-Text with optimizations"""
    stt_start_time = time.time()
    logger.info("🎙️ GOOGLE CLOUD STT: Starting transcription...")

    try:
        # Validate audio duration (same as other providers)
        audio_duration = len(audio_data) / (48000 * 2)  # Assuming 16kHz, 16-bit
        if audio_duration < 0.05 or audio_duration > 30:
            logger.info("❌ GOOGLE CLOUD STT: Audio rejected due to invalid duration")
            return None

        if not google_speech_client:
            logger.error("❌ GOOGLE CLOUD STT: No API key configured")
            return None

        # Apply audio optimizations
        preprocessing_start = time.time()
        optimized_audio = optimize_audio_for_google_cloud(audio_data)
        preprocessing_time = (time.time() - preprocessing_start) * 1000

        audio_size_kb = len(optimized_audio) / 1024
        logger.info(f"📁 Optimized audio size: {audio_size_kb:.1f} KB (preprocessing: {preprocessing_time:.1f}ms)")

        # Configure recognition with optimized settings for Hindi child speech
        config = speech.RecognitionConfig(
            encoding = speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz = 48000,  # Google's recommended optimal rate
            language_code = "hi-IN",    # Hindi (India)
            # Alternative languages for code-switching
            # alternative_language_codes=["en-IN", "en-US"],
            model = "latest_long",      # Latest model for better accuracy
            use_enhanced = True,        # Enhanced model if available
            enable_automatic_punctuation = True,
            audio_channel_count = 1,
            # This helps with mixed language
            enable_spoken_punctuation=False,
            enable_spoken_emojis=False,
            # Optimization for child speech
            speech_contexts=[
                speech.SpeechContext(
                    phrases=["स्कूल", "घर", "माँ", "पापा", "खेल", "किताब", "दोस्त", "खुश", "अच्छा", "बुरा","सबीर", "मोर", "ऊँट", "बाघ", "मई",
                    
                    # Family (Module 2) - High priority since these are unique Hindi terms
                    "मौसी", "मौसा", "बुआ", "फूफा", "भाई", "बहन",
                    
                    # Common verbs kids will use
                    "सुनना", "बोलना",
                    
                    # Food (Module 3) - Very common in conversations
                    "सब्ज़ी", "दूध", "फल", "मिठाई",
                    
                    # Festivals (Module 4)
                    "दिवाली", "होली", "राखी", "दीया", "पटाखे", "गुलाल",
                    
                    # Animals (Module 5)
                    "चिड़िया",
                    
                    # Story-specific (Module 6)
                    "कहानी", "जंगल", "मगरमच्छ", "जामुन", "कुआँ", "परछाई",
                    
                    # Places
                    "पार्क", "मंदिर", "दुकान"
                ]
                )
            ]
        )

        # Create audio object
        audio = speech.RecognitionAudio(content=optimized_audio)

        # Make API request with timing
        api_start_time = time.time()
        try:
            response = google_speech_client.recognize(config=config, audio=audio)
        except Exception as api_error:
            # If SDK fails (authentication, credentials, etc.), fallback to REST API
            error_msg = str(api_error).lower()
            if any(keyword in error_msg for keyword in ["authentication", "credentials", "permission", "forbidden"]):
                logger.info("🔄 GOOGLE CLOUD STT: SDK authentication failed, trying REST API with API key...")
                return speech_to_text_hindi_google_rest(optimized_audio, stt_start_time)
            else:
                raise api_error

        api_end_time = time.time()
        api_response_time = (api_end_time - api_start_time) * 1000

        # Extract transcription
        transcription = None
        if response.results:
            for result in response.results:
                if result.alternatives:
                    transcription = result.alternatives[0].transcript
                    break

        if not transcription:
            logger.warning("❌ GOOGLE CLOUD STT: No transcription in response")
            return None

        # Calculate total processing time
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000

        # Log performance metrics (same format as other providers)
        logger.info(f"⚡ API Response Time: {api_response_time:.1f}ms")
        logger.info(f"✅ GOOGLE CLOUD STT: Success! Total time: {total_latency:.1f}ms")
        logger.info(f"📊 Audio/Time Ratio: {audio_size_kb/(total_latency/1000):.1f} KB/sec")

        return transcription.strip()

    except Exception as e:
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000
        logger.error(f"❌ GOOGLE CLOUD STT: Failed after {total_latency:.1f}ms - {str(e)}")
        return None

def speech_to_text_hindi_google_rest(audio_data, stt_start_time):
    """Fallback REST API implementation for Google Cloud Speech-to-Text"""
    try:
        logger.info("🌐 GOOGLE CLOUD STT: Using REST API with API key...")

        # Encode audio as base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Prepare request payload
        payload = {
            "config": {
                "encoding": "WEBM_OPUS",
                "sampleRateHertz": 48000,
                "languageCode": "hi-IN",
                "model": "latest_long",
                "useEnhanced": True,
                "enableAutomaticPunctuation": True,
                "audioChannelCount": 1
            },
            "audio": {
                "content": audio_base64
            }
        }

        # Make REST API request
        api_start_time = time.time()
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_CLOUD_API_KEY
        }

        response = requests.post(
            "https://speech.googleapis.com/v1/speech:recognize",
            headers=headers,
            json=payload,
            timeout=10
        )

        api_end_time = time.time()
        api_response_time = (api_end_time - api_start_time) * 1000

        response.raise_for_status()
        result = response.json()

        # Extract transcription
        transcription = None
        if "results" in result and result["results"]:
            for res in result["results"]:
                if "alternatives" in res and res["alternatives"]:
                    transcription = res["alternatives"][0].get("transcript")
                    break

        if not transcription:
            logger.warning("❌ GOOGLE CLOUD STT REST: No transcription in response")
            return None

        # Calculate total processing time
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000

        logger.info(f"⚡ API Response Time: {api_response_time:.1f}ms")
        logger.info(f"✅ GOOGLE CLOUD STT REST: Success! Total time: {total_latency:.1f}ms")

        return transcription.strip()

    except Exception as e:
        stt_end_time = time.time()
        total_latency = (stt_end_time - stt_start_time) * 1000
        logger.error(f"❌ GOOGLE CLOUD STT REST: Failed after {total_latency:.1f}ms - {str(e)}")
        return None

def speech_to_text_hindi(audio_data):
    """Convert Hindi speech to text using the configured STT provider"""
    if STT_PROVIDER.lower() == 'groq':
        return speech_to_text_hindi_groq(audio_data)
    elif STT_PROVIDER.lower() == 'google':
        return speech_to_text_hindi_google(audio_data)
    else:
        return speech_to_text_hindi_sarvam(audio_data)

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

    # Organize topics by module
    modules_data = {}
    for topic_key, topic_data in CONVERSATION_TYPES.items():
        module_key = topic_data.get('module')
        if module_key not in modules_data:
            modules_data[module_key] = {
                'metadata': MODULES[module_key],
                'topics': []
            }
        modules_data[module_key]['topics'].append({
            'key': topic_key,
            **topic_data
        })

    return render_template('conversation_select.html', modules=modules_data, module_order=['main_aur_meri_baatein', 'mera_parivaar', 'khana_peena', 'tyohaar', 'bahar_ki_duniya'])

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

@app.route('/completion_celebration')
@login_required
def completion_celebration():
    """Celebration page for completing structured conversations"""
    completed_topic = request.args.get('topic', None)
    related_topics = []

    if completed_topic and completed_topic in CONVERSATION_TYPES:
        # Find which module this topic belongs to
        completed_topic_module = CONVERSATION_TYPES[completed_topic].get('module')

        if completed_topic_module:
            # Find all other topics in the same module
            for topic_id, topic_data in CONVERSATION_TYPES.items():
                if (topic_data.get('module') == completed_topic_module and
                    topic_id != completed_topic):
                    related_topics.append({
                        'id': topic_id,
                        'title_en': topic_data.get('name'),
                        'title_hi': topic_data.get('name')  # Use same name for both
                    })

    return render_template('completion_celebration.html',
                         related_topics=related_topics,
                         completed_topic=completed_topic)

@app.route('/about')
def about():
    """About page - combines mission and contact - accessible to all users"""
    return render_template('about.html')

@app.route('/mission')
def mission():
    """Redirect old mission URL to about page"""
    return redirect(url_for('about'))

@app.route('/contact')
def contact():
    """Redirect old contact URL to about page"""
    return redirect(url_for('about'))

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

        # Use Gemini for translation
        system_prompt = f"""You are a translator. Translate the given text to English. Provide only the translation, no additional text.

Text to translate: {text}"""

        # Use Gemini streaming for translation (faster response)
        translation_chunks = []
        for chunk in gemini_stream_content(system_prompt, conversation_history=None):
            translation_chunks.append(chunk)

        translation = ''.join(translation_chunks).strip()
        return jsonify({'translation': translation})

    except Exception as e:
        print(f"Translation Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# process_audio() is only a fallback to process_audio_stream()
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
        
        response_data = {
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
        }

        return jsonify(response_data)
        
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

        # Increment sentence count
        session_data['sentences_count'] += 1
        current_count = session_data['sentences_count']
        session_store.save_session(session_id, session_data)

        # Process audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)
            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read())

        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        # Check for farewell (early termination)
        is_farewell = detect_farewell(transcript)

        # Determine should_end based on count OR farewell
        should_end = (current_count >= 11) or is_farewell
        logger.info(f"🔚 Should End Decision: current_count={current_count}, is_farewell={is_farewell}, should_end={should_end}")

        # Get conversation context
        conversation_type = session_data.get('conversation_type', 'everyday')
        conversation_history = session_data.get('conversation_history', [])
        child_name = session_data.get('child_name', 'दोस्त')
        child_age = session_data.get('child_age', 6)
        child_gender = session_data.get('child_gender', 'neutral')

        # Extract last talker response for evaluation
        last_talker_response = None
        for message in reversed(conversation_history):
            if message.get('role') == 'assistant':
                last_talker_response = message.get('content')
                break

        # Run evaluation in parallel
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
            nonlocal should_end
            
            try:
                # Send initial metadata
                yield f"data: {json.dumps({'type': 'metadata', 'transcript': transcript, 'evaluation': evaluation})}\n\n"

                # Get base system prompt for conversation type
                if conversation_type in CONVERSATION_TYPES:
                    system_prompt_base = CONVERSATION_TYPES[conversation_type]['system_prompts']['conversation']
                else:
                    system_prompt_base = CONVERSATION_TYPES['everyday']['system_prompts']['conversation']

                # Transform prompt for streaming with phase instructions
                system_prompt = get_streaming_system_prompt(
                    system_prompt_base,
                    current_count,
                    child_name,
                    child_age,
                    child_gender,
                    is_farewell
                )

                # Prepare conversation history for Gemini
                gemini_history = conversation_history + [{"role": "user", "content": transcript}]

                # Create streaming response with Gemini
                response_stream = gemini_stream_content(
                    system_prompt=system_prompt,
                    conversation_history=gemini_history
                )

                # Word buffering for smooth display
                word_buffer = ""
                accumulated_text = ""
                word_count = 0
                first_words_sent = False

                for chunk_text in response_stream:
                    # Gemini streams text directly, not delta objects
                    content = chunk_text
                    word_buffer += content
                    accumulated_text += content

                    # Send buffered words (2-3 words or on punctuation)
                    if (' ' in word_buffer and word_count >= 2) or any(p in word_buffer for p in '.!?,।'):
                        words_to_send = word_buffer.strip()
                        if words_to_send:
                            if not first_words_sent:
                                first_words_time = time.time()
                                logger.info(f"📝 FIRST WORDS: {(first_words_time - request_start_time) * 1000:.1f}ms")
                                first_words_sent = True
                            yield f"data: {json.dumps({'type': 'words', 'content': words_to_send, 'accumulated': accumulated_text})}\n\n"
                        word_buffer = ""
                        word_count = 0
                    elif ' ' in word_buffer:
                        word_count += 1

                # Send remaining buffer
                if word_buffer.strip():
                    yield f"data: {json.dumps({'type': 'words', 'content': word_buffer.strip(), 'accumulated': accumulated_text})}\n\n"

                # Track good responses
                if evaluation['feedback_type'] == 'green':
                    session_data['good_response_count'] = session_data.get('good_response_count', 0) + 1
                elif evaluation['feedback_type'] == 'amber':
                    amber_entry = {
                        'user_response': transcript,
                        'corrected_response': evaluation['corrected_response'],
                        'issues': evaluation['issues']
                    }
                    session_data.setdefault('amber_responses', []).append(amber_entry)

                # Calculate popup and milestone status
                should_show_popup = (
                    current_count % 4 == 0 and
                    current_count > 0 and
                    len(session_data.get('amber_responses', [])) > 0
                )

                is_milestone = (
                    evaluation['feedback_type'] == 'green' and
                    session_data.get('good_response_count', 0) % 5 == 0 and
                    session_data.get('good_response_count', 0) > 0
                )

                new_rewards = calculate_rewards(evaluation, session_data.get('good_response_count', 0))
                if new_rewards > 0:
                    session_data['reward_points'] = session_data.get('reward_points', 0) + new_rewards

                # Validate accumulated_text
                if not accumulated_text or not accumulated_text.strip():
                    logger.error(f"Empty response from Groq for conversation_type={conversation_type}")
                    accumulated_text = "क्षमा करें, मुझे समझ नहीं आया। कृपया फिर से बोलें।"

                # Generate hints asynchronously (only if conversation is NOT ending)
                hints = []
                if not should_end:
                    # Update conversation history first for better hint context
                    temp_history = conversation_history + [
                        {"role": "user", "content": transcript},
                        {"role": "assistant", "content": accumulated_text}
                    ]
                    hints = generate_hints(temp_history, conversation_type, child_name, child_age)

                # Send completion with all data
                completion_data = {
                    'type': 'complete',
                    'final_text': accumulated_text,
                    'should_end': should_end,
                    'hints': hints,
                    'should_show_popup': should_show_popup,
                    'amber_responses': session_data.get('amber_responses', []) if should_show_popup else [],
                    'is_milestone': is_milestone,
                    'good_response_count': session_data.get('good_response_count', 0),
                    'sentence_count': current_count,
                    'reward_points': session_data.get('reward_points', 0),
                    'new_rewards': new_rewards
                }

                # If conversation should end, add function_call to redirect to completion celebration
                if should_end:
                    completion_page_data = show_completion_page()
                    completion_data['function_call'] = completion_page_data
                    logger.info(f"🎉 Conversation ending - added function_call to redirect to completion_celebration")

                logger.info(f"📤 Sending completion data: should_end={should_end}, sentence_count={current_count}, is_milestone={is_milestone}")
                yield f"data: {json.dumps(completion_data)}\n\n"

                # Update conversation history
                session_data['conversation_history'].extend([
                    {"role": "user", "content": transcript},
                    {"role": "assistant", "content": accumulated_text}
                ])

                # Update database
                if 'conversation_id' in session_data:
                    try:
                        with app.app_context():
                            conversation = Conversation.query.get(session_data['conversation_id'])
                            if conversation:
                                conversation.sentences_count = current_count
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

@app.route('/api/get_hints', methods=['POST'])
@login_required
def get_hints():
    """API endpoint to get hints on demand"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400
        
        session_data = session_store.load_session(session_id)
        if not session_data:
            return jsonify({'error': 'Invalid session'}), 400
        
        conversation_history = session_data.get('conversation_history', [])
        conversation_type = session_data.get('conversation_type', 'everyday')
        child_name = session_data.get('child_name', 'दोस्त')
        child_age = session_data.get('child_age', 6)
        
        hints = generate_hints(conversation_history, conversation_type, child_name, child_age)
        
        return jsonify({'hints': hints})
        
    except Exception as e:
        logger.error(f"Error getting hints: {str(e)}")
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
                'about_me': {'name': 'About Me', 'icon': '🙋'},
                'my_family': {'name': 'My Family', 'icon': '👨‍👩‍👧‍👦'},
                'everyday': {'name': 'Everyday Life', 'icon': '🏠'},
                'my_toys': {'name': 'My Toys', 'icon': '🧸'},
                'food_i_like': {'name': 'Food I Like', 'icon': '🍽️'},
                'superheroes': {'name': 'Superheroes', 'icon': '🦸'},
                'animals_nature': {'name': 'Animals and Nature', 'icon': '🦊'},
                'adventure_story': {'name': 'Adventure Story', 'icon': '🗺️'},
                'panchatantra_story': {'name': 'Panchatantra Story', 'icon': '📖'}
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