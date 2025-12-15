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
        applause: new Audio('/static/audio/applause_v1.wav') // Use applause sound file
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
        const audio = new Audio('/static/audio/applause_v1.wav');
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
let conversationPairs = []; // Track conversation pairs (keeping for potential future use)

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

// Add CSS for subtle reward animations, typewriter effect, and smooth conversation sliding
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

    /* Typewriter effect for streaming text */
    .typing::after {
        content: '|';
        animation: blink 1s infinite;
        color: #666;
        margin-left: 2px;
    }

    @keyframes blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
    }

    /* Smooth text appearance */
    .text-content {
        transition: all 0.2s ease;
    }

    /* Smooth conversation sliding styles */
    #conversation {
        transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        will-change: transform;
    }

    .message-pair {
        transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .message-visible {
        opacity: 1;
        transform: translateY(0);
        pointer-events: all;
    }

    /* Enhanced smooth sliding for mobile */
    @media (max-width: 768px) {
        #conversation {
            transition: transform 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        }

        .message-pair {
            transition: all 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        }
    }

    /* Thinking Loader Styles */
    .thinking-loader {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        margin: 8px auto;
        width: fit-content;
    }

    .thinking-spinner {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: conic-gradient(
            from 0deg,
            #3b82f6 0deg,
            #8b5cf6 90deg,
            #ec4899 180deg,
            #f59e0b 270deg,
            #3b82f6 360deg
        );
        animation: thinkingSpin 2s linear infinite;
        position: relative;
    }

    .thinking-spinner::before {
        content: '';
        position: absolute;
        inset: 2.5px;
        background: white;
        border-radius: 50%;
    }

    .thinking-text {
        font-size: 16px;
        color: #6b7280;
        font-weight: 400;
    }

    @keyframes thinkingSpin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    /* Smooth text flow animation */
    .text-flow-in {
        animation: textFlowIn 0.4s ease-out forwards;
    }

    @keyframes textFlowIn {
        0% {
            opacity: 0.3;
            transform: translateY(2px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Enhanced text content transitions */
    .text-content {
        transition: opacity 0.2s ease-out, transform 0.2s ease-out;
    }
`;
document.head.appendChild(subtleRewardStyles);

// Show thinking loader in conversation area
function showThinkingLoader() {
    console.log('🔄 showThinkingLoader called');

    // Remove any existing loader
    hideThinkingLoader();

    // Hide the record button completely when thinking
    const recordButton = document.getElementById('recordButton');
    if (recordButton) {
        recordButton.style.display = 'none';
    }

    const conversation = document.getElementById('conversation');
    if (!conversation) {
        console.error('❌ Conversation element not found');
        return;
    }

    const loaderDiv = document.createElement('div');
    loaderDiv.id = 'thinkingLoader';
    loaderDiv.className = 'thinking-loader';

    loaderDiv.innerHTML = `
        <div class="thinking-spinner"></div>
        <div class="thinking-text">Thinking..</div>
    `;

    conversation.appendChild(loaderDiv);
    conversation.scrollTop = conversation.scrollHeight;

    console.log('✅ Thinking loader added to conversation');
}

// Hide thinking loader
function hideThinkingLoader() {
    const loader = document.getElementById('thinkingLoader');
    if (loader) {
        console.log('🗑️ Hiding thinking loader');
        loader.remove();
    }

    // Show the record button again when thinking is done
    const recordButton = document.getElementById('recordButton');
    if (recordButton) {
        recordButton.style.display = 'flex';
    }
}

// Smart conversation scrolling functionality
function scrollToLatestUserMessage() {
    const conversation = document.getElementById('conversation');
    const allMessages = conversation.querySelectorAll('.p-4'); // All message divs

    if (allMessages.length === 0) return;

    // Find the latest user message (they have 'bg-green-100' class)
    let latestUserMessage = null;
    for (let i = allMessages.length - 1; i >= 0; i--) {
        if (allMessages[i].classList.contains('bg-green-100')) {
            latestUserMessage = allMessages[i];
            break;
        }
    }

    if (!latestUserMessage) return;

    // Calculate the scroll position to put user message at very top of viewport
    const messageRect = latestUserMessage.getBoundingClientRect();
    const currentScrollY = window.scrollY;

    // Target scroll position: scroll so user message appears just below header (70px from top)
    const targetScrollY = currentScrollY + messageRect.top - 70;

    // Scroll to position user message at top
    window.scrollTo({
        top: Math.max(0, targetScrollY), // Ensure we don't scroll to negative values
        behavior: 'smooth'
    });

    console.log(`📍 SCROLL: Positioned latest user message at top of viewport`);
}

function initializeMessageForSliding(messageDiv) {
    // Add classes for smooth transitions
    messageDiv.classList.add('message-visible');

    // Ensure proper display
    messageDiv.style.display = '';
}


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

        // Update UI to show processing state - simplified button state
        elements.recordButton.disabled = true;
        elements.recordButton.classList.add('opacity-50', 'cursor-not-allowed');
        elements.recordButton.classList.remove('bg-red-500', 'recording-pulse');
        elements.recordText.textContent = 'Start Speaking';
        elements.recordIcon.textContent = '🎤';

        // Remove recording indicator
        const indicator = elements.recordButton.querySelector('.recording-indicator');
        if (indicator) {
            indicator.remove();
        }

        // Remove conversation area animation
        elements.conversation.style.boxShadow = '';

        // Create new thinking loader in conversation area (left-aligned like assistant messages)
        showThinkingLoader();
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

            // Try streaming version first, fallback to original if needed
            try {
                await sendAudioToServerStream(audioBlob);
            } catch (error) {
                console.log('Streaming failed, using fallback:', error);
                await sendAudioToServer(audioBlob);
            }

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
    
    // Calculate dynamic width for user messages based on text length
    let widthClass = 'max-w-[80%]';
    if (role === 'user') {
        const textLength = text.length;
        if (textLength < 20) {
            widthClass = 'w-fit max-w-[80%]';
        } else if (textLength < 50) {
            widthClass = 'w-fit max-w-[70%]';
        } else {
            widthClass = 'max-w-[80%]';
        }
    }

    messageDiv.className = `p-4 rounded-lg my-2 flex flex-col ${borderClass} ${
        role === 'user'
            ? `bg-green-100 ml-auto ${widthClass}` // Right-aligned for user messages with dynamic width
            : 'bg-gray-100 mr-auto max-w-[80%]'     // Left-aligned for assistant messages
    }`;

    // Create text content with larger font and appropriate alignment
    const textContent = document.createElement('div');
    textContent.className = `text-lg mb-2 ${role === 'user' ? 'text-right' : ''}`; // Right-aligned text for user messages
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
        // Validate text is not empty
        if (!text || !text.trim()) {
            console.warn('No text to speak - text content is empty');
            return;
        }

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
        })
        .catch(error => {
            console.error('Error in speak button:', error);
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

    // Initialize message for sliding animation
    initializeMessageForSliding(messageDiv);

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


// Enhanced streaming version with typewriter effect
async function sendAudioToServerStream(audioBlob) {
    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.wav');
        formData.append('session_id', sessionId);

        // Create EventSource for streaming
        const response = await fetch('/api/process_audio_stream', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Handle the streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let messageDiv = null;
        let textContentDiv = null;
        let transcript = '';
        let evaluation = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === 'metadata') {
                            // Store transcript and evaluation data
                            transcript = data.transcript;
                            evaluation = data.evaluation;

                            // Display user message
                            displayMessage('user', transcript, [], evaluation?.feedback_type);
                            conversationHistory.push({ role: 'user', content: transcript });
                        }

                        if (data.type === 'words') {
                            // Show white box on FIRST word chunk and hide thinking loader
                            if (!messageDiv) {
                                const whiteBoxTime = performance.now();
                                console.log(`📱 WHITE BOX: Appeared at ${whiteBoxTime.toFixed(1)}ms after page load`);

                                // Hide thinking loader when response starts
                                hideThinkingLoader();

                                messageDiv = createEmptyMessageDiv('assistant');
                                textContentDiv = messageDiv.querySelector('.text-content');
                                conversation.appendChild(messageDiv);
                                conversation.scrollTop = conversation.scrollHeight;
                            }

                            // Update text progressively with smooth flow animation
                            textContentDiv.textContent = data.accumulated;
                            textContentDiv.classList.add('typing');

                            // Add smooth flow animation for new text
                            textContentDiv.classList.remove('text-flow-in');
                            // Force reflow to restart animation
                            textContentDiv.offsetHeight;
                            textContentDiv.classList.add('text-flow-in');
                        }

                        if (data.type === 'complete') {
                            // Remove typing effect and add final smooth animation
                            if (textContentDiv) {
                                textContentDiv.classList.remove('typing');
                                textContentDiv.textContent = data.final_text;

                                // Add smooth flow animation for final text
                                textContentDiv.classList.remove('text-flow-in');
                                textContentDiv.offsetHeight; // Force reflow
                                textContentDiv.classList.add('text-flow-in');
                            }

                            // Add to conversation history
                            conversationHistory.push({ role: 'assistant', content: data.final_text });

                            // Check for function calls in structured conversations
                            if (data.function_call) {
                                console.log('Function call detected:', data.function_call);
                                handleFunctionCall(data.function_call);
                                return; // Don't continue with normal flow
                            }

                            // Handle celebrations and rewards
                            if (data.is_milestone && data.new_rewards > 10) {
                                const childName = sessionStorage.getItem('childName') || 'दोस्त';
                                showCelebration('milestone',
                                    `Excellent ${childName}! You've given ${data.good_response_count} great Hindi responses! 🌟`,
                                    true  // Enable applause sound for milestone celebrations
                                );
                            }

                            if (data.new_rewards > 0 && !data.is_milestone) {
                                showSubtleReward(data.new_rewards);
                            }

                            // Update rewards display
                            updateRewardsDisplay(data.sentence_count, data.reward_points);

                            // Handle correction popup
                            if (data.should_show_popup && data.amber_responses && data.amber_responses.length > 0) {
                                showCorrectionPopup(data.amber_responses, () => {
                                    setTimeout(() => {
                                        // Generate and play TTS after popup closes
                                        generateAndPlayAudio(data.final_text);
                                    }, 1000);
                                });
                            } else {
                                // Generate and play TTS immediately
                                const ttsStartTime = performance.now();
                                console.log(`🔊 TTS START: Beginning audio generation at ${ttsStartTime.toFixed(1)}ms after page load`);
                                generateAndPlayAudio(data.final_text);

                                // Scroll to position user message at top after user response (small delay for DOM update)
                                setTimeout(() => {
                                    scrollToLatestUserMessage();
                                }, 50);
                            }
                        }

                        if (data.type === 'error') {
                            throw new Error(data.message);
                        }

                    } catch (parseError) {
                        console.error('Error parsing streaming data:', parseError);
                    }
                }
            }
        }

        // Reset button state
        resetRecordingInterface();

    } catch (error) {
        console.error('Streaming Error:', error);

        // Fallback to original method
        console.log('Falling back to original sendAudioToServer');
        return sendAudioToServer(audioBlob);
    }
}

