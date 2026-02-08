from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, Response
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
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
from google.cloud import speech
from google.cloud.speech_v2 import SpeechClient as SpeechClientV2
from google.cloud.speech_v2.types import cloud_speech as cloud_speech_v2
from google.api_core.client_options import ClientOptions
from datetime import datetime, timedelta
import json
import tempfile
import time
import concurrent.futures
import random
from conversation_config import CONVERSATION_TYPES, MODULES, TOPICS

# Import our models and auth
from models import db, User, Conversation, ConversationAudio, AnalyticsHelper, PageView, UserAction, FunnelAnalytics, UserSticker
from s3_audio import ENABLE_AUDIO_STORAGE, generate_s3_key, upload_audio_async, generate_presigned_url
from auth import auth_bp, init_oauth
from sticker_config import STICKER_CATALOG, PACK_TIERS
import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
    traces_sample_rate=0.1,
    send_default_pii=False,
    release=os.getenv("HEROKU_SLUG_COMMIT", "dev"),
)

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

@app.before_request
def set_sentry_user_context():
    if current_user.is_authenticated:
        sentry_sdk.set_user({
            "id": str(current_user.id),
            "email": current_user.email,
            "username": current_user.child_name or current_user.name,
        })
    else:
        sentry_sdk.set_user(None)

# Configure API keys from environment variables
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

# Extract project ID from credentials for V2 API (Chirp 3)
GOOGLE_CLOUD_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT')

# Configurable conversation length (env var now, per-school model later)
MAX_CONVERSATION_TURNS = int(os.getenv('MAX_CONVERSATION_TURNS', '6'))


GOOGLE_STT_REGION = os.getenv('GOOGLE_STT_REGION', 'us')

STT_PROVIDER = os.getenv('STT_PROVIDER', 'google')  # Default to google (options: sarvam, groq, google)
TTS_PROVIDER = os.getenv('TTS_PROVIDER', 'elevenlabs')  # Options: elevenlabs, sarvam

# Google STT model configuration
GOOGLE_STT_MODEL = os.getenv('GOOGLE_STT_MODEL', 'chirp_3')  # Options: chirp_3, latest_long

# ASR correction configuration (Phase 4 - disabled by default)
ENABLE_ASR_CORRECTION = os.getenv('ENABLE_ASR_CORRECTION', 'false').lower() == 'true'
ASR_CORRECTION_TIMEOUT = float(os.getenv('ASR_CORRECTION_TIMEOUT', '2.0'))

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

    # Create separate model for evaluation (more accurate for grammar detection)
    gemini_eval_model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        safety_settings=safety_settings
    )
    logger.info("Gemini evaluation model initialized: gemini-2.0-flash")

    # Create model for hints (higher quality suggestions)
    gemini_hints_model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        safety_settings=safety_settings
    )
    logger.info("Gemini hints model initialized: gemini-2.5-flash")
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
SARVAM_TRANSLITERATE_URL = "https://api.sarvam.ai/transliterate"


def transliterate_to_roman(text):
    """Convert Devanagari Hindi text to Roman script via Sarvam API.
    Returns the transliterated text, or empty string on failure."""
    if not text or not text.strip() or not SARVAM_API_KEY:
        return ''
    start_ms = time.time()
    try:
        resp = requests.post(
            SARVAM_TRANSLITERATE_URL,
            headers={
                'api-subscription-key': SARVAM_API_KEY,
                'Content-Type': 'application/json'
            },
            json={
                'input': text,
                'source_language_code': 'hi-IN',
                'target_language_code': 'en-IN'
            },
            timeout=5
        )
        elapsed = (time.time() - start_ms) * 1000
        if resp.status_code == 200:
            result = resp.json().get('transliterated_text', '')
            logger.info(f"🔤 SARVAM TRANSLITERATE: {elapsed:.0f}ms for '{text[:40]}…' → '{result[:40]}…'")
            return result
        logger.warning(f"Sarvam transliterate returned {resp.status_code} in {elapsed:.0f}ms: {resp.text[:200]}")
        return ''
    except Exception as e:
        elapsed = (time.time() - start_ms) * 1000
        logger.warning(f"Sarvam transliterate failed in {elapsed:.0f}ms: {e}")
        return ''

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
    
    if sentences_count >= MAX_CONVERSATION_TURNS:
        return """
IMPORTANT - FINAL RESPONSE:
This is your FINAL response in this conversation.
- Give a warm, affectionate goodbye
- Briefly mention something nice from the conversation
- Give them a fun "homework": something to ask Mummy/Papa basis the discussion you had; for example: if the discussion was about favorite colors, the homework to the child can be to ask mom what her favorite color is.
- Do NOT ask any new questions
- Make the child feel proud and successful
"""

    if sentences_count == MAX_CONVERSATION_TURNS - 1:
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

def gemini_generate_content(system_prompt, conversation_history=None, response_format="json", use_eval_model=False, model_override=None):
    """
    Generate content using Gemini with optional JSON formatting

    Args:
        system_prompt: The system prompt
        conversation_history: Optional list of previous messages
        response_format: "json" or "text"
        use_eval_model: Use the more accurate evaluation model (gemini-2.0-flash)
        model_override: Directly pass a model instance to use
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

        # Select appropriate model
        if model_override:
            model = model_override
        elif use_eval_model:
            model = gemini_eval_model
        else:
            model = gemini_model

        # Generate content
        response = model.generate_content(
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

def get_streaming_system_prompt(base_prompt, sentences_count, child_name, child_age, child_gender, is_farewell=False, recast_context=None):
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

    # Get phase-specific instruction
    phase_instruction = get_phase_instruction(sentences_count, is_farewell)

    # Build recast instruction if grammar error detected (amber feedback)
    recast_instruction = ""
    if recast_context and recast_context.get('feedback_type') == 'amber':
        corrected = recast_context.get('corrected_response', '')
        original = recast_context.get('original_text', '')
        if corrected and corrected.strip() and original:
            recast_instruction = f"""CRITICAL - NATURAL GRAMMAR RECAST:
