/**
 * V NOTICE — Minimal Digital Signage Engine (Port 5000)
 * Client Display Engine: Rotation, Video Handling, Urgent Takeover, Offline Resilience
 * Minimal, quiet, flat, type-led interface.
 */

(function () {
  'use strict';

  // State
  let allNotices = [];
  let displayQueue = [];
  let currentIndex = 0;
  let rotationTimer = null;
  let isVideoPlaying = false;
  let isUrgentTakeover = false;
  let isOffline = false;
  let lastSyncTimestamp = Date.now();

  const syncDot = document.getElementById('clock-sync-dot');
  if (syncDot) {
    syncDot.className = 'clock-sync-dot sync-healthy';
    syncDot.title = 'Live sync active';
  }


  // Screen Configuration (Phase 1 & 3: Department IS a screen, extracted from URL path)
  function getScreenFromPath() {
    const segments = window.location.pathname.split('/').filter(Boolean);
    if (segments.length >= 2 && segments[0].toLowerCase() === 'display') {
      return segments[1].toUpperCase();
    }
    const p = new URLSearchParams(window.location.search);
    const q = p.get('screen') || p.get('screen_id');
    if (q) return q.toUpperCase() === 'DEFAULT' ? 'ALL' : q.toUpperCase();
    return 'ALL';
  }
  const currentScreenCode = getScreenFromPath();
  const currentScreenId = currentScreenCode;

  // Preview Mode Detection (Admin iframe previews must remain strictly silent and send no heartbeats)
  const urlParams = new URLSearchParams(window.location.search);
  const isPreviewMode = urlParams.get('preview') === '1' || window.self !== window.top;

  // Audio Readiness Detection (Autoplay unlock test)
  let audioReady = false;
  let audioCtxInstance = null;
  let currentPlayingNotice = null;

  async function testAudioAutoplay() {
    if (isPreviewMode) {
      audioReady = false;
      return false;
    }
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        if (!audioCtxInstance) {
          audioCtxInstance = new AudioCtx();
        }
        if (audioCtxInstance.state === 'suspended') {
          await audioCtxInstance.resume();
        }
        if (audioCtxInstance.state === 'running') {
          audioReady = true;
          return true;
        }
      }
      const testAudio = document.createElement('audio');
      testAudio.src = '/static/audio/silent.wav';
      testAudio.volume = 0.01;
      testAudio.muted = false;
      await testAudio.play();
      testAudio.pause();
      audioReady = true;
      return true;
    } catch (e) {
      audioReady = false;
      return false;
    }
  }

  function syncAudioStateOnActiveVideo() {
    if (isPreviewMode) {
      if (videoElement) {
        videoElement.muted = true;
        videoElement.volume = 0;
      }
      if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
      return;
    }
    if (isVideoPlaying && currentPlayingNotice && videoElement) {
      const noticeSound = Boolean(currentPlayingNotice.play_sound);
      const shouldPlaySound = noticeSound && currentScreenSoundEnabled && audioReady;
      if (shouldPlaySound) {
        videoElement.muted = false;
        videoElement.volume = Math.max(0, Math.min(1, currentScreenSoundVolume / 100));
        if (stageSpeakerIndicator) stageSpeakerIndicator.classList.remove('hidden');
        videoElement.play().catch(() => {});
      } else {
        videoElement.muted = true;
        videoElement.volume = 0;
        if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
      }
    }
  }

  // Heartbeat tracking (Phase 2 & 3 + Sound Readiness)
  async function sendHeartbeat() {
    if (isPreviewMode) return;
    try {
      await fetch('/api/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          screen: currentScreenCode,
          audio_ready: audioReady
        })
      });
    } catch (e) {}
  }

  if (!isPreviewMode) {
    setInterval(sendHeartbeat, 30000);
    testAudioAutoplay().finally(() => {
      sendHeartbeat();
      syncAudioStateOnActiveVideo();
    });

    ['click', 'touchstart', 'keydown', 'pointerdown'].forEach(evt => {
      window.addEventListener(evt, async () => {
        if (!audioReady) {
          await testAudioAutoplay();
          sendHeartbeat();
        }
        syncAudioStateOnActiveVideo();
      }, { passive: true });
    });
  } else {
    // In preview mode, ensure muted and silent state immediately
    audioReady = false;
    syncAudioStateOnActiveVideo();
  }

  // Screen sound settings
  let currentScreenSoundEnabled = false;
  let currentScreenSoundVolume = 70;

  async function loadDepartmentInfo() {
    const deptPill = document.getElementById('dept-header-pill');
    const deptPillCode = document.getElementById('dept-pill-code');
    const deptPillName = document.getElementById('dept-pill-name');
    const deptSep = document.getElementById('dept-sep');

    try {
      const res = await fetch('/api/screens');
      if (res.ok) {
        const data = await res.json();
        const screens = data.screens || [];
        const match = screens.find(s => (s.code || s.id || '').toUpperCase() === currentScreenCode);
        if (match) {
          currentScreenSoundEnabled = Boolean(match.sound_enabled);
          currentScreenSoundVolume = (typeof match.sound_volume === 'number') ? match.sound_volume : 70;
          syncAudioStateOnActiveVideo();

          if (currentScreenCode !== 'ALL') {
            if (deptPillCode) {
              deptPillCode.textContent = match.code || currentScreenCode;
              deptPillCode.classList.remove('hidden');
            }
            if (deptSep) deptSep.classList.remove('hidden');
            if (deptPillName) {
              const name = match.name || match.code;
              deptPillName.textContent = name;
              deptPillName.title = name;
            }
            if (deptPill && match.accent_color) {
              deptPill.style.setProperty('--dept-accent', match.accent_color);
            }
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load screen info:', e);
    }

    if (currentScreenCode === 'ALL') {
      if (deptPillCode) deptPillCode.classList.add('hidden');
      if (deptSep) deptSep.classList.add('hidden');
      if (deptPillName) {
        deptPillName.textContent = 'College-wide';
        deptPillName.removeAttribute('title');
      }
    }
  }
  loadDepartmentInfo();
  setInterval(loadDepartmentInfo, 60000);

  // DOM Elements - Frame & Header
  const stagePanel = document.getElementById('stage-panel');
  const offlineBadge = document.getElementById('offline-badge');
  const timeDigits = document.getElementById('time-digits');
  const timePeriod = document.getElementById('time-period');
  const clockDate = document.getElementById('clock-date');

  // Weather Elements
  const headerWeather = document.getElementById('header-weather');
  const weatherIcon = document.getElementById('weather-icon');
  const weatherTemp = document.getElementById('weather-temp');
  const weatherCity = document.getElementById('weather-city');

  // Stage Elements
  const stagePriority = document.getElementById('stage-priority');
  const stageType = document.getElementById('stage-type');
  const stageAudience = document.getElementById('stage-audience');
  const stageCounter = document.getElementById('stage-counter');
  const stageDots = document.getElementById('stage-dots');

  // Stage QR Badge
  const stageQrBadge = document.getElementById('stage-qr-badge');
  const stageQrCanvas = document.getElementById('stage-qr-canvas');
  let currentQrNoticeId = null;

  // Cards
  const cardText = document.getElementById('card-text');
  const textHeadline = document.getElementById('text-headline');
  const textBody = document.getElementById('text-body');

  const cardImage = document.getElementById('card-image');
  const imageElement = document.getElementById('image-element');
  const imageHeadline = document.getElementById('image-headline');
  const imageBody = document.getElementById('image-body');
  const imageAmbient = document.getElementById('image-ambient');

  const cardVideo = document.getElementById('card-video');
  const videoElement = document.getElementById('video-element');
  const videoHeadline = document.getElementById('video-headline');
  const videoBody = document.getElementById('video-body');
  const videoAmbient = document.getElementById('video-ambient');
  const stageSpeakerIndicator = document.getElementById('stage-speaker-indicator');

  const cardEmpty = document.getElementById('card-empty');
  const emptyTitle = document.getElementById('empty-title');
  const emptySubtitle = document.getElementById('empty-subtitle');

  // Flag Overlay Elements
  const flagOverlay = document.getElementById('flag-overlay');
  const standupScreen = document.getElementById('standup-screen');
  const flagScreen = document.getElementById('flag-screen');

  // Rail & Ticker
  const upNextList = document.getElementById('up-next-list');
  const upNextCount = document.getElementById('up-next-count');
  const tickerLabel = document.getElementById('ticker-label');
  const tickerContent = document.getElementById('ticker-content');

  // ==========================================================================
  // Clock & Date Engine
  // ==========================================================================
  function updateClock() {
    const now = new Date();
    
    // Time format: 10:42 AM (no seconds, tabular numbers)
    let hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const period = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12; // '0' becomes '12'

    if (timeDigits) timeDigits.textContent = `${hours}:${minutes}`;
    if (timePeriod) timePeriod.textContent = period;

    // Date format: Tuesday, 29 September 2026
    if (clockDate) {
      clockDate.textContent = now.toLocaleDateString('en-US', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
      });
    }

    // Live Sync Health Dot (<60s green, stale gray)
    const syncDot = document.getElementById('clock-sync-dot');
    if (syncDot) {
      const isHealthy = (Date.now() - lastSyncTimestamp) < 60000 && !isOffline;
      if (isHealthy) {
        syncDot.className = 'clock-sync-dot sync-healthy';
        syncDot.title = 'Live sync active (< 60s ago)';
      } else {
        syncDot.className = 'clock-sync-dot sync-stale';
        syncDot.title = isOffline ? 'Offline' : 'Sync stale (> 60s ago)';
      }
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // ==========================================================================
  // Cursor Auto-Hide (Kiosk Presentation)
  // ==========================================================================
  let mouseTimer = null;
  window.addEventListener('mousemove', () => {
    document.body.classList.add('show-cursor');
    clearTimeout(mouseTimer);
    mouseTimer = setTimeout(() => {
      document.body.classList.remove('show-cursor');
    }, 3000);
  });

  // ==========================================================================
  // Fetch Notices & Cache for Offline Resilience
  // ==========================================================================
  let lastNoticesEtag = null;
  let basePollInterval = 5000;
  let backoffDelay = basePollInterval;
  let pollTimeoutId = null;
  let sseSource = null;

  async function fetchNotices(forceRefresh = false) {
    try {
      const headers = {
        'Cache-Control': 'no-cache'
      };
      if (lastNoticesEtag && !forceRefresh) {
        headers['If-None-Match'] = lastNoticesEtag;
      }

      const response = await fetch(`/api/notices?screen=${encodeURIComponent(currentScreenId)}`, {
        cache: 'no-cache',
        headers
      });

      if (response.status === 304) {
        // HTTP 304 Not Modified: notices unchanged, zero DOM rebuild, zero JSON re-parsing
        isOffline = false;
        lastSyncTimestamp = Date.now();

        const syncDot = document.getElementById('clock-sync-dot');
        if (syncDot) {
          syncDot.className = 'clock-sync-dot sync-healthy';
          syncDot.title = 'Live sync active';
        }

        if (offlineBadge) offlineBadge.classList.add('hidden');
        backoffDelay = basePollInterval;
        return;
      }

      if (!response.ok) throw new Error(`HTTP error ${response.status}`);

      const etag = response.headers.get('ETag');
      if (etag) lastNoticesEtag = etag;

      const data = await response.json();

      isOffline = false;
      lastSyncTimestamp = Date.now();

      const syncDot = document.getElementById('clock-sync-dot');
      if (syncDot) {
        syncDot.className = 'clock-sync-dot sync-healthy';
        syncDot.title = 'Live sync active';
      }

      if (offlineBadge) offlineBadge.classList.add('hidden');
      backoffDelay = basePollInterval;

      // Cache notices to localStorage
      try {
        localStorage.setItem(`vnotice_cache_${currentScreenId}`, JSON.stringify(data));
      } catch (e) {
        console.warn('LocalStorage save failed:', e);
      }

      applyNotices(data);
    } catch (err) {
      console.warn('Network sync error:', err);
      isOffline = true;

    const syncDot = document.getElementById('clock-sync-dot');
    if (syncDot) {
      syncDot.className = 'clock-sync-dot sync-stale';
      syncDot.title = 'Network reconnecting...';
    }

      if (offlineBadge) offlineBadge.classList.remove('hidden');

      // Exponential backoff with random reconnect jitter (0 - 500ms)
      backoffDelay = Math.min(60000, Math.round(backoffDelay * 1.5)) + Math.floor(Math.random() * 500);

      // Fallback to localStorage cache if queue is empty
      if (displayQueue.length === 0) {
        try {
          const cached = localStorage.getItem(`vnotice_cache_${currentScreenId}`) || localStorage.getItem('vnotice_cache');
          if (cached) {
            applyNotices(JSON.parse(cached));
          } else {
            applyNotices([]);
          }
        } catch (e) {
          console.error('Error reading localStorage cache:', e);
          applyNotices([]);
        }
      }
    }
  }

  function scheduleNextPoll() {
    if (pollTimeoutId) clearTimeout(pollTimeoutId);
    pollTimeoutId = setTimeout(async () => {
      await fetchNotices();
      scheduleNextPoll();
    }, backoffDelay);
  }

  function initSSE() {
    if (!window.EventSource || !systemInfo.sse_enabled) return;
    try {
      if (sseSource) sseSource.close();
      sseSource = new EventSource(`/api/events?screen=${encodeURIComponent(currentScreenCode)}`);
      sseSource.addEventListener('notice_update', () => {
        fetchNotices(true);
      });
      sseSource.addEventListener('flag_changed', () => {
        if (window.syncFlagEvent) {
          window.syncFlagEvent(true);
        }
      });
      sseSource.onerror = () => {
        console.warn('[Sync] SSE connection interrupted; relying on conditional polling');
        if (sseSource) {
          sseSource.close();
          sseSource = null;
        }
      };
    } catch (e) {
      console.warn('[Sync] SSE init error:', e);
    }
  }

  // Network state listeners for instantaneous reconnection detection
  window.addEventListener('offline', () => {
    isOffline = true;

    const syncDot = document.getElementById('clock-sync-dot');
    if (syncDot) {
      syncDot.className = 'clock-sync-dot sync-stale';
      syncDot.title = 'Network reconnecting...';
    }

    if (offlineBadge) offlineBadge.classList.remove('hidden');
  });

  window.addEventListener('online', () => {
    isOffline = false;

    const syncDot = document.getElementById('clock-sync-dot');
    if (syncDot) {
      syncDot.className = 'clock-sync-dot sync-healthy';
      syncDot.title = 'Live sync active';
    }

    if (offlineBadge) offlineBadge.classList.add('hidden');
    backoffDelay = basePollInterval;
    fetchNotices(true);
    scheduleNextPoll();
  });

  // ==========================================================================
  // Apply Notices & Manage Urgent Takeover
  // ==========================================================================
  function applyNotices(notices) {
    if (!Array.isArray(notices)) notices = [];
    allNotices = notices;
    window.allNotices = allNotices;

    // Check for urgent notices
    const urgentNotices = notices.filter(n => (n.priority || '').toLowerCase() === 'urgent');

    let newQueue = [];
    if (urgentNotices.length > 0) {
      // Urgent Takeover Mode: ONLY urgent notices are shown
      newQueue = urgentNotices;
      if (!isUrgentTakeover) {
        isUrgentTakeover = true;
        if (stagePanel) stagePanel.classList.add('urgent-state');
        if (tickerLabel) tickerLabel.classList.add('ticker-urgent');
        const headerLogo = document.getElementById('display-header-logo');
        if (headerLogo) headerLogo.classList.add('urgent-logo-active');
      }
    } else {
      // Normal Mode: all active notices
      newQueue = notices;
      if (isUrgentTakeover) {
        isUrgentTakeover = false;
        if (stagePanel) stagePanel.classList.remove('urgent-state');
        if (tickerLabel) tickerLabel.classList.remove('ticker-urgent');
        const headerLogo = document.getElementById('display-header-logo');
        if (headerLogo) headerLogo.classList.remove('urgent-logo-active');
      }
    }

    const oldIds = displayQueue.map(n => n.id).join(',');
    const newIds = newQueue.map(n => n.id).join(',');

    displayQueue = newQueue;

    // Update bottom ticker
    updateTicker(displayQueue);

    // If queue changed or newly empty
    if (oldIds !== newIds || displayQueue.length === 0) {
      if (currentIndex >= displayQueue.length) {
        currentIndex = 0;
      }
      renderStage();
    }
  }

  // ==========================================================================
  // Live Campus Weather & System Info Engine (Auto-detect city, temp & LAN IP)
  // ==========================================================================
  let systemInfo = {
    lan_ip: window.location.hostname,
    display_port: window.location.port || '5000',
    city: 'Campus',
    temp: '28°C',
    icon: '🌤'
  };

  async function fetchCampusWeather() {
    if (!headerWeather) return;
    try {
      // 1. Fetch system-info from backend with 3s timeout (LAN IP, weather, public base URL, urgent chime)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      const res = await fetch('/api/system-info', { cache: 'no-store', signal: controller.signal });
      clearTimeout(timeoutId);

      if (res.ok) {
        const info = await res.json();
        if (info) {
          systemInfo = { ...systemInfo, ...info };
          if (info.poll_interval_seconds) {
            basePollInterval = Math.max(2, info.poll_interval_seconds) * 1000;
          }
          if (info.sse_enabled && !sseSource) {
            initSSE();
          }

          if (info.weather_enabled === false) {
            headerWeather.classList.add('hidden');
            return;
          }

          if (info.temp && info.icon) {
            headerWeather.classList.remove('hidden');
            applyWeather({ temp: info.temp, icon: info.icon, city: info.city || 'Campus' });
            try {
              localStorage.setItem('vnotice_weather', JSON.stringify({
                temp: info.temp,
                icon: info.icon,
                city: info.city || 'Campus',
                timestamp: Date.now()
              }));
            } catch (e) {}
            return;
          }
        }
      }
    } catch (err) {
      console.warn('Backend weather fetch failed, attempting client fallback:', err);
    }

    // Fallback: cached weather if younger than 60 minutes, else hide silently
    try {
      const cachedStr = localStorage.getItem('vnotice_weather');
      if (cachedStr) {
        const cached = JSON.parse(cachedStr);
        const age = Date.now() - (cached.timestamp || 0);
        if (age < 60 * 60 * 1000 && cached.temp) {
          headerWeather.classList.remove('hidden');
          applyWeather(cached);
          return;
        }
      }
    } catch (e) {}

    // Older than 60m or unavailable: hide silently (graceful degradation, zero error displayed)
    headerWeather.classList.add('hidden');
  }

  function applyWeather(w) {
    if (weatherTemp) weatherTemp.textContent = w.temp || '28°C';
    if (weatherIcon) weatherIcon.textContent = w.icon || '🌤';
    if (weatherCity) weatherCity.textContent = w.city || 'Campus';
  }

  // ==========================================================================
  // "Scan to Phone / Download" QR Code Generator (Uses real LAN IP)
  // ==========================================================================
  function updateStageQr(notice) {
    if (!stageQrBadge || !stageQrCanvas) return;
    if (!notice || !notice.id) {
      stageQrBadge.classList.add('hidden');
      currentQrNoticeId = null;
      return;
    }

    stageQrBadge.classList.remove('hidden');
    if (currentQrNoticeId === notice.id) return;
    currentQrNoticeId = notice.id;

    stageQrCanvas.innerHTML = '';

    // If PUBLIC_BASE_URL is configured, use it. Otherwise use current origin / LAN IP
    let targetUrl;
    if (systemInfo.public_base_url) {
      targetUrl = `${systemInfo.public_base_url}/n/${notice.id}`;
    } else if (window.location.protocol === 'https:' || window.location.hostname.includes('railway.app') || window.location.hostname.includes('trycloudflare.com') || window.location.hostname.includes('onrender.com')) {
      targetUrl = `${window.location.origin}/n/${notice.id}`;
    } else {
      const host = (systemInfo.lan_ip && systemInfo.lan_ip !== '127.0.0.1') ? systemInfo.lan_ip : window.location.hostname;
      const port = systemInfo.display_port ? `:${systemInfo.display_port}` : (window.location.port ? `:${window.location.port}` : ':5000');
      targetUrl = `http://${host}${port}/n/${notice.id}`;
    }

    if (window.QRCode) {
      try {
        new QRCode(stageQrCanvas, {
          text: targetUrl,
          width: 180,
          height: 180,
          colorDark: '#0B1020',
          colorLight: '#FFFFFF',
          correctLevel: QRCode.CorrectLevel.M
        });
      } catch (e) {
        console.warn('QR generation error:', e);
      }
    }
  }

  // ==========================================================================
  // Render Main Stage
  // ==========================================================================

  // Background Preloader for ultra-smooth video & poster transitions
  function preloadNextMedia() {
    if (!displayQueue || displayQueue.length < 2) return;
    const nextIdx = (currentIndex + 1) % displayQueue.length;
    const nextNotice = displayQueue[nextIdx];
    if (nextNotice && nextNotice.media) {
      const nextSrc = (nextNotice.media && nextNotice.media.startsWith('http'))
        ? nextNotice.media
        : `/media/${encodeURIComponent(nextNotice.media)}`;
      const mediaType = (nextNotice.media_type || '').toLowerCase();
      if (mediaType.startsWith('video') || nextNotice.media.endsWith('.mp4') || nextNotice.media.endsWith('.webm') || nextNotice.type === 'video') {
        const preloader = document.createElement('video');
        preloader.preload = 'auto';
        preloader.muted = true;
        preloader.volume = 0;
        preloader.playsInline = true;
        preloader.src = nextSrc;
      } else {
        const preloader = new Image();
        preloader.src = nextSrc;
      }
    }
  }

  
  // Synthetic Urgent Chime via Web Audio API (Zero audio dependencies, safe autoplay catch)
  let audioCtx = null;
  function playUrgentChime() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioCtx) {
        audioCtx = new AudioCtx();
      }
      if (audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {});
      }
      const now = audioCtx.currentTime;
      const osc1 = audioCtx.createOscillator();
      const osc2 = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, now); // A5

      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(1046.5, now + 0.12); // C6

      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(0.15, now + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.38);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(audioCtx.destination);

      osc1.start(now);
      osc1.stop(now + 0.12);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.38);
    } catch (e) {
      console.warn('Urgent chime playback skipped:', e);
    }
  }

  function renderStage() {
    clearTimeout(rotationTimer);

    // Empty state
    if (displayQueue.length === 0) {
      showCard('empty');
      if (stageCounter) stageCounter.textContent = 'Now showing 0 of 0';
      if (stagePriority) stagePriority.classList.add('hidden');
      if (stageType) stageType.textContent = 'Notice board';
      if (stageDots) stageDots.innerHTML = '';
      if (stageQrBadge) stageQrBadge.classList.add('hidden');
      if (upNextList) upNextList.innerHTML = '<div class="rail-empty">Nothing else queued</div>';
      if (upNextCount) upNextCount.textContent = '0';

      const emptyIconEl = cardEmpty ? cardEmpty.querySelector('.empty-icon') : null;
      if (isOffline) {
        if (emptyTitle) emptyTitle.textContent = 'Waiting for the server';
        if (emptySubtitle) emptySubtitle.textContent = 'Reconnecting automatically. Notices will appear as soon as connection is restored.';
        if (emptyIconEl) emptyIconEl.classList.add('reconnecting');
      } else {
        if (emptyTitle) emptyTitle.textContent = (currentScreenCode === 'ALL') ? 'No announcements right now' : `No announcements for ${currentScreenCode} right now`;
        if (emptySubtitle) emptySubtitle.textContent = 'New notices appear here as soon as they are published.';
        if (emptyIconEl) emptyIconEl.classList.remove('reconnecting');
      }
      return;
    }

    if (currentIndex >= displayQueue.length) {
      currentIndex = 0;
    }

    const notice = displayQueue[currentIndex];
    const durationSec = notice.duration || 10;
    const currentDurationMs = durationSec * 1000;

    // Meta Row: College-wide audience tag (Phase 3)
    const isCollegeWide = (notice.screens && notice.screens.includes('ALL')) || (notice.screen_id === 'ALL');
    if (stageAudience) {
      if (isCollegeWide && currentScreenCode !== 'ALL') {
        stageAudience.classList.remove('hidden');
      } else {
        stageAudience.classList.add('hidden');
      }
    }

    // Meta Row: Priority
    const prio = (notice.priority || 'normal').toLowerCase();
    if (prio === 'urgent') {
      stagePriority.className = 'pill-urgent';
      stagePriority.textContent = 'Urgent';
      stagePriority.classList.remove('hidden');
      if (systemInfo.urgent_chime) {
        playUrgentChime();
      }
    } else if (prio === 'info') {
      stagePriority.className = 'label-info';
      stagePriority.innerHTML = '<span class="dot-info"></span>Info';
      stagePriority.classList.remove('hidden');
    } else {
      // Normal is omitted entirely per design spec
      stagePriority.classList.add('hidden');
    }

    // Meta Row: Type (Sentence case)
    const ntype = notice.type || 'text';
    const typeLabel = ntype.charAt(0).toUpperCase() + ntype.slice(1).toLowerCase();
    if (stageType) stageType.textContent = typeLabel;

    // Dynamic stage ambient glow (Step 2: Info = blue, Urgent = crimson)
    const stageEl = document.getElementById('stage-panel');
    if (stageEl) {
      stageEl.classList.remove('glow-urgent', 'glow-info', 'glow-normal');
      if (prio === 'urgent') {
        stageEl.classList.add('glow-urgent');
      } else if (prio === 'info') {
        stageEl.classList.add('glow-info');
      } else {
        stageEl.classList.add('glow-normal');
      }
    }


    // Meta Row: Position (1 / 4)
    if (stageCounter) stageCounter.textContent = `Now showing ${currentIndex + 1} of ${displayQueue.length}`;

    // Update Dots & Up Next Rail
    updateDots();
    updateUpNext();

    // Render by type
    if (notice.type === 'video' && notice.media) {
      renderVideoNotice(notice);
    } else if (notice.type === 'image' && notice.media) {
      renderImageNotice(notice);
    } else {
      renderTextNotice(notice);
    }

    // Update QR Code pointing to this notice
    updateStageQr(notice);
    preloadNextMedia();

    // Advance timer if not waiting for video to end
    if (!isVideoPlaying) {
      if (displayQueue.length > 1) {
        rotationTimer = setTimeout(advanceNotice, currentDurationMs);
      } else {
        // Single notice: rerun periodically
        rotationTimer = setTimeout(renderStage, currentDurationMs);
      }
    }
  }

  let activeCardType = null;

  function showCard(cardType) {
    const cards = [
      { type: 'text', el: cardText },
      { type: 'image', el: cardImage },
      { type: 'video', el: cardVideo },
      { type: 'empty', el: cardEmpty },
    ];

    cards.forEach(({ type, el }) => {
      if (!el) return;
      if (type === cardType) {
        el.classList.remove('hidden');
        if (displayQueue.length > 1 || activeCardType !== cardType) {
          el.classList.add('card-entering');
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              el.classList.remove('card-entering');
            });
          });
        }
      } else {
        el.classList.add('hidden');
        el.classList.remove('card-entering');
      }
    });

    activeCardType = cardType;

    // Clean up video resources when leaving video notice
    if (cardType !== 'video') {
      currentPlayingNotice = null;
      if (videoElement) {
        videoElement.pause();
        videoElement.muted = true;
        videoElement.volume = 0;
        videoElement.removeAttribute('src');
        videoElement.load();
        isVideoPlaying = false;
        if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
      }
    }
  }

  
  // Deterministic gradient themes for text slides (contrast >= 7:1)
  const TEXT_GRADIENTS = [
    'theme-deep-blue',
    'theme-indigo',
    'theme-teal',
    'theme-slate'
  ];

  function getDeterministicTheme(id) {
    if (!id) return TEXT_GRADIENTS[0];
    let hash = 0;
    const str = String(id);
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return TEXT_GRADIENTS[Math.abs(hash) % TEXT_GRADIENTS.length];
  }

  function fitTextNotice() {
    if (!cardText || !textHeadline || cardText.classList.contains('hidden')) return;

    // 1. Measure real space available inside cardText after padding
    const cardStyle = window.getComputedStyle(cardText);
    const padTop = parseFloat(cardStyle.paddingTop) || 0;
    const padBottom = parseFloat(cardStyle.paddingBottom) || 0;
    const padLeft = parseFloat(cardStyle.paddingLeft) || 0;
    const padRight = parseFloat(cardStyle.paddingRight) || 0;

    const availW = cardText.clientWidth - padLeft - padRight;
    const availH = cardText.clientHeight - padTop - padBottom;
    if (availW <= 0 || availH <= 0) return;

    const hasBody = Boolean(textBody && textBody.textContent && textBody.textContent.trim().length > 0);

    // Scaling limits relative to 1080p (Requirement 4)
    const scale = Math.max(0.2, window.innerHeight / 1080);
    const maxHeadline = Math.round(112 * scale);
    const minHeadline = Math.round(36 * scale);
    const minBody = Math.round(20 * scale);
    const maxBody = Math.round(40 * scale);

    const headlineStyle = window.getComputedStyle(textHeadline);
    const mb = hasBody ? (parseFloat(headlineStyle.marginBottom) || 0) : 0;
    const maxHeadlineH = hasBody ? (availH * 0.55) : availH;

    textHeadline.style.display = 'block';
    textHeadline.style.webkitLineClamp = 'unset';
    textHeadline.style.overflow = 'visible';
    textHeadline.style.paddingBottom = '0.12em';
    if (textBody) {
      textBody.style.display = hasBody ? 'block' : 'none';
      textBody.style.webkitLineClamp = 'unset';
      textBody.style.overflow = 'visible';
    }

    function testSize(hSize) {
      textHeadline.style.fontSize = `${hSize}px`;
      if (textHeadline.scrollHeight > maxHeadlineH) return false;
      if (hasBody && textBody) {
        const bSize = Math.max(minBody, Math.min(maxBody, Math.round(hSize * 0.40)));
        textBody.style.fontSize = `${bSize}px`;
        const totalH = textHeadline.scrollHeight + mb + textBody.scrollHeight;
        if (totalH > availH) return false;
      }
      return true;
    }

    // Binary search between minHeadline and maxHeadline (about 8 iterations)
    let low = minHeadline;
    let high = maxHeadline;
    let best = minHeadline;

    // Requirement 5: short headlines keep today's large look
    if (testSize(maxHeadline)) {
      best = maxHeadline;
    } else {
      for (let i = 0; i < 8; i++) {
        const mid = Math.round((low + high) / 2);
        if (testSize(mid)) {
          best = mid;
          low = mid + 1; // Try larger
        } else {
          high = mid - 1; // Try smaller
        }
        if (low > high) break;
      }
    }

    // Apply optimal headline size
    textHeadline.style.fontSize = `${best}px`;
    if (hasBody && textBody) {
      const bSize = Math.max(minBody, Math.min(maxBody, Math.round(best * 0.40)));
      textBody.style.fontSize = `${bSize}px`;

      // Requirement 6: Last resort body clamping with ellipsis if total still overflows at min sizes
      const totalH = textHeadline.scrollHeight + mb + textBody.scrollHeight;
      if (totalH > availH) {
        const remainingH = availH - textHeadline.scrollHeight - mb;
        const bLineH = parseFloat(window.getComputedStyle(textBody).lineHeight) || (bSize * 1.38);
        const maxLines = Math.max(1, Math.floor(remainingH / bLineH));
        textBody.style.display = '-webkit-box';
        textBody.style.webkitBoxOrient = 'vertical';
        textBody.style.webkitLineClamp = String(maxLines);
        textBody.style.overflow = 'hidden';
      } else {
        textBody.style.display = 'block';
        textBody.style.webkitLineClamp = 'unset';
        textBody.style.overflow = 'visible';
      }
    }
  }

  let fitRafId = null;
  function scheduleFitText() {
    if (fitRafId) cancelAnimationFrame(fitRafId);
    fitRafId = requestAnimationFrame(() => {
      fitRafId = null;
      fitTextNotice();
    });
  }

  window.fitTextNotice = fitTextNotice;
  window.renderTextNotice = renderTextNotice;

  // Requirement 7: Re-run fit on resize, orientation change, and document.fonts.ready
  window.addEventListener('resize', scheduleFitText, { passive: true });
  window.addEventListener('orientationchange', scheduleFitText, { passive: true });
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (activeCardType === 'text') {
        scheduleFitText();
      }
    });
  }

  function renderTextNotice(notice) {
    isVideoPlaying = false;
    currentPlayingNotice = null;
    const title = notice.title || 'Untitled Notice';
    textHeadline.textContent = title;
    textBody.textContent = notice.body || '';

    // Set deterministic gradient theme
    if (cardText) {
      cardText.className = 'notice-view notice-text ' + getDeterministicTheme(notice.id);
    }

    textHeadline.className = 'notice-headline';

    showCard('text');
    scheduleFitText();
  }

  function renderImageNotice(notice) {
    isVideoPlaying = false;
    const mediaUrl = (notice.media && notice.media.startsWith('http')) ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
    imageElement.src = mediaUrl;
    imageHeadline.textContent = notice.title || '';
    imageBody.textContent = notice.body || '';

    // Ambient frosted backdrop for vertical/square posters on landscape monitors
    if (imageAmbient) {
      imageAmbient.style.backgroundImage = `url("${mediaUrl}")`;
    }

    showCard('image');
  }

  function renderVideoNotice(notice) {
    currentPlayingNotice = notice;
    isVideoPlaying = true;
    showCard('video');
    videoHeadline.textContent = notice.title || '';
    videoBody.textContent = notice.body || '';

    // Ambient frosted backdrop for video without rendering a second video element
    if (videoAmbient) {
      if (notice.thumbnail) {
        videoAmbient.style.backgroundImage = `url("${notice.thumbnail}")`;
        videoAmbient.style.background = '';
      } else {
        videoAmbient.style.backgroundImage = '';
        videoAmbient.style.background = 'radial-gradient(circle at center, rgba(47, 107, 255, 0.35) 0%, rgba(15, 23, 42, 0.95) 75%)';
      }
    }

    const mediaSrc = (notice.media && notice.media.startsWith('http')) ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
    if (videoElement.src !== mediaSrc && videoElement.src !== window.location.origin + mediaSrc) {
      videoElement.src = mediaSrc;
      videoElement.load();
    }

    // Capture first frame to offscreen canvas once ready (Raspberry Pi 3B+ low budget)
    const capturePoster = () => {
      try {
        if (!videoElement.videoWidth || !videoElement.videoHeight) return;
        const canvas = document.createElement('canvas');
        canvas.width = 64;
        canvas.height = Math.round((videoElement.videoHeight / videoElement.videoWidth) * 64) || 36;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
        if (videoAmbient) {
          videoAmbient.style.backgroundImage = `url("${dataUrl}")`;
          videoAmbient.style.background = '';
        }
      } catch (e) {
        // Fallback gradient remains active
      }
    };
    videoElement.addEventListener('loadeddata', capturePoster, { once: true });

    const noticeSound = Boolean(notice.play_sound);
    const shouldPlaySound = !isPreviewMode && noticeSound && currentScreenSoundEnabled && audioReady;

    if (shouldPlaySound) {
      videoElement.muted = false;
      videoElement.volume = Math.max(0, Math.min(1, currentScreenSoundVolume / 100));
      if (stageSpeakerIndicator) stageSpeakerIndicator.classList.remove('hidden');
    } else {
      videoElement.muted = true;
      videoElement.volume = 0;
      if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
    }
    videoElement.playsInline = true;

    // Single active notice: loop video
    if (displayQueue.length === 1) {
      videoElement.loop = true;
    } else {
      videoElement.loop = false;
    }

    const playPromise = videoElement.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        console.warn('Autoplay error:', err);
        if (shouldPlaySound && !videoElement.muted) {
          // Autoplay policy prevented unmuted playback, retry muted
          videoElement.muted = true;
          videoElement.volume = 0;
          if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
          audioReady = false;
          sendHeartbeat();
          videoElement.play().catch(e2 => {
            console.warn('Muted video playback failed:', e2);
            isVideoPlaying = false;
            const durationSec = notice.duration || 10;
            rotationTimer = setTimeout(advanceNotice, durationSec * 1000);
          });
          return;
        }
        isVideoPlaying = false;
        const durationSec = notice.duration || 10;
        rotationTimer = setTimeout(advanceNotice, durationSec * 1000);
      });
    }

    videoElement.onended = () => {
      currentPlayingNotice = null;
      isVideoPlaying = false;
      videoElement.pause();
      videoElement.muted = true;
      videoElement.volume = 0;
      if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
      advanceNotice();
    };

    videoElement.onerror = (err) => {
      console.warn('Video failed to load:', err);
      currentPlayingNotice = null;
      isVideoPlaying = false;
      videoElement.pause();
      videoElement.muted = true;
      videoElement.volume = 0;
      if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
      const durationSec = notice.duration || 10;
      rotationTimer = setTimeout(advanceNotice, durationSec * 1000);
    };
  }

  function advanceNotice() {
    if (videoElement) {
      videoElement.pause();
      videoElement.muted = true;
      videoElement.volume = 0;
    }
    if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
    if (displayQueue.length <= 1) {
      renderStage();
      return;
    }
    currentIndex = (currentIndex + 1) % displayQueue.length;
    renderStage();
  }

  // ==========================================================================
  // Stage Dots (Inactive: 6px, Active: 24px pill)
  // ==========================================================================
  function updateDots() {
    if (!stageDots) return;
    stageDots.innerHTML = '';
    if (displayQueue.length <= 1) {
      stageDots.style.display = 'none';
      return;
    }
    stageDots.style.display = 'flex';
    const notice = displayQueue[currentIndex] || {};
    const durSec = notice.duration || 10;
    displayQueue.forEach((_, idx) => {
      const dot = document.createElement('span');
      if (idx === currentIndex) {
        dot.className = 'dot active';
        const fill = document.createElement('span');
        fill.className = 'dot-progress-fill';
        fill.style.animationDuration = `${durSec}s`;
        dot.appendChild(fill);
      } else {
        dot.className = 'dot';
      }
      stageDots.appendChild(dot);
    });
  }

  // ==========================================================================
  // Up Next Rail
  // ==========================================================================
  function updateUpNext() {
    if (!upNextList || !upNextCount) return;
    upNextList.innerHTML = '';
    const total = displayQueue.length;

    if (total <= 1) {
      upNextCount.textContent = '0';
      upNextList.innerHTML = '<div class="rail-empty">Nothing else queued</div>';
      return;
    }

    const upcomingNotices = [];
    for (let i = 1; i < total; i++) {
      const idx = (currentIndex + i) % total;
      upcomingNotices.push({ notice: displayQueue[idx], position: idx + 1 });
    }

    upNextCount.textContent = `${upcomingNotices.length}`;

    // Dynamically scale visible upcoming notices based on viewport height:
    // 2 on <=520px displays (e.g. 800x480), 3 on small displays, 5 on 720p/900p, 6 on 1080p monitors
    const maxVisible = window.innerHeight >= 850 ? 6 : (window.innerHeight >= 650 ? 5 : (window.innerHeight <= 520 ? 2 : 3));
    const visibleNotices = upcomingNotices.slice(0, maxVisible);

    visibleNotices.forEach(({ notice, position }) => {
      const item = document.createElement('div');
      item.className = 'rail-item';

      const pos = document.createElement('span');
      pos.className = 'rail-item-pos';
      pos.textContent = `${position}`;

      const info = document.createElement('div');
      info.className = 'rail-item-info';

      const title = document.createElement('div');
      title.className = 'rail-item-title';
      title.textContent = notice.title || 'Untitled Notice';

      const prio = (notice.priority || 'normal').toLowerCase();
      const prioText = prio.charAt(0).toUpperCase() + prio.slice(1);
      const ntype = notice.type || 'text';
      const typeText = ntype.charAt(0).toUpperCase() + ntype.slice(1);

      const meta = document.createElement('div');
      meta.className = 'rail-item-meta';

      const isNoticeCW = (notice.screens && notice.screens.includes('ALL')) || (notice.screen_id === 'ALL');
      const cwBadge = (isNoticeCW && currentScreenCode !== 'ALL') ? '<span class="badge-college-wide">College-wide</span>' : '';
      if (prio === 'urgent') {
        meta.innerHTML = `<span class="meta-urgent">Urgent</span> · ${typeText}${cwBadge}`;
      } else {
        meta.innerHTML = `${prioText} · ${typeText}${cwBadge}`;
      }

      info.appendChild(title);
      info.appendChild(meta);

      item.appendChild(pos);
      item.appendChild(info);

      upNextList.appendChild(item);
    });

    if (upcomingNotices.length > maxVisible) {
      const more = document.createElement('div');
      more.className = 'rail-more-count';
      more.innerHTML = `
        <svg class="rail-more-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
          <polyline points="2 17 12 22 22 17"></polyline>
          <polyline points="2 12 12 17 22 12"></polyline>
        </svg>
        <span>+ ${upcomingNotices.length - maxVisible} more in rotation</span>
      `;
      upNextList.appendChild(more);
    }
  }

  // ==========================================================================
  // Bottom Marquee Ticker (Sentence case, seamless)
  // ==========================================================================
  function updateTicker(notices) {
    if (!tickerContent) return;
    const tickerFooter = document.querySelector('.display-ticker');

    if (!notices || notices.length === 0) {
      tickerContent.textContent = 'All college notices are up to date';
      if (tickerLabel) {
        tickerLabel.textContent = 'Latest';
        tickerLabel.classList.remove('ticker-urgent');
      }
      if (tickerFooter) tickerFooter.classList.remove('urgent-ticker');
      return;
    }

    const headlines = notices.map(n => n.title || '').filter(Boolean);
    if (headlines.length === 0) {
      tickerContent.textContent = 'V Notice campus announcement system';
      return;
    }

    // Clean unicode bullet (•)
    const bullet = '   \u2022   ';
    const textStr = headlines.join(bullet);
    tickerContent.textContent = `${textStr}${bullet}${textStr}`;

    if (tickerLabel) {
      if (isUrgentTakeover) {
        tickerLabel.textContent = 'URGENT';
        tickerLabel.classList.add('ticker-urgent');
        if (tickerFooter) tickerFooter.classList.add('urgent-ticker');
      } else {
        tickerLabel.textContent = 'Latest';
        tickerLabel.classList.remove('ticker-urgent');
        if (tickerFooter) tickerFooter.classList.remove('urgent-ticker');
      }
    }
  }

  // ==========================================================================
  // Initialization & Adaptive Sync Scheduling (Phase 4)
  // ==========================================================================
  fetchNotices(true);
  fetchCampusWeather();
  scheduleNextPoll();
  setInterval(fetchCampusWeather, 1800000); // Campus weather update every 30 minutes

  // ==========================================================================
  // Daily National Flag Scheduler (Part B)
  // ==========================================================================
  function fitStandupText() {
    const screen = document.getElementById('standup-screen');
    const content = document.getElementById('standup-content');
    const enLine = document.getElementById('standup-text-en');
    const hiLine = document.getElementById('standup-text-hi');
    const mrLine = document.getElementById('standup-text-mr');
    if (!screen || !content || screen.classList.contains('hidden')) return;

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const isPortrait = vh > vw;
    const minDim = Math.min(vw, vh);

    let baseEn = Math.max(18, Math.min(96, Math.round(minDim * 0.042)));
    let baseHi = Math.max(16, Math.min(84, Math.round(minDim * 0.038)));
    let baseGap = Math.max(12, Math.min(48, Math.round(minDim * 0.024)));

    if (isPortrait) {
      baseEn = Math.max(20, Math.min(54, Math.round(vw * 0.05)));
      baseHi = Math.max(18, Math.min(48, Math.round(vw * 0.045)));
      baseGap = Math.max(16, Math.min(40, Math.round(vh * 0.02)));
    }

    content.style.gap = `${baseGap}px`;
    if (enLine) enLine.style.fontSize = `${baseEn}px`;
    if (hiLine) hiLine.style.fontSize = `${baseHi}px`;
    if (mrLine) mrLine.style.fontSize = `${baseHi}px`;

    const maxW = screen.clientWidth * 0.92;
    const maxH = screen.clientHeight * 0.85;
    let iterations = 0;
    while (iterations < 10 && (content.scrollHeight > maxH || content.scrollWidth > maxW) && baseEn > 14) {
      baseEn *= 0.9;
      baseHi *= 0.9;
      baseGap *= 0.9;
      content.style.gap = `${Math.round(baseGap)}px`;
      if (enLine) enLine.style.fontSize = `${Math.round(baseEn)}px`;
      if (hiLine) hiLine.style.fontSize = `${Math.round(baseHi)}px`;
      if (mrLine) mrLine.style.fontSize = `${Math.round(baseHi)}px`;
      iterations++;
    }
  }
  window.fitStandupText = fitStandupText;
  window.addEventListener('resize', fitStandupText);

  let flagScheduler = null;
  if (typeof FlagStateMachine !== 'undefined') {
    flagScheduler = new FlagStateMachine({
      onEnterStandup: () => {
        clearTimeout(rotationTimer);
        if (videoElement) {
          videoElement.pause();
          videoElement.muted = true;
          videoElement.volume = 0;
        }
        if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
        if (flagOverlay) flagOverlay.classList.remove('hidden');

        // Populate event's three standup lines if available in schedule
        const sched = flagScheduler ? flagScheduler.getSchedule() : null;
        const enLine = document.getElementById('standup-text-en');
        const hiLine = document.getElementById('standup-text-hi');
        const mrLine = document.getElementById('standup-text-mr');
        if (enLine && sched && sched.standup_en) enLine.textContent = sched.standup_en;
        if (hiLine && sched && sched.standup_hi) hiLine.textContent = sched.standup_hi;
        if (mrLine && sched && sched.standup_mr) mrLine.textContent = sched.standup_mr;

        if (standupScreen) {
          standupScreen.classList.remove('hidden');
          fitStandupText();
        }
        if (flagScreen) flagScreen.classList.add('hidden');
      },
      onEnterFlag: () => {
        document.body.classList.add('flag-active');
        clearTimeout(rotationTimer);
        if (videoElement) {
          videoElement.pause();
          videoElement.muted = true;
          videoElement.volume = 0;
          videoElement.removeAttribute('src');
          videoElement.load();
        }
        isVideoPlaying = false;
        if (stageSpeakerIndicator) stageSpeakerIndicator.classList.add('hidden');
        if (flagOverlay) flagOverlay.classList.remove('hidden');
        if (standupScreen) standupScreen.classList.add('hidden');
        if (flagScreen) flagScreen.classList.remove('hidden');
      },
      onExitFlag: () => {
        document.body.classList.remove('flag-active');
        if (flagOverlay) flagOverlay.classList.add('hidden');
        if (standupScreen) standupScreen.classList.add('hidden');
        if (flagScreen) flagScreen.classList.add('hidden');
        // Requirement 4: After every flag end, re-fetch schedule so tomorrow's occurrence is armed
        if (window.syncFlagEvent) {
          window.syncFlagEvent(true);
        }
      },
      onEnterRotation: () => {
        document.body.classList.remove('flag-active');
        if (flagOverlay) flagOverlay.classList.add('hidden');
        if (standupScreen) standupScreen.classList.add('hidden');
        if (flagScreen) flagScreen.classList.add('hidden');
        advanceNotice();
        if (window.syncFlagEvent) {
          window.syncFlagEvent(true);
        }
      }
    });
    window.flagScheduler = flagScheduler;

    // Load cached schedule from localStorage if offline on startup
    try {
      const cachedSched = localStorage.getItem(`vnotice_flag_sched_${currentScreenCode}`);
      const cachedOffset = localStorage.getItem(`vnotice_flag_offset_${currentScreenCode}`);
      if (cachedOffset !== null) {
        flagScheduler.clockOffset = parseFloat(cachedOffset) || 0;
      }
      if (cachedSched) {
        flagScheduler.setSchedule(JSON.parse(cachedSched));
      }
    } catch (e) {
      console.warn('Could not read cached flag schedule:', e);
    }

    let flagPollTimeoutId = null;
    let flagBackoffDelay = 3000;
    let lastFlagEtag = null;
    let lastFlagScheduleFetchTime = 0;

    async function syncFlagEvent(forceRefresh = false) {
      try {
        const headers = {};
        if (lastFlagEtag && !forceRefresh) {
          headers['If-None-Match'] = lastFlagEtag;
        }

        const reqStart = Date.now();
        const res = await fetch(`/api/events/today?screen=${encodeURIComponent(currentScreenCode)}`, {
          cache: 'no-store',
          headers
        });
        const reqEnd = Date.now();

        if (res.status === 304) {
          // HTTP 304 Not Modified: cheap return, schedule unchanged
          flagBackoffDelay = 3000;
          return;
        }

        if (res.ok) {
          const etag = res.headers.get('ETag');
          if (etag) lastFlagEtag = etag;

          const data = await res.json();
          lastFlagScheduleFetchTime = Date.now();
          flagBackoffDelay = 3000;

          if (data && typeof data.server_time_ms === 'number') {
            flagScheduler.updateClockOffset(data.server_time_ms, reqStart, reqEnd);
          }
          flagScheduler.setSchedule(data);

          try {
            localStorage.setItem(`vnotice_flag_sched_${currentScreenCode}`, JSON.stringify(data));
            localStorage.setItem(`vnotice_flag_offset_${currentScreenCode}`, String(flagScheduler.clockOffset || 0));
          } catch (e) {}
        }
      } catch (e) {
        console.warn('Flag schedule sync warning:', e);
        // Exponential backoff up to 60s
        flagBackoffDelay = Math.min(60000, Math.round(flagBackoffDelay * 1.5)) + Math.floor(Math.random() * 500);
        // Do not wipe schedule; evaluate with existing schedule & clock offset
        flagScheduler.evaluate();
      }
    }

    window.syncFlagEvent = syncFlagEvent;

    function scheduleNextFlagPoll() {
      if (flagPollTimeoutId) clearTimeout(flagPollTimeoutId);
      flagPollTimeoutId = setTimeout(async () => {
        // Requirement 4: at least every 60 seconds, re-fetch the schedule without ETag to arm tomorrow
        const shouldForce = (Date.now() - lastFlagScheduleFetchTime) >= 60000;
        await syncFlagEvent(shouldForce);
        scheduleNextFlagPoll();
      }, flagBackoffDelay);
    }

    // Initial sync & start 3-second poll loop
    syncFlagEvent(true).finally(() => {
      scheduleNextFlagPoll();
    });

    // Requirement 3: Tick loop every 250ms that compares server-corrected clock
    setInterval(() => {
      flagScheduler.evaluate();
    }, 250);
  }

})();

