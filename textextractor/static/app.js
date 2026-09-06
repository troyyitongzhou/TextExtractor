const form = document.querySelector('#transcribe-form');
const tabs = document.querySelectorAll('.tab');
const sourceType = document.querySelector('#source-type');
const urlPanel = document.querySelector('#url-panel');
const filePanel = document.querySelector('#file-panel');
const fileInput = document.querySelector('#file');
const fileLabel = document.querySelector('#file-label');
const statusSection = document.querySelector('#status-section');
const resultSection = document.querySelector('#result-section');
const stage = document.querySelector('#stage');
const modelDownloadHint = document.querySelector('#model-download-hint');
const errorMessage = document.querySelector('#error-message');
const jobTitle = document.querySelector('#job-title');
const preview = document.querySelector('#transcript-preview');
const resultMeta = document.querySelector('#result-meta');
const downloadLinks = document.querySelector('#download-links');
const copyButton = document.querySelector('#copy-button');
const dropZone = document.querySelector('#drop-zone');
const themeButton = document.querySelector('#theme-button');
const soundButton = document.querySelector('#sound-button');
const submitButtons = document.querySelectorAll('.submit-button');

let pollTimer = null;
let audioContext = null;
let muted = localStorage.getItem('transcript-sound') === 'muted';
let lastHoverSoundAt = 0;
const downloadHoverFrequencies = [261.63, 293.66, 329.63, 392.0, 440.0];

function getAudioContext() {
  if (audioContext) return audioContext;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  audioContext = new AudioContextClass();
  return audioContext;
}

async function unlockAudio() {
  const context = getAudioContext();
  if (!context) return false;
  if (context.state === 'suspended') {
    try {
      await context.resume();
    } catch {
      return false;
    }
  }
  return context.state === 'running';
}

function emitMechanicalSound(snapLevel, thockLevel, startFrequency) {
  const context = getAudioContext();
  if (!context || context.state !== 'running') return;
  const now = context.currentTime;

  const noiseLength = Math.floor(context.sampleRate * .045);
  const noiseBuffer = context.createBuffer(1, noiseLength, context.sampleRate);
  const samples = noiseBuffer.getChannelData(0);
  for (let index = 0; index < noiseLength; index += 1) {
    samples[index] = (Math.random() * 2 - 1) * (1 - index / noiseLength);
  }
  const snap = context.createBufferSource();
  const snapFilter = context.createBiquadFilter();
  const snapGain = context.createGain();
  snap.buffer = noiseBuffer;
  snapFilter.type = 'bandpass';
  snapFilter.frequency.value = 2600;
  snapFilter.Q.value = 1.1;
  snapGain.gain.setValueAtTime(snapLevel, now);
  snapGain.gain.exponentialRampToValueAtTime(.0001, now + .034);
  snap.connect(snapFilter).connect(snapGain).connect(context.destination);

  const thock = context.createOscillator();
  const thockGain = context.createGain();
  thock.type = 'triangle';
  thock.frequency.setValueAtTime(startFrequency, now);
  thock.frequency.exponentialRampToValueAtTime(92, now + .052);
  thockGain.gain.setValueAtTime(thockLevel, now);
  thockGain.gain.exponentialRampToValueAtTime(.0001, now + .062);
  thock.connect(thockGain).connect(context.destination);

  snap.start(now);
  thock.start(now);
  thock.stop(now + .065);
}

function playMechanicalHover() {
  if (muted || performance.now() - lastHoverSoundAt < 110) return;
  lastHoverSoundAt = performance.now();
  emitMechanicalSound(.065, .032, 205);
}

function playMechanicalClick() {
  if (muted) return;
  emitMechanicalSound(.105, .052, 185);
}

function playDownloadHover(index) {
  if (muted) return;
  const frequency = downloadHoverFrequencies[index];
  const context = getAudioContext();
  if (!frequency || !context || context.state !== 'running') return;

  const now = context.currentTime;
  const tone = context.createOscillator();
  const gain = context.createGain();
  tone.type = 'sine';
  tone.frequency.setValueAtTime(frequency, now);
  gain.gain.setValueAtTime(.0001, now);
  gain.gain.exponentialRampToValueAtTime(.032, now + .008);
  gain.gain.exponentialRampToValueAtTime(.0001, now + .085);
  tone.connect(gain).connect(context.destination);
  tone.start(now);
  tone.stop(now + .09);
}

