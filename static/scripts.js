let currentVoiceId = null;
let mediaRecorder = null;
let audioChunks = [];
let recordingTimeout = null;
let selectedStoryId = null;
let stream = null;
let isCanceled = false;
let progressInterval = null;

const loadingStories = new Set(); // Track loading story IDs
const API_BASE_URL = '/api';
const STORIES_BASE_URL = '/stories';

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        document.getElementById('splashScreen').style.display = 'none';
        document.getElementById('appContainer').style.display = 'block';
        currentVoiceId = localStorage.getItem('voiceId');
        showScreen(currentVoiceId ? 'synthesisScreen' : 'cloneScreen');
        if(currentVoiceId) loadStories();
    }, 3000);
});

// Screen Management
function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active-screen');
    });

    document.getElementById(screenId).classList.add('active-screen');
    
    // Update header state
    const backButton = document.getElementById('headerBackButton');
    if (screenId === 'synthesisScreen') {
        backButton.classList.remove('hidden');
        document.getElementById('audioControls').style.bottom = '0';
        loadStories();
    } else {
        backButton.classList.add('hidden');
        document.getElementById('audioControls').style.bottom = '-8rem';
        hideAudioControls();
    }

    const stickyHeader = document.querySelector('.sticky-header');
    const audioControls = document.getElementById('audioControls');

    if (screenId === 'synthesisScreen') {
        // Slide down the sticky header
        stickyHeader.classList.remove('hidden');
        stickyHeader.classList.remove('sticky-header-slide-up');
        stickyHeader.classList.add('sticky-header-slide-down');

        // Slide up the audio controls
        audioControls.classList.remove('audio-controls-slide-down');
        audioControls.classList.add('audio-controls-slide-up');
    } else {
        // Slide up the sticky header (hide)
        stickyHeader.classList.remove('sticky-header-slide-down');
        stickyHeader.classList.add('sticky-header-slide-up');

        // Slide down the audio controls (hide)
        audioControls.classList.remove('audio-controls-slide-up');
        audioControls.classList.add('audio-controls-slide-down');
    }
window.scrollTo(0, 0);
}

function showCloneScreen() {
    if (currentVoiceId) {
        // Show confirmation modal
        const modal = document.getElementById('confirmModal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        
        // Handle modal actions
        const handleConfirm = async () => {
            const confirmBtn = document.getElementById('confirmDelete');
            const cancelBtn = document.getElementById('confirmCancel');
            
            try {
                // Disable buttons during operation
                confirmBtn.disabled = true;
                cancelBtn.disabled = true;
        
                const response = await fetch(`/api/voices/${currentVoiceId}`, {
                    method: 'DELETE'
                });
        
                if (!response.ok) throw new Error('Deletion failed');
                
                // Clear all related state
                localStorage.removeItem('voiceId');
                currentVoiceId = null;
                selectedStoryId = null;
                
                // Force UI refresh
                resetRecordingUI();
                hideAudioControls();
                await loadStories(true);
                
                // Switch screens and reset UI
                showScreen('cloneScreen');
                document.getElementById('audioPreview').src = '';
                
                showStatus('Voice successfully deleted', 'success');
        
            } catch (error) {
                showError(error.message);
            } finally {
                // Always re-enable buttons and hide modal
                confirmBtn.disabled = false;
                cancelBtn.disabled = false;
                modal.classList.add('hidden');
                
                // Cleanup event listeners
                document.getElementById('confirmDelete').removeEventListener('click', handleConfirm);
                document.getElementById('confirmCancel').removeEventListener('click', handleCancel);
            }
        };

        const handleCancel = () => {
            modal.classList.add('hidden');
            // Cleanup event listeners
            document.getElementById('confirmDelete').removeEventListener('click', handleConfirm);
            document.getElementById('confirmCancel').removeEventListener('click', handleCancel);
        };

        document.getElementById('confirmDelete').addEventListener('click', handleConfirm);
        document.getElementById('confirmCancel').addEventListener('click', handleCancel);
        
        // Close modal on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) handleCancel();
        });
    } else {
        // No voice to delete - go directly
        localStorage.removeItem('voiceId');
        currentVoiceId = null;
        resetRecordingUI();
        showScreen('cloneScreen');
    }
}

