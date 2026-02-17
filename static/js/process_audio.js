let audioEffects = null;
let currentHints = [];

// ─── Transliteration Engine ───────────────────────────────────────────
let transliterationEnabled = false;

const DEVANAGARI_VOWELS = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
    'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'ऋ': 'ri', 'ॠ': 'ri',
    'ऑ': 'o'
};

const DEVANAGARI_MATRAS = {
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ृ': 'ri',
    'ॉ': 'o', 'ॅ': 'e'
};

const DEVANAGARI_CONSONANTS = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
    'ष': 'sh', 'स': 's', 'ह': 'h'
};

// Nuqta consonants (borrowed sounds)
const DEVANAGARI_NUQTA = {
    'क़': 'q', 'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z', 'फ़': 'f',
    'ड़': 'r', 'ढ़': 'rh', 'श़': 'zh'
};

const DEVANAGARI_NUMBERS = {
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
};

const HALANT = '्';
const ANUSVARA = 'ं';
const VISARGA = 'ः';
const CHANDRABINDU = 'ँ';
const NUQTA = '़';

/**
 * Convert Devanagari text to casual Roman Hindi.
 * Non-Devanagari characters (English, emoji, punctuation) pass through unchanged.
 */
function transliterateToRoman(text) {
    if (!text) return text;

    let result = '';
    let i = 0;

    while (i < text.length) {
        const char = text[i];
        const nextChar = text[i + 1] || '';
        const twoChar = char + nextChar;

        // 1. Check nuqta consonants (consonant + ़) first
        if (DEVANAGARI_NUQTA[twoChar]) {
            result += processConsonant(DEVANAGARI_NUQTA[twoChar], text, i + 2);
            i = skipToNextUnit(text, i + 2);
            continue;
        }

        // 2. Check if current char is a consonant with nuqta following
        if (DEVANAGARI_CONSONANTS[char] && nextChar === NUQTA) {
            const nuqtaCombo = char + nextChar;
            const roman = DEVANAGARI_NUQTA[nuqtaCombo] || DEVANAGARI_CONSONANTS[char];
            result += processConsonant(roman, text, i + 2);
            i = skipToNextUnit(text, i + 2);
            continue;
        }

        // 3. Standalone vowels
        if (DEVANAGARI_VOWELS[char]) {
            result += DEVANAGARI_VOWELS[char];
            i++;
            continue;
        }

        // 4. Consonants
        if (DEVANAGARI_CONSONANTS[char]) {
            result += processConsonant(DEVANAGARI_CONSONANTS[char], text, i + 1);
            i = skipToNextUnit(text, i + 1);
            continue;
        }

        // 5. Anusvara, Visarga, Chandrabindu (when appearing standalone/after vowels)
        if (char === ANUSVARA) { result += 'n'; i++; continue; }
        if (char === VISARGA) { result += 'h'; i++; continue; }
        if (char === CHANDRABINDU) { result += 'n'; i++; continue; }

        // 6. Devanagari numbers
        if (DEVANAGARI_NUMBERS[char]) { result += DEVANAGARI_NUMBERS[char]; i++; continue; }

        // 7. Devanagari danda (।) → period
        if (char === '।') { result += '.'; i++; continue; }
        if (char === '॥') { result += '.'; i++; continue; }

        // 8. Pass through everything else (English, emoji, punctuation, spaces)
        result += char;
        i++;
    }

    return result;
}

/**
 * Process a consonant: check if followed by matra, halant, or gets inherent 'a'.
 */
function processConsonant(romanBase, text, nextIndex) {
    const nextChar = text[nextIndex] || '';

    // Halant (्) — suppress inherent vowel, consonant cluster continues
    if (nextChar === HALANT) {
        return romanBase; // No inherent 'a'
    }

    // Matra — use the vowel sign instead of inherent 'a'
    if (DEVANAGARI_MATRAS[nextChar]) {
        return romanBase + DEVANAGARI_MATRAS[nextChar];
    }

    // Anusvara after consonant
    if (nextChar === ANUSVARA) {
        return romanBase + 'an';
    }

    // Chandrabindu after consonant
    if (nextChar === CHANDRABINDU) {
        return romanBase + 'an';
    }

    // Default: inherent 'a'
    return romanBase + 'a';
}

/**
 * Advance index past any matra/modifier that was consumed by processConsonant.
 */
function skipToNextUnit(text, idx) {
    const ch = text[idx] || '';
    if (ch === HALANT) {
        return idx + 1; // Skip halant
    }
    if (DEVANAGARI_MATRAS[ch]) {
        // Check for anusvara/chandrabindu after matra
        const after = text[idx + 1] || '';
        if (after === ANUSVARA || after === CHANDRABINDU) return idx + 2;
        return idx + 1;
    }
    if (ch === ANUSVARA || ch === CHANDRABINDU) {
        return idx + 1;
    }
    return idx;
}

/** Return text in the active script mode. */
function displayText(text) {
    return transliterationEnabled ? transliterateToRoman(text) : text;
}

/** Re-render all text elements that have a stored Devanagari original.
 *  Prefers API-quality roman text (data-roman-text) over JS transliteration. */
function reRenderAllText() {
    document.querySelectorAll('[data-original-text]').forEach(el => {
        if (transliterationEnabled) {
            // Prefer Sarvam API roman text if available, fall back to JS
            const apiRoman = el.getAttribute('data-roman-text');
            el.textContent = apiRoman || transliterateToRoman(el.getAttribute('data-original-text'));
        } else {
            el.textContent = el.getAttribute('data-original-text');
        }
    });
}

/**
 * Upgrade the last message of a given role with API-quality transliterated text.
 * Keeps data-original-text as Devanagari, replaces visible text with API roman.
 * If romanText is provided, uses it; otherwise falls back to displayText().
 */
function upgradeLastMessageText(romanText, originalDevanagari, role = 'assistant') {
    if (!romanText) return;
    const selector = role === 'user'
        ? '#conversation .ml-auto'
        : '#conversation .flex.items-start.gap-3:last-of-type .text-content, #conversation .bg-gray-100.mr-auto:last-of-type .text-lg';
    const candidates = document.querySelectorAll(
        role === 'user' ? '#conversation .ml-auto' : '#conversation .bg-gray-100'
    );
    const lastMsg = candidates[candidates.length - 1];
    if (!lastMsg) return;

    const textEl = lastMsg.querySelector('[data-original-text]') || lastMsg.querySelector('.text-lg');
    if (textEl) {
        if (originalDevanagari) {
            textEl.setAttribute('data-original-text', originalDevanagari);
        }
        textEl.setAttribute('data-roman-text', romanText);
        if (transliterationEnabled) {
            textEl.textContent = romanText;
        }
    }
}

/** Update the toggle button label to reflect current mode. */
function updateTransliterationToggle() {
    const label = document.getElementById('toggleLabel');
    const btn = document.getElementById('transliterationToggle');
    if (label && btn) {
        label.textContent = transliterationEnabled ? 'A' : 'अ';
        btn.title = transliterationEnabled ? 'Switch to Devanagari' : 'Switch to Roman';
        btn.classList.toggle('transliteration-active', transliterationEnabled);
    }
}
// ─── End Transliteration Engine ───────────────────────────────────────

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
        audio.volume = 0.5;
        
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
        recordIcon: document.getElementById('recordIcon'),
        status: document.getElementById('status'),
        conversation: document.getElementById('conversation')
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
let mediaStream = null; // Track media stream for iOS cleanup
let recordingCancelled = false; // Flag for cancel-recording flow
let maxTurns = 6; // Updated from server on start

// ============================================
// AUTO-START / MANUAL-SEND STATE MACHINE
// ============================================
// States: IDLE | KIKI_SPEAKING | LISTENING | PROCESSING
let appState = 'IDLE';

// Web Audio API nodes for waveform visualization
let analyserNode = null;
let micSourceNode = null;

// Waveform canvas rendering
let waveformCanvas = null;
let waveformCtx = null;
let waveformRAF = null;

// Timers
let safetyTimeoutId = null;
let autoStartDelayId = null;

// Constants
const NOISE_FLOOR = 150;           // visual threshold (0-255) for ignoring background noise
const SAFETY_TIMEOUT_MS = 60000; // 60s auto-stop timer
const AUTO_START_DELAY_MS = 500; // delay after audio ends before mic opens

/**
 * transitionTo(newState) — single source of truth for all UI state
 */