// Helper function to create empty message div for progressive text
function createEmptyMessageDiv(role) {
    const messageDiv = document.createElement('div');

    let borderClass = '';
    if (role === 'user') {
        borderClass = 'border-l-4 border-green-500';
    }

    messageDiv.className = `p-4 rounded-lg my-2 flex flex-col ${borderClass} ${
        role === 'user'
            ? 'bg-green-100 ml-auto max-w-[80%]'
            : 'bg-gray-100 mr-auto max-w-[80%]'
    }`;

    // Create text content with typing class
    const textContent = document.createElement('div');
    textContent.className = 'text-lg mb-2 text-content';
    textContent.textContent = '';
    messageDiv.appendChild(textContent);

    // Add buttons container (only for assistant messages)
    if (role === 'assistant') {
        const buttonsDiv = createMessageButtons();
        messageDiv.appendChild(buttonsDiv);
    }

    return messageDiv;
}

// Helper function to create message buttons
function createMessageButtons() {
    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end gap-2 mt-2';

    // Create speak button
    const speakButton = document.createElement('button');
    speakButton.className = 'p-1 rounded hover:bg-gray-200';
    speakButton.innerHTML = '🔊';
    speakButton.onclick = function() {
        const text = this.closest('.p-4').querySelector('.text-content').textContent.trim();
        if (!text) {
            console.warn('No text to speak - text content is empty');
            return;
        }
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
        })
        .catch(error => {
            console.error('Error in speak button:', error);
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
    translateButton.onclick = async function() {
        try {
            const text = this.closest('.p-4').querySelector('.text-content').textContent;
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text })
            });
            const data = await response.json();
            if (data.translation) {
                showTranslation(data.translation, translateButton);
            }
        } catch (error) {
            console.error('Translation error:', error);
        }
    };

    buttonsDiv.appendChild(speakButton);
    buttonsDiv.appendChild(translateButton);
    return buttonsDiv;
}