function setMuted(nextMuted) {
  muted = nextMuted;
  soundButton.classList.toggle('muted', muted);
  soundButton.setAttribute('aria-pressed', String(muted));
  soundButton.setAttribute('aria-label', muted ? 'Enable button sounds' : 'Mute button sounds');
  soundButton.title = muted ? 'Enable button sounds' : 'Mute button sounds';
  localStorage.setItem('transcript-sound', muted ? 'muted' : 'enabled');
}

setMuted(muted);
document.addEventListener('pointerdown', () => { void unlockAudio(); }, { once: true, capture: true });
const silentUtilityButtons = new Set([soundButton, themeButton]);
document.querySelectorAll('.primary, .icon-button').forEach((button) => {
  if (silentUtilityButtons.has(button)) return;
  button.addEventListener('pointerenter', playMechanicalHover);
  button.addEventListener('pointerdown', async () => {
    if (await unlockAudio()) playMechanicalClick();
  });
});
soundButton.addEventListener('click', async () => {
  await unlockAudio();
  setMuted(!muted);
});

async function playDownloadActivation(event) {
  const link = event.target.closest('.download-link');
  if (!link || (event.type === 'pointerdown' && event.button !== 0)) return;
  if (event.type === 'click' && event.detail !== 0) return;
  if (await unlockAudio()) playMechanicalClick();
}

downloadLinks.addEventListener('pointerdown', playDownloadActivation);
downloadLinks.addEventListener('click', playDownloadActivation);

function setTheme(dark) {
  document.body.classList.toggle('theme-dark', dark);
  themeButton.setAttribute('aria-pressed', String(dark));
  themeButton.setAttribute('aria-label', dark ? 'Use light mode' : 'Use dark mode');
  themeButton.title = dark ? 'Use light mode' : 'Use dark mode';
  localStorage.setItem('transcript-theme', dark ? 'dark' : 'light');
}

setTheme(localStorage.getItem('transcript-theme') === 'dark');
themeButton.addEventListener('click', () => setTheme(!document.body.classList.contains('theme-dark')));

const customSelects = [...document.querySelectorAll('[data-select]')];

function closeSelect(container) {
  container.classList.remove('open');
  container.querySelector('.select-trigger').setAttribute('aria-expanded', 'false');
  container.querySelector('.select-menu').hidden = true;
}

function closeAllSelects(except = null) {
  customSelects.forEach((container) => {
    if (container !== except) closeSelect(container);
  });
}

customSelects.forEach((container) => {
  const input = container.querySelector('input[type="hidden"]');
  const trigger = container.querySelector('.select-trigger');
  const triggerText = trigger.querySelector('span');
  const menu = container.querySelector('.select-menu');
  const options = [...menu.querySelectorAll('[role="option"]')];

  function openSelect(focusOption = false) {
    closeAllSelects(container);
    container.classList.add('open');
    trigger.setAttribute('aria-expanded', 'true');
    menu.hidden = false;
    if (focusOption) {
      (options.find((option) => option.getAttribute('aria-selected') === 'true') || options[0]).focus();
    }
  }

  function chooseOption(option) {
    input.value = option.dataset.value;
    triggerText.textContent = option.textContent;
    options.forEach((item) => item.setAttribute('aria-selected', String(item === option)));
    closeSelect(container);
    trigger.focus();
  }

  trigger.addEventListener('click', () => {
    if (container.classList.contains('open')) closeSelect(container);
    else openSelect(false);
  });
  trigger.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    openSelect(true);
  });
  options.forEach((option, index) => {
    option.addEventListener('click', () => chooseOption(option));
    option.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeSelect(container);
        trigger.focus();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = index;
      if (event.key === 'ArrowDown') nextIndex = (index + 1) % options.length;
      if (event.key === 'ArrowUp') nextIndex = (index - 1 + options.length) % options.length;
      if (event.key === 'Home') nextIndex = 0;
      if (event.key === 'End') nextIndex = options.length - 1;
      options[nextIndex].focus();
    });
  });
  container.addEventListener('pointerleave', () => closeSelect(container));
  container.addEventListener('focusout', () => {
    setTimeout(() => {
      if (!container.contains(document.activeElement)) closeSelect(container);
    }, 0);
  });
});

document.addEventListener('pointerdown', (event) => {
  if (!event.target.closest('[data-select]')) closeAllSelects();
});

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    const source = tab.dataset.source;
    sourceType.value = source;
    tabs.forEach((item) => {
      const active = item === tab;
      item.classList.toggle('active', active);
      item.setAttribute('aria-selected', String(active));
    });
    urlPanel.classList.toggle('hidden', source !== 'url');
    filePanel.classList.toggle('hidden', source !== 'file');
  });
});

fileInput.addEventListener('change', () => {
  fileLabel.textContent = fileInput.files[0]?.name || 'Choose a video or audio file';
});

