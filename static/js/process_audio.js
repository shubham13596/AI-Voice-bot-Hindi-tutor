let audioEffects = null;

// First, let's add the necessary styles to the document
const recordingStyles = document.createElement('style');
recordingStyles.textContent = `
    /* Recording button animations */
    .recording-pulse {
        position: relative;
    }

    .recording-pulse::before {
        content: '';
        position: absolute;
        inset: -4px;  /* Creates space around the button */
        border-radius: 9999px;  /* Fully rounded */
        border: 2px solid #ef4444;  /* Red border */
        animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    /* Recording indicator animations */
    .recording-indicator {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-top: 0.5rem;
        padding: 0.25rem 0.75rem;
        background-color: rgba(239, 68, 68, 0.1);
        border-radius: 9999px;
        white-space: nowrap;
    }

    .recording-dot {
        width: 8px;
        height: 8px;
        background-color: #ef4444;
        border-radius: 50%;
        animation: blink 1s ease-in-out infinite;
    }

    /* Button press animation */
    .button-press {
        animation: pressDown 0.1s ease-out;
    }

    /* Keyframe animations */
    @keyframes pulse {
        0%, 100% {
            opacity: 1;
            transform: scale(1);
        }
        50% {
            opacity: 0.5;
            transform: scale(1.05);
        }
    }

    @keyframes blink {
        0%, 100% {
            opacity: 1;
        }
        50% {
            opacity: 0.3;
        }
    }

    @keyframes pressDown {
        0% {
            transform: scale(1);
        }
        50% {
            transform: scale(0.95);
        }
        100% {
            transform: scale(1);
        }
    }
`;

document.head.appendChild(recordingStyles);

function initializeAudioEffects() {
    const audioEffects = {
        firstMessage: new Audio('/static/sounds/first-message.mp3'),
        milestone: new Audio('/static/sounds/milestone.mp3'),
        reward: new Audio('/static/sounds/reward.mp3'),
        applause: new Audio('/static/applause_v1.wav') // Use applause sound file
    };
    
    // Preload audio
    Object.values(audioEffects).forEach(audio => {
        if (audio.load) audio.load(); // Check if it has load method (generated sounds may not)
    });
    return audioEffects;
}

// Create applause sound from audio file
function createApplauseSound() {
    try {
        const audio = new Audio('/static/applause_v1.wav');
        audio.volume = 0.3; // Set volume to 30%
        
        return {
            play: () => {
                return new Promise((resolve) => {
                    audio.currentTime = 0; // Reset to beginning
                    audio.play().then(() => {
                        // Resolve after audio finishes playing
                        audio.addEventListener('ended', resolve, { once: true });
                    }).catch((error) => {
                        console.warn('Applause sound playback failed:', error);
                        resolve();
                    });
                });
            }
        };
    } catch (error) {
        console.warn('Applause audio file not available, using fallback');
        return {
            play: () => {
                console.log('🎉 Applause sound would play here!');
                return Promise.resolve();
            }
        };
    }
}

// Let's create a function to get these elements
function initializeDOMElements() {
    return {
        recordButton: document.getElementById('recordButton'),
        recordText: document.getElementById('recordText'),
        recordIcon: document.getElementById('recordIcon'),
        status: document.getElementById('status'),
        conversation: document.getElementById('conversation')
        //waveform: document.getElementById('waveform')
    };
}

// Global variables
let mediaRecorder;
let audioChunks = [];
let conversationHistory = [];
let isRecording = false;
let sessionId = null;
let waveformAnimationFrame;

// Initialize recording visualization
/*
function initializeWaveform() {
    // Create wave bars
    for (let i = 0; i < 20; i++) {
        const bar = document.createElement('div');
        bar.className = 'wave-bar';
        waveform.appendChild(bar);
    }
}
*/

// Animate waveform during recording
/*
function animateWaveform() {
    const bars = waveform.querySelectorAll('.wave-bar');
    bars.forEach((bar, index) => {
        const height = 10 + Math.random() * 30;
        bar.style.height = `${height}px`;
        bar.style.animation = 'waveAnimation 0.5s ease-in-out infinite';
        bar.style.animationDelay = `${index * 0.05}s`;
    });

    if (isRecording) {
        waveformAnimationFrame = requestAnimationFrame(animateWaveform);
    }
}
    */


