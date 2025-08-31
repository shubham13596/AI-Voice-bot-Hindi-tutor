// DOM Elements
const recordButton = document.getElementById('recordButton');
const recordText = document.getElementById('recordText');
const recordIcon = document.getElementById('recordIcon');
const status = document.getElementById('status');
const conversation = document.getElementById('conversation');

// Global variables
let mediaRecorder;
let audioChunks = [];
let conversationHistory = [];
let isRecording = false;
let sessionId = null;
let recognition = null;
let currentUserMessageDiv = null;


// Initialize audio recording and start conversation
async function initializeRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        
        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            await sendAudioToServer(audioBlob);
            audioChunks = [];
        };

        // Start the initial conversation
        await startConversation();

        // Enable the record button once everything is set up
        recordButton.disabled = false;
        status.textContent = 'Click the button to start talking!';
        
        return true;
    } catch (error) {
        console.error('Error accessing microphone:', error);
        status.textContent = 'Error accessing microphone. Please check permissions.';
        return false;
    }
}

// Start the initial conversation
async function startConversation() {
    try {
        status.textContent = 'Starting conversation...';
        
        const response = await fetch('/api/start_conversation', {
            method: 'GET'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        // Store the session ID
        sessionId = data.session_id;

        // Display initial message
        displayMessage('assistant', data.text);
        
        // Add to conversation history
        conversationHistory.push({ role: 'assistant', content: data.text });

        // Play initial audio
        playAudioResponse(data.audio);
        
        // Initialize rewards display
        updateRewardsDisplay(0, 0);
        
        status.textContent = 'Ready to listen!';
    } catch (error) {
        console.error('Error starting conversation:', error);
        status.textContent = `Error: ${error.message}`;
    }
}

// Send audio to server and handle response
async function sendAudioToServer(audioBlob) {
    try {
        status.textContent = 'Processing...';
        
        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.wav');
        formData.append('conversation_history', JSON.stringify(conversationHistory));
        formData.append('session_id', sessionId);

        const response = await fetch('/api/process_audio', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Add messages to conversation history
        conversationHistory.push(
            { role: 'user', content: data.transcript },
            { role: 'assistant', content: data.text }
        );

        // Display messages
        displayMessage('user', data.transcript);
        displayMessage('assistant', data.text);

        // Update rewards and progress
        updateRewardsDisplay(data.sentence_count, data.reward_points);

        // Show reward animation if new points earned
        if (data.new_rewards > 0) {
            showRewardAnimation(data.new_rewards);
        }

        // Play audio response
        playAudioResponse(data.audio);
        
        status.textContent = 'Ready to listen!';
    } catch (error) {
        console.error('Error:', error);
        status.textContent = `Error: ${error.message}`;
    }
}

// Display message in conversation
function displayMessage(role, text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `p-4 rounded-lg my-2 flex flex-col ${
        role === 'user' 
            ? 'bg-purple-100 ml-auto max-w-[80%]' // Right-aligned for user messages
            : 'bg-gray-100 mr-auto max-w-[80%]'   // Left-aligned for assistant messages
    }`;

    // Create text content with larger font
    const textContent = document.createElement('div');
    textContent.className = 'text-lg mb-2'; // Larger text size
    textContent.textContent = text;
    messageDiv.appendChild(textContent);

    // Create buttons container
    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end gap-2 mt-2'; // Right-aligned buttons

    // Create speak button
    const speakButton = document.createElement('button');
    speakButton.className = 'p-1 rounded hover:bg-gray-200';
    speakButton.innerHTML = '🔊'; // Speaker emoji
    speakButton.onclick = () => {
    
        // Use the existing TTS system to speak the text
        const formData = new FormData();
        formData.append('text', text);
        fetch('/api/speak', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.audio) {
                playAudioResponse(data.audio);
            }
        });
    };

    // Create translate button
    const translateButton = document.createElement('button');
    translateButton.className = 'p-1 rounded hover:bg-gray-200';
    const uniqueId = `translate-gradient-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    translateButton.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="21" height="18">
        <defs>
            <linearGradient id="${uniqueId}" x1="0%" y1="50%" y2="106.671%">
                <stop offset="0%" stop-color="#000046"/>
                <stop offset="100%" stop-color="#1CB5E0"/>
            </linearGradient>
        </defs>
        <path d="M20.55 8.4v1.557h-1.5V18h-2.016v-3.373a2.17 2.17 0 0 1-.643.1c-.258 0-.486-.057-.7-.143v.086c0 1.615-1.216 2.8-3.16 2.8-1.872 0-2.844-1.015-3.2-1.544l1.386-1.272c.3.53.915 1.144 1.844 1.144.758 0 1.2-.458 1.2-1.086 0-.615-.442-.987-1.357-.987h-.772v-1.672h.5c.872 0 1.23-.457 1.23-1.1 0-.558-.386-.944-1-.944-.572 0-.958.272-1.23.715L9.872 9.538c.457-.657 1.358-1.2 2.544-1.2 1.672 0 2.787.957 2.787 2.415 0 .815-.37 1.515-1.043 1.844v.057a1.67 1.67 0 0 1 .486.172h.014c.025.023.054.043.086.057.386.2.786.286 1.143.286.5 0 .872-.1 1.144-.243v-2.96h-1.115V8.4h4.63zM3.03 0h3.045L9.12 10.02H6.832l-.63-2.302h-3.36L2.2 10.02H0L3.03 0zm.73 4.46l-.415 1.457h2.358l-.386-1.4-.757-3.002h-.058c-.17.858-.386 1.672-.743 2.945z" 
            fill="url(#${uniqueId})" 
            fill-rule="evenodd"/>
    </svg>`;

    translateButton.style.display = 'flex';
    translateButton.style.alignItems = 'center';
    translateButton.style.justifyContent = 'center';
    translateButton.onclick = async () => {
        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text })
            });
            const data = await response.json();
            if (data.translation) {
                // Show translation in a tooltip or small popup
                showTranslation(data.translation, translateButton);
            }
        } catch (error) {
            console.error('Translation error:', error);
        }
    };

    // Add buttons to container
    buttonsDiv.appendChild(speakButton);
    buttonsDiv.appendChild(translateButton);
    messageDiv.appendChild(buttonsDiv);

    // Add message to conversation
    conversation.appendChild(messageDiv);
    conversation.scrollTop = conversation.scrollHeight;
}