['dragenter', 'dragover'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragging');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragging');
  });
});

dropZone.addEventListener('drop', (event) => {
  const files = event.dataTransfer?.files;
  if (!files?.length) return;
  fileInput.files = files;
  fileLabel.textContent = files[0].name;
});

function setSubmitting(submitting) {
  submitButtons.forEach((button) => { button.disabled = submitting; });
}

function setStatus(label, busy) {
  jobTitle.textContent = label;
  form.setAttribute('aria-busy', String(busy));
  if (!busy) modelDownloadHint.classList.add('hidden');
}

function showError(message, statusLabel = 'Error') {
  setStatus(statusLabel, false);
  errorMessage.textContent = message;
  errorMessage.classList.remove('hidden');
  statusSection.classList.remove('hidden');
}

function updateStatus(job) {
  const terminalLabel = job.status === 'failed'
    ? 'Failed'
    : (job.status === 'cancelled' || job.status === 'canceled' ? 'Cancelled' : null);
  stage.textContent = job.stage || 'Processing';
  if (terminalLabel) {
    setStatus(terminalLabel, false);
  } else if (job.status === 'complete') {
    setStatus('Completed', false);
  } else {
    setStatus('Working…', true);
  }
  const showModelDownloadHint = !terminalLabel
    && job.status !== 'complete'
    && job.stage === 'Transcribing with Apple GPU';
  modelDownloadHint.classList.toggle('hidden', !showModelDownloadHint);
}

function showResult(job, shouldScroll = true) {
  setStatus('Completed', false);
  resultSection.classList.remove('hidden');
  preview.value = job.preview || '';
  const minutes = job.duration ? Math.max(1, Math.round(job.duration / 60)) : 0;
  const confidence = job.language_probability
    ? ` · ${Math.round(job.language_probability * 100)}% language confidence`
    : '';
  resultMeta.textContent = `Language: ${job.language || 'Unknown'} · About ${minutes} min${confidence}`;
  downloadLinks.replaceChildren();
  (job.downloads || []).forEach((item, index) => {
    const link = document.createElement('a');
    link.className = 'download-link';
    link.href = `/jobs/${job.id}/download/${item.format}`;
    link.textContent = `Download ${item.label}`;
    link.addEventListener('pointerenter', () => playDownloadHover(index));
    downloadLinks.appendChild(link);
  });
  setSubmitting(false);
  if (shouldScroll) resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/jobs/${jobId}`);
    if (!response.ok) throw new Error('Unable to read the job status.');
    const job = await response.json();
    updateStatus(job);
    if (job.status === 'complete') {
      clearInterval(pollTimer);
      showResult(job);
    } else if (job.status === 'failed') {
      clearInterval(pollTimer);
      setSubmitting(false);
      showError(job.error || 'Processing failed.', 'Failed');
    } else if (job.status === 'cancelled' || job.status === 'canceled') {
      clearInterval(pollTimer);
      setSubmitting(false);
    }
  } catch (error) {
    clearInterval(pollTimer);
    setSubmitting(false);
    showError(error.message, 'Stopped');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearInterval(pollTimer);
  setSubmitting(false);
  statusSection.classList.add('hidden');
  errorMessage.classList.add('hidden');
  resultSection.classList.add('hidden');

  if (sourceType.value === 'url' && !form.elements.url.value.trim()) {
    showError('Enter a video URL.');
    return;
  }
  if (sourceType.value === 'file' && !fileInput.files.length) {
    showError('Choose a video or audio file.');
    return;
  }

  statusSection.classList.remove('hidden');
  setSubmitting(true);
  updateStatus({ status: 'submitting', stage: 'Submitting' });
  statusSection.scrollIntoView({ behavior: 'smooth', block: 'center' });

  try {
    const response = await fetch('/jobs', { method: 'POST', body: new FormData(form) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Submission failed.');
    updateStatus(payload);
    pollTimer = setInterval(() => pollJob(payload.id), 1200);
    await pollJob(payload.id);
  } catch (error) {
    setSubmitting(false);
    showError(error.message, 'Stopped');
  }
});

copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(preview.value);
    copyButton.textContent = 'Copied';
    setTimeout(() => { copyButton.textContent = 'Copy all'; }, 1600);
  } catch {
    showError('Copy permission was denied. Select the transcript manually.');
  }
});

async function restoreRecentJob() {
  try {
    const response = await fetch('/jobs/recent');
    if (response.status === 204 || !response.ok) return;
    showResult(await response.json(), false);
  } catch {
    // A previous transcript is optional; the form remains fully usable.
  }
}

restoreRecentJob();