function transitionTo(newState) {
    const oldState = appState;
    appState = newState;
    console.log(`🔄 State: ${oldState} → ${newState}`);

    const recordButton = document.getElementById('recordButton');
    const recordIcon = document.getElementById('recordIcon');
    const status = document.getElementById('status');
    const waveformContainer = document.getElementById('waveformContainer');
    const speakPrompt = document.getElementById('speakPrompt');
    const speakPromptText = document.getElementById('speakPromptText');
    const hintsBulbBtn = document.getElementById('hintsBulbBtn');
    const cancelButton = document.getElementById('cancelButton');
    const hintsContainer = document.getElementById('hintsContainer');

    switch (newState) {
        case 'KIKI_SPEAKING':
            if (speakPrompt) speakPrompt.style.display = 'none';
            if (hintsBulbBtn) hintsBulbBtn.style.display = 'none';
            if (waveformContainer) waveformContainer.style.display = 'none';
            if (cancelButton) cancelButton.style.display = 'none';
            if (recordButton) recordButton.style.display = 'none';
            if (hintsContainer) hintsContainer.style.display = 'none';
            if (status) status.textContent = 'Kiki is speaking...';
            stopWaveform();
            clearTimeout(safetyTimeoutId);
            break;

        case 'LISTENING':
            // Clear stale no-speech messages
            document.querySelectorAll('.no-speech-msg').forEach(el => el.remove());
            if (speakPrompt) speakPrompt.style.display = 'flex';
            if (speakPromptText) speakPromptText.textContent = 'Speak now...';
            if (hintsBulbBtn) hintsBulbBtn.style.display = currentHints.length > 0 ? 'flex' : 'none';
            if (waveformContainer) waveformContainer.style.display = 'flex';
            if (cancelButton) cancelButton.style.display = 'flex';
            if (recordButton) {
                recordButton.style.display = 'flex';
                recordButton.disabled = false;
                recordButton.classList.add('send-mode');
            }
            if (recordIcon) recordIcon.textContent = '➤';
            if (status) status.textContent = '';
            startWaveform();
            // Safety timeout: auto-stop after 60s
            clearTimeout(safetyTimeoutId);
            safetyTimeoutId = setTimeout(() => {
                if (appState === 'LISTENING') {
                    console.log('⏰ Safety timeout: auto-stopping recording');
                    stopRecordingAndSend();
                }
            }, SAFETY_TIMEOUT_MS);
            break;

        case 'PROCESSING':
            document.querySelectorAll('.no-speech-msg').forEach(el => el.remove());
            if (speakPrompt) speakPrompt.style.display = 'none';
            if (waveformContainer) waveformContainer.style.display = 'none';
            if (cancelButton) cancelButton.style.display = 'none';
            if (recordButton) recordButton.style.display = 'none';
            if (hintsContainer) hintsContainer.style.display = 'none';
            stopWaveform();
            clearTimeout(safetyTimeoutId);
            showThinkingLoader();
            break;

        case 'IDLE':
            if (speakPrompt) speakPrompt.style.display = 'flex';
            if (speakPromptText) speakPromptText.textContent = 'Press Record';
            if (hintsBulbBtn) hintsBulbBtn.style.display = 'none';
            if (waveformContainer) waveformContainer.style.display = 'none';
            if (cancelButton) cancelButton.style.display = 'none';
            if (recordButton) {
                recordButton.style.display = 'flex';
                recordButton.disabled = false;
                recordButton.classList.remove('send-mode');
            }
            if (recordIcon) recordIcon.textContent = '🎤';
            if (status) status.textContent = '';
            stopWaveform();
            clearTimeout(safetyTimeoutId);
            break;
    }
}

// ============================================
// iOS/iPadOS AUDIO COMPATIBILITY FIXES
// ============================================

// Audio context for iOS audio unlocking
let audioContext = null;
let isAudioUnlocked = false;

// Platform detection
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
              (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
const isAndroid = /android/i.test(navigator.userAgent);

console.log('🔍 Platform Detection:', { isIOS, isSafari, isAndroid, userAgent: navigator.userAgent });

/**
 * Unlock audio context for iOS - must be called from user gesture
 */
async function unlockAudioContext() {
    if (isAudioUnlocked) return Promise.resolve();

    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            console.warn('AudioContext not supported');
            return;
        }

        audioContext = new AudioContextClass();

        if (audioContext.state === 'suspended') {
            await audioContext.resume();
        }

        // Play silent buffer to fully unlock
        const buffer = audioContext.createBuffer(1, 1, 22050);
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        source.start(0);

        // Also create and play a silent HTML audio element to unlock that path too
        const silentAudio = document.createElement('audio');
        silentAudio.src = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYYoRwmHAAAAAAD/+1DEAAAFAAGf9AAAIgAANIAAAARMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7UMQbg8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV';
        silentAudio.volume = 0.01;
        silentAudio.play().catch(() => {});

        isAudioUnlocked = true;
        console.log('🔊 Audio context unlocked successfully');

    } catch (error) {
        console.error('Failed to unlock audio context:', error);
    }
}

/**
 * Setup early audio unlock - listen for first user interaction
 * This ensures audio is unlocked BEFORE Kiki's first message plays
 */
function setupEarlyAudioUnlock() {
    const unlockEvents = ['touchstart', 'touchend', 'click', 'keydown'];

    const earlyUnlock = async () => {
        await unlockAudioContext();
        // Remove listeners after first unlock
        unlockEvents.forEach(event => {
            document.removeEventListener(event, earlyUnlock, true);
        });
        console.log('🔓 Early audio unlock triggered by user interaction');
    };

    // Add listeners with capture to catch events early
    unlockEvents.forEach(event => {
        document.addEventListener(event, earlyUnlock, true);
    });

    console.log('👆 Waiting for first user interaction to unlock audio...');
}

/**
 * Get supported MIME type for MediaRecorder (iOS compatibility)
 */
function getSupportedMimeType() {
    const types = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/ogg;codecs=opus',
        'audio/wav'
    ];

    for (const type of types) {
        if (MediaRecorder.isTypeSupported(type)) {
            console.log('✅ Supported MIME type found:', type);
            return type;
        }
    }
    console.warn('⚠️ No preferred MIME type supported, using default');
    return null;
}


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
            if (audio.volume !== undefined) audio.volume = 0.5;
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

// Update conversation progress bar
function updateProgressBar(sentenceCount) {
    const fill = document.getElementById('progressBarFill');
    if (!fill) return;
    const pct = Math.min(100, (sentenceCount / maxTurns) * 100);
    fill.style.width = pct + '%';
    // Shift gradient position as progress increases
    fill.style.backgroundPosition = (100 - pct) + '% 0';
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

    .message-enter {
        opacity: 0;
        transform: translateY(14px);
        transition: opacity 0.35s ease-out, transform 0.35s ease-out;
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

    .thinking-emoji {
        font-size: 16px;
        display: inline-block;
        animation: emojiCyclePop 0.3s ease-out forwards;
    }

    .thinking-text {
        font-size: 16px;
        color: #6b7280;
        font-weight: 400;
    }

    @keyframes emojiCyclePop {
        0% {
            opacity: 0;
            transform: scale(0);
        }
        50% {
            transform: scale(1.2);
        }
        100% {
            opacity: 1;
            transform: scale(1);
        }
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

    // Hide controls when thinking
    const recordButton = document.getElementById('recordButton');
    if (recordButton) recordButton.style.display = 'none';
    const waveformContainer = document.getElementById('waveformContainer');
    if (waveformContainer) waveformContainer.style.display = 'none';
    const speakPrompt = document.getElementById('speakPrompt');
    if (speakPrompt) speakPrompt.style.display = 'none';
    const cancelButton = document.getElementById('cancelButton');
    if (cancelButton) cancelButton.style.display = 'none';

    const conversation = document.getElementById('conversation');
    if (!conversation) {
        console.error('❌ Conversation element not found');
        return;
    }

    const loaderDiv = document.createElement('div');
    loaderDiv.id = 'thinkingLoader';
    loaderDiv.className = 'thinking-loader';

    const emojis = ['🤔', '💡', '✨'];

    loaderDiv.innerHTML = `
        <span class="thinking-emoji">${emojis[0]}</span>
        <div class="thinking-text">Thinking..</div>
    `;

    // Append remaining emojis one by one, then stop
    let emojiIndex = 1;
    const textEl = loaderDiv.querySelector('.thinking-text');
    loaderDiv._emojiInterval = setInterval(() => {
        if (emojiIndex >= emojis.length) {
            clearInterval(loaderDiv._emojiInterval);
            return;
        }
        const span = document.createElement('span');
        span.className = 'thinking-emoji';
        span.textContent = emojis[emojiIndex];
        loaderDiv.insertBefore(span, textEl);
        emojiIndex++;
    }, 1000);

    conversation.appendChild(loaderDiv);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    console.log('✅ Thinking loader added to conversation');
}

// Hide thinking loader
function hideThinkingLoader() {
    const loader = document.getElementById('thinkingLoader');
    if (loader) {
        console.log('🗑️ Hiding thinking loader');
        if (loader._emojiInterval) {
            clearInterval(loader._emojiInterval);
        }
        loader.remove();
    }
    // Note: record button visibility is managed by the state machine (transitionTo)
}

// Smart conversation scrolling — scroll to bottom so "Send Reply" CTA is visible
function scrollToLatestUserMessage() {
    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: 'smooth'
    });
}