// Show celebration overlay with improved styling
function showCelebration(type, message, playSound = true, useApplause = false) {
    // Create main overlay container
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50 fade-in';
    
    // Create content container
    const content = document.createElement('div');
    content.className = 'bg-white rounded-lg p-6 mx-4 max-w-md w-full transform scale-in';
    
    // Add appropriate icon based on celebration type
    const icon = document.createElement('div');
    icon.className = 'text-center mb-4';
    
    if (type === 'milestone') {
        // Create Captain America shield animation
        icon.innerHTML = `
            <div class="shield-container mx-auto w-24 h-24 mb-4">
                <div class="shield animate-spin-slow">
                    <div class="shield-inner">
                        <div class="star"></div>
                    </div>
                </div>
            </div>
        `;
    } else if (type === 'firstMessage') {
        // Add star burst animation
        icon.innerHTML = `
            <div class="star-burst mx-auto w-24 h-24 mb-4">
                ⭐
            </div>
        `;
    }
    
    // Add message
    const messageEl = document.createElement('div');
    messageEl.className = 'text-center text-lg font-medium text-gray-800 mb-6';
    messageEl.textContent = message;
    
    // Add continue button
    const button = document.createElement('button');
    button.className = 'w-full bg-green-500 text-white rounded-lg py-2 px-4 hover:bg-green-600 transition-colors';
    button.textContent = 'Continue';
    button.onclick = () => {
        overlay.classList.add('fade-out');
        setTimeout(() => overlay.remove(), 500);
    };
    
    // Assemble the components
    content.appendChild(icon);
    content.appendChild(messageEl);
    content.appendChild(button);
    overlay.appendChild(content);
    
    // Add to document
    document.body.appendChild(overlay);
    
    // Play celebration sound only if requested and available
    if (playSound && audioEffects) {
        if (useApplause && audioEffects.applause) {
            // Use applause sound for correction completion celebrations
            audioEffects.applause.play().catch(e => console.log('Applause sound failed:', e));
        } else if (audioEffects[type]) {
            // Use default type-specific sound
            const audio = audioEffects[type];
            if (audio.volume !== undefined) audio.volume = 0.3; // Reduce volume if it's a regular audio element
            audio.play().catch(e => console.log('Audio playback failed:', e));
        }
    }
    
    // Add necessary styles
    const styles = document.createElement('style');
    styles.textContent = `
        .fade-in {
            animation: fadeIn 0.3s ease-out;
        }
        
        .fade-out {
            animation: fadeOut 0.3s ease-in forwards;
        }
        
        .scale-in {
            animation: scaleIn 0.3s ease-out;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; }
        }
        
        @keyframes scaleIn {
            from { transform: scale(0.95); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }
        
        @keyframes spin-slow {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .animate-spin-slow {
            animation: spin-slow 3s linear infinite;
        }
        
        .shield-container {
            perspective: 800px;
        }
        
        .shield {
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #ff0000, #cc0000);
            border-radius: 50%;
            position: relative;
            transform-style: preserve-3d;
        }
        
        .shield-inner {
            position: absolute;
            inset: 10%;
            background: radial-gradient(circle, #0000cc, #000099);
            border-radius: 50%;
            border: 2px solid white;
        }
        
        .star {
            position: absolute;
            inset: 25%;
            background: white;
            clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);
        }
        
        .star-burst {
            font-size: 48px;
            animation: starBurst 2s infinite;
        }
        
        @keyframes starBurst {
            0% { transform: scale(1); }
            50% { transform: scale(1.2); }
            100% { transform: scale(1); }
        }
    `;
    
    document.head.appendChild(styles);
    
    // Auto-remove after 3 seconds if user hasn't clicked continue (less intrusive)
    setTimeout(() => {
        if (document.body.contains(overlay)) {
            overlay.classList.add('fade-out');
            setTimeout(() => overlay.remove(), 500);
        }
    }, 3000);
}

// Update rewards display with animation
function updateRewardsDisplay(sentenceCount, rewardPoints) {
    // Update stars count in new minimal header
    const starsCountElement = document.getElementById('starsCount');
    if (starsCountElement && rewardPoints !== undefined) {
        animateNumberChange(starsCountElement, rewardPoints);
    }
}