The child just said: "{original}"
The grammatically correct form is: "{corrected}"

You MUST naturally echo the corrected grammar as a confirmation/follow-up, BUT shift pronouns to YOUR perspective:
- "मैं" (I) → "तुम" (you)
- "मेरा/मेरी/मेरे" (my) → "तुम्हारा/तुम्हारी/तुम्हारे" (your)
- "मुझे" (to me) → "तुम्हें" (to you)

Do NOT explicitly correct them. Do NOT say "the correct way is..." or "you should say..."
Just echo the corrected form naturally with shifted pronouns, then continue the conversation.

Examples:
Child: "मेरे पापा कल पार्क में गई थी" → You: "अच्छा, तुम्हारे पापा कल पार्क गए थे? वहाँ क्या किया?"
Child: "Main kal park gaya tha" (girl) → You: "Achha, tum kal park gayi thin? Wahan kya khela?"
"""
            logger.info(f"🔄 Recast: '{original}' → '{corrected}'")

    # Add phase instruction and recast instruction if we have them
    prefix = ""
    if phase_instruction:
        prefix += phase_instruction + "\n\n"
    if recast_instruction:
        prefix += recast_instruction + "\n\n"
    if prefix:
        modified_prompt = prefix + modified_prompt

    return modified_prompt

def generate_hints(conversation_history, conversation_type, child_name, child_age):
    """Generate hint suggestions for what the child could say next using Gemini"""
    try:
        hints_prompt = f"""You are helping a {child_age}-year-old child learning Hindi.
Based on the conversation so far, suggest ONLY 1 Hindi sentence the child could say next.

Rules:
- Use Devanagari script ONLY (no romanized Hindi)
- Keep sentence of 8-10 words max
- Prefer the most idiomatic and natural-sounding word for the SPECIFIC CONTEXT, not just any grammatically correct synonym.
- Make them age-appropriate for a {child_age}-year-old
- Sentence should be a NATURAL RESPONSE to the LAST ASSISTANT message
- Check for naturalness: Would a native speaker say this phrase this way, or does it sound translated/awkward?

RESPONSE FORMAT (CRITICAL - FOLLOW EXACTLY):
Return a JSON object with this exact structure:
{{
  "hint": "Your Devanagari Hindi hint here"
}}

Example: {{"hint": "मुझे पिज़्ज़ा पसंद है"}}
"""

        # Get last few exchanges for context
        recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history

        # Use Gemini 3 Flash for higher quality hints
        result = gemini_generate_content(
            system_prompt=hints_prompt,
            conversation_history=recent_history,
            response_format="json",
            model_override=gemini_hints_model
        )

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
            You are a Hindi tutor evaluating this Hindi response from a 6-year-old child for:
            1. Completeness (is it a sentence or just 1 word?)
            2. Grammar correctness - ESPECIALLY gender agreement errors
            3. Grammar correctness in Hindi from a CONVERSATIONAL perspective; NOT from a WRITTEN Hindi perspective.

            CRITICAL - GENDER AGREEMENT ERRORS (these are ALWAYS amber):
            - Verb must match the gender of the subject noun
            - "पापा" (dad) is MASCULINE → use "गए थे", "आए थे", NOT "गई थी", "आई थी"
            - "मम्मी" (mom) is FEMININE → use "गई थी", "आई थी", NOT "गया था", "आया था"
            - "मैं" must match the speaker's gender in past tense verbs
            - Possessives must match: "मेरी मम्मी" (not "मेरा मम्मी"), "मेरे पापा" (not "मेरी पापा")

            EXAMPLES OF ERRORS (all should be amber):
            ❌ "मेरे पापा कल पार्क में गई थी" → ✅ "मेरे पापा कल पार्क गए थे" (पापा is masculine)
            ❌ "मेरा मम्मी भी उधर गया था" → ✅ "मेरी मम्मी भी वहाँ गई थी" (मम्मी is feminine)
            ❌ "हमने दिया जलाना अच्छा लगता है" → ✅ "हमें दीये जलाना अच्छा लगता है"

            NOTE: Don't evaluate answer correctness. If the kid says "I don't know" or gives a wrong answer but the sentence structure is correct, that's green.

            FILLER WORDS - IGNORE for scoring:
            - Sounds like "उम्म", "अं", "हम्म", "umm", "hmm" are normal for a 6-year-old thinking aloud
            - Do NOT penalize fillers when evaluating completeness or grammar
            - Evaluate only the core sentence: "उम्म... मेरे पापा... अं... ऑफिस गए थे" → evaluate as "मेरे पापा ऑफिस गए थे" = green
            - If response is ONLY fillers with no Hindi content, mark as incomplete

            {context_section}

            Return JSON format:
            {{{{
                "score": 1-10,
                "is_complete": true/false,
                "is_grammatically_correct": true/false,
                "issues": ["incomplete", "grammar_error", "gender_agreement"],
                "corrected_response": "grammatically correct version in Hindi",
                "feedback_type": "green/amber"
            }}}}

            Score guide:
            - 7-10: Complete, grammatically correct = green
            - 1-6: Incomplete OR any grammar/gender errors = amber

            For corrected_response, provide the corrected Hindi sentence (keep it short, age-appropriate).
            """

            # Use Gemini for evaluation (use more accurate model for grammar detection)
            result = gemini_generate_content(
                system_prompt=system_prompt,
                conversation_history=None,
                response_format="json",
                use_eval_model=True
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

            # Check if conversation should end (server-side override based on count)
            should_end = conversation_response.get('should_end', False) if isinstance(conversation_response, dict) else False
            if session_data['sentences_count'] >= MAX_CONVERSATION_TURNS:
                should_end = True

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

            # Check if correction popup should trigger (every 4 interactions, suppress on final turn)
            should_show_popup = (
                not should_end and
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

            if should_end:
                result['function_call'] = show_completion_page()

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

        # Run TTS and transliteration in parallel (transliteration ~200ms finishes within TTS ~500ms)
        logger.info("Converting text to speech + transliterating in parallel")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as startup_executor:
            tts_future = startup_executor.submit(text_to_speech_hindi, initial_message)
            translit_future = startup_executor.submit(transliterate_to_roman, initial_message)
            audio_response = tts_future.result()
            text_roman = translit_future.result()

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
            'reward_points': current_user.reward_points,
            'base_reward_points': current_user.reward_points,
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
            'text_roman': text_roman,
            'audio': audio_response,
            'session_id': session_id,
            'corrections': None  # Explicitly include corrections as None
        })
        
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Error in start_conversation: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({'error': str(e)}), 500
    

