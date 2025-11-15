// Accessibility and UI State Management
const ACCESSIBILITY_PREFS = {
  highContrast: localStorage.getItem('highContrast') === 'true',
  reducedMotion: localStorage.getItem('reducedMotion') === 'true' || window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  largeText: localStorage.getItem('largeText') === 'true'
};

// Apply accessibility preferences on load
function applyAccessibilityPrefs() {
  const body = document.body;
  if (ACCESSIBILITY_PREFS.highContrast) {
    body.classList.add('high-contrast');
  }
  if (ACCESSIBILITY_PREFS.reducedMotion) {
    body.classList.add('reduce-motion');
  }
  if (ACCESSIBILITY_PREFS.largeText) {
    body.classList.add('large-text');
  }
}

// Initialize accessibility
applyAccessibilityPrefs();

// DOM Elements
const runBtn = document.getElementById('run');
const out = document.getElementById('out');
const status = document.getElementById('status');
const statusIcon = status.parentElement.querySelector('.status-icon');
const playBtn = document.getElementById('play-audio');
const player = document.getElementById('player');
const audioContainer = document.getElementById('audio-container');

let lastAudioBlob = null;
let isProcessing = false;

// Update status with visual feedback
function updateStatus(message, icon = '💤', type = 'info') {
  const statusText = document.getElementById('status');
  if (statusIcon) {
    statusIcon.textContent = icon;
  }
  statusText.textContent = message;
  
  // Update status box appearance based on type
  const statusBox = document.getElementById('card-output');
  statusBox.className = 'status-box';
  statusBox.classList.add(`status-${type}`);
  
  // Announce to screen readers
  statusBox.setAttribute('aria-live', 'polite');
}

// Show loading state
function setLoading(loading) {
  isProcessing = loading;
  if (loading) {
    runBtn.classList.add('is-loading');
    runBtn.disabled = true;
    updateStatus('Generating audio... Please wait', '⏳', 'loading');
  } else {
    runBtn.classList.remove('is-loading');
    runBtn.disabled = false;
  }
}

// Format JSON output for better readability
function formatOutput(data) {
  try {
    return JSON.stringify(data, null, 2);
  } catch (e) {
    return String(data);
  }
}

