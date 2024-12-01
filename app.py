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
from nltk.tokenize import sent_tokenize
import nltk
from elevenlabs import ElevenLabs, VoiceSettings
import io
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download necessary NLTK data
nltk.download('punkt')

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

def count_hindi_sentences(text):
    """Count the number of Hindi sentences in the text"""
    try:
        sentences = sent_tokenize(text, language='hindi')
        return len(sentences)
    except:
        # Fallback: basic period-based counting
        return len([s for s in text.split('.') if s.strip()])

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
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file'}), 400
        
        session_id = request.form.get('session_id')
        if not session_id or session_id not in user_sessions:
            return jsonify({'error': 'Invalid session'}), 400
            
        session_data = user_sessions[session_id]
        
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
        sentence_count = count_hindi_sentences(transcript)
        session_data['sentence_count'] += sentence_count
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)