function initializeMessageForSliding(element) {
    // Start hidden — the element gets appended to the DOM first,
    // then we flip to visible on the next frame for a smooth slide-up.
    element.classList.add('message-enter');
}


// Toggle recording state
async function toggleRecording() {
    if (!audioEffects) {
        console.error('Audio effects not initialized');
        return;
    }

    const elements = {
        recordButton: document.getElementById('recordButton'),
        recordIcon: document.getElementById('recordIcon'),
        status: document.getElementById('status'),
        conversation: document.getElementById('conversation')
    };

    if (!Object.values(elements).every(element => element)) {
        console.error('Missing required DOM elements');
        return;
    }

    // ★ iOS FIX: Unlock audio context on first interaction
    await unlockAudioContext();

    elements.recordButton.classList.add('button-press');
    setTimeout(() => elements.recordButton.classList.remove('button-press'), 100);

    if (!isRecording) {
        // ============================================
        // START RECORDING - iOS FIX
        // ============================================

        try {
            // ★ iOS FIX: Create fresh MediaRecorder for each recording on iOS
            if (isIOS) {
                console.log('📱 iOS detected: Preparing MediaRecorder');

                // Check if we need a new stream (reuse existing if still active)
                const needNewStream = !mediaStream ||
                    mediaStream.getTracks().some(track => track.readyState === 'ended');

                if (needNewStream) {
                    console.log('📱 Getting new audio stream...');
                    // Stop old stream tracks if any
                    if (mediaStream) {
                        mediaStream.getTracks().forEach(track => track.stop());
                    }
                    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                } else {
                    console.log('📱 Reusing existing audio stream (faster!)');
                }

                // Get supported MIME type
                const mimeType = getSupportedMimeType();
                const options = mimeType ? { mimeType } : {};

                // Create new MediaRecorder (required for each recording on iOS)
                mediaRecorder = new MediaRecorder(mediaStream, options);

                // Reset chunks
                audioChunks = [];

                // Set up event handlers
                mediaRecorder.ondataavailable = (event) => {
                    if (event.data && event.data.size > 0) {
                        audioChunks.push(event.data);
                        console.log('📦 Audio chunk received, size:', event.data.size);
                    }
                };

                mediaRecorder.onstop = async () => {
                    if (recordingCancelled) { recordingCancelled = false; audioChunks = []; return; }

                    console.log('🛑 MediaRecorder stopped');
                    console.log('=== AUDIO DEBUG ===');
                    console.log('Number of chunks:', audioChunks.length);
                    console.log('Chunk sizes:', audioChunks.map(c => c.size));
                    console.log('MediaRecorder mimeType:', mediaRecorder.mimeType);

                    // ★ iOS FIX: Use actual MIME type from recorder
                    const actualMimeType = mediaRecorder.mimeType || 'audio/webm';
                    const audioBlob = new Blob(audioChunks, { type: actualMimeType });

                    console.log('Total blob size:', audioBlob.size);
                    console.log('==================');

                    // Check for empty recording
                    if (audioBlob.size < 1000) {
                        console.warn('⚠️ Audio blob too small, likely empty recording');
                        displayNoSpeechMessage();
                        transitionTo('IDLE');
                        audioChunks = [];
                        return;
                    }

                    try {
                        await sendAudioToServerStream(audioBlob);
                    } catch (error) {
                        console.log('Streaming failed, using fallback:', error);
                        await sendAudioToServer(audioBlob);
                    }
                    // Note: audioChunks is reset in startRecordingAuto() before each new recording
                };

                mediaRecorder.onerror = (event) => {
                    console.error('MediaRecorder error:', event.error);
                    resetRecordingInterface();
                    elements.status.textContent = 'Recording error. Please try again.';
                };
            }

            // ★ iOS FIX: Start with timeslice to ensure data collection
            mediaRecorder.start(100); // Collect data every 100ms

            isRecording = true;
            transitionTo('LISTENING');

            // Auto-collapse hints
            const hintsContent = document.getElementById('hintsContent');
            if (hintsContent && hintsContent.classList.contains('expanded')) {
                hintsContent.classList.remove('expanded');
                hintsContent.classList.add('collapsed');
            }

            console.log('🎙️ Recording started');

        } catch (error) {
            console.error('Error starting recording:', error);
            elements.status.textContent = 'Microphone error. Please check permissions.';
            resetRecordingInterface();
        }

    } else {
        // ============================================
        // STOP RECORDING
        // ============================================

        // ★ iOS FIX: Warm up audio element NOW (during user gesture)
        // so it can play Kiki's response later without NotAllowedError
        warmUpAudioElement();

        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }

        isRecording = false;
        showThinkingLoader();

        console.log('🛑 Recording stopped, processing...');
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

        // Hide button initially — state machine will show it when appropriate
        elements.recordButton.style.display = 'none';

        // Show start overlay on ALL platforms (mic permission requested on button tap)
        elements.status.textContent = 'Tap to start your conversation!';
        showStartOverlay();

        return true;
    } catch (error) {
        // Log the full error for debugging
        console.error('Initialization error:', error);

        // Update UI with user-friendly error message
        const status = document.getElementById('status');
        if (status) {
            status.textContent = `Error: ${error.message}. Please refresh and try again.`;
        }

        return false;
    }
}

// Set up MediaRecorder handlers on the current mediaRecorder instance
function setupMediaRecorderHandlers() {
    mediaRecorder.ondataavailable = (event) => {
        // ★ iOS FIX: Only add chunks with data
        if (event.data && event.data.size > 0) {
            audioChunks.push(event.data);
            console.log('📦 Audio chunk received, size:', event.data.size);
        }
    };

    mediaRecorder.onstop = async () => {
        if (recordingCancelled) { recordingCancelled = false; audioChunks = []; return; }

        // ★ iOS FIX: Use actual MIME type from recorder, not hardcoded 'audio/wav'
        const actualMimeType = mediaRecorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunks, { type: actualMimeType });

        console.log('=== AUDIO DEBUG ===');
        console.log('Number of chunks:', audioChunks.length);
        console.log('Total blob size:', audioBlob.size);
        console.log('MIME type:', actualMimeType);
        console.log('==================');

        // ★ iOS FIX: Check for empty recording
        if (audioBlob.size < 1000) {
            console.warn('⚠️ Audio blob too small, likely empty recording');
            displayNoSpeechMessage();
            transitionTo('IDLE');
            audioChunks = [];
            return;
        }

        transitionTo('PROCESSING');

        // Try streaming version first, fallback to original if needed
        try {
            await sendAudioToServerStream(audioBlob);
        } catch (error) {
            console.log('Streaming failed, using fallback:', error);
            await sendAudioToServer(audioBlob);
        }
        // Note: audioChunks is reset in startRecordingAuto() before each new recording
    };
}

// Start the initial conversation
async function startConversation() {
    try {
        const status = document.getElementById('status');
        const recordButton = document.getElementById('recordButton');

        // Hide button at the start — state machine will manage visibility
        recordButton.style.display = 'none';
        
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

        // Store max turns and init progress bar
        if (data.max_turns) maxTurns = data.max_turns;
        updateProgressBar(data.sentence_count || 0);

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

                // Always store API-quality transliteration on DOM for later toggle use
                if (data.text_roman) {
                    upgradeLastMessageText(data.text_roman, data.text);
                }

                // Add to conversation history
                conversationHistory.push({
                    role: 'assistant',
                    content: data.text
                });
            } else {
                throw new Error('No initial message received');
            }
        }
        
        // Play initial audio if available, then auto-start recording
        if (data.audio) {
            await playAudioResponse(data.audio);
            scheduleAutoStartRecording();
        } else {
            // No audio to play, go to IDLE for manual start
            transitionTo('IDLE');
        }
        
    } catch (error) {
        console.error('Error starting conversation:', error);
        if (window.Sentry) Sentry.captureException(error);
        status.textContent = `Error: ${error.message}. Please refresh the page.`;
        // Add a refresh button
        addRefreshButton();
    }
}