// Helper function to animate number changes
function animateNumberChange(element, newValue) {
    if (!element || newValue === undefined) return;
    
    const currentValue = parseInt(element.textContent) || 0;
    const difference = newValue - currentValue;
    
    if (difference === 0) return;
    
    const steps = 10;
    const increment = difference / steps;
    let currentStep = 0;
    
    const animation = setInterval(() => {
        currentStep++;
        const value = Math.round(currentValue + (increment * currentStep));
        element.textContent = value;
        
        if (currentStep === steps) {
            clearInterval(animation);
            element.textContent = newValue;
            
            // Add a brief highlight effect
            element.classList.add('highlight');
            setTimeout(() => element.classList.remove('highlight'), 500);
        }
    }, 50);
}

// Show subtle reward feedback for good responses
function showSubtleReward(points) {
    const starsElement = document.getElementById('starsCount');
    if (!starsElement) return;
    
    // Create a small floating points indicator
    const floatingPoints = document.createElement('div');
    floatingPoints.className = 'absolute text-green-500 text-sm font-bold pointer-events-none';
    floatingPoints.textContent = `+${points}`;
    floatingPoints.style.cssText = `
        top: -20px;
        right: 0;
        animation: subtleReward 2s ease-out forwards;
        z-index: 1001;
    `;
    
    // Position relative to stars element
    const starsContainer = starsElement.parentElement;
    if (starsContainer) {
        starsContainer.style.position = 'relative';
        starsContainer.appendChild(floatingPoints);
        
        // Add subtle glow to stars element
        starsElement.classList.add('reward-glow');
        setTimeout(() => starsElement.classList.remove('reward-glow'), 1000);
        
        // Remove floating element
        setTimeout(() => floatingPoints.remove(), 2000);
    }
}

// Add CSS for subtle reward animations
const subtleRewardStyles = document.createElement('style');
subtleRewardStyles.textContent = `
    @keyframes subtleReward {
        0% {
            opacity: 1;
            transform: translateY(0);
        }
        100% {
            opacity: 0;
            transform: translateY(-20px);
        }
    }
    
    .reward-glow {
        box-shadow: 0 0 10px rgba(34, 197, 94, 0.5);
        transition: box-shadow 0.3s ease;
    }
    
    .highlight {
        background: rgba(34, 197, 94, 0.2);
        transition: background 0.5s ease;
    }
    
    /* Animation for checking state */
    .animate-pulse {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
`;
document.head.appendChild(subtleRewardStyles);


// Toggle recording state
function toggleRecording() {

    if (!audioEffects) {
        console.error('Audio effects not initialized');
        return; // Prevent further execution if audio isn't ready
    }

    const elements = {
        recordButton: document.getElementById('recordButton'),
        recordText: document.getElementById('recordText'),
        recordIcon: document.getElementById('recordIcon'),
        status: document.getElementById('status'),
        conversation: document.getElementById('conversation')
    };

    // Validate all required elements exist
    if (!Object.values(elements).every(element => element)) {
        console.error('Missing required DOM elements');
        return;
    }

    // Add button press animation
    elements.recordButton.classList.add('button-press');
    setTimeout(() => elements.recordButton.classList.remove('button-press'), 100);

    if (!isRecording) {
        mediaRecorder.start();
        isRecording = true;
        elements.recordText.textContent = 'Stop Speaking';
        elements.recordIcon.textContent = '⏹️';
        elements.recordButton.classList.add('bg-red-500', 'recording-pulse');
        
        // Add recording indicator
        const indicator = document.createElement('div');
        indicator.className = 'recording-indicator';
        indicator.innerHTML = `
            <div class="recording-dot"></div>
            <span class="text-red-500 text-sm font-medium">Recording...</span>
        `;
        elements.recordButton.appendChild(indicator);

        // Optional: Add a subtle background animation to the conversation area
        elements.conversation.style.boxShadow = 'inset 0 0 10px rgba(239, 68, 68, 0.1)';

    } else {

        mediaRecorder.stop();
        isRecording = false;

        // Update UI to show processing state
        elements.recordButton.disabled = true;
        elements.recordButton.classList.add('opacity-50', 'cursor-not-allowed');
        elements.recordButton.classList.remove('bg-red-500', 'recording-pulse');
        elements.recordText.textContent = 'Processing...';
        elements.recordIcon.textContent = '⏳';

        // Remove recording indicator
        const indicator = elements.recordButton.querySelector('.recording-indicator');
        if (indicator) {
            indicator.remove();
        }
        
        // Remove conversation area animation
        elements.conversation.style.boxShadow = '';

        // Create a processing message in the conversation
        const processingDiv = document.createElement('div');
        processingDiv.id = 'processingMessage';
        processingDiv.className = 'p-4 text-center text-gray-600 animate-pulse';
        processingDiv.textContent = 'Your Hindi Tutor is thinking ...';
        elements.conversation.appendChild(processingDiv);
        elements.conversation.scrollTop = elements.conversation.scrollHeight;
    }
}