def text_to_speech_hindi_elevenlabs(text, output_filename="response.wav"):
    """Convert text to speech using ElevenLabs"""
    tts_function_start = time.time()
    logger.info(f"🔊 ELEVENLABS TTS: Starting synthesis for '{text[:50]}...'")

    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                audio_stream = eleven_labs.text_to_speech.convert_as_stream(
                    text=text,
                    model_id="eleven_multilingual_v2",
                    language_code="hi",
                    voice_id="Sm1seazb4gs7RSlUVw7c", #
                    optimize_streaming_latency="2",
                    output_format="mp3_44100_128",
                    voice_settings=VoiceSettings(
                        stability=0.75,
                        similarity_boost=0.75,
                        style=0.05,
                        use_speaker_boost=False,
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
        sentry_sdk.capture_exception(e)
        logger.error(f"TTS Error: {str(e)}")
        return None


def text_to_speech_hindi(text, output_filename="response.wav"):
    """Route TTS to the configured provider"""
    if TTS_PROVIDER.lower() == 'sarvam':
        return text_to_speech_hindi_sarvam(text, output_filename)
    else:
        return text_to_speech_hindi_elevenlabs(text, output_filename)


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
        # Find first and last bytes above silence threshold
        silence_threshold = 10
        audio_bytes = audio_data if isinstance(audio_data, (bytes, bytearray)) else bytes(audio_data)
        first_idx = -1
        last_idx = -1
        for i, b in enumerate(audio_bytes):
            if b > silence_threshold:
                if first_idx == -1:
                    first_idx = i
                last_idx = i

        if first_idx != -1:
            # Keep small buffer around speech to avoid cutting off words
            buffer_size = 100
            start_idx = max(0, first_idx - buffer_size)
            end_idx = min(len(audio_data), last_idx + buffer_size)

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
    Note: Silence trimming disabled - doesn't work with compressed WEBM_OPUS format.
    The trim_audio_silence function incorrectly treats compressed bytes as raw PCM
    amplitude values, causing random truncation of longer recordings.
    """
    # Return audio unchanged - silence trimming only works for raw PCM, not compressed formats
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

# Initialize V2 client for Chirp 3
google_speech_client_v2 = None
if GOOGLE_CLOUD_PROJECT:
    try:
        google_speech_client_v2 = SpeechClientV2(
            client_options=ClientOptions(
                api_endpoint=f"{GOOGLE_STT_REGION}-speech.googleapis.com"
            )
        )
        logger.info(f"Google Cloud Speech V2 client initialized (region: {GOOGLE_STT_REGION})")
    except Exception as e:
        logger.warning(f"V2 client initialization failed, will use V1: {e}")
else:
    logger.warning("GOOGLE_CLOUD_PROJECT not available, Chirp 3 disabled")


def speech_to_text_hindi_chirp3(audio_data, child_name=None):
    """Transcribe using Chirp 3 model (V2 API) with auto language detection"""
    stt_start_time = time.time()
    logger.info(f"🎙️ CHIRP 3 STT: Starting transcription...")

    try:
        # V2 config - auto_decoding_config handles WebM/Opus automatically
        config = cloud_speech_v2.RecognitionConfig(
            auto_decoding_config=cloud_speech_v2.AutoDetectDecodingConfig(),
            language_codes=["hi-IN", "en-IN"],  # Multi-language for code-switching
            model="chirp_3",
            features=cloud_speech_v2.RecognitionFeatures(
                enable_automatic_punctuation=True,
            ),
        )

        request = cloud_speech_v2.RecognizeRequest(
            recognizer=f"projects/{GOOGLE_CLOUD_PROJECT}/locations/{GOOGLE_STT_REGION}/recognizers/_",
            config=config,
            content=audio_data,
        )

        response = google_speech_client_v2.recognize(request=request)

        # Extract transcription
        transcriptions = []
        for result in response.results:
            if result.alternatives:
                transcriptions.append(result.alternatives[0].transcript)

        transcription = " ".join(transcriptions) if transcriptions else None

        total_time = (time.time() - stt_start_time) * 1000
        if transcription:
            logger.info(f"✅ CHIRP 3 STT: Success in {total_time:.1f}ms")
        else:
            logger.warning(f"❌ CHIRP 3 STT: No transcription in {total_time:.1f}ms")

        return transcription.strip() if transcription else None

    except Exception as e:
        total_time = (time.time() - stt_start_time) * 1000
        logger.error(f"❌ CHIRP 3 STT: Failed after {total_time:.1f}ms - {e}")
        return None


def speech_to_text_hindi_google_v1(audio_data, child_name=None):
    """V1 API implementation - Convert Hindi speech to text using Google Cloud Speech-to-Text"""
    stt_start_time = time.time()
    logger.info(f"🎙️ GOOGLE CLOUD STT: Starting transcription with model={GOOGLE_STT_MODEL}...")

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
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,  # Google's recommended optimal rate
            language_code="hi-IN",    # Hindi (India)
            # Alternative languages for code-switching (helps with Hindi/English mix)
            alternative_language_codes=["en-IN"],
            model='latest_long',   # Chirp 3 for better accuracy with auto language detection
            enable_automatic_punctuation=True,
            audio_channel_count=1,
            # This helps with mixed language
            enable_spoken_punctuation=False,
            enable_spoken_emojis=False,
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
                return speech_to_text_hindi_google_rest(optimized_audio, stt_start_time, child_name)
            else:
                raise api_error

        api_end_time = time.time()
        api_response_time = (api_end_time - api_start_time) * 1000

        # Extract transcription - concatenate ALL results (pauses create multiple segments)
        transcriptions = []
        if response.results:
            for result in response.results:
                if result.alternatives:
                    transcriptions.append(result.alternatives[0].transcript)

        transcription = " ".join(transcriptions) if transcriptions else None

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

def speech_to_text_hindi_google_rest(audio_data, stt_start_time, child_name=None):
    """Fallback REST API implementation for Google Cloud Speech-to-Text"""
    try:
        logger.info(f"🌐 GOOGLE CLOUD STT: Using REST API with API key, model={GOOGLE_STT_MODEL}...")

        # Encode audio as base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Prepare request payload
        payload = {
            "config": {
                "encoding": "WEBM_OPUS",
                "sampleRateHertz": 48000,
                "languageCode": "hi-IN",
                "alternativeLanguageCodes": ["en-IN"],  # Enable code-switching
                "model": GOOGLE_STT_MODEL,  # Use Chirp 3 for better accuracy
                "useEnhanced": False,
                "enableAutomaticPunctuation": True,
                "audioChannelCount": 1,
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

        # Extract transcription - concatenate ALL results (pauses create multiple segments)
        transcriptions = []
        if "results" in result and result["results"]:
            for res in result["results"]:
                if "alternatives" in res and res["alternatives"]:
                    transcript = res["alternatives"][0].get("transcript")
                    if transcript:
                        transcriptions.append(transcript)

        transcription = " ".join(transcriptions) if transcriptions else None

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

def speech_to_text_hindi_google(audio_data, child_name=None):
    """Route to appropriate STT implementation based on model config"""

    # Try Chirp 3 (V2) if configured and available
    if GOOGLE_STT_MODEL == 'chirp_3' and google_speech_client_v2:
        result = speech_to_text_hindi_chirp3(audio_data, child_name)
        if result:
            return result
        # Fallback to V1 on Chirp 3 failure
        logger.info("🔄 Chirp 3 failed, falling back to V1 API...")

    # V1 fallback (latest_long model)
    return speech_to_text_hindi_google_v1(audio_data, child_name)


def speech_to_text_hindi(audio_data, child_name=None):
    """Convert Hindi speech to text using the configured STT provider"""
    if STT_PROVIDER.lower() == 'groq':
        return speech_to_text_hindi_groq(audio_data)
    elif STT_PROVIDER.lower() == 'google':
        return speech_to_text_hindi_google(audio_data, child_name)
    else:
        return speech_to_text_hindi_sarvam(audio_data)


def is_correction_safe(raw, corrected, confidence):
    """Validate that ASR correction is reasonable and not too aggressive"""
    # Low confidence corrections are risky
    if confidence < 0.6:
        return False
    # Don't allow corrections that significantly expand the text
    if len(corrected) > len(raw) * 1.5:
        return False
    # Don't allow corrections that significantly shrink the text
    if len(corrected) < len(raw) * 0.5:
        return False
    return True


def correct_asr_transcript(raw_transcript, conversation_history, child_name):
    """Use Gemini to correct obvious ASR errors using conversation context.

    This is Phase 4 of ASR improvement - only enabled when ENABLE_ASR_CORRECTION=true.
    Uses LLM to fix common ASR mistakes like:
    - English words transcribed as Hindi (e.g., "book" -> "भूख")
    - Garbage prefixes from background noise
    - Wrong name recognition
    """
    # Skip very short utterances - not enough context to correct
    if len(raw_transcript.strip()) < 3:
        return raw_transcript, False, 1.0

    # Build conversation context from recent history
    recent_history = conversation_history[-4:] if conversation_history else []
    context_str = "\n".join([
        f"{'Child' if m['role']=='user' else 'Tutor'}: {m['content']}"
        for m in recent_history
    ])

    prompt = f"""Fix ASR errors in this Hindi child speech transcript.

RAW TRANSCRIPT: "{raw_transcript}"
CHILD'S NAME: {child_name}

CONTEXT:
{context_str or "(No prior context)"}

RULES:
1. ONLY fix obvious ASR errors (wrong words, garbage prefixes)
2. Do NOT fix grammar or rephrase
3. Preserve Hindi-English code-switching (e.g., "book पढ़ना है" is correct)
4. If unsure, return original with low confidence

Return JSON: {{"corrected": "text", "was_corrected": true/false, "confidence": 0.0-1.0}}"""

    try:
        result = gemini_generate_content(prompt, response_format="json")
        data = json.loads(result)

        corrected = data.get("corrected", raw_transcript)
        was_corrected = data.get("was_corrected", False)
        confidence = data.get("confidence", 0.5)

        # Safety check - don't apply risky corrections
        if was_corrected and not is_correction_safe(raw_transcript, corrected, confidence):
            logger.info(f"ASR correction rejected as unsafe: '{raw_transcript}' -> '{corrected}' (conf={confidence})")
            return raw_transcript, False, 0.0

        return corrected, was_corrected, confidence
    except Exception as e:
        logger.error(f"ASR correction failed: {e}")
        return raw_transcript, False, 0.0


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

@app.route('/profile')
@login_required
def profile():
    """Profile page for viewing/editing child info"""
    if not current_user.child_name:
        return redirect(url_for('profile_setup'))
    return render_template('profile.html')

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
    
    return render_template('conversation.html',
        conversation_type=conversation_type,
        sentry_dsn_frontend=os.getenv('SENTRY_DSN_FRONTEND', ''),
        sentry_environment=os.getenv('SENTRY_ENVIRONMENT', 'development'),
    )

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with analytics"""
    return render_template('dashboard.html')

@app.route('/sticker-album')
@login_required
def sticker_album():
    """Sticker album collection page"""
    return render_template('sticker_album.html')


@app.route('/api/sticker-album')
@login_required
def get_sticker_album():
    """Return all stickers with ownership status and user star balance"""
    owned_ids = {s.sticker_id for s in UserSticker.query.filter_by(user_id=current_user.id).all()}

    stickers = []
    for sticker_id, data in STICKER_CATALOG.items():
        stickers.append({
            **data,
            'id': sticker_id,
            'owned': sticker_id in owned_ids
        })

    return jsonify({
        'success': True,
        'stickers': stickers,
        'available_stars': current_user.available_stars,
        'total_stars_earned': current_user.reward_points,
        'stars_spent': current_user.stars_spent or 0,
        'owned_count': len(owned_ids),
        'total_count': len(STICKER_CATALOG),
        'pack_tiers': PACK_TIERS
    })


@app.route('/api/open-pack', methods=['POST'])
@login_required
def open_pack():
    """Gacha logic — randomly awards an unowned sticker from the chosen tier"""
    data = request.get_json()
    tier = data.get('tier')

    if tier not in PACK_TIERS:
        return jsonify({'success': False, 'error': 'Invalid tier'}), 400

    cost = PACK_TIERS[tier]['cost']

    if current_user.available_stars < cost:
        return jsonify({'success': False, 'error': 'Not enough stars!'}), 400

    owned_ids = {s.sticker_id for s in UserSticker.query.filter_by(user_id=current_user.id).all()}
    available = [(sid, s) for sid, s in STICKER_CATALOG.items()
                 if s['tier'] == tier and sid not in owned_ids]

    if not available:
        return jsonify({'success': False, 'error': 'You already have all stickers in this tier!'}), 400

    sticker_id, sticker_data = random.choice(available)

    current_user.stars_spent = (current_user.stars_spent or 0) + cost
    new_sticker = UserSticker(user_id=current_user.id, sticker_id=sticker_id, tier=tier)
    db.session.add(new_sticker)
    db.session.commit()

    return jsonify({
        'success': True,
        'sticker': {**sticker_data, 'id': sticker_id},
        'available_stars': current_user.available_stars,
        'stars_spent': current_user.stars_spent,
        'remaining_in_tier': len(available) - 1
    })


@app.route('/completion_celebration')
@login_required
def completion_celebration():
    """Celebration page for completing structured conversations"""
    completed_topic = request.args.get('topic', None)
    conversation_id = request.args.get('conversation_id', None)
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
                         completed_topic=completed_topic,
                         conversation_id=conversation_id,
                         child_name=current_user.child_name or 'My kid')

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

        # Extract child info for speech context
        child_name = session_data.get('child_name', 'दोस्त')
        conversation_history = session_data.get('conversation_history', [])

        # Use tempfile for secure file handling
        # Step 1: Save audio file
        file_start_time = time.time()
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)

            with open(temp_file.name, 'rb') as f:
                audio_bytes = f.read()
                raw_transcript = speech_to_text_hindi(audio_bytes, child_name=child_name)

        file_end_time = time.time()
        logger.info(f"📁 FILE PROCESSING: {(file_end_time - file_start_time) * 1000:.1f}ms")

        if not raw_transcript:
            return jsonify({'error': 'no_speech', 'message': "Sorry, we couldn't hear you. Please try recording again."}), 200

        # Submit background S3 upload for kid's audio
        if ENABLE_AUDIO_STORAGE and 'conversation_id' in session_data:
            turn_index = len(conversation_history)
            upload_audio_async(
                app, audio_bytes,
                user_id=current_user.id,
                conversation_id=session_data['conversation_id'],
                turn_index=turn_index,
                role='user',
                audio_format='webm',
            )

        # Optional LLM post-processing for ASR correction (Phase 4)
        if ENABLE_ASR_CORRECTION:
            transcript, was_corrected, conf = correct_asr_transcript(
                raw_transcript, conversation_history, child_name
            )
            logger.info(f"ASR_RAW: '{raw_transcript}'")
            if was_corrected:
                logger.info(f"ASR_CORRECTED: '{transcript}' (conf={conf})")
        else:
            transcript = raw_transcript
            logger.info(f"ASR: '{transcript}'")

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
                    conversation.reward_points = session_data['reward_points'] - session_data.get('base_reward_points', 0)
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
            'amber_responses': controller_result['amber_responses'],
            'should_end': controller_result.get('should_end', False)
        }

        if controller_result.get('function_call'):
            response_data['function_call'] = controller_result['function_call']
            response_data['conversation_id'] = session_data.get('conversation_id')

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

        # Get conversation context (extract early for STT)
        conversation_type = session_data.get('conversation_type', 'everyday')
        conversation_history = session_data.get('conversation_history', [])
        child_name = session_data.get('child_name', 'दोस्त')
        child_age = session_data.get('child_age', 6)
        child_gender = session_data.get('child_gender', 'neutral')

        # Process audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)
            with open(temp_file.name, 'rb') as f:
                audio_bytes = f.read()
                raw_transcript = speech_to_text_hindi(audio_bytes, child_name=child_name)

        if not raw_transcript:
            return jsonify({'error': 'no_speech', 'message': "Sorry, we couldn't hear you. Please try recording again."}), 200

        # Submit background S3 upload for kid's audio
        if ENABLE_AUDIO_STORAGE and 'conversation_id' in session_data:
            turn_index = len(conversation_history)
            upload_audio_async(
                app, audio_bytes,
                user_id=current_user.id,
                conversation_id=session_data['conversation_id'],
                turn_index=turn_index,
                role='user',
                audio_format='webm',
            )

        # Optional LLM post-processing for ASR correction (Phase 4)
        if ENABLE_ASR_CORRECTION:
            transcript, was_corrected, conf = correct_asr_transcript(
                raw_transcript, conversation_history, child_name
            )
            logger.info(f"ASR_RAW: '{raw_transcript}'")
            if was_corrected:
                logger.info(f"ASR_CORRECTED: '{transcript}' (conf={conf})")
        else:
            transcript = raw_transcript
            logger.info(f"ASR: '{transcript}'")

        # Check for farewell (early termination)
        is_farewell = detect_farewell(transcript)

        # Determine should_end based on count OR farewell
        should_end = (current_count >= MAX_CONVERSATION_TURNS) or is_farewell
        logger.info(f"🔚 Should End Decision: current_count={current_count}, is_farewell={is_farewell}, should_end={should_end}")

        # Extract last talker response for evaluation
        last_talker_response = None
        for message in reversed(conversation_history):
            if message.get('role') == 'assistant':
                last_talker_response = message.get('content')
                break

        # Launch evaluation + transcript transliteration in parallel
        controller = ConversationController()
        eval_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        eval_future = eval_executor.submit(
            controller.evaluator.evaluate_response,
            transcript,
            last_talker_response
        )
        transcript_translit_future = eval_executor.submit(transliterate_to_roman, transcript)

        # Streaming response generator
        def generate_streaming_response():
            nonlocal should_end

            try:
                # Wait for transcript transliteration (~200ms, eval runs in parallel ~1-2s)
                transcript_roman = transcript_translit_future.result(timeout=5)

                # Send transcript with roman version so client can show user message
                yield f"data: {json.dumps({'type': 'transcript', 'transcript': transcript, 'transcript_roman': transcript_roman})}\n\n"

                # Wait for evaluation result (may already be done by now)
                evaluation = eval_future.result()
                eval_executor.shutdown(wait=False)

                # Send evaluation as separate event
                yield f"data: {json.dumps({'type': 'evaluation', 'evaluation': evaluation})}\n\n"

                # Get base system prompt for conversation type
                if conversation_type in CONVERSATION_TYPES:
                    system_prompt_base = CONVERSATION_TYPES[conversation_type]['system_prompts']['conversation']
                else:
                    system_prompt_base = CONVERSATION_TYPES['everyday']['system_prompts']['conversation']

                # Prepare recast context from evaluation (only recast for amber feedback)
                recast_context = {
                    'feedback_type': evaluation.get('feedback_type', 'green'),
                    'corrected_response': evaluation.get('corrected_response', ''),
                    'original_text': transcript
                }

                # Transform prompt for streaming with phase instructions
                system_prompt = get_streaming_system_prompt(
                    system_prompt_base,
                    current_count,
                    child_name,
                    child_age,
                    child_gender,
                    is_farewell,
                    recast_context
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

                # Calculate popup and milestone status (suppress on final turn)
                should_show_popup = (
                    not should_end and
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

                # Send completion immediately — don't wait for hints
                completion_data = {
                    'type': 'complete',
                    'final_text': accumulated_text,
                    'should_end': should_end,
                    'hints': [],
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
                    completion_data['conversation_id'] = session_data.get('conversation_id')
                    logger.info(f"🎉 Conversation ending - added function_call to redirect to completion_celebration")

                logger.info(f"📤 Sending completion data: should_end={should_end}, sentence_count={current_count}, is_milestone={is_milestone}")
                yield f"data: {json.dumps(completion_data)}\n\n"

                # Fire response + amber transliteration immediately (~200ms)
                # Send BEFORE hints so the frontend swaps text while TTS is still playing
                translit_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
                response_translit_future = translit_executor.submit(transliterate_to_roman, accumulated_text)

                # Collect amber correction texts for batch transliteration
                amber_for_popup = completion_data.get('amber_responses', [])
                amber_translit_futures = {}
                for idx, amber in enumerate(amber_for_popup):
                    amber_translit_futures[f'user_{idx}'] = translit_executor.submit(
                        transliterate_to_roman, amber.get('user_response', ''))
                    amber_translit_futures[f'corrected_{idx}'] = translit_executor.submit(
                        transliterate_to_roman, amber.get('corrected_response', ''))

                # Wait for response+amber transliteration (~200ms) and send immediately
                translit_data = {'type': 'transliteration'}
                translit_data['final_text_roman'] = response_translit_future.result(timeout=5)

                if amber_for_popup:
                    translit_data['amber_responses_roman'] = []
                    for idx in range(len(amber_for_popup)):
                        translit_data['amber_responses_roman'].append({
                            'user_response_roman': amber_translit_futures[f'user_{idx}'].result(timeout=5),
                            'corrected_response_roman': amber_translit_futures[f'corrected_{idx}'].result(timeout=5)
                        })

                yield f"data: {json.dumps(translit_data)}\n\n"

                # Generate hints AFTER transliteration is sent (non-blocking for TTS)
                hints = []
                if not should_end:
                    temp_history = conversation_history + [
                        {"role": "user", "content": transcript},
                        {"role": "assistant", "content": accumulated_text}
                    ]
                    hints = generate_hints(temp_history, conversation_type, child_name, child_age) or []
                    if hints:
                        yield f"data: {json.dumps({'type': 'hints', 'hints': hints})}\n\n"
                        # Transliterate hints and send as separate event
                        hints_joined = ' या '.join(hints)
                        hints_roman = transliterate_to_roman(hints_joined)
                        if hints_roman:
                            yield f"data: {json.dumps({'type': 'hints_transliteration', 'hints_roman': hints_roman})}\n\n"

                translit_executor.shutdown(wait=False)

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
                                conversation.reward_points = session_data.get('reward_points', 0) - session_data.get('base_reward_points', 0)
                                conversation.conversation_data = session_data['conversation_history']
                                conversation.amber_data = session_data.get('amber_responses', [])
                                conversation.updated_at = datetime.utcnow()
                                db.session.commit()
                    except Exception as e:
                        logger.error(f"Failed to update conversation in database: {e}")

                session_store.save_session(session_id, session_data)

            except Exception as e:
                sentry_sdk.capture_exception(e)
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

        # Get optional session_id for child_name context
        session_id = request.form.get('session_id')
        child_name = None
        if session_id:
            session_data = session_store.load_session(session_id)
            if session_data:
                child_name = session_data.get('child_name')

        # Use tempfile for secure file handling
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)

            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read(), child_name=child_name)

        if not transcript:
            return jsonify({'error': 'no_speech', 'message': "Sorry, we couldn't hear you. Please try recording again."}), 200

        correction_end_time = time.time()
        total_time = (correction_end_time - correction_start_time) * 1000
        logger.info(f"✅ CORRECTION STT: Complete in {total_time:.1f}ms")
        logger.info(f"ASR: '{transcript}'")

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
                'things_i_love': {'name': 'Things I Love', 'icon': '🤩'},
                'how_im_feeling': {'name': 'How I Feel', 'icon': '😄'},
                'my_day': {'name': 'My Day', 'icon': '🫡'},
                'what_i_can_do': {'name': 'What I can Do', 'icon': '⛹🏻'},
                'family_members': {'name': 'Family Members', 'icon': '👨‍👩‍👧‍👦'},
                'talking_to_grandparents': {'name': 'Talking to Grandparents', 'icon': '👵'},
                'talking_to_chacha_mausi': {'name': 'Talking to Uncles/Aunts', 'icon': '👴'},
                'family_gathering': {'name': 'At a family gathering', 'icon': '👩‍👦‍👦'},
                'what_i_like_to_eat': {'name': 'What I like to eat', 'icon': '🥘'},
                'at_the_dinner_table': {'name': 'At the dinner table', 'icon': '🍽️'},
                'at_dadi_house': {'name': "Food at Grandparents'", 'icon': '👨‍🍳'},
                'festival_foods': {'name': 'Festival Foods', 'icon': '🍬'},
                'diwali': {'name': 'Diwali', 'icon': '🪔'},
                'holi': {'name': 'Holi', 'icon': '🎨'},
                'raksha_bandhan': {'name': 'Raksha Bandhan', 'icon': '🏵️'},
                'indian_birthdays': {'name': 'Indian Birthdays', 'icon': '🎂'},
                'animals_i_like': {'name': 'Animals I Like', 'icon': '🦁'},
                'indian_animals': {'name': 'Indian Animals', 'icon': '🦚'},
                'weather_today': {'name': 'Weather today', 'icon': '🌧️'},
                'my_favorite_place': {'name': 'My favorite place', 'icon': '🎡'},
                'panchatantra_monkey_crocodile': {'name': 'Panchatantra: Monkey & Crocodile', 'icon': '🐵'},
                'panchatantra_lion_rabbit': {'name': 'Panchatantra: Lion & Rabbit', 'icon': '🦁'},
                'lets_make_a_story': {'name': 'Create your own Story!', 'icon': '🦸'},
                'my_favorite_story': {'name': 'My Favorite Story', 'icon': '📖'}
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

@app.route('/api/conversation/<int:conversation_id>/audio', methods=['GET'])
@login_required
def get_conversation_audio(conversation_id):
    """Return audio metadata + presigned playback URLs for a conversation."""
    try:
        # Verify ownership
        conversation = Conversation.query.filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        ).first()
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404

        audio_records = ConversationAudio.query.filter(
            ConversationAudio.conversation_id == conversation_id,
            ConversationAudio.upload_status == 'uploaded',
        ).order_by(ConversationAudio.turn_index).all()

        results = []
        for rec in audio_records:
            entry = rec.to_dict()
            entry['playback_url'] = generate_presigned_url(rec.s3_key)
            results.append(entry)

        return jsonify({'success': True, 'audio': results})

    except Exception as e:
        logger.error(f"Get conversation audio error: {e}")
        return jsonify({'error': 'Failed to fetch audio files'}), 500