// Voice Cloning
async function startRecording() {
    try {
        // Check microphone availability first
        const devices = await navigator.mediaDevices.enumerateDevices();
        const hasAudioInput = devices.some(device => device.kind === 'audioinput');
        
        if (!hasAudioInput) {
            throw new Error('NO_MICROPHONE_FOUND');
        }

        openClonePrompt();
        isCanceled = false;
        
        // Add more detailed constraints
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });
        
        // Store stream reference
        window.currentStream = stream;

        mediaRecorder = new MediaRecorder(stream);
        resetRecordingUI();

        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            clearInterval(progressInterval);
            if (isCanceled) return;
            
            showProcessingUI();
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            try {
                await handleAudioUpload(audioBlob);
                showScreen('synthesisScreen');
            } catch (error) {
                showError(error.message);
            } finally {
                closeClonePrompt();
                cleanupMediaResources();
            }
        };

        mediaRecorder.start();
        startProgressAnimation();
        
        recordingTimeout = setTimeout(() => {
            if (mediaRecorder.state === 'recording') mediaRecorder.stop();
        }, 30000);

    } catch (error) {
        console.error('Recording error:', error);
        cleanupMediaResources();
        closeClonePrompt();
        
        // Handle specific error cases
        switch(error.name || error.message) {
            case 'NotAllowedError':
            case 'Permission denied':
                showError('Please enable microphone access in browser settings');
                break;
            case 'NO_MICROPHONE_FOUND':
                showError('No microphone detected');
                break;
            case 'NotFoundError':
                showError('No audio input device available');
                break;
            default:
                showError('Microphone initialization failed: ');
        }
    }
}


// Audio Upload
document.getElementById('audioFile').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    // TODO
    openClonePrompt();
    showProcessingUI();
    
    try {
        await handleAudioUpload(file);
        status.textContent = 'Voice model created successfully!';
        showScreen('synthesisScreen');
    } catch (error) {
        showError(error.message);
    } finally {
        // Reset UI
        closeClonePrompt();
        cleanupMediaResources();
        e.target.value = ''; // Clear file input
    }
});

async function handleAudioUpload(blob) {
    const formData = new FormData();
    formData.append('file', blob, 'voice_sample.wav');

    try {
        const response = await fetch(`${API_BASE_URL}/clone`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Upload failed');
        }

        currentVoiceId = data.voice_id;
        localStorage.setItem('voiceId', data.voice_id);
        return true;
        
    } catch (error) {
        throw new Error(`Upload failed: ${error.message}`);
    }
}

// Story Management
async function loadStories() {
    try {
        // Show loader and hide stories container
        document.getElementById('storiesLoader').style.display = 'block';
        document.getElementById('storiesContainer').classList.add('hidden');

        const stories = await fetchStories();
        await renderStories(stories);

        // Hide loader and show stories
        document.getElementById('storiesLoader').style.display = 'none';
        document.getElementById('storiesContainer').classList.remove('hidden');

    } catch (error) {
        showError('Failed to load stories');
        // Hide loader on error too
        document.getElementById('storiesLoader').style.display = 'none';
    }
}

async function fetchStories() {
    const response = await fetch(`${STORIES_BASE_URL}/index.json`);
    return response.json();
}

