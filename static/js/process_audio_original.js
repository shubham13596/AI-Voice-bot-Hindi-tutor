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

        // Display initial message - pass null for corrections since there are none initially
        displayMessage('assistant', data.text, null);
        
        // Add to conversation history
        conversationHistory.push({ role: 'assistant', content: data.text });

        // Play initial audio
        if (data.audio) {
            playAudioResponse(data.audio);
        }
        
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
        displayMessage('user', data.transcript, data.corrections);
        displayMessage('assistant', data.text, []);

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

function showCorrectionDialog(correctedText) {
    const dialogHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                <h3 class="text-lg font-medium text-center mb-4">सही वाक्य बोलें | Say the correct sentence</h3>
                <p class="text-center text-gray-700 mb-6">${correctedText}</p>
                <div class="flex justify-center gap-4">
                    <button class="start-recording px-4 py-2 bg-purple-600 text-white rounded-full hover:bg-purple-700">
                        🎤 Record
                    </button>
                    <button class="cancel-correction px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300">
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    `;
    
    const dialogElement = document.createElement('div');
    dialogElement.innerHTML = dialogHTML;
    document.body.appendChild(dialogElement);
    
    // Add event listeners
    dialogElement.querySelector('.start-recording').addEventListener('click', () => {
        toggleRecording();
        dialogElement.remove();
    });
    
    dialogElement.querySelector('.cancel-correction').addEventListener('click', () => {
        dialogElement.remove();
    });
}

function createCorrectionSuggestion(message, corrections, onCorrect, onDismiss) {
    const container = document.createElement('div');
    container.className = 'mt-2 bg-purple-50 rounded-lg p-3 border border-purple-100 text-sm';
    
    container.innerHTML = `
        <div class="flex justify-between items-start">
            <div>
                <div class="font-medium text-purple-900"> Suggestions </div>
                <div class="mt-2 space-y-1 corrections-list"></div>
            </div>
            <button class="dismiss-btn text-gray-400 hover:text-gray-500">✕</button>
        </div>
    `;

    // Add corrections
    const correctionsList = container.querySelector('.corrections-list');
    corrections.forEach(correction => {
        const correctionItem = document.createElement('div');
        correctionItem.className = 'text-gray-600';
        correctionItem.innerHTML = `
            <span class="text-red-500">${correction.original}</span>
            <span class="mx-2">→</span>
            <span class="text-green-600 font-medium">${correction.corrected}</span>
        `;
        correctionsList.appendChild(correctionItem);
    });

    // Add event listeners
    container.querySelector('.dismiss-btn').addEventListener('click', onDismiss);
    //container.querySelector('.correct-btn').addEventListener('click', onCorrect);

    return container;
}


// Display message in conversation
function displayMessage(role, text, corrections = null) {
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

    // Add correction suggestion if available and corrections exist
    if (corrections && Array.isArray(corrections) && corrections.length > 0) {  // Add proper type checking
        let correctedText = text;
        corrections.forEach(correction => {
            correctedText = correctedText.replace(
                new RegExp(correction.original, 'gi'),
                correction.corrected
            );
        });

        const correctionElement = createCorrectionSuggestion(
            text,
            corrections,
            () => showCorrectionDialog(correctedText),
            () => correctionElement.remove()
        );
        
        messageDiv.appendChild(correctionElement);
    }
    

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

function showCorrectionDialog(correctedText) {
    const dialogHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                <h3 class="text-lg font-medium text-center mb-4">सही वाक्य बोलें | Say the correct sentence</h3>
                <p class="text-center text-gray-700 mb-6">${correctedText}</p>
                <div class="flex justify-center gap-4">
                    <button class="start-recording px-4 py-2 bg-purple-600 text-white rounded-full hover:bg-purple-700">
                        🎤 Record
                    </button>
                    <button class="cancel-correction px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300">
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    `;
    
    const dialogElement = document.createElement('div');
    dialogElement.innerHTML = dialogHTML;
    document.body.appendChild(dialogElement);
    
    // Add event listeners
    dialogElement.querySelector('.start-recording').addEventListener('click', () => {
        toggleRecording();
        dialogElement.remove();
    });
    
    dialogElement.querySelector('.cancel-correction').addEventListener('click', () => {
        dialogElement.remove();
    });
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



// Update the existing updateRewardsDisplay function
function updateRewardsDisplay(sentenceCount, rewardPoints) {
    // Update the header values
    const sentenceElement = document.getElementById('sentenceCount');
    const pointsElement = document.getElementById('rewardPoints');
    
    // Animate the number changes
    animateNumberChange(sentenceElement, sentenceCount);
    animateNumberChange(pointsElement, rewardPoints);
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

// Add this to your existing styles
const highlightStyle = document.createElement('style');
highlightStyle.textContent = `
    .highlight {
        animation: highlight 0.5s ease-out;
    }
    
    @keyframes highlight {
        0% { color: white; }
        50% { color: #fef08a; transform: scale(1.1); }
        100% { color: white; transform: scale(1); }
    }
`;
document.head.appendChild(highlightStyle);

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