// Display message in conversation
function displayMessage(role, text, corrections = null, feedbackType = 'green') {
    // Determine border color based on feedback type for user messages
    let borderClass = '';
    let bgClass = 'bg-green-100';
    if (role === 'user') {
        if (feedbackType === 'pending') {
            borderClass = 'border-l-4 border-gray-200';
            bgClass = 'bg-white';
        } else if (feedbackType === 'amber') {
            borderClass = 'border-l-4 border-amber-500';
            bgClass = 'bg-green-100';
        } else {
            borderClass = 'border-l-4 border-green-500';
            bgClass = 'bg-green-100';
        }
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

    // Create message bubble
    const messageDiv = document.createElement('div');
    messageDiv.className = `p-4 rounded-lg my-2 flex flex-col ${borderClass} ${
        role === 'user'
            ? `${bgClass} ml-auto ${widthClass}` // Right-aligned for user messages with dynamic width
            : 'bg-gray-100 mr-auto max-w-[80%]'     // Left-aligned for assistant messages
    }`;

    // Create text content with larger font and appropriate alignment
    const textContent = document.createElement('div');
    textContent.className = `text-lg mb-2 ${role === 'user' ? 'text-right' : ''}`; // Right-aligned text for user messages
    textContent.setAttribute('data-original-text', text);
    textContent.textContent = displayText(text);
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

    // Add amber micro-copy indicator for grammar corrections
    if (role === 'user' && feedbackType === 'amber') {
        const amberIndicator = document.createElement('div');
        amberIndicator.className = 'text-xs text-gray-400 text-left mt-1 italic';
        amberIndicator.textContent = '📝 Note saved for review';
        messageDiv.appendChild(amberIndicator);
    }

    // For assistant messages, wrap with Kiki avatar
    // The element that gets appended to the conversation (and animated) may
    // be the wrapper (assistant) or messageDiv itself (user).
    let animTarget;

    if (role === 'assistant') {
        const messageWithAvatar = document.createElement('div');
        messageWithAvatar.className = 'flex items-start gap-3 my-2';

        const avatar = document.createElement('img');
        avatar.src = '/static/illustrations/Kiki.png';
        avatar.className = 'w-12 h-12 rounded-full object-cover flex-shrink-0';
        avatar.alt = 'Kiki';

        messageWithAvatar.appendChild(avatar);
        messageWithAvatar.appendChild(messageDiv);

        messageDiv.classList.remove('my-2');

        // Apply enter class to the wrapper so the whole row slides in
        initializeMessageForSliding(messageWithAvatar);
        conversation.appendChild(messageWithAvatar);
        animTarget = messageWithAvatar;
    } else {
        initializeMessageForSliding(messageDiv);
        conversation.appendChild(messageDiv);
        animTarget = messageDiv;
    }

    // Trigger the transition on the next frame (element must be in the DOM first)
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            animTarget.classList.add('message-visible');
        });
    });

    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
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

// Debug helper - logs to console only (no visual panel in production)
function debugLog(message, isError = false) {
    if (isError) {
        console.warn(message);
    } else {
        console.log(message);
    }
}

// ★ iOS FIX: Shared audio element that gets "unlocked" during user gesture
let sharedAudioElement = null;

/**
 * Get or create the shared audio element
 */
function getSharedAudioElement() {
    if (!sharedAudioElement) {
        sharedAudioElement = document.createElement('audio');
        sharedAudioElement.id = 'kikiSharedAudio';
        sharedAudioElement.setAttribute('playsinline', '');
        sharedAudioElement.setAttribute('webkit-playsinline', '');
        document.body.appendChild(sharedAudioElement);
        debugLog('Created shared audio element');
    }
    return sharedAudioElement;
}

/**
 * ★ iOS FIX: "Warm up" the audio element during a user gesture
 * This must be called directly from a click/touch handler
 */
function warmUpAudioElement() {
    if (!isIOS && !isSafari) return; // Only needed for iOS/Safari

    const audio = getSharedAudioElement();
    // Tiny silent WAV file (44 bytes)
    audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    audio.play().then(() => {
        debugLog('✅ Audio element warmed up during user gesture');
    }).catch(e => {
        debugLog(`⚠️ Warm up failed: ${e.message}`, true);
    });
}

/**
 * Show start overlay on all platforms before requesting mic permission.
 * The user gesture (button tap) triggers getUserMedia, ensuring the user
 * understands why mic access is needed before the browser prompt appears.
 */
function showStartOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'startOverlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        backdrop-filter: blur(5px);
        -webkit-backdrop-filter: blur(5px);
    `;

    overlay.innerHTML = `
        <div id="startOverlayContent" style="text-align: center; color: white; padding: 20px;">
            <div style="font-size: 48px; margin-bottom: 16px;">🎙️</div>
            <h2 style="font-size: 24px; margin-bottom: 8px; font-weight: 600;">Ready to talk with Kiki?</h2>
            <p style="font-size: 16px; opacity: 0.8; margin-bottom: 24px;">Kiki needs your microphone to hear you speak Hindi</p>
            <button id="startButton" style="
                background: linear-gradient(135deg, #22c55e, #16a34a);
                color: white;
                border: none;
                padding: 16px 48px;
                font-size: 18px;
                font-weight: 600;
                border-radius: 50px;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
                transition: transform 0.2s, box-shadow 0.2s;
            ">Start Talking! 🎙️</button>
        </div>
    `;

    document.body.appendChild(overlay);

    const button = document.getElementById('startButton');

    // Add hover effect
    button.addEventListener('mouseenter', () => {
        button.style.transform = 'scale(1.05)';
        button.style.boxShadow = '0 6px 20px rgba(34, 197, 94, 0.5)';
    });
    button.addEventListener('mouseleave', () => {
        button.style.transform = 'scale(1)';
        button.style.boxShadow = '0 4px 15px rgba(34, 197, 94, 0.4)';
    });

    button.addEventListener('click', async () => {
        debugLog('🚀 Start button clicked - requesting microphone access');

        // Disable button to prevent double-tap
        button.disabled = true;
        button.textContent = 'Connecting...';

        try {
            // 1. Request mic permission (triggers browser prompt)
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // 2. Create MediaRecorder
            const mimeType = getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};
            console.log('🎤 Creating MediaRecorder with options:', options);

            mediaRecorder = new MediaRecorder(stream, options);
            mediaStream = stream;

            // 3. Attach recording handlers
            setupMediaRecorderHandlers();

            // 4. iOS/Safari audio warmup (must happen in user gesture)
            if (isIOS || isSafari) {
                await unlockAudioContext();
                warmUpAudioElement();
            }

            // 5. Fade out overlay and start conversation
            overlay.style.transition = 'opacity 0.3s';
            overlay.style.opacity = '0';
            setTimeout(async () => {
                overlay.remove();
                const status = document.getElementById('status');
                if (status) status.textContent = 'Starting conversation...';
                await startConversation();
            }, 300);

        } catch (error) {
            console.error('Mic permission error:', error);
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                showPermissionDeniedUI(overlay);
            } else {
                showMicErrorUI(overlay, error.message);
            }
        }
    });

    debugLog('🎙️ Start overlay shown - waiting for user tap');
}

/**
 * Show recovery UI when microphone permission is denied.
 * Replaces overlay content with instructions to re-enable mic access.
 */
function showPermissionDeniedUI(overlay) {
    const content = document.getElementById('startOverlayContent');
    if (!content) return;

    content.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 16px;">🔇</div>
        <h2 style="font-size: 24px; margin-bottom: 8px; font-weight: 600;">Kiki can't hear you</h2>
        <p style="font-size: 16px; opacity: 0.8; margin-bottom: 16px;">Please allow microphone access so Kiki can hear you speak Hindi</p>
        <p style="font-size: 14px; opacity: 0.7; margin-bottom: 24px; line-height: 1.5;">
            Tap the 🔒 icon in your browser's address bar<br>
            → Set Microphone to <strong>Allow</strong><br>
            → Then tap "Try Again" below
        </p>
        <button id="retryMicButton" style="
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
            border: none;
            padding: 16px 48px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 50px;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
            transition: transform 0.2s, box-shadow 0.2s;
        ">Try Again 🎙️</button>
    `;

    const retryButton = document.getElementById('retryMicButton');

    retryButton.addEventListener('mouseenter', () => {
        retryButton.style.transform = 'scale(1.05)';
        retryButton.style.boxShadow = '0 6px 20px rgba(34, 197, 94, 0.5)';
    });
    retryButton.addEventListener('mouseleave', () => {
        retryButton.style.transform = 'scale(1)';
        retryButton.style.boxShadow = '0 4px 15px rgba(34, 197, 94, 0.4)';
    });

    retryButton.addEventListener('click', async () => {
        retryButton.disabled = true;
        retryButton.textContent = 'Connecting...';

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            const mimeType = getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};
            mediaRecorder = new MediaRecorder(stream, options);
            mediaStream = stream;
            setupMediaRecorderHandlers();

            if (isIOS || isSafari) {
                await unlockAudioContext();
                warmUpAudioElement();
            }

            overlay.style.transition = 'opacity 0.3s';
            overlay.style.opacity = '0';
            setTimeout(async () => {
                overlay.remove();
                const status = document.getElementById('status');
                if (status) status.textContent = 'Starting conversation...';
                await startConversation();
            }, 300);

        } catch (error) {
            retryButton.disabled = false;
            retryButton.textContent = 'Try Again 🎙️';
            if (error.name !== 'NotAllowedError' && error.name !== 'PermissionDeniedError') {
                showMicErrorUI(overlay, error.message);
            }
        }
    });
}