async function renderStories() {
    try {
        const stories = await fetchStories();
        const container = document.getElementById('storiesContainer');
        
        // First process all async checks in parallel
        const storiesWithStatus = await Promise.all(
            stories.map(async story => ({
                ...story,
                isLoading: loadingStories.has(story.id),
                audioExists: currentVoiceId ? await checkAudioExists(story.id) : false
            }))
        );

        container.innerHTML = storiesWithStatus.map(story => `
            <div class="story-item bg-white p-4 rounded-xl shadow-sm  transition-all 
                        ${selectedStoryId === story.id ? 'selected' : ''}" 
                 data-story-id="${story.id}">
                <div class="flex items-center justify-between gap-2">
                    <div class="flex-1">
                        <h3 class="text-lg font-semibold">${story.title}</h3>
                        <p class="text-gray-600 text-sm">Autor: ${story.author}</p>
                    </div>
                    <button onclick="handleStoryClick(${story.id})" 
                            id="story-${story.id}" 
                            class="${story.audioExists ? 'bg-green-500 hover:bg-green-600' : 
                                   story.isLoading ? 'bg-gray-300 cursor-not-allowed' : 'bg-peach hover:bg-peach/90'} 
                                   text-white p-2 rounded-full flex items-center justify-center transition-all"
                            ${story.isLoading ? 'disabled' : ''}>
                        ${story.isLoading ? `
                            <svg class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
                            </svg>
                        ` : `
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                ${story.audioExists ? `
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                      d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>` :
                                `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                      d="M12 4v16m8-8H4"/>`}
                            </svg>
                        `}
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        showError('Failed to load stories');
    }
}

async function checkAudioExists(storyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/audio/exists/${currentVoiceId}/${storyId}`);
        const data = await response.json();
        return data.exists;
    } catch (error) {
        return false;
    }
}

// Story Handling
async function handleStoryClick(storyId) {
    if (loadingStories.has(storyId)) return; // Prevent multiple clicks
    
    const button = document.getElementById(`story-${storyId}`);
    
    try {

        const audioExists = await checkAudioExists(storyId);
        
        if (!audioExists) {
            // Set loading state        
            loadingStories.add(storyId);
            await renderStories();
            await generateStory(storyId);
        }
        
        await playStory(storyId);
        selectedStoryId = storyId;

    } catch (error) {
        showError(error.message);
    } finally {
        // Clear loading state
        loadingStories.delete(storyId);
        await renderStories();
    }
}