// Generate audio handler
runBtn.addEventListener('click', async () => {
  if (isProcessing) return;
  
  setLoading(true);
  out.textContent = '';
  updateStatus('Connecting to server...', '🔄', 'loading');

  try {
    const res = await fetch('/api/process', {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      }
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status} ${res.statusText}`);
    }

    const data = await res.json();

    // Update info panel
    const emotionEl = document.getElementById('last-emotion');
    const promptEl = document.getElementById('last-prompt');
    const seedEl = document.getElementById('last-seed');

    if (data.emotion) {
      emotionEl.textContent = typeof data.emotion === 'string' 
        ? data.emotion 
        : `${data.emotion.emotion || 'calm'} (valence: ${data.emotion.valence?.toFixed(2) || 'N/A'})`;
      emotionEl.setAttribute('aria-label', `Last detected emotion: ${emotionEl.textContent}`);
    }

    if (data.prompt) {
      promptEl.textContent = data.prompt;
      promptEl.setAttribute('aria-label', `Audio prompt: ${data.prompt}`);
    }

    if (data.seed !== undefined) {
      seedEl.textContent = data.seed;
      seedEl.setAttribute('aria-label', `Generation seed: ${data.seed}`);
    }

    // Update output
    out.textContent = formatOutput(data);
    updateStatus('Audio generated successfully! Ready to play', '✅', 'success');

    // Handle audio
    if (data.audio_b64) {
      try {
        const binary = atob(data.audio_b64);
        const len = binary.length;
        const bytes = new Uint8Array(len);

        for (let i = 0; i < len; i++) {
          bytes[i] = binary.charCodeAt(i);
        }

        lastAudioBlob = new Blob([bytes], { type: 'audio/wav' });
        const audioUrl = URL.createObjectURL(lastAudioBlob);
        
        // Clean up old URL if exists
        if (player.src && player.src.startsWith('blob:')) {
          URL.revokeObjectURL(player.src);
        }
        
        player.src = audioUrl;
        player.load(); // Ensure audio is ready
        audioContainer.style.display = 'block';
        playBtn.disabled = false;
        playBtn.setAttribute('aria-label', 'Play the generated audio');
        
        updateStatus('Audio ready! Click Play Audio to listen', '🎵', 'success');
      } catch (audioError) {
        console.error('Audio processing error:', audioError);
        updateStatus('Error processing audio: ' + audioError.message, '⚠️', 'error');
      }
    } else {
      updateStatus('No audio data received from server', '⚠️', 'warning');
      playBtn.disabled = true;
    }

  } catch (error) {
    console.error('Generation error:', error);
    updateStatus(`Error: ${error.message}`, '❌', 'error');
    out.textContent = `Error details:\n${error.message}\n\nPlease check if the server is running.`;
    playBtn.disabled = true;
  } finally {
    setLoading(false);
  }
});

// Play audio handler
playBtn.addEventListener('click', () => {
  if (!player.src) {
    updateStatus('No audio available to play', '⚠️', 'warning');
    return;
  }

  try {
    const playPromise = player.play();
    
    if (playPromise !== undefined) {
      playPromise
        .then(() => {
          updateStatus('Playing audio...', '🔊', 'playing');
          playBtn.disabled = true;
          playBtn.setAttribute('aria-label', 'Audio is playing');
        })
        .catch(error => {
          console.error('Playback error:', error);
          updateStatus(`Playback error: ${error.message}`, '❌', 'error');
        });
    }
  } catch (error) {
    console.error('Play error:', error);
    updateStatus(`Error playing audio: ${error.message}`, '❌', 'error');
  }
});

// Update button text when audio starts/stops
player.addEventListener('play', () => {
  updateStatus('Audio is playing', '🔊', 'playing');
  playBtn.disabled = true;
});

player.addEventListener('pause', () => {
  updateStatus('Audio paused', '⏸️', 'info');
  playBtn.disabled = false;
  playBtn.setAttribute('aria-label', 'Play the generated audio');
});

player.addEventListener('ended', () => {
  updateStatus('Audio finished playing', '✅', 'success');
  playBtn.disabled = false;
  playBtn.setAttribute('aria-label', 'Play the generated audio again');
});

player.addEventListener('error', (e) => {
  console.error('Audio element error:', e);
  updateStatus('Error playing audio file', '❌', 'error');
  playBtn.disabled = false;
});

// Accessibility Controls - with safety checks
document.addEventListener('DOMContentLoaded', () => {
  const highContrastBtn = document.getElementById('toggle-high-contrast');
  const reducedMotionBtn = document.getElementById('toggle-reduced-motion');
  const largeTextBtn = document.getElementById('toggle-large-text');

  if (highContrastBtn) {
    highContrastBtn.addEventListener('click', () => {
      ACCESSIBILITY_PREFS.highContrast = !ACCESSIBILITY_PREFS.highContrast;
      document.body.classList.toggle('high-contrast', ACCESSIBILITY_PREFS.highContrast);
      localStorage.setItem('highContrast', ACCESSIBILITY_PREFS.highContrast);
    });
  }

  if (reducedMotionBtn) {
    reducedMotionBtn.addEventListener('click', () => {
      ACCESSIBILITY_PREFS.reducedMotion = !ACCESSIBILITY_PREFS.reducedMotion;
      document.body.classList.toggle('reduce-motion', ACCESSIBILITY_PREFS.reducedMotion);
      localStorage.setItem('reducedMotion', ACCESSIBILITY_PREFS.reducedMotion);
    });
  }

  if (largeTextBtn) {
    largeTextBtn.addEventListener('click', () => {
      ACCESSIBILITY_PREFS.largeText = !ACCESSIBILITY_PREFS.largeText;
      document.body.classList.toggle('large-text', ACCESSIBILITY_PREFS.largeText);
      localStorage.setItem('largeText', ACCESSIBILITY_PREFS.largeText);
    });
  }
});

// Keyboard navigation support
document.addEventListener('keydown', (e) => {
  // Space or Enter on buttons
  if ((e.key === ' ' || e.key === 'Enter') && e.target.matches('button:not(:disabled)')) {
    e.preventDefault();
    e.target.click();
  }
});

// Focus management for better keyboard navigation
runBtn.addEventListener('focus', () => {
  runBtn.classList.add('keyboard-focus');
});

runBtn.addEventListener('blur', () => {
  runBtn.classList.remove('keyboard-focus');
});

playBtn.addEventListener('focus', () => {
  playBtn.classList.add('keyboard-focus');
});

playBtn.addEventListener('blur', () => {
  playBtn.classList.remove('keyboard-focus');
});

// Check for reduced motion preference on load
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  ACCESSIBILITY_PREFS.reducedMotion = true;
  document.body.classList.add('reduce-motion');
}