@app.route('/api/conversation/<int:conversation_id>/best-audio', methods=['GET'])
@login_required
def get_best_audio(conversation_id):
    """Identify the kid's cleanest Hindi response and return its audio URL."""
    try:
        if not ENABLE_AUDIO_STORAGE:
            return jsonify({'success': False, 'reason': 'no_audio'})

        # Verify ownership
        conversation = Conversation.query.filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        ).first()
        if not conversation:
            return jsonify({'success': False, 'reason': 'not_found'}), 404

        # Load user audio records
        audio_records = ConversationAudio.query.filter(
            ConversationAudio.conversation_id == conversation_id,
            ConversationAudio.role == 'user',
            ConversationAudio.upload_status == 'uploaded',
        ).order_by(ConversationAudio.turn_index).all()

        if not audio_records:
            return jsonify({'success': False, 'reason': 'no_audio'})

        # Build map of turn_index -> audio record
        audio_by_turn = {rec.turn_index: rec for rec in audio_records}

        # Extract user turns from conversation transcript
        transcript_data = conversation.conversation_data
        user_turns = []
        for i, msg in enumerate(transcript_data):
            if msg.get('role') == 'user' and i in audio_by_turn:
                user_turns.append({'turn_index': i, 'text': msg.get('content', '')})

        if not user_turns:
            return jsonify({'success': False, 'reason': 'no_audio'})

        # If only one user turn with audio, skip Gemini call
        reason = ''
        if len(user_turns) == 1:
            best_turn = user_turns[0]
        else:
            # Ask Gemini to pick the best Hindi response
            numbered_responses = '\n'.join(
                f"{idx + 1}. \"{t['text']}\"" for idx, t in enumerate(user_turns)
            )
            prompt = f"""You are evaluating a child's Hindi conversation responses. Pick the SINGLE best response that demonstrates the cleanest Hindi — good grammar, complete sentence, minimal English code-switching.

Here are the child's responses (numbered):
{numbered_responses}

Return ONLY a JSON object: {{"best_turn": <number>, "reason": "<brief reason in English>"}}"""

            try:
                result = gemini_generate_content(
                    prompt,
                    response_format="json",
                    model_override=gemini_hints_model
                )
                parsed = json.loads(result)
                best_index = int(parsed.get('best_turn', 1)) - 1  # Convert 1-based to 0-based
                best_index = max(0, min(best_index, len(user_turns) - 1))
                best_turn = user_turns[best_index]
                reason = parsed.get('reason', '')
            except Exception as e:
                logger.warning(f"Gemini best-audio pick failed, defaulting to last turn: {e}")
                best_turn = user_turns[-1]
                reason = ''

        # Generate presigned URL for the best audio
        audio_record = audio_by_turn[best_turn['turn_index']]
        playback_url = generate_presigned_url(audio_record.s3_key)

        return jsonify({
            'success': True,
            'transcript': best_turn['text'],
            'playback_url': playback_url,
            'reason': reason,
            'audio_format': audio_record.audio_format,
        })

    except Exception as e:
        logger.error(f"Get best audio error: {e}")
        return jsonify({'success': False, 'reason': 'error'}), 500


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
            'reward_points': current_user.reward_points,
            'base_reward_points': current_user.reward_points - (conversation.reward_points or 0),
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
        import ssl

        # Parse the URL to determine if SSL is needed
        if redis_url.startswith('rediss://'):
            # Heroku Redis uses rediss:// for SSL connections
            # Disable cert verification for Heroku's self-signed certificates
            self.redis = redis.from_url(
                redis_url,
                decode_responses=False,
                ssl_cert_reqs=None  # Disable certificate verification
            )
        elif 'amazonaws.com' in redis_url or 'heroku' in redis_url:
            # For redis:// URLs that require SSL (older Heroku format)
            # Convert redis:// to rediss:// for SSL
            if redis_url.startswith('redis://'):
                redis_url = redis_url.replace('redis://', 'rediss://', 1)
            self.redis = redis.from_url(
                redis_url,
                decode_responses=False,
                ssl_cert_reqs=None  # Disable certificate verification
            )
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
                logger.info(f"Session loaded from Redis: {session_id}")
                return session_data

            # Session not found in Redis, try FileSessionStore fallback
            logger.info(f"Session not in Redis, trying FileSessionStore fallback: {session_id}")
            fallback_store = FileSessionStore()
            fallback_data = fallback_store.load_session(session_id)
            if fallback_data:
                logger.info(f"Session loaded from FileSessionStore fallback: {session_id}")
                return fallback_data

            logger.warning(f"No session found in Redis or FileSessionStore: {session_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to load session from Redis: {e}")
            # Try fallback to file storage on exception
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
            # Migrate: add stars_spent column to user table if missing
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            user_cols = [c['name'] for c in inspector.get_columns('user')]
            if 'stars_spent' not in user_cols:
                db.session.execute(text('ALTER TABLE user ADD COLUMN stars_spent INTEGER DEFAULT 0'))
                db.session.commit()
                logger.info("Migration: added stars_spent column to user table")
            if 'transliteration_enabled' not in user_cols:
                db.session.execute(text('ALTER TABLE "user" ADD COLUMN transliteration_enabled BOOLEAN DEFAULT 0'))
                db.session.commit()
                logger.info("Migration: added transliteration_enabled column to user table")
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")


if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    app.run(host='0.0.0.0', port=port)