async function generateStory(storyId) {
    showStatus('Starting audio generation...', 'info');
    
    try {
        const story = await fetch(`${STORIES_BASE_URL}/${storyId}.json`).then(r => r.json());
        
        const response = await fetch(`${API_BASE_URL}/synthesize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                voice_id: currentVoiceId,
                story_id: storyId
            })
        });

        if (!response.ok) {
            console.warn('Synthesis request failed. Proceeding to poll for audio availability.');
        }

        // Start polling for audio readiness
        let audioReady = false;
        const maxPollingTime = 2 * 60 * 1000; // 2 minutes
        const pollingInterval = 5000; // 5 seconds
        const startTime = Date.now();

        while (!audioReady && Date.now() - startTime < maxPollingTime) {
            await new Promise(resolve => setTimeout(resolve, pollingInterval));
            audioReady = await checkAudioExists(storyId);
        }

        if (!audioReady) throw new Error('Generation timeout');
        
        showStatus('Audio ready!', 'success');
    } catch (error) {
        throw new Error(`Generation failed: ${error.message}`);
    }
}

const audioElement = document.getElementById('storyAudio');
const playIcon = document.getElementById('playIcon');
const pauseIcon = document.getElementById('pauseIcon');
const playPauseButton = document.getElementById('playPause');
const rewindButton = document.getElementById('rewind');
const forwardButton = document.getElementById('forward');
const progressSlider = document.getElementById('progress');
const durationDisplay = document.getElementById('duration');
const currentTimeDisplay = document.getElementById('currentTime');

// Update UI on play, pause, and when audio ends
audioElement.addEventListener('play', () => {
    playIcon.classList.add('hidden');
    pauseIcon.classList.remove('hidden');
});
audioElement.addEventListener('pause', () => {
    playIcon.classList.remove('hidden');
    pauseIcon.classList.add('hidden');
});
audioElement.addEventListener('ended', () => {
    playIcon.classList.remove('hidden');
    pauseIcon.classList.add('hidden');
});

// Update current time and progress slider as the audio plays
audioElement.addEventListener('timeupdate', () => {
    currentTimeDisplay.textContent = formatTime(audioElement.currentTime);
    if (audioElement.duration) {
    progressSlider.value = (audioElement.currentTime / audioElement.duration) * 100;
    }
});

// Update duration display when metadata is loaded
audioElement.addEventListener('loadedmetadata', () => {
    durationDisplay.textContent = formatTime(audioElement.duration);
});

// Play/Pause button (use a single event type to avoid duplicate triggers)
playPauseButton.addEventListener('click', (e) => {
    e.preventDefault();
    if (audioElement.paused) {
    audioElement.play();
    } else {
    audioElement.pause();
    }
});

// Rewind: go back 5 seconds
rewindButton.addEventListener('click', () => {
    audioElement.currentTime = Math.max(0, audioElement.currentTime - 5);
});

// Forward: go forward 5 seconds
forwardButton.addEventListener('click', () => {
    audioElement.currentTime = Math.min(audioElement.duration, audioElement.currentTime + 5);
});

// Progress slider: allow seeking within the audio track
progressSlider.addEventListener('input', (e) => {
    const seekTime = (e.target.value / 100) * audioElement.duration;
    audioElement.currentTime = seekTime;
});

// Prevent touchstart on the progress slider from interfering with other events
progressSlider.addEventListener('touchstart', (e) => {
    e.stopPropagation();
});

async function playStory(storyId) {
showAudioControls();
showStatus('Loading audio...', 'info');

// Build the audio URL with a cache-busting timestamp
const audioUrl = `${API_BASE_URL}/audio/${currentVoiceId}/${storyId}.mp3?t=${Date.now()}`;
audioElement.src = audioUrl;

// Use a one-time loadedmetadata listener to auto-play when ready
const onLoaded = () => {
    // Metadata is loaded and duration is updated via initializeAudioControls
    audioElement.play().catch(error => {
    showError('Auto-play failed. Please click the play button.');
    });
    // Remove this listener so it only runs once per source change
    audioElement.removeEventListener('loadedmetadata', onLoaded);
};
audioElement.addEventListener('loadedmetadata', onLoaded);
}

function stopAudio() {
    const audioElement = document.getElementById('storyAudio');
    audioElement.pause();
    audioElement.currentTime = 0;
    hideAudioControls();
}

// Initialize with empty state
document.addEventListener('DOMContentLoaded', () => {
    hideAudioControls(); // Shows the default message
});


// UI Helpers
function resetRecordingUI() {
    audioChunks = [];
    document.querySelector('.progress-bar').style.width = '0%';
    document.getElementById('recordStatus').innerHTML = '';
    document.getElementById('audioPreview').src = '';
}

function updateRecordStatus(message, type) {
    const statusDiv = document.getElementById('recordStatus');
    statusDiv.innerHTML = message;
    statusDiv.className = `text-sm p-2 rounded-lg ${
        type === 'error' ? 'bg-red-100 text-red-700' : 
        type === 'info' ? 'bg-peach/20 text-peach-700' : 'text-gray-600'
    }`;
}

function showStatus(message, type) {
    const toast = document.getElementById('statusToast');
    const content = toast.querySelector('div:last-child');
    const icon = toast.querySelector('svg');
    
    // Define style configurations
    const typeStyles = {
        info: {
            class: 'toast-info',
            icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                   d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>`,
            iconColor: 'text-lavender'
        },
        success: {
            class: 'toast-success',
            icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                   d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>`,
            iconColor: 'text-mint'
        },
        error: {
            class: 'toast-error',
            icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                   d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>`,
            iconColor: 'text-peach'
        }
    };

    // Get the correct style configuration
    const style = typeStyles[type] || typeStyles.info;
    
    // Reset classes
    toast.className = '';
    toast.classList.add('rounded-lg', 'shadow-xl', 'p-4', 'flex', 
                      'items-start', 'gap-3', 'border-l-4', 'toast-show',
                      style.class); // Add the specific style class

    // Set icon styling
    icon.className = `w-5 h-5 ${style.iconColor}`;
    icon.innerHTML = style.icon;
    
    // Set content
    content.innerHTML = message;
    
    // Show toast
    toast.classList.remove('hidden', 'opacity-0', 'translate-y-[-20px]');
    
    // Auto-hide after 3 seconds
    clearTimeout(toast.timeout);
    toast.timeout = setTimeout(() => {
        toast.classList.add('toast-hide');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 300);
    }, 3000);
}

