from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import openai
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import requests
import base64
import wave
import os
import json
from dotenv import load_dotenv
from nltk.tokenize import sent_tokenize
import nltk

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

# Sarvam AI API endpoints
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

# Get port from environment variable
port = int(os.getenv('PORT', 5001))

# Cache for storing user session data
user_sessions = {}

def get_initial_conversation():
    """Generate initial conversation starter"""
    try:
        client = openai.OpenAI()
        
        system_prompt = """
        You are a friendly Hindi tutor starting a conversation with a 6-year-old child.
        Create a warm, engaging greeting and ask a simple question about their day.
        Guidelines:
        1. Keep it very short (max 10 words)
        2. Use simple Hindi words
        3. Make it cheerful and inviting
        4. End with a question about their day or activities
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7,
            max_tokens=50
        )
        
        return response.choices[0].message.content
        
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
        You are a friendly Hindi tutor speaking with a 6-year-old child.
        The child has spoken {sentence_count} sentences so far.
        
        Follow these guidelines:
        1. Always respond in Hindi
        2. Keep responses short (max 20 words)
        3. If they've spoken 3 or more sentences, praise their effort
        4. Gently encourage more speaking if they use very short responses
        5. Make corrections kindly if needed
        6. Keep the conversation flowing naturally
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": audio_transcript}
        ]
        
        # Use streaming for faster initial response
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error in GPT-4 response: {str(e)}")
        return None
    
@app.route('/api/start_conversation', methods=['GET'])
def start_conversation():
    """Endpoint to start the initial conversation"""
    try:
        initial_message = get_initial_conversation()
        audio_response = text_to_speech_hindi(initial_message)
        
        session_id = base64.b64encode(os.urandom(16)).decode('utf-8')
        user_sessions[session_id] = {
            'conversation_history': [{"role": "assistant", "content": initial_message}],
            'sentence_count': 0,
            'reward_points': 0
        }
        
        return jsonify({
            'text': initial_message,
            'audio': audio_response,
            'session_id': session_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def text_to_speech_hindi(text, output_filename="response.wav"):
    """Convert text to speech using Sarvam AI"""
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": [text],
        "target_language_code": "hi-IN",
        "speaker": "amol",
        "pitch": 0,
        "pace": 0.8,
        "loudness": 1.5,
        "speech_sample_rate": 8000,
        "enable_preprocessing": True,
        "model": "bulbul:v1"
    }
    
    try:
        response = requests.post(SARVAM_TTS_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        response_data = response.json()
        
        if 'audios' not in response_data:
            raise ValueError("No 'audios' key in response")
            
        audio_base64 = response_data['audios'][0]
        
        # Save audio file
        audio_binary = base64.b64decode(audio_base64)
        
        with wave.open(output_filename, 'wb') as wav_file:
            wav_file.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            wav_file.writeframes(audio_binary)
            
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
        audio_response = text_to_speech_hindi(response_text)
        
        if not audio_response:
            return jsonify({'error': 'Text-to-speech failed'}), 500
        
        # Update conversation history
        session_data['conversation_history'].extend([
            {"role": "user", "content": transcript},
            {"role": "assistant", "content": response_text}
        ])
        
        # Clean up temporary files
        if os.path.exists(temp_input):
            os.remove(temp_input)
        
        return jsonify({
            'text': response_text,
            'audio': audio_response,
            'transcript': transcript,
            'sentence_count': session_data['sentence_count'],
            'reward_points': session_data['reward_points'],
            'new_rewards': new_rewards
        })
        
    except Exception as e:
        print(f"Process Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)