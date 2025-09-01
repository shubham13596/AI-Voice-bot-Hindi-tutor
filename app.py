from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
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

CORS(app)

# Configure API keys from environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')
SARVAM_API_KEY = os.getenv('SARVAM_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')


# Sarvam AI API endpoints
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
# Initialize ElevenLabs client
eleven_labs = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Get port from environment variable
port = int(os.getenv('PORT', 5001))

# Cache for storing user session data
user_sessions = {}


def get_initial_conversation(child_name="दोस्त"):
    """Generate initial conversation starter"""
    try:
        client = openai.OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url="https://api.openai.com/v1",  # Explicitly set base URL
            http_client=None  # Prevent automatic proxy detection
        )
        
        system_prompt = f"""
        You are a friendly Hindi tutor starting a conversation with a 6-year-old child, named {child_name}.
        Create a warm, engaging greeting and ask if they went to school today or not in Hindi.
        Guidelines:
        1. Keep it very short (max 10 words)
        2. Use simple Hindi words
        3. Make it cheerful and inviting

        Return response in JSON format:
        {{
            "response": "Your Hindi greeting here"
        }}
        """

        # Add logging
        logger.info("Making OpenAI API call for initial conversation")
        
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
        print(f"Error in initial conversation: {str(e)}")
        return "नमस्ते! कैसा है आपका दिन?"  # Fallback greeting


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
    def get_response(conversation_history, user_text, evaluation_result, sentence_count):
        """Generate conversation response based on evaluation context"""
        try:
            client = openai.OpenAI(
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url="https://api.openai.com/v1",
                http_client=None
            )
            
            # Determine conversation strategy based on evaluation
            if not evaluation_result["is_complete"]:
                strategy = "nudge_for_completeness"
            else:
                strategy = "continue_conversation"
            
            system_prompt = f"""
            You are a friendly Hindi tutor speaking with a 6-year-old child.
            The child has spoken {sentence_count} sentences so far.
            
            Strategy: {strategy}
            
            Guidelines:
            1. If strategy is 'nudge_for_completeness': Gently encourage them to give a longer, complete answer
            2. If strategy is 'continue_conversation': Continue the natural conversation flow
            3. Keep responses short (max 20 words)
            4. Be curious and encouraging
            5. Respond only in Hindi
            
            Return JSON format:
            {{
                "response": "Your Hindi response here"
            }}
            """
            
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
            # Evaluate response in parallel with conversation
            evaluation = self.evaluator.evaluate_response(user_text)
            
            # Generate conversation response
            conversation_response = self.talker.get_response(
                session_data['conversation_history'],
                user_text,
                evaluation,
                session_data['sentence_count']
            )
            
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
            
            # Check if correction popup should trigger (every 5 interactions, and we have amber responses)
            should_show_popup = (
                session_data['sentence_count'] % 5 == 0 and
                session_data['sentence_count'] > 0 and
                len(session_data.get('amber_responses', [])) > 0
            )
            
            # Calculate milestone status for celebration
            is_milestone = (
                evaluation['feedback_type'] == 'green' and 
                session_data['good_response_count'] % 5 == 0 and
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

def get_hindi_response(conversation_history, audio_transcript, sentence_count):
    """Get response from GPT-4 with Hindi conversation context and gamification"""
    try:
        client = openai.OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url="https://api.openai.com/v1",
            http_client=None
        )
        
        # Enhanced system prompt with gamification awareness
        system_prompt = f"""
        You are a friendly Hindi tutor speaking with a 6-year-old child. The goal is to improve the user's Hindi.
        The child has spoken {sentence_count} sentences so far.
        
        Follow these guidelines:
        1. First, analyze their input and read each word. See if there is any English words or phrases used instead of Hindi words.
        2. For each English word/phrase found, provide the correct Hindi translation. 
        3. Also provide the entire corrected proper Hindi sentence against what is spoken.
        4. Then generate your normal response in Hindi. 
        5. Be curious as a mom would to know more about the user's activities.
        6. Keep responses short (max 20 words).
        7. Keep the conversation flowing naturally by asking questions and showing curiosity.
         
        Return your response in this exact JSON format. In this Json, include only corrections limited to that chat, not the entire chat session.
        {{
            "corrections": [
                {{"original": "book", "corrected": "किताब"}},
                {{"original": "school", "corrected": "स्कूल"}},
                {{"original": "आज हमने बर्ड्स को डिस्कस किया लाइक पैरेट आउल", "corrected": "आज हमने पक्षियों पर चर्चा की, जैसे तोता, उल्लू"}}
            ],
            "response": "Your Hindi response here"
        }}

        If no corrections are needed, return empty array for corrections.
        Keep your response short and friendly as before.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": audio_transcript}
        ]
        
        # Use streaming for faster initial response
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "json_object" },
            temperature=0.6,
            max_tokens=150
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        logger.error(f"Error in GPT-4 response: {str(e)}")
        # Return a fallback response structure
        return {
            "corrections": [],
            "response": "मैं समझ नहीं पाया। कृपया दोबारा बोलें।"  # "I didn't understand. Please speak again."
        }
    
@app.route('/api/start_conversation', methods=['POST'])
def start_conversation():
    """Endpoint to start the initial conversation"""
    try:
        logger.info("Starting new conversation")
        
        # Get child name from request
        data = request.json or {}
        child_name = data.get('child_name', 'दोस्त')
        
        initial_message = get_initial_conversation(child_name)
        
        logger.info("Converting text to speech")
        audio_response = text_to_speech_hindi(initial_message)

        if not audio_response:
            raise Exception("Failed to generate audio response")
        
        session_id = base64.b64encode(os.urandom(16)).decode('utf-8')

        # Initialize session data
        session_data = {
            'conversation_history': [],
            'sentence_count': 0,
            'good_response_count': 0,
            'reward_points': 0,
            'amber_responses': [],
            'created_at': datetime.now()
        }
        
        # Save session
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
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                audio_stream = eleven_labs.text_to_speech.convert_as_stream(
                    text=text,
                    model_id="eleven_turbo_v2_5",
                    language_code="hi",
                    voice_id="MF4J4IDTRo0AxOO4dpFR",
                    optimize_streaming_latency="3",
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
                        
                return audio_base64
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"TTS attempt {attempt + 1} failed: {e}")
                time.sleep(0.1 * (attempt + 1))
        
    except Exception as e:
        print(f"TTS Error: {str(e)}")
        return None

def speech_to_text_hindi(audio_data):
    """Convert Hindi speech to text using Sarvam AI"""
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
            'model': 'saarika:v1',
            'with_timestamps': False
        }
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                return result.get("transcript")
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"STT attempt {attempt + 1} failed: {e}")
                time.sleep(0.1 * (attempt + 1))

    except Exception as e:
        print(f"STT Error: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/conversation')
def conversation():
    return render_template('conversation.html')

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

#@app.route('/api/process_text', methods=['POST'])
#def process_text():
    try:
        data = request.json
        text = data.get('text')
        conversation_history = data.get('conversation_history', [])
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
            
        # Get response from GPT-4
        response_text = get_hindi_response(conversation_history, text, 0)  # You might want to handle sentence count differently
        
        if not response_text:
            return jsonify({'error': 'Failed to get GPT response'}), 500
            
        # Convert response to speech
        audio_response = text_to_speech_hindi(response_text)
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
            
        return jsonify({
            'text': response_text,
            'audio': audio_response
        })
        
    except Exception as e:
        print(f"Process Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process_audio', methods=['POST'])
def process_audio():
    temp_file = None
    try:
        # Log incoming request data
        logger.info("Received process_audio request")
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
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file = request.files['audio']
            audio_file.save(temp_file.name)

            with open(temp_file.name, 'rb') as f:
                transcript = speech_to_text_hindi(f.read())
        
        
        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        # Initialize conversation controller
        controller = ConversationController()
        
        # Process user response through controller
        controller_result = controller.process_user_response(session_data, transcript)
        
        new_rewards = calculate_rewards(
            controller_result['evaluation'], 
            controller_result['good_response_count']
        )
        
        if new_rewards > 0:
            session_data['reward_points'] += new_rewards
        
        if not controller_result['response']:
            return jsonify({'error': 'Failed to get conversation response'}), 500
        
        # Convert response to speech
        audio_response = text_to_speech_hindi(controller_result['response'])
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
        
        # Update conversation history
        session_data['conversation_history'].extend([
            {"role": "user", "content": transcript},
            {"role": "assistant", "content": controller_result['response']}
        ])

        # Add this line to save all updates
        session_store.save_session(session_id, session_data)

        try:
            os.unlink(temp_file.name)
        except Exception as e:
                logger.error(f"Failed to delete temporary file: {e}")
        
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

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check Redis connection
        session_store.redis.ping()
        
        # Check ElevenLabs API
        eleven_labs.voices.list()
        
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



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)