// Initialize recording
async function initializeRecording() {
    try {

        // First, get DOM elements
        const elements = initializeDOMElements();

        // Check if all required elements exist
        const missingElements = Object.entries(elements)
            .filter(([key, value]) => !value)
            .map(([key]) => key);
            
        if (missingElements.length > 0) {
            throw new Error(`Missing required DOM elements: ${missingElements.join(', ')}`);
        }

        // Initialize audio effects
        audioEffects = initializeAudioEffects();

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

        // Make sure button starts disabled
        elements.recordButton.disabled = true;
        elements.recordButton.classList.add('opacity-50', 'cursor-not-allowed');
        elements.status.textContent = 'Starting conversation...';

        await startConversation();
        //initializeWaveform();
        
        return true;
    } catch (error) {
        // Log the full error for debugging
        console.error('Initialization error:', error);
        
        // Update UI with user-friendly error message
        const status = document.getElementById('status');
        if (status) {
            status.textContent = `Error: ${error.message}. Please refresh and try again.`;
        }
        
        // Also check if error is due to microphone permissions
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            status.textContent = 'Please allow microphone access to use this application.';
        }
        
        return false;
    }
}

// Start the initial conversation
async function startConversation() {
    try {
        const status = document.getElementById('status');
        const recordButton = document.getElementById('recordButton');
        
        // Disable button at the start
        recordButton.disabled = true;
        recordButton.classList.add('opacity-50', 'cursor-not-allowed');
        
        // Check if we're resuming a conversation
        const isResuming = window.isResumingConversation;
        const conversationId = window.conversationId;
        
        let response;
        
        if (isResuming && conversationId) {
            status.textContent = 'Resuming conversation...';
            console.log('Making API call to resume conversation', conversationId);
            
            response = await fetch('/api/resume_conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    conversation_id: conversationId
                })
            });
        } else {
            status.textContent = 'Starting conversation...';
            console.log('Making API call to start conversation');
            const conversationType = window.conversationType || 'everyday';
            console.log('Conversation type:', conversationType);
            
            response = await fetch('/api/start_conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    conversation_type: conversationType
                })
            });
        }

        console.log('API response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('API response data:', data);
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Store the session ID
        sessionId = data.session_id;
        
        // Handle resumed conversation differently
        if (isResuming && data.conversation_history) {
            // Load existing conversation history
            conversationHistory = data.conversation_history;
            
            // Display all previous messages
            const conversationDiv = document.getElementById('conversation');
            conversationDiv.innerHTML = ''; // Clear any existing content
            
            data.conversation_history.forEach(msg => {
                displayMessage(msg.role, msg.content, null);
            });
            
            // Only display continuation message if provided
            if (data.text) {
                displayMessage('assistant', data.text, null);
                
                // Add the continuation message to history
                conversationHistory.push({
                    role: 'assistant',
                    content: data.text
                });
            }
            
            // Update conversation type indicator if available
            if (data.conversation_type && window.conversationType !== data.conversation_type) {
                window.conversationType = data.conversation_type;
                // Update the conversation type display
                updateConversationTypeDisplay(data.conversation_type);
            }
            
        } else {
            // New conversation - display initial message
            if (data.text) {
                displayMessage('assistant', data.text, null);
                
                // Add to conversation history
                conversationHistory.push({ 
                    role: 'assistant', 
                    content: data.text 
                });
            } else {
                throw new Error('No initial message received');
            }
        }
        
        // Play initial audio if available
        if (data.audio) {
            playAudioResponse(data.audio);
        }
        
        // Enable the button and update status
        recordButton.disabled = false;
        recordButton.classList.remove('opacity-50', 'cursor-not-allowed');
        status.textContent = isResuming ? 'Conversation resumed! Click to continue talking.' : 'Click the button to start talking!';
        
    } catch (error) {
        console.error('Error starting conversation:', error);
        status.textContent = `Error: ${error.message}. Please refresh the page.`;
        // Add a refresh button
        addRefreshButton();
    }
}

