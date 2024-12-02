from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import openai
import logging
import requests
import base64
import wave
import os
import json
from dotenv import load_dotenv
from elevenlabs import ElevenLabs, VoiceSettings
import io
import redis
from datetime import datetime, timedelta
import json

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


def get_initial_conversation():
    """Generate initial conversation starter"""
    try:
        client = openai.OpenAI()
        
        system_prompt = """
        You are a friendly Hindi tutor starting a conversation with a 6-year-old child, named Abir.
        Create a warm, engaging greeting and ask if they went to school today or not in Hindi.
        Guidelines:
        1. Keep it very short (max 10 words)
        2. Use simple Hindi words
        3. Make it cheerful and inviting

        Return response in JSON format:
        {
            "response": "Your Hindi greeting here"
        }
        """

        # Add logging
        logger.info("Making OpenAI API call for initial conversation")
        
        response = client.chat.completions.create(
            model="gpt-4o",
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

#def count_hindi_sentences(text):
    """Count the number of Hindi sentences using GPT-4"""
    try:
        client = openai.OpenAI()
        
        prompt = f"""
        Count the number of complete sentences in this Hindi text and return ONLY the number:
        {text}
        
        Return response in JSON format:
        {{"sentence_count": number}}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            response_format={ "type": "json_object" },
            temperature=0
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get('sentence_count', 0)
        
    except Exception as e:
        print(f"Error counting sentences: {str(e)}")
        # Fallback: basic period-based counting
        return len([s for s in text.split('।') if s.strip()])

def calculate_rewards(sentence_count):
    """Calculate reward points based on sentence count"""
    if sentence_count >= 3:
        return 10
    return 0

def get_hindi_response(conversation_history, audio_transcript, sentence_count):
    """Get response from GPT-4 with Hindi conversation context and gamification"""
    try:
        client = openai.OpenAI()
        
        # Enhanced system prompt with gamification awareness
        system_prompt = f"""
        You are a friendly Hindi tutor speaking with a 6-year-old child. The goal is to improve the user's Hindi.
        The child has spoken {sentence_count} sentences so far.
        
        Follow these guidelines:
        1. First, analyze their input and read each word. See if there is any English words or phrases used instead of Hindi words.
        2. For each English word/phrase found, provide the correct Hindi translation. 
        3. Also provide the entire corrected proper Hindi sentence against what is spoken.
        4. Then generate your normal response in Hindi
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
            model="gpt-4o",
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
    
@app.route('/api/start_conversation', methods=['GET'])
def start_conversation():
    """Endpoint to start the initial conversation"""
    try:
        logger.info("Starting new conversation")
        initial_message = get_initial_conversation()
        
        logger.info("Converting text to speech")
        audio_response = text_to_speech_hindi(initial_message)

        if not audio_response:
            raise Exception("Failed to generate audio response")
        
        session_id = base64.b64encode(os.urandom(16)).decode('utf-8')

        # Initialize session data
        session_data = {
            'conversation_history': [],
            'sentence_count': 0,
            'reward_points': 0,
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
        # Convert text to audio stream using ElevenLabs
        # You can adjust the voice_id and settings as needed
        audio_stream = eleven_labs.text_to_speech.convert_as_stream(
            text=text,
            model_id="eleven_turbo_v2_5",
            language_code="hi",
            voice_id="cgSgspJ2msm6clMCkdW9",  # Replace with your preferred Hindi voice ID
            optimize_streaming_latency="3",  # Maximum latency optimization
            output_format="mp3_44100_128",
            voice_settings=VoiceSettings(
                stability=0.3,
                similarity_boost=0.5,
                style=0.0,
            )
        )
        
        # Read the entire stream into a buffer
        audio_data = io.BytesIO()
        for chunk in audio_stream:
            audio_data.write(chunk)
        
        # Convert to base64 for sending to frontend
        audio_base64 = base64.b64encode(audio_data.getvalue()).decode('utf-8')
        
        # Optionally save the audio file if needed
        with open(output_filename, 'wb') as f:
            f.write(audio_data.getvalue())
            
        return audio_base64
        
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
        response = requests.post(SARVAM_STT_URL, headers=headers, files = files, data=data)
        
        # Log response details
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response content: {response.text[:200]}...")

        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Parsed response: {result}")
        
        # Return transcript from response
        return result.get("transcript")

    except Exception as e:
        print(f"STT Error: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

# Configure static files handling
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

#Make sure process_audio.js is served correctly
# Optional: Add a specific route for process_audio.js if needed
@app.route('/static/js/process_audio.js')
def serve_js():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'),
        'process_audio.js',
        mimetype='application/javascript'
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

        #if not session_id or session_id not in user_sessions:
            logger.error(f"Session ID {session_id} not found in user_sessions")
            logger.info(f"Available sessions: {list(user_sessions.keys())}")
            return jsonify({'error': 'Invalid session'}), 400
        
         # Log current session state
        logger.info(f"Current sentence count: {session_data['sentence_count']}")

        # Simply increment sentence count by 1 for each user interaction
        session_data['sentence_count'] += 1
        logger.info(f"Updated sentence count: {session_data['sentence_count']}")
        
        audio_file = request.files['audio']
        
        # Save incoming audio temporarily
        temp_input = f"temp_input_{session_id}.wav"
        audio_file.save(temp_input)

        # Convert speech to text
        with open(temp_input, 'rb') as f:
            transcript = speech_to_text_hindi(f.read())
        
        if not transcript:
            return jsonify({'error': 'Speech-to-text failed'}), 500

        # Count sentences and update rewards
        #sentence_count = count_hindi_sentences(transcript)
        #session_data['sentence_count'] += sentence_count
        new_rewards = calculate_rewards(session_data['sentence_count'])
        
        if new_rewards > 0:
            session_data['reward_points'] += new_rewards
        
        # Get response from GPT-4
        response_text = get_hindi_response(
            session_data['conversation_history'], 
            transcript,
            session_data['sentence_count']
        )

        
        if not response_text:
            return jsonify({'error': 'Failed to get GPT response'}), 500
        
        # Convert response to speech
        audio_response = text_to_speech_hindi(response_text['response'])
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
        
        # Update conversation history
        session_data['conversation_history'].extend([
            {"role": "user", "content": transcript},
            {"role": "assistant", "content": response_text['response']}
        ])
        
        # Clean up temporary files
        if os.path.exists(temp_input):
            os.remove(temp_input)
        
        return jsonify({
            'text': response_text['response'],
            'audio': audio_response,
            'transcript': transcript,
            'corrections': response_text['corrections'],
            'sentence_count': session_data['sentence_count'],
            'reward_points': session_data['reward_points'],
            'new_rewards': new_rewards
        })
        
    except Exception as e:
        print(f"Process Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


#def save_sessions():
    """Save sessions to a file"""
    try:
        session_data = {
            sid: {
                'conversation_history': data['conversation_history'],
                'sentence_count': data['sentence_count'],
                'reward_points': data['reward_points'],
                'created_at': data['created_at'].isoformat() if isinstance(data.get('created_at'), datetime) else data.get('created_at')
            }
            for sid, data in user_sessions.items()
        }
        with open('sessions.json', 'w') as f:
            json.dump(session_data, f)
    except Exception as e:
        logger.error(f"Failed to save sessions: {e}")

#def load_sessions():
    """Load sessions from file"""
    try:
        with open('sessions.json', 'r') as f:
            data = json.load(f)
            for sid, session in data.items():
                if 'created_at' in session and isinstance(session['created_at'], str):
                    session['created_at'] = datetime.fromisoformat(session['created_at'])
            return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Failed to load sessions: {e}")
        return {}
    

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

# Redis session storage for production
class RedisSessionStore(SessionStore):
    def __init__(self, redis_url):
        import redis
        self.redis = redis.from_url(redis_url)
    
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
        except Exception as e:
            logging.error(f"Failed to save session to Redis: {e}")

    def load_session(self, session_id):
        try:
            data = self.redis.get(f"session:{session_id}")
            if data:
                session_data = json.loads(data)
                if 'created_at' in session_data:
                    session_data['created_at'] = datetime.fromisoformat(session_data['created_at'])
                return session_data
            return None
        except Exception as e:
            logging.error(f"Failed to load session from Redis: {e}")
            return None

    def cleanup_old_sessions(self):
        # Redis automatically handles expiration
        pass

# Initialize session store based on environment
def get_session_store():
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        try:
            import redis
            return RedisSessionStore(redis_url)
        except ImportError:
            logging.warning("Redis package not installed, falling back to file storage")
            return FileSessionStore()
    return FileSessionStore()

# Initialize the appropriate session store
session_store = get_session_store()



# Load sessions when app starts
#user_sessions.update(load_sessions())

#def cleanup_old_sessions():
 #   """Remove sessions older than 24 hours"""
  #  current_time = datetime.now()
    
    # Add timestamp to new sessions
   # for session_id, session_data in user_sessions.items():
    #    if 'created_at' not in session_data:
     #       session_data['created_at'] = current_time
    
    # Remove old sessions
    #expired_sessions = [
     #   session_id for session_id, session_data in user_sessions.items()
      #  if current_time - datetime.fromisoformat(str(session_data['created_at'])) > timedelta(hours=24)
    #]
    
    #for session_id in expired_sessions:
     #   del user_sessions[session_id]
    
    # Save sessions after cleanup
    #save_sessions()*/



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)