// Helper function to generate and play audio
async function generateAndPlayAudio(text) {
    try {
        // Use existing TTS endpoint
        const formData = new FormData();
        formData.append('text', text);
        const response = await fetch('/api/speak', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.audio) {
            playAudioResponse(data.audio);
        }
    } catch (error) {
        console.error('TTS Error:', error);
    }
}

// Process audio and handle responses (Original function - kept as fallback)
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

        // Remove thinking loader if it exists
        hideThinkingLoader();
        
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

        // Check for function calls in structured conversations
        if (data.function_call) {
            console.log('Function call detected:', data.function_call);
            handleFunctionCall(data.function_call);
            return; // Don't continue with normal flow
        }

        displayMessage('user', data.transcript, data.corrections, data.evaluation?.feedback_type);

        // Scroll to position user message at top after user response (small delay for DOM update)
        setTimeout(() => {
            scrollToLatestUserMessage();
        }, 50);

        // Check if correction popup should be shown FIRST
        if (data.should_show_popup && data.amber_responses && data.amber_responses.length > 0) {
            // Hold the talker response and show correction popup first
            showCorrectionPopup(data.amber_responses, () => {
                // This callback runs after popup closes
                setTimeout(() => {
                    // Display assistant message and play audio after 1-second delay
                    displayMessage('assistant', data.text, []);
                    updateRewardsDisplay(data.sentence_count, data.reward_points);
                    playAudioResponse(data.audio);
                }, 4500);
            });
        } else {
            // No correction popup, proceed normally
            displayMessage('assistant', data.text, []);
            updateRewardsDisplay(data.sentence_count, data.reward_points);
            playAudioResponse(data.audio);
        }

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
function showCorrectionPopup(amberResponses, onCloseCallback = null) {
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
        setTimeout(() => {
            overlay.remove();

            // Execute the callback after popup is closed
            if (onCloseCallback) {
                onCloseCallback();
            }
        }, 300);

        // Award bonus points for completion
        awardCorrectionBonus();

        // Play soft clapping sound to celebrate completion
        if (audioEffects && audioEffects.applause) {
            audioEffects.applause.play().catch(e => console.log('Applause sound failed:', e));
        }

        // Show completion message with Captain America shield and clapping sound
        showCelebration('milestone', 'Great work on improving your Hindi! You have scored 50 additional stars! Keep practicing! 🌟', true, true);

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

                    // DEBUG: Log the comparison values
                    console.log('=== SIMILARITY DEBUG ===');
                    console.log('User text:', JSON.stringify(userText));
                    console.log('Target text:', JSON.stringify(targetTextNormalized));
                    console.log('User words:', userText.split(' ').filter(w => w.length > 0));
                    console.log('Target words:', targetTextNormalized.split(' ').filter(w => w.length > 0));

                    // Show what user said
                    if (userText) {
                        spokenWords.textContent = userText;
                        spokenWordsArea.classList.remove('hidden');
                    }

                    // Simple text matching
                    const similarity = calculateSimilarity(userText, targetTextNormalized);
                    console.log('Calculated similarity:', similarity);
                    console.log('Threshold check (>0.7):', similarity > 0.7);
                    console.log('========================');
                    
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
        
        // Remove any thinking loader
        hideThinkingLoader();
        
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
        'about_me': 'About Me',
        'my_family': 'My Family',
        'everyday': 'Everyday Life',
        'my_toys': 'My Toys',
        'food_i_like': 'Food I Like',
        'superheroes': 'Superheroes',
        'animals_nature': 'Animals and Nature',
        'adventure_story': 'Adventure Story',
        'panchatantra_story': 'Panchatantra Story'
    };
    const typeDescs = {
        'about_me': 'Talk about yourself - your name, age, and favorite things',
        'my_family': 'Talk about your family - parents, siblings, and pets',
        'everyday': 'Talk about daily activities and school',
        'my_toys': 'Talk about your favorite toys and what you play with',
        'food_i_like': 'Talk about your favorite foods, snacks, and treats',
        'superheroes': 'Talk about your favorite superheroes and superpowers',
        'animals_nature': 'Chat about your favorite animals, pets, and wildlife',
        'adventure_story': 'Create exciting adventure stories together',
        'panchatantra_story': 'Build the famous "Thirsty Crow" story together'
    };
    const typeIcons = {
        'about_me': '🙋',
        'my_family': '👨‍👩‍👧‍👦',
        'everyday': '🏠',
        'my_toys': '🧸',
        'food_i_like': '🍽️',
        'superheroes': '🦸',
        'animals_nature': '🦊',
        'adventure_story': '🗺️',
        'panchatantra_story': '📖'
    };
    
    // Update conversation type indicator
    const nameEl = document.getElementById('conversationTypeName');
    const descEl = document.getElementById('conversationTypeDesc');
    const iconEl = document.getElementById('conversationIcon');
    
    if (nameEl) nameEl.textContent = typeNames[conversationType] || 'Conversation';
    if (descEl) descEl.textContent = typeDescs[conversationType] || 'General conversation';
    if (iconEl) iconEl.textContent = typeIcons[conversationType] || '💬';
}

// Handle function calls from structured conversations
function handleFunctionCall(functionCall) {
    console.log('Handling function call:', functionCall);

    if (functionCall.action === 'redirect' && functionCall.page === 'completion_celebration') {
        // Show completion celebration
        setTimeout(() => {
            window.location.href = '/completion_celebration';
        }, 2000); // Give 2 seconds to read the final message
    }
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