// Display message in conversation
function displayMessage(role, text, corrections = null, feedbackType = 'green') {
    const messageDiv = document.createElement('div');
    
    // Determine border color based on feedback type for user messages
    let borderClass = '';
    if (role === 'user') {
        borderClass = feedbackType === 'amber' ? 'border-l-4 border-amber-500' : 'border-l-4 border-green-500';
    }
    
    messageDiv.className = `p-4 rounded-lg my-2 flex flex-col ${borderClass} ${
        role === 'user' 
            ? 'bg-green-100 ml-auto max-w-[80%]' // Right-aligned for user messages
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

// Play audio response
function playAudioResponse(base64Audio) {
    const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
    audio.play();
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


function showCorrectionDialog(correctedText) {
    const dialogHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                <h3 class="text-lg font-medium text-center mb-4">सही वाक्य बोलें | Say the correct sentence</h3>
                <p class="text-center text-gray-700 mb-6">${correctedText}</p>
                <div class="flex justify-center gap-4">
                    <button class="start-recording px-4 py-2 bg-green-500 text-white rounded-full hover:bg-green-600">
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
    container.className = 'mt-2 bg-green-50 rounded-lg p-3 border border-green-100 text-sm';
    
    container.innerHTML = `
        <div class="flex justify-between items-start">
            <div>
                <div class="font-medium text-green-900"> Suggestions </div>
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


// Process audio and handle responses
async function sendAudioToServer(audioBlob) {
    try {
        //status.textContent = 'Processing...';
        
        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.wav');
        formData.append('conversation_history', JSON.stringify(conversationHistory));
        formData.append('session_id', sessionId);

        const response = await fetch('/api/process_audio', {
            method: 'POST',
            body: formData
        });

        if (response.status === 400) {
            const errorData = await response.json();
            if (errorData.error.includes('Invalid session') || errorData.error.includes('session')) {
                // Session expired, restart conversation
                console.log('Session expired, restarting conversation...');
                const newSession = await startConversation();
                if (newSession) {
                    // Retry the audio send with new session
                    return sendAudioToServer(audioBlob);
                }
            }
            throw new Error(errorData.error);
        }

        const data = await response.json();

        // Remove processing message if it exists
        const processingMessage = document.getElementById('processingMessage');
        if (processingMessage) {
            processingMessage.remove();
        }
        
        // Quality-based celebrations only
        if (data.is_milestone && data.new_rewards > 10) {
            const childName = sessionStorage.getItem('childName') || 'दोस्त';
            showCelebration('milestone', 
                `Excellent ${childName}! You've given ${data.good_response_count} great Hindi responses! 🌟`, 
                false // No sound
            );
        }
        
        // Subtle reward feedback for good responses
        if (data.new_rewards > 0 && !data.is_milestone) {
            showSubtleReward(data.new_rewards);
        }
        
        // Update conversation
        conversationHistory.push(
            { role: 'user', content: data.transcript },
            { role: 'assistant', content: data.text }
        );

        displayMessage('user', data.transcript, data.corrections, data.evaluation?.feedback_type);
        displayMessage('assistant', data.text, []);
        
        // Check if correction popup should be shown
        if (data.should_show_popup && data.amber_responses && data.amber_responses.length > 0) {
            showCorrectionPopup(data.amber_responses);
        }
        
        updateRewardsDisplay(data.sentence_count, data.reward_points);
        playAudioResponse(data.audio);

        // Reset button state
        const recordButton = document.getElementById('recordButton');
        const recordText = document.getElementById('recordText');
        const recordIcon = document.getElementById('recordIcon');
        
        recordButton.disabled = false;
        recordButton.classList.remove('opacity-50', 'cursor-not-allowed');
        recordText.textContent = 'Start Speaking';
        recordIcon.textContent = '🎤';
        status.textContent = 'Ready to listen!';
        
        status.textContent = 'Ready to listen!';
        
    } catch (error) {
        console.error('Error:', error);
        status.textContent = `Error: ${error.message}`;

        // Reset button state even on error
        const recordButton = document.getElementById('recordButton');
        const recordText = document.getElementById('recordText');
        const recordIcon = document.getElementById('recordIcon');
        
        recordButton.disabled = false;
        recordButton.classList.remove('opacity-50', 'cursor-not-allowed');
        recordText.textContent = 'Start Speaking';
        recordIcon.textContent = '🎤';
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const initialized = await initializeRecording();
        if (!initialized) {
            throw new Error('Failed to initialize recording');
        }
    } catch (error) {
        console.error('Failed to initialize application:', error);
        // Show a user-friendly error message
        const status = document.getElementById('status');
        if (status) {
            status.textContent = 'Failed to start application. Please refresh and try again.';
        }
    }
});