/**
 * Show generic mic error UI (hardware not found, etc.)
 */
function showMicErrorUI(overlay, errorMessage) {
    const content = document.getElementById('startOverlayContent');
    if (!content) return;

    content.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
        <h2 style="font-size: 24px; margin-bottom: 8px; font-weight: 600;">Microphone not available</h2>
        <p style="font-size: 16px; opacity: 0.8; margin-bottom: 16px;">Kiki couldn't find a microphone on your device</p>
        <p id="micErrorDetail" style="font-size: 14px; opacity: 0.6; margin-bottom: 24px;"></p>
        <button id="retryMicButton" style="
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
            border: none;
            padding: 16px 48px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 50px;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
            transition: transform 0.2s, box-shadow 0.2s;
        ">Try Again 🎙️</button>
    `;

    // Set error message safely via textContent (not innerHTML)
    const errorDetail = document.getElementById('micErrorDetail');
    if (errorDetail) errorDetail.textContent = errorMessage;

    const retryButton = document.getElementById('retryMicButton');
    retryButton.addEventListener('click', () => {
        // Reset overlay to initial state
        overlay.remove();
        showStartOverlay();
    });
}

// Play audio response (awaitable — resolves when audio finishes)
async function playAudioResponse(base64Audio) {
    debugLog(`playAudioResponse called, data length: ${base64Audio ? base64Audio.length : 'NULL'}`);

    transitionTo('KIKI_SPEAKING');

    try {
        if (!base64Audio || base64Audio.length < 100) {
            debugLog('ERROR: base64Audio is empty or too short!', true);
            return;
        }

        // Use the shared <audio> element on all platforms.
        // On iOS/Safari this is already warmed up via warmUpAudioElement()
        // during the user gesture, so it plays in the "media" audio category
        // and respects hardware volume buttons.
        const audio = getSharedAudioElement();
        audio.src = `data:audio/wav;base64,${base64Audio}`;

        debugLog(`Audio src set, attempting play...`);

        await new Promise((resolve, reject) => {
            audio.onplay = () => debugLog('✅ Audio started playing!');
            audio.onerror = (e) => {
                debugLog(`❌ Audio error: ${e.type}`, true);
                reject(new Error(`Audio error: ${e.type}`));
            };
            audio.onended = () => {
                debugLog('Audio finished playing');
                resolve();
            };

            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => debugLog('✅ Play promise resolved'))
                    .catch(error => {
                        debugLog(`❌ Play promise rejected: ${error.name} - ${error.message}`, true);
                        reject(error);
                    });
            }
        });
    } catch (error) {
        debugLog(`❌ Exception in playAudioResponse: ${error.message}`, true);
    }
}


// ============================================
// AUTO-START / MANUAL-SEND FUNCTIONS
// ============================================

/**
 * Schedule mic auto-start after a short delay
 */
function scheduleAutoStartRecording() {
    clearTimeout(autoStartDelayId);
    autoStartDelayId = setTimeout(() => {
        startRecordingAuto();
    }, AUTO_START_DELAY_MS);
}

/**
 * Auto-start recording (called after Kiki finishes speaking)
 */
async function startRecordingAuto() {
    // Guards
    if (appState === 'LISTENING' || isRecording) {
        console.log('⚠️ Already listening or recording, skipping auto-start');
        return;
    }

    try {
        if (isIOS) {
            console.log('📱 iOS auto-start: Preparing MediaRecorder');

            // Check if we need a new stream
            const needNewStream = !mediaStream ||
                mediaStream.getTracks().some(track => track.readyState === 'ended');

            if (needNewStream) {
                console.log('📱 Getting new audio stream...');
                if (mediaStream) {
                    mediaStream.getTracks().forEach(track => track.stop());
                }
                try {
                    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                } catch (micError) {
                    console.warn('📱 Mic access failed (no gesture?), falling back to IDLE');
                    transitionTo('IDLE');
                    return;
                }
            } else {
                console.log('📱 Reusing existing audio stream');
            }

            // Get supported MIME type
            const mimeType = getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};

            // Create new MediaRecorder
            mediaRecorder = new MediaRecorder(mediaStream, options);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                if (recordingCancelled) { recordingCancelled = false; audioChunks = []; return; }

                console.log('🛑 iOS auto MediaRecorder stopped');
                const actualMimeType = mediaRecorder.mimeType || 'audio/webm';
                const audioBlob = new Blob(audioChunks, { type: actualMimeType });

                if (audioBlob.size < 1000) {
                    console.warn('⚠️ Audio blob too small, likely empty recording');
                    displayNoSpeechMessage();
                    transitionTo('IDLE');
                    audioChunks = [];
                    return;
                }

                transitionTo('PROCESSING');

                try {
                    await sendAudioToServerStream(audioBlob);
                } catch (error) {
                    console.log('Streaming failed, using fallback:', error);
                    await sendAudioToServer(audioBlob);
                }
                // Note: audioChunks is reset in startRecordingAuto() before each new recording
            };

            mediaRecorder.onerror = (event) => {
                console.error('MediaRecorder error:', event.error);
                transitionTo('IDLE');
            };
        }
        // Non-iOS: reuse existing mediaRecorder from initializeRecording()
        // Just reset audioChunks
        audioChunks = [];

        // Connect analyser for waveform
        connectAnalyser();

        // Start recording
        mediaRecorder.start(100);
        isRecording = true;
        transitionTo('LISTENING');

        // Auto-collapse hints
        const hintsContent = document.getElementById('hintsContent');
        if (hintsContent && hintsContent.classList.contains('expanded')) {
            hintsContent.classList.remove('expanded');
            hintsContent.classList.add('collapsed');
        }

        console.log('🎙️ Auto-recording started');

    } catch (error) {
        console.error('Error in auto-start recording:', error);
        transitionTo('IDLE');
    }
}

/**
 * Stop recording and send audio (called by "Send Reply" or safety timeout)
 */
function stopRecordingAndSend() {
    if (!isRecording) {
        console.log('⚠️ Not recording, ignoring stop');
        return;
    }

    // iOS: warm up audio element for next playback
    warmUpAudioElement();

    // Disconnect analyser
    disconnectAnalyser();

    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }

    isRecording = false;
    clearTimeout(safetyTimeoutId);

    // Note: transitionTo('PROCESSING') happens inside onstop handler after blob validation
    console.log('🛑 Recording stopped via stopRecordingAndSend');
}

/**
 * Cancel recording — discard audio and return to IDLE
 */
function cancelRecording() {
    recordingCancelled = true;
    disconnectAnalyser();

    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }

    isRecording = false;
    clearTimeout(safetyTimeoutId);
    transitionTo('IDLE');
    console.log('❌ Recording cancelled by user');
}

/**
 * Display a "couldn't hear you" message bubble in the conversation
 */
function displayNoSpeechMessage() {
    const conversation = document.getElementById('conversation');
    if (!conversation) return;

    // Remove any previous no-speech messages first
    conversation.querySelectorAll('.no-speech-msg').forEach(el => el.remove());

    const msgDiv = document.createElement('div');
    msgDiv.className = 'no-speech-msg bg-orange-50 border border-orange-200 rounded-lg p-3 text-center text-sm text-orange-700 my-2';
    msgDiv.textContent = "Sorry, we couldn't hear you. Please try recording again.";
    conversation.appendChild(msgDiv);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    // Auto-expand hints if available
    const hintsContent = document.getElementById('hintsContent');
    if (hintsContent && !hintsContent.classList.contains('expanded') && currentHints.length > 0) {
        hintsContent.classList.remove('collapsed');
        hintsContent.classList.add('expanded');
    }
}

// ============================================
// WAVEFORM VISUALIZATION (Web Audio API)
// ============================================

/**
 * Connect AnalyserNode to mic stream for waveform data
 */
function connectAnalyser() {
    try {
        if (!audioContext) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                audioContext = new AudioContextClass();
            }
        }
        if (!audioContext || !mediaStream) return;

        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }

        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 256;
        analyserNode.smoothingTimeConstant = 0.8;

        micSourceNode = audioContext.createMediaStreamSource(mediaStream);
        micSourceNode.connect(analyserNode);
        // NOT connected to destination — no speaker feedback
    } catch (error) {
        console.warn('Could not connect analyser:', error);
    }
}

/**
 * Disconnect analyser from mic stream
 */
function disconnectAnalyser() {
    try {
        if (micSourceNode) {
            micSourceNode.disconnect();
            micSourceNode = null;
        }
    } catch (e) {
        console.warn('Error disconnecting analyser:', e);
    }
}

/**
 * Start waveform rendering on canvas — compact dot-based visualization
 */
function startWaveform() {
    if (!waveformCanvas) {
        waveformCanvas = document.getElementById('waveformCanvas');
    }
    if (!waveformCanvas) return;
    waveformCtx = waveformCanvas.getContext('2d');

    // Dynamic canvas sizing — sync drawing buffer to CSS layout size with devicePixelRatio for retina
    function syncCanvasSize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = waveformCanvas.getBoundingClientRect();
        waveformCanvas.width = rect.width * dpr;
        waveformCanvas.height = rect.height * dpr;
        waveformCtx.scale(dpr, dpr);
    }
    syncCanvasSize();

    const barCount = 21;
    const DOT_RADIUS = 2.5;
    const MAX_BAR_HEIGHT = 28;
    const barWidth = 5;
    const gap = 6;
    const excitement = new Float32Array(barCount);
    const startTime = performance.now();
    const centerIndex = Math.floor(barCount / 2);

    function draw() {
        waveformRAF = requestAnimationFrame(draw);

        const dpr = window.devicePixelRatio || 1;
        const cssWidth = waveformCanvas.getBoundingClientRect().width;
        const cssHeight = waveformCanvas.getBoundingClientRect().height;

        if (Math.abs(waveformCanvas.width - cssWidth * dpr) > 1) {
            syncCanvasSize();
        }

        waveformCtx.clearRect(0, 0, cssWidth, cssHeight);

        const elapsed = (performance.now() - startTime) / 1000;

        // Get average volume from analyser
        const AVG_NOISE_FLOOR = 8;
        let avgVolume = 0;
        if (analyserNode) {
            const bufferLength = analyserNode.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);
            analyserNode.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let j = 0; j < bufferLength; j++) {
                sum += dataArray[j];
            }
            avgVolume = sum / bufferLength;
        }

        const isSpeaking = avgVolume > AVG_NOISE_FLOOR;
        const totalWidth = barCount * barWidth + (barCount - 1) * gap;
        const startX = (cssWidth - totalWidth) / 2;

        for (let i = 0; i < barCount; i++) {
            const distFromCenter = Math.abs(i - centerIndex);

            // Idle: only middle 2-3 bars get tiny sin oscillation
            let idleExtra = 0;
            if (distFromCenter <= 1) {
                const sineVal = Math.sin(elapsed * 2.5 + i * 0.5);
                idleExtra = (sineVal * 0.5 + 0.5) * 3; // 0–3px
            }

            // Speaking excitement: center bars react most
            if (isSpeaking && distFromCenter <= 3 && Math.random() < 0.4) {
                const proximityFactor = 1.0 - distFromCenter / 4;
                const normalizedVol = Math.min(1.0, avgVolume / 60);
                const boost = normalizedVol * proximityFactor * (0.5 + Math.random() * 0.5);
                excitement[i] = Math.min(1.0, excitement[i] + boost);
            }

            // Snappier decay
            excitement[i] *= 0.88;

            // Bar height: dot minimum + idle + excitement
            const excitedHeight = excitement[i] * MAX_BAR_HEIGHT;
            const barHeight = Math.max(DOT_RADIUS * 2, DOT_RADIUS * 2 + idleExtra + excitedHeight);

            const x = startX + i * (barWidth + gap);
            const y = (cssHeight - barHeight) / 2;

            // Marigold orange: brighter when excited
            const lightness = Math.floor(35 + excitement[i] * 25);
            waveformCtx.fillStyle = `hsl(35, 90%, ${lightness}%)`;

            // Draw rounded bar (pill shape)
            const radius = Math.min(barWidth / 2, barHeight / 2);
            if (waveformCtx.roundRect) {
                waveformCtx.beginPath();
                waveformCtx.roundRect(x, y, barWidth, barHeight, radius);
                waveformCtx.fill();
            } else {
                waveformCtx.fillRect(x, y, barWidth, barHeight);
            }
        }
    }

    draw();
}

/**
 * Stop waveform rendering and clear canvas
 */
function stopWaveform() {
    if (waveformRAF) {
        cancelAnimationFrame(waveformRAF);
        waveformRAF = null;
    }
    if (waveformCtx && waveformCanvas) {
        waveformCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    }
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
                <h3 class="text-lg font-medium text-center mb-4" data-original-text="सही वाक्य बोलें | Say the correct sentence">${displayText('सही वाक्य बोलें')} | Say the correct sentence</h3>
                <p class="text-center text-gray-700 mb-6" data-original-text="${correctedText}">${displayText(correctedText)}</p>
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
            <span class="text-red-500" data-original-text="${correction.original}">${displayText(correction.original)}</span>
            <span class="mx-2">→</span>
            <span class="text-green-600 font-medium" data-original-text="${correction.corrected}">${displayText(correction.corrected)}</span>
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

        // Check for no_speech JSON response (not a stream)
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const jsonData = await response.json();
            if (jsonData.error === 'no_speech') {
                displayNoSpeechMessage();
                transitionTo('IDLE');
                return;
            }
            throw new Error(jsonData.message || 'Unknown error');
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
                            // Legacy: combined transcript + evaluation
                            transcript = data.transcript;
                            evaluation = data.evaluation;
                            displayMessage('user', transcript, [], evaluation?.feedback_type);
                            conversationHistory.push({ role: 'user', content: transcript });
                        }

                        if (data.type === 'transcript') {
                            // Show user message immediately with neutral/white style
                            transcript = data.transcript;
                            displayMessage('user', transcript, [], 'pending');
                            conversationHistory.push({ role: 'user', content: transcript });

                            // Upgrade to API-quality transliteration if available
                            if (data.transcript_roman && transliterationEnabled) {
                                upgradeLastMessageText(data.transcript_roman, transcript, 'user');
                            }
                        }

                        if (data.type === 'evaluation') {
                            // Evaluation arrived — update the last user bubble's border + bg
                            evaluation = data.evaluation;
                            const allUserMsgs = document.querySelectorAll('#conversation .bg-white.ml-auto, #conversation .bg-green-100.ml-auto');
                            const lastUserMsg = allUserMsgs[allUserMsgs.length - 1];
                            if (lastUserMsg) {
                                // Remove pending styles
                                lastUserMsg.classList.remove('bg-white', 'border-gray-200');
                                if (evaluation?.feedback_type === 'amber') {
                                    lastUserMsg.classList.add('bg-green-100', 'border-amber-500');
                                    // Add amber micro-copy indicator
                                    if (!lastUserMsg.querySelector('.text-gray-400.italic')) {
                                        const amberIndicator = document.createElement('div');
                                        amberIndicator.className = 'text-xs text-gray-400 text-left mt-1 italic';
                                        amberIndicator.textContent = '📝 Note saved for review';
                                        lastUserMsg.appendChild(amberIndicator);
                                    }
                                } else {
                                    lastUserMsg.classList.add('bg-green-100', 'border-green-500');
                                }
                            }
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

                                // Wrap assistant message with Kiki avatar
                                const messageWithAvatar = document.createElement('div');
                                messageWithAvatar.className = 'flex items-start gap-3 my-2';

                                // Create Kiki avatar
                                const avatar = document.createElement('img');
                                avatar.src = '/static/illustrations/Kiki.png';
                                avatar.className = 'w-12 h-12 rounded-full object-cover flex-shrink-0';
                                avatar.alt = 'Kiki';

                                // Remove my-2 from messageDiv since it's now on the wrapper
                                messageDiv.classList.remove('my-2');

                                // Add avatar and message to wrapper
                                messageWithAvatar.appendChild(avatar);
                                messageWithAvatar.appendChild(messageDiv);

                                // Slide-in animation
                                initializeMessageForSliding(messageWithAvatar);
                                conversation.appendChild(messageWithAvatar);
                                requestAnimationFrame(() => {
                                    requestAnimationFrame(() => {
                                        messageWithAvatar.classList.add('message-visible');
                                    });
                                });
                                window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                            }

                            // Update text progressively with smooth flow animation
                            textContentDiv.setAttribute('data-original-text', data.accumulated);
                            textContentDiv.textContent = displayText(data.accumulated);
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
                                textContentDiv.setAttribute('data-original-text', data.final_text);
                                textContentDiv.textContent = displayText(data.final_text);

                                // Add smooth flow animation for final text
                                textContentDiv.classList.remove('text-flow-in');
                                textContentDiv.offsetHeight; // Force reflow
                                textContentDiv.classList.add('text-flow-in');
                            }

                            // Add to conversation history
                            conversationHistory.push({ role: 'assistant', content: data.final_text });

                            // Store function_call for after TTS plays
                            const pendingFunctionCall = data.function_call;
                            const pendingConversationId = data.conversation_id;

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
                            updateProgressBar(data.sentence_count);

                            // Update hints display
                            if (!pendingFunctionCall && data.hints && data.hints.length > 0) {
                                currentHints = data.hints;
                                updateHintsDisplay(data.hints);
                            }

                            // Handle correction popup
                            if (data.should_show_popup && data.amber_responses && data.amber_responses.length > 0) {
                                showCorrectionPopup(data.amber_responses, async () => {
                                    setTimeout(async () => {
                                        // Generate and play TTS after popup closes
                                        await generateAndPlayAudio(data.final_text, { skipAutoRecord: !!pendingFunctionCall });
                                        if (pendingFunctionCall) {
                                            handleFunctionCall(pendingFunctionCall, pendingConversationId);
                                        }
                                    }, 1000);
                                });
                            } else {
                                // Generate and play TTS (skip auto-record if conversation is ending)
                                const ttsStartTime = performance.now();
                                console.log(`🔊 TTS START: Beginning audio generation at ${ttsStartTime.toFixed(1)}ms after page load`);
                                await generateAndPlayAudio(data.final_text, { skipAutoRecord: !!pendingFunctionCall });

                                if (pendingFunctionCall) {
                                    console.log('Function call detected, redirecting after TTS:', pendingFunctionCall);
                                    handleFunctionCall(pendingFunctionCall, pendingConversationId);
                                } else {
                                    // Scroll to position user message at top after user response (small delay for DOM update)
                                    setTimeout(() => {
                                        scrollToLatestUserMessage();
                                    }, 50);
                                }
                            }
                        }

                        if (data.type === 'hints') {
                            // Late-arriving hints — update display
                            if (data.hints && data.hints.length > 0) {
                                currentHints = data.hints;
                                updateHintsDisplay(data.hints);
                            }
                        }

                        if (data.type === 'transliteration') {
                            // API-quality response transliteration — arrives ~200ms after complete
                            if (transliterationEnabled) {
                                if (data.final_text_roman) {
                                    upgradeLastMessageText(data.final_text_roman, null, 'assistant');
                                }
                                if (data.amber_responses_roman) {
                                    window._amberTranslitRoman = data.amber_responses_roman;
                                }
                            }
                            // Always cache for later toggle use
                            if (data.final_text_roman && textContentDiv) {
                                textContentDiv.setAttribute('data-roman-text', data.final_text_roman);
                            }
                        }

                        if (data.type === 'hints_transliteration') {
                            // API-quality hints transliteration (arrives after hints)
                            const hintsText = document.getElementById('hintsText');
                            if (hintsText && data.hints_roman) {
                                hintsText.setAttribute('data-roman-text', data.hints_roman);
                                if (transliterationEnabled) {
                                    hintsText.textContent = data.hints_roman;
                                }
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

        // State is managed by the state machine, no manual reset needed

    } catch (error) {
        console.error('Streaming Error:', error);
        if (window.Sentry) Sentry.captureException(error);

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

// Helper function to generate and play audio (now awaits playback + auto-starts)
async function generateAndPlayAudio(text, options = {}) {
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
            await playAudioResponse(data.audio);
            if (!options.skipAutoRecord) {
                scheduleAutoStartRecording();
            }
        }
    } catch (error) {
        console.error('TTS Error:', error);
        transitionTo('IDLE');
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

        // Store function_call for after TTS plays
        const pendingFunctionCall = data.function_call;
        const pendingConversationId = data.conversation_id;

        displayMessage('user', data.transcript, data.corrections, data.evaluation?.feedback_type);

        // Scroll to position user message at top after user response (small delay for DOM update)
        setTimeout(() => {
            scrollToLatestUserMessage();
        }, 50);

        // Check if correction popup should be shown FIRST
        if (data.should_show_popup && data.amber_responses && data.amber_responses.length > 0) {
            // Hold the talker response and show correction popup first
            showCorrectionPopup(data.amber_responses, async () => {
                // This callback runs after popup closes
                setTimeout(async () => {
                    // Display assistant message and play audio after delay
                    displayMessage('assistant', data.text, []);
                    updateRewardsDisplay(data.sentence_count, data.reward_points);
                    updateProgressBar(data.sentence_count);
                    await playAudioResponse(data.audio);
                    if (pendingFunctionCall) {
                        handleFunctionCall(pendingFunctionCall, pendingConversationId);
                    } else {
                        scheduleAutoStartRecording();
                    }
                }, 4500);
            });
        } else {
            // No correction popup, proceed normally
            displayMessage('assistant', data.text, []);
            updateRewardsDisplay(data.sentence_count, data.reward_points);
            updateProgressBar(data.sentence_count);
            await playAudioResponse(data.audio);
            if (pendingFunctionCall) {
                console.log('Function call detected, redirecting after TTS:', pendingFunctionCall);
                handleFunctionCall(pendingFunctionCall, pendingConversationId);
            } else {
                scheduleAutoStartRecording();
            }
        }

        // State is managed by the state machine, no manual reset needed

    } catch (error) {
        console.error('Error:', error);
        const statusEl = document.getElementById('status');
        if (statusEl) statusEl.textContent = `Error: ${error.message}`;
        transitionTo('IDLE');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize transliteration from stored preference
    transliterationEnabled = sessionStorage.getItem('transliterationEnabled') === 'true';
    updateTransliterationToggle();

    // Wire up transliteration toggle button
    const translitToggle = document.getElementById('transliterationToggle');
    if (translitToggle) {
        translitToggle.addEventListener('click', () => {
            transliterationEnabled = !transliterationEnabled;
            sessionStorage.setItem('transliterationEnabled', String(transliterationEnabled));
            updateTransliterationToggle();
            reRenderAllText();

            // Persist to backend (fire and forget)
            fetch('/api/user/transliteration', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: transliterationEnabled })
            }).catch(err => console.error('Failed to save transliteration pref:', err));
        });
    }

    // ★ iOS FIX: Setup early audio unlock to catch first user interaction
    if (isIOS || isSafari) {
        setupEarlyAudioUnlock();
    }

    try {
        const initialized = await initializeRecording();
        if (!initialized) {
            throw new Error('Failed to initialize recording');
        }
    } catch (error) {
        console.error('Failed to initialize application:', error);
        if (window.Sentry) Sentry.captureException(error);
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
        recordButton.addEventListener('click', () => {
            if (appState === 'LISTENING') {
                // "Send Reply" pressed
                stopRecordingAndSend();
            } else if (appState === 'IDLE') {
                // Manual fallback
                startRecordingAuto();
            }
            // All other states → ignore (button hidden anyway)
        });
    }

    // Setup hints bulb toggle
    const hintsBulbBtn = document.getElementById('hintsBulbBtn');
    if (hintsBulbBtn) {
        hintsBulbBtn.addEventListener('click', toggleHints);
        console.log('💡 Hints bulb button initialized');
    }

    // Setup cancel button
    const cancelButton = document.getElementById('cancelButton');
    if (cancelButton) {
        cancelButton.addEventListener('click', cancelRecording);
        console.log('❌ Cancel button initialized');
    }
});

// Show correction popup for amber responses
function showCorrectionPopup(amberResponses, onCloseCallback = null) {
    // Clean up any existing correction state before showing popup
    isCorrectionRecording = false;
    if (correctionRecorder && correctionRecorder.state === 'recording') {
        correctionRecorder.stop();
    }
    if (correctionStream) {
        correctionStream.getTracks().forEach(track => track.stop());
        correctionStream = null;
    }
    
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
    
    const popup = document.createElement('div');
    popup.className = 'bg-white rounded-lg p-6 mx-4 max-w-md w-full';
    
    let currentIndex = 0;
    
    function renderCorrectionItem(index) {
        // Reset correction recording state for each new item
        isCorrectionRecording = false;
        if (correctionRecorder && correctionRecorder.state === 'recording') {
            correctionRecorder.stop();
        }
        if (correctionStream) {
            correctionStream.getTracks().forEach(track => track.stop());
            correctionStream = null;
        }
        
        const item = amberResponses[index];
        // Prefer API-quality roman text if available
        const amberRoman = window._amberTranslitRoman && window._amberTranslitRoman[index];
        const userResponseDisplay = (transliterationEnabled && amberRoman?.user_response_roman)
            ? amberRoman.user_response_roman : displayText(item.user_response);
        const correctedResponseDisplay = (transliterationEnabled && amberRoman?.corrected_response_roman)
            ? amberRoman.corrected_response_roman : displayText(item.corrected_response);

        popup.innerHTML = `
            <div class="text-center mb-4">
                <h3 class="text-lg font-bold text-green-600">Let's improve your Hindi!</h3>
                <p class="text-sm text-gray-600">Complete all corrections to earn more stars 🏆</p>
            </div>

            <div class="mb-6">
                <div class="text-sm text-gray-500 mb-2">Your original response:</div>
                <div class="bg-red-50 p-3 rounded border-l-4 border-red-300 mb-4" data-original-text="${item.user_response}">
                    ${userResponseDisplay}
                </div>

                <div class="text-sm text-gray-500 mb-2">Correct response should be:</div>
                <div class="bg-green-50 p-3 rounded border-l-4 border-green-500 mb-4 font-medium" data-original-text="${item.corrected_response}">
                    ${correctedResponseDisplay}
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
        
        // Add event listeners after a small delay to ensure DOM is ready
        setTimeout(() => {
            const recordBtn = popup.querySelector('#recordCorrectionBtn');
            const skipBtn = popup.querySelector('#skipCorrectionBtn');
            
            if (recordBtn) {
                recordBtn.addEventListener('click', () => {
                    recordCorrection(item.corrected_response, () => {
                        if (index + 1 < amberResponses.length) {
                            renderCorrectionItem(index + 1);
                        } else {
                            closeCorrectionPopup();
                        }
                    });
                });
            }
            
            if (skipBtn) {
                skipBtn.addEventListener('click', () => {
                    // Stop any ongoing recording before skipping
                    if (correctionRecorder && correctionRecorder.state === 'recording') {
                        correctionRecorder.stop();
                    }
                    isCorrectionRecording = false;
                    
                    if (index + 1 < amberResponses.length) {
                        renderCorrectionItem(index + 1);
                    } else {
                        closeCorrectionPopup();
                    }
                });
            }
        }, 50);
    }
    
    function closeCorrectionPopup() {
        // Clean up any ongoing recording
        if (correctionRecorder && correctionRecorder.state === 'recording') {
            correctionRecorder.stop();
        }
        isCorrectionRecording = false;
        if (correctionStream) {
            correctionStream.getTracks().forEach(track => track.stop());
            correctionStream = null;
        }
        
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

        // Audio will play next via the onCloseCallback, so enter KIKI_SPEAKING
        transitionTo('KIKI_SPEAKING');
    }
    
    renderCorrectionItem(0);
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
}