function showError(message) {
    showStatus(message, 'error');
}

// Cleanup
window.addEventListener('beforeunload', () => {
    if (mediaRecorder?.state === 'recording') mediaRecorder.stop();
});

function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}


function showAudioControls() {
    const controls = document.getElementById('audioControls');
    controls.classList.add('active');
}

function hideAudioControls() {
    const controls = document.getElementById('audioControls');
    controls.classList.remove('active');
}

function showClonePrompt() {
    const modal = document.getElementById('clonePromptModal');
    modal.dataset.visible = "true";
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeClonePrompt() {
    const modal = document.getElementById('clonePromptModal');
    modal.dataset.visible = "false";
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function showProcessingUI() {
    document.getElementById('recordingContent').classList.add('hidden');
    document.getElementById('processingContent').classList.remove('hidden');
    document.getElementById('clonePromptModalFooter').classList.add('hidden');
}

function startProgressAnimation() {
    const progressBar = document.querySelector('.progress-bar');
    let seconds = 0;
    progressBar.style.width = '0%';
    
    progressInterval = setInterval(() => {
        seconds += 1;
        const progress = (seconds / 30) * 100;
        progressBar.style.width = `${progress}%`;
    }, 1000);
}

// Cancel recording handler
document.getElementById('cancelRecording').addEventListener('click', () => {
    isCanceled = true;
    if (mediaRecorder?.state === 'recording') {
        mediaRecorder.stop();
        clearTimeout(recordingTimeout);
        clearInterval(progressInterval);
        if (stream) stream.getTracks().forEach(t => t.stop());
    }
    closeClonePrompt();
    resetRecordingUI();
    showStatus('Recording canceled', 'info');
});

// Update openClonePrompt function
function openClonePrompt() {
    const modal = document.getElementById('clonePromptModal');
    const scrollingText = modal.querySelector('.scrolling-text');
    
    // Reset animation state
    scrollingText.style.animation = 'none';
    void scrollingText.offsetWidth; // Trigger reflow
    
    // Calculate duration based on text length
    const textHeight = scrollingText.scrollHeight;
    const containerHeight = modal.querySelector('.scrolling-container').offsetHeight;
    const scrollDuration = 90;
    
    scrollingText.style.animation = `autoScroll ${scrollDuration}s linear infinite`;
    scrollingText.style.transform = 'translateY(100%)';
    
    modal.dataset.visible = "true";
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

// Add cleanup function
function cleanupMediaResources() {
    if (window.currentStream) {
        window.currentStream.getTracks().forEach(track => {
            track.stop();
            track.enabled = false;
        });
        window.currentStream = null;
    }
    mediaRecorder = null;
    audioChunks = [];
}

document.getElementById('uploadButton').addEventListener('click', () => {
    document.getElementById('audioFile').click();
});

// Register Service Worker
if('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js?v=1.6') // Update this version for each deployment
      .then(reg => {
        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          newWorker.addEventListener('statechange', () => {
            if(newWorker.state === 'activated' && navigator.serviceWorker.controller) {
              window.location.reload();
            }
          });
        });
      });
    
    // Check for updates every time the page loads
    navigator.serviceWorker.ready.then(reg => reg.update());
}
  
  // Install Prompt
  let deferredPrompt;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    // Show install button (optional)
    // document.getElementById('installButton').style.display = 'block';
  });
  
  // Handle install button click
  function installPWA() {
    if(deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
          console.log('User accepted install');
        }
        deferredPrompt = null;
      });
    }
  }


function nativeTapFeedback() {
    if ('vibrate' in navigator) {
        navigator.vibrate(50); // 50ms vibration
    }
}

// Add to button click handlers
document.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', nativeTapFeedback);
});

// Detect platform
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const isAndroid = /Android/.test(navigator.userAgent);

if (isIOS) {
    document.documentElement.classList.add('ios');
    document.documentElement.style.setProperty('--font-body', '-apple-system');
}

if (isAndroid) {
    document.documentElement.classList.add('android');
    document.documentElement.style.setProperty('--font-body', 'Roboto');
}