// Event listeners - will be added after DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const recordButton = document.getElementById('recordButton');
    if (recordButton) {
        recordButton.addEventListener('click', toggleRecording);
    }
});

// Show correction popup for amber responses
function showCorrectionPopup(amberResponses) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
    
    const popup = document.createElement('div');
    popup.className = 'bg-white rounded-lg p-6 mx-4 max-w-md w-full';
    
    let currentIndex = 0;
    
    function renderCorrectionItem(index) {
        const item = amberResponses[index];
        popup.innerHTML = `
            <div class="text-center mb-4">
                <h3 class="text-lg font-bold text-green-600">Let's improve your Hindi!</h3>
                <p class="text-sm text-gray-600">Complete all corrections to earn badges 🏆</p>
            </div>
            
            <div class="mb-6">
                <div class="text-sm text-gray-500 mb-2">Your original response:</div>
                <div class="bg-red-50 p-3 rounded border-l-4 border-red-300 mb-4">
                    ${item.user_response}
                </div>
                
                <div class="text-sm text-gray-500 mb-2">Correct response should be:</div>
                <div class="bg-green-50 p-3 rounded border-l-4 border-green-500 mb-4 font-medium">
                    ${item.corrected_response}
                </div>
                
                <!-- User's current spoken words display area -->
                <div id="spokenWordsArea" class="hidden mb-4">
                    <div class="text-sm text-gray-500 mb-2">What you just said:</div>
                    <div id="spokenWords" class="bg-blue-50 p-3 rounded border-l-4 border-blue-300 font-medium">
                    </div>
                </div>
            </div>
            
            <div class="text-center mb-4">
                <button id="recordCorrectionBtn" class="bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-green-600 transition-colors mx-auto">
                    <span id="recordCorrectionIcon">🎤</span>
                    <span id="recordCorrectionText">Record Correct Response</span>
                </button>
            </div>
            
            <div class="flex justify-between text-sm text-gray-500">
                <span>${index + 1} of ${amberResponses.length}</span>
                <button id="skipCorrectionBtn" class="text-gray-400 hover:text-gray-600">Skip for now</button>
            </div>
        `;
        
        // Add event listeners
        const recordBtn = popup.querySelector('#recordCorrectionBtn');
        const skipBtn = popup.querySelector('#skipCorrectionBtn');
        
        recordBtn.addEventListener('click', () => {
            recordCorrection(item.corrected_response, () => {
                if (index + 1 < amberResponses.length) {
                    renderCorrectionItem(index + 1);
                } else {
                    closeCorrectionPopup();
                }
            });
        });
        
        skipBtn.addEventListener('click', () => {
            if (index + 1 < amberResponses.length) {
                renderCorrectionItem(index + 1);
            } else {
                closeCorrectionPopup();
            }
        });
    }
    
    function closeCorrectionPopup() {
        overlay.classList.add('fade-out');
        setTimeout(() => overlay.remove(), 300);
        
        // Award bonus points for completion
        awardCorrectionBonus();
        
        // Play soft clapping sound to celebrate completion
        if (audioEffects && audioEffects.applause) {
            audioEffects.applause.play().catch(e => console.log('Applause sound failed:', e));
        }
        
        // Show completion message with Captain America shield and clapping sound
        showCelebration('milestone', 'Great work on improving your Hindi! Keep practicing! 🌟', true, true);
        
        // Clear amber responses from session
        clearAmberResponses();
        
        // Reset main recording interface to ready state
        resetRecordingInterface();
    }
    
    renderCorrectionItem(0);
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
}

// Global variables for correction recording state
let correctionRecorder = null;
let isCorrectionRecording = false;