// Global variables for correction recording state
let correctionRecorder = null;
let isCorrectionRecording = false;
let correctionStream = null; // Track the stream separately

// Record correction attempt with proper UI state management
async function recordCorrection(targetText, onSuccess) {
    const recordBtn = document.getElementById('recordCorrectionBtn');
    const recordIcon = document.getElementById('recordCorrectionIcon');
    const recordText = document.getElementById('recordCorrectionText');
    const spokenWordsArea = document.getElementById('spokenWordsArea');
    const spokenWords = document.getElementById('spokenWords');
    
    // Prevent rapid double-clicks
    if (recordBtn.disabled) {
        console.log('Button disabled, ignoring click');
        return;
    }
    
    // Handle button click based on current state
    if (!isCorrectionRecording) {
        // START RECORDING STATE
        
        // Immediately disable button to prevent double-clicks
        recordBtn.disabled = true;
        
        try {
            // Stop any existing main mediaRecorder first
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                console.log('Stopping main mediaRecorder before correction recording');
                mediaRecorder.stop();
            }
            
            // Clean up any previous correction recorder
            if (correctionRecorder && correctionRecorder.state === 'recording') {
                console.log('Stopping previous correction recorder');
                correctionRecorder.stop();
            }
            if (correctionStream) {
                correctionStream.getTracks().forEach(track => track.stop());
                correctionStream = null;
            }
            
            // Small delay to ensure previous streams are released
            await new Promise(resolve => setTimeout(resolve, 150));
            
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            correctionStream = stream; // Store reference for cleanup
            correctionRecorder = new MediaRecorder(stream);
            const tempAudioChunks = [];
            
            // Set up handlers BEFORE starting
            correctionRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    tempAudioChunks.push(event.data);
                    console.log('Audio chunk received, size:', event.data.size);
                }
            };
            
            correctionRecorder.onstop = async () => {
                console.log('Correction recorder stopped, chunks:', tempAudioChunks.length);
                
                // Check if we actually recorded anything meaningful
                const totalSize = tempAudioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
                if (tempAudioChunks.length === 0 || totalSize < 1000) {
                    console.warn('No meaningful audio data captured - resetting state');
                    recordIcon.textContent = '🎤';
                    recordText.textContent = 'Record Correct Response';
                    recordBtn.className = 'bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-green-600 transition-colors mx-auto';
                    recordBtn.disabled = false;
                    isCorrectionRecording = false;
                    
                    // Cleanup stream
                    if (correctionStream) {
                        correctionStream.getTracks().forEach(track => track.stop());
                        correctionStream = null;
                    }
                    return;
                }
                
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
                        spokenWords.setAttribute('data-original-text', userText);
                        spokenWords.textContent = displayText(userText);
                        spokenWordsArea.classList.remove('hidden');
                    }

                    // Simple text matching
                    const similarity = calculateSimilarity(userText, targetTextNormalized);
                    console.log('Calculated similarity:', similarity);
                    console.log('Threshold check (>0.65):', similarity > 0.65);
                    console.log('========================');
                    
                    if (similarity > 0.65) { // 65% similarity threshold
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
                            if (!isCorrectionRecording && recordBtn && recordText.textContent === 'Try Again') {
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
                    // Cleanup stream
                    if (correctionStream) {
                        correctionStream.getTracks().forEach(track => track.stop());
                        correctionStream = null;
                    }
                }
            };
            
            // Update UI to recording state
            isCorrectionRecording = true;
            recordIcon.textContent = '⏹️';
            recordText.textContent = 'Stop Recording';
            recordBtn.className = 'bg-red-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-red-600 transition-colors mx-auto';
            
            // Hide previous spoken words
            spokenWordsArea.classList.add('hidden');
            
            // Start recording with timeslice to ensure ondataavailable fires periodically
            correctionRecorder.start(500); // Collect data every 500ms
            
            console.log('Correction recording started');
            
            // Re-enable button after a short delay to allow stopping
            setTimeout(() => {
                if (isCorrectionRecording) {
                    recordBtn.disabled = false;
                }
            }, 300);
            
            // Auto-stop after 10 seconds
            setTimeout(() => {
                if (correctionRecorder && correctionRecorder.state === 'recording') {
                    console.log('Auto-stopping correction recording after 10 seconds');
                    correctionRecorder.stop();
                    isCorrectionRecording = false;
                }
            }, 10000);
            
        } catch (error) {
            console.error('Error starting correction recording:', error);
            recordIcon.textContent = '❌';
            recordText.textContent = 'Microphone Error - Try Again';
            recordBtn.className = 'bg-red-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-red-600 transition-colors mx-auto';
            recordBtn.disabled = false;
            isCorrectionRecording = false;
            
            // Cleanup stream on error
            if (correctionStream) {
                correctionStream.getTracks().forEach(track => track.stop());
                correctionStream = null;
            }
            
            setTimeout(() => {
                recordIcon.textContent = '🎤';
                recordText.textContent = 'Record Correct Response';
                recordBtn.className = 'bg-green-500 text-white px-6 py-3 rounded-full flex items-center gap-2 hover:bg-green-600 transition-colors mx-auto';
            }, 3000);
        }
        
    } else {
        // STOP RECORDING
        console.log('User clicked stop');
        if (correctionRecorder && correctionRecorder.state === 'recording') {
            // Disable button immediately to prevent double-stop
            recordBtn.disabled = true;
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
    isRecording = false;
    hideThinkingLoader();
    transitionTo('IDLE');
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
function handleFunctionCall(functionCall, conversationId) {
    console.log('Handling function call:', functionCall);

    if (functionCall.action === 'redirect' && functionCall.page === 'completion_celebration') {
        // Show completion celebration
        setTimeout(() => {
            const conversationType = window.conversationType || '';
            let url = `/completion_celebration?topic=${conversationType}`;
            if (conversationId) {
                url += `&conversation_id=${conversationId}`;
            }
            window.location.href = url;
        }, 1000); // Short delay since TTS farewell has already played
    }
}

// Hints display and accordion functions
function updateHintsDisplay(hints) {
    const hintsContainer = document.getElementById('hintsContainer');
    const hintsText = document.getElementById('hintsText');
    const hintsBulbBtn = document.getElementById('hintsBulbBtn');

    if (hints && hints.length > 0) {
        // Join hints with "या" (or) if multiple hints
        const originalHints = hints.join(' या ');
        hintsText.setAttribute('data-original-text', originalHints);
        hintsText.textContent = displayText(originalHints);
        hintsContainer.style.display = 'block';
        // Show bulb button in LISTENING state
        if (hintsBulbBtn && appState === 'LISTENING') {
            hintsBulbBtn.style.display = 'flex';
        }
        console.log('💡 Hints updated:', hints);
    } else {
        hintsContainer.style.display = 'none';
        if (hintsBulbBtn) hintsBulbBtn.style.display = 'none';
    }
}

function toggleHints() {
    const hintsContent = document.getElementById('hintsContent');

    if (hintsContent.classList.contains('expanded')) {
        hintsContent.classList.remove('expanded');
        hintsContent.classList.add('collapsed');
    } else {
        hintsContent.classList.remove('collapsed');
        hintsContent.classList.add('expanded');
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