// Function to show translation
function showTranslation(translation, buttonElement) {
    // Create or get existing tooltip
    let tooltip = document.getElementById('translation-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'translation-tooltip';
        tooltip.className = 'fixed bg-white p-2 rounded shadow-lg z-50 text-sm';
        document.body.appendChild(tooltip);
    }

    // Position tooltip near the button
    const buttonRect = buttonElement.getBoundingClientRect();
    tooltip.style.top = `${buttonRect.bottom + 5}px`;
    tooltip.style.left = `${buttonRect.left}px`;
    tooltip.textContent = translation;

    // Hide tooltip after 3 seconds
    setTimeout(() => {
        tooltip.remove();
    }, 3000);
}

// Add CSS for tooltip animations
const tooltipStyle = document.createElement('style');
tooltipStyle.textContent = `
    #translation-tooltip {
        animation: fadeIn 0.3s ease-in-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(tooltipStyle);



// Update rewards display
function updateRewardsDisplay(sentenceCount, rewardPoints) {
    // Create or update rewards display
    let rewardsDiv = document.getElementById('rewardsDisplay');
    if (!rewardsDiv) {
        rewardsDiv = document.createElement('div');
        rewardsDiv.id = 'rewardsDisplay';
        rewardsDiv.className = 'fixed top-4 right-4 bg-purple-600 text-white p-4 rounded-lg shadow-lg';
        document.body.appendChild(rewardsDiv);
    }
    
    rewardsDiv.innerHTML = `
        <div class="text-lg font-bold">Progress</div>
        <div>Sentences: ${sentenceCount}</div>
        <div>Points: ${rewardPoints} ⭐</div>
    `;
}

// Show reward animation
function showRewardAnimation(points) {
    const animation = document.createElement('div');
    animation.className = 'fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-4xl';
    animation.textContent = `+${points} Points! 🎉`;
    
    // Add animation styles
    animation.style.animation = 'reward-popup 1.5s ease-out forwards';
    document.body.appendChild(animation);
    
    // Remove after animation
    setTimeout(() => {
        animation.remove();
    }, 1500);
}

// Play audio response
function playAudioResponse(base64Audio) {
    const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
    audio.play();
}

// Toggle recording state
function toggleRecording() {
    if (!isRecording) {
        // Start recording
        mediaRecorder.start();
        isRecording = true;
        recordText.textContent = 'Stop Speaking';
        recordIcon.textContent = '⏹️';
        status.textContent = 'Listening...';
        recordButton.classList.add('bg-red-500');
    } else {
        // Stop recording
        mediaRecorder.stop();
        isRecording = false;
        recordText.textContent = 'Start Speaking';
        recordIcon.textContent = '🎤';
        recordButton.classList.remove('bg-red-500');
    }
}

// Add CSS for reward animation
const style = document.createElement('style');
style.textContent = `
    @keyframes reward-popup {
        0% { 
            opacity: 0;
            transform: translate(-50%, -50%) scale(0.5);
        }
        50% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1.2);
        }
        100% {
            opacity: 0;
            transform: translate(-50%, -50%) scale(1);
        }
    }