// Record correction attempt with proper UI state management
async function recordCorrection(targetText, onSuccess) {
    const recordBtn = document.getElementById('recordCorrectionBtn');
    const recordIcon = document.getElementById('recordCorrectionIcon');
    const recordText = document.getElementById('recordCorrectionText');
    const spokenWordsArea = document.getElementById('spokenWordsArea');
    const spokenWords = document.getElementById('spokenWords');
    
    // Handle button click based on current state
    if (!isCorrectionRecording) {
        // START RECORDING STATE
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            correctionRecorder = new MediaRecorder(stream);
            const tempAudioChunks = [];
            
            // Update UI to recording state
            isCorrectionRecording = true;
            recordIcon.textContent = '⏹️';
            recordText.textContent = 'Stop Recording';
            recordBtn.className = 'bg-red-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-red-600 transition-colors mx-auto';
            
            // Hide previous spoken words
            spokenWordsArea.classList.add('hidden');
            
            correctionRecorder.ondataavailable = (event) => {
                tempAudioChunks.push(event.data);
            };
            
            correctionRecorder.onstop = async () => {
                // CHECKING STATE
                recordIcon.textContent = '🔄';
                recordText.textContent = 'Your Hindi tutor is checking...';
                recordBtn.className = 'bg-blue-500 text-white px-6 py-3 rounded-full flex items-center gap-2 mx-auto animate-pulse';
                recordBtn.disabled = true;
                
                const audioBlob = new Blob(tempAudioChunks, { type: 'audio/wav' });
                
                try {
                    // Use STT-only endpoint for corrections
                    const formData = new FormData();
                    formData.append('audio', audioBlob, 'audio.wav');
                    
                    const response = await fetch('/api/correction_stt', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    const userText = data.transcript?.toLowerCase().trim() || '';
                    const targetTextNormalized = targetText.toLowerCase().trim();
                    
                    // Show what user said
                    if (userText) {
                        spokenWords.textContent = userText;
                        spokenWordsArea.classList.remove('hidden');
                    }
                    
                    // Simple text matching
                    const similarity = calculateSimilarity(userText, targetTextNormalized);
                    
                    if (similarity > 0.7) { // 70% similarity threshold
                        // SUCCESS STATE
                        recordIcon.textContent = '✅';
                        recordText.textContent = 'You got this right; let\'s move on';
                        recordBtn.className = 'bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 mx-auto';
                        recordBtn.disabled = true;
                        setTimeout(onSuccess, 2000);
                    } else {
                        // TRY AGAIN STATE
                        recordIcon.textContent = '🔄';
                        recordText.textContent = 'Try Again';
                        recordBtn.className = 'bg-orange-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-orange-600 transition-colors mx-auto';
                        recordBtn.disabled = false;
                        isCorrectionRecording = false; // Allow user to record again
                        
                        // Reset to initial state after 3 seconds if user doesn't click
                        setTimeout(() => {
                            if (!isCorrectionRecording) {
                                recordIcon.textContent = '🎤';
                                recordText.textContent = 'Record Correct Response';
                                recordBtn.className = 'bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-green-600 transition-colors mx-auto';
                            }
                        }, 3000);
                    }
                    
                } catch (error) {
                    console.error('Error processing correction:', error);
                    // ERROR STATE
                    recordIcon.textContent = '🔄';
                    recordText.textContent = 'Try Again';
                    recordBtn.className = 'bg-orange-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-orange-600 transition-colors mx-auto';
                    recordBtn.disabled = false;
                    isCorrectionRecording = false;
                } finally {
                    // Stop and cleanup correction recorder
                    stream.getTracks().forEach(track => track.stop());
                }
            };
            
            correctionRecorder.start();
            
            // Auto-stop after 10 seconds
            setTimeout(() => {
                if (correctionRecorder && correctionRecorder.state === 'recording') {
                    correctionRecorder.stop();
                    isCorrectionRecording = false;
                }
            }, 10000);
            
        } catch (error) {
            console.error('Error starting correction recording:', error);
            recordIcon.textContent = '❌';
            recordText.textContent = 'Microphone Error - Try Again';
            recordBtn.className = 'bg-red-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-red-600 transition-colors mx-auto';
            setTimeout(() => {
                recordIcon.textContent = '🎤';
                recordText.textContent = 'Record Correct Response';
                recordBtn.className = 'bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-green-600 transition-colors mx-auto';
            }, 3000);
        }
        
    } else {
        // STOP RECORDING
        if (correctionRecorder && correctionRecorder.state === 'recording') {
            correctionRecorder.stop();
            isCorrectionRecording = false;
        }
    }
}

// Simple text similarity calculation
function calculateSimilarity(text1, text2) {
    const words1 = text1.split(' ').filter(w => w.length > 0);
    const words2 = text2.split(' ').filter(w => w.length > 0);
    
    let matches = 0;
    const maxWords = Math.max(words1.length, words2.length);
    
    words1.forEach(word => {
        if (words2.includes(word)) {
            matches++;
        }
    });
    
    return matches / maxWords;
}

// Award bonus points for completing correction popup
async function awardCorrectionBonus() {
    try {
        const bonusPoints = 50; // Generous bonus for completing corrections
        
        // Update stars display immediately
        const starsElement = document.getElementById('starsCount');
        if (starsElement) {
            const currentPoints = parseInt(starsElement.textContent) || 0;
            animateNumberChange(starsElement, currentPoints + bonusPoints);
            
            // Show bonus feedback
            showSubtleReward(bonusPoints);
        }
        
        // Optionally sync with server (you could add an endpoint for this)
        // For now, the bonus is just visual feedback
        
    } catch (error) {
        console.error('Error awarding correction bonus:', error);
    }
}

// Clear amber responses from session
async function clearAmberResponses() {
    try {
        await fetch('/api/clear_amber_responses', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ session_id: sessionId })
        });
    } catch (error) {
        console.error('Error clearing amber responses:', error);
    }
}

// Reset recording interface to ready state
function resetRecordingInterface() {
    const recordButton = document.getElementById('recordButton');
    const recordText = document.getElementById('recordText');
    const recordIcon = document.getElementById('recordIcon');
    const status = document.getElementById('status');
    
    if (recordButton && recordText && recordIcon && status) {
        // Ensure recording is not active
        isRecording = false;
        
        // Reset button state
        recordButton.disabled = false;
        recordButton.classList.remove('opacity-50', 'cursor-not-allowed', 'bg-red-500', 'recording-pulse');
        recordButton.classList.add('bg-green-500');
        recordText.textContent = 'Start Speaking';
        recordIcon.textContent = '🎤';
        status.textContent = 'Ready to listen!';
        
        // Remove any processing messages
        const processingMessage = document.getElementById('processingMessage');
        if (processingMessage) {
            processingMessage.remove();
        }
        
        // Remove any recording indicators
        const indicator = recordButton.querySelector('.recording-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
}

// Helper function to update conversation type display
function updateConversationTypeDisplay(conversationType) {
    const typeNames = {
        'everyday': 'Everyday Life',
        'cartoons': 'Favorite Cartoons',
        'adventure_story': 'Adventure Story',
        'mystery_story': 'Mystery Story'
    };
    const typeDescs = {
        'everyday': 'Talk about daily activities and school',
        'cartoons': 'Chat about favorite cartoon characters',
        'adventure_story': 'Create exciting adventure stories together',
        'mystery_story': 'Solve fun mysteries and detective stories'
    };
    const typeIcons = {
        'everyday': '🏠',
        'cartoons': '🎭',
        'adventure_story': '🗺️',
        'mystery_story': '🔍'
    };
    
    // Update conversation type indicator
    const nameEl = document.getElementById('conversationTypeName');
    const descEl = document.getElementById('conversationTypeDesc');
    const iconEl = document.getElementById('conversationIcon');
    
    if (nameEl) nameEl.textContent = typeNames[conversationType] || 'Conversation';
    if (descEl) descEl.textContent = typeDescs[conversationType] || 'General conversation';
    if (iconEl) iconEl.textContent = typeIcons[conversationType] || '💬';
}

// Add refresh button for errors
function addRefreshButton() {
    const refreshBtn = document.createElement('button');
    refreshBtn.textContent = 'Refresh Page';
    refreshBtn.className = 'mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600';
    refreshBtn.onclick = () => window.location.reload();
    
    const status = document.getElementById('status');
    if (status && status.parentNode) {
        status.parentNode.appendChild(refreshBtn);
    }
}

// Error handling for audio playback
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    const status = document.getElementById('status');
    if (status) {
        status.textContent = 'Error: Something went wrong. Please try again.';
    }
});