`;
document.head.appendChild(style);

// Event Listeners
recordButton.addEventListener('click', toggleRecording);

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', async () => {
    await initializeRecording();
});

// Error handling for audio playback
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    status.textContent = 'Error: Something went wrong. Please try again.';
});

// Initialize speech recognition
function initializeSpeechRecognition() {
    try {
        // Check for browser support
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            throw new Error('Speech recognition not supported');
        }

        recognition = new (window.webkitSpeechRecognition || window.SpeechRecognition)();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'hi-IN';

        // Handle results
        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0].transcript)
                .join('');

            // Update or create user message div
            if (!currentUserMessageDiv) {
                currentUserMessageDiv = createMessageDiv('user');
                conversation.appendChild(currentUserMessageDiv);
            }
            updateMessageContent(currentUserMessageDiv, transcript);

            // If this is a final result
            if (event.results[event.results.length - 1].isFinal) {
                // Add buttons to the message
                addMessageButtons(currentUserMessageDiv, transcript);
            }
        };

        // Handle end of speech
        recognition.onend = async () => {
            if (isRecording) {
                // If still recording, restart recognition
                recognition.start();
            } else if (currentUserMessageDiv) {
                // Get the final transcript
                const transcript = currentUserMessageDiv.querySelector('.message-content').textContent;
                
                // Process response only if we have actual content
                if (transcript.trim()) {
                    // Show loading state
                    const loadingDiv = createLoadingMessage();
                    conversation.appendChild(loadingDiv);

                    try {
                        // Get response from backend
                        const response = await processGPTResponse(transcript);
                        
                        // Remove loading message
                        loadingDiv.remove();
                        
                        // Display assistant's response
                        displayMessage('assistant', response.text);
                        
                        // Play audio response
                        if (response.audio) {
                            playAudioResponse(response.audio);
                        }
                        
                        // Update conversation history
                        conversationHistory.push(
                            { role: 'user', content: transcript },
                            { role: 'assistant', content: response.text }
                        );
                    } catch (error) {
                        console.error('Error getting response:', error);
                        loadingDiv.remove();
                        displayErrorMessage('Failed to get response');
                    }
                }
                currentUserMessageDiv = null;
            }
        };

        recognition.onerror = (event) => {
            console.error('Recognition error:', event.error);
            status.textContent = `Error: ${event.error}`;
        };

        return true;
    } catch (error) {
        console.error('Speech recognition initialization error:', error);
        status.textContent = 'Speech recognition not available. Please try another browser.';
        return false;
    }
}

// Create message div
function createMessageDiv(role) {
    const div = document.createElement('div');
    div.className = `p-4 rounded-lg my-2 flex flex-col ${
        role === 'user' 
            ? 'bg-purple-100 ml-auto max-w-[80%]'
            : 'bg-gray-100 mr-auto max-w-[80%]'
    }`;
    
    const content = document.createElement('div');
    content.className = 'message-content text-lg mb-2';
    div.appendChild(content);
    
    return div;
}

// Update message content
function updateMessageContent(div, text) {
    const content = div.querySelector('.message-content');
    content.textContent = text;
    conversation.scrollTop = conversation.scrollHeight;
}

// Create loading message
function createLoadingMessage() {
    const div = document.createElement('div');
    div.className = 'bg-gray-100 mr-auto max-w-[80%] p-4 rounded-lg my-2 flex items-center';
    div.innerHTML = '<div class="loading-circle"></div><span class="ml-2">Thinking...</span>';
    return div;
}

// Process GPT response
async function processGPTResponse(transcript) {
    const response = await fetch('/api/process_text', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            text: transcript,
            conversation_history: conversationHistory
        })
    });

    if (!response.ok) {
        throw new Error('Failed to get response');
    }

    return response.json();
}

// Toggle recording state
function toggleRecording() {
    if (!recognition) {
        status.textContent = 'Speech recognition not available';
        return;
    }

    if (!isRecording) {
        // Start recording
        recognition.start();
        isRecording = true;
        recordText.textContent = 'Stop Speaking';
        recordIcon.textContent = '⏹️';
        status.textContent = 'Listening...';
        recordButton.classList.add('bg-red-500');
    } else {
        // Stop recording
        recognition.stop();
        isRecording = false;
        recordText.textContent = 'Start Speaking';
        recordIcon.textContent = '🎤';
        recordButton.classList.remove('bg-red-500');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    if (initializeSpeechRecognition()) {
        recordButton.addEventListener('click', toggleRecording);
    } else {
        recordButton.disabled = true;
    }
});