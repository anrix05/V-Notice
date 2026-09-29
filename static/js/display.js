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

  const cardEmpty = document.getElementById('card-empty');
  const emptyTitle = document.getElementById('empty-title');
  const emptySubtitle = document.getElementById('empty-subtitle');

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
  async function fetchNotices() {
    try {
      const response = await fetch(`/api/notices?_t=${Date.now()}`, {
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache'
        }
      });
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();

      isOffline = false;
      if (offlineBadge) offlineBadge.classList.add('hidden');

      // Cache notices to localStorage
      try {
        localStorage.setItem('vnotice_cache', JSON.stringify(data));
      } catch (e) {
        console.warn('LocalStorage save failed:', e);
      }

      applyNotices(data);
    } catch (err) {
      console.warn('Network fetch error, loading from local cache:', err);
      isOffline = true;
      if (offlineBadge) offlineBadge.classList.remove('hidden');

      // Fallback to localStorage cache
      try {
        const cached = localStorage.getItem('vnotice_cache');
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

  // Network state listeners for instantaneous reconnection detection
  window.addEventListener('offline', () => {
    isOffline = true;
    if (offlineBadge) offlineBadge.classList.remove('hidden');
  });

  window.addEventListener('online', () => {
    isOffline = false;
    if (offlineBadge) offlineBadge.classList.add('hidden');
    fetchNotices();
  });

  // ==========================================================================
  // Apply Notices & Manage Urgent Takeover
  // ==========================================================================
  function applyNotices(notices) {
    if (!Array.isArray(notices)) notices = [];
    allNotices = notices;

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
      }
    } else {
      // Normal Mode: all active notices
      newQueue = notices;
      if (isUrgentTakeover) {
        isUrgentTakeover = false;
        if (stagePanel) stagePanel.classList.remove('urgent-state');
        if (tickerLabel) tickerLabel.classList.remove('ticker-urgent');
      }
    }

    const oldIds = displayQueue.map(n => n.id).join(',');
    const newIds = newQueue.map(n => n.id).join(',');

    displayQueue = newQueue;

    // Update bottom ticker
    updateTicker(displayQueue);

    // If queue changed or newly empty
    if (oldIds !== newIds) {
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
      // 1. Fetch system-info from backend (provides LAN IP and accurate localized weather)
      const res = await fetch('/api/system-info', { cache: 'no-store' });
      if (res.ok) {
        const info = await res.json();
        if (info) {
          systemInfo = { ...systemInfo, ...info };
          applyWeather({ temp: info.temp || '28°C', icon: info.icon || '🌤', city: info.city || 'Campus' });
          try {
            localStorage.setItem('vnotice_weather', JSON.stringify({ temp: info.temp, icon: info.icon, city: info.city }));
          } catch (e) {}
          return;
        }
      }
    } catch (err) {
      console.warn('Backend weather fetch failed, attempting client fallback:', err);
    }

    // Fallback: cached weather or default
    try {
      const cached = localStorage.getItem('vnotice_weather');
      if (cached) {
        applyWeather(JSON.parse(cached));
        return;
      }
    } catch (e) {}
    applyWeather({ temp: '28°C', icon: '🌤', city: 'Campus' });
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

    // Use actual LAN Wi-Fi IP so phones on the same network connect directly (not localhost)
    const host = (systemInfo.lan_ip && systemInfo.lan_ip !== '127.0.0.1') ? systemInfo.lan_ip : window.location.hostname;
    const port = systemInfo.display_port ? `:${systemInfo.display_port}` : (window.location.port ? `:${window.location.port}` : ':5000');
    const targetUrl = `http://${host}${port}/notice/${notice.id}?download=1`;

    if (window.QRCode) {
      try {
        new QRCode(stageQrCanvas, {
          text: targetUrl,
          width: 180,
          height: 180,
          colorDark: '#0F172A',
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
  function renderStage() {
    clearTimeout(rotationTimer);

    // Empty state
    if (displayQueue.length === 0) {
      showCard('empty');
      if (stageCounter) stageCounter.textContent = '0 / 0';
      if (stagePriority) stagePriority.classList.add('hidden');
      if (stageType) stageType.textContent = 'Notice board';
      if (stageDots) stageDots.innerHTML = '';
      if (stageQrBadge) stageQrBadge.classList.add('hidden');
      if (upNextList) upNextList.innerHTML = '<div class="rail-empty">Nothing else queued</div>';
      if (upNextCount) upNextCount.textContent = '0';

      if (isOffline) {
        if (emptyTitle) emptyTitle.textContent = 'Waiting for the server';
        if (emptySubtitle) emptySubtitle.textContent = 'Reconnecting automatically.';
      } else {
        if (emptyTitle) emptyTitle.textContent = 'No notices right now';
        if (emptySubtitle) emptySubtitle.textContent = 'New notices appear here as soon as they are published.';
      }
      return;
    }

    if (currentIndex >= displayQueue.length) {
      currentIndex = 0;
    }

    const notice = displayQueue[currentIndex];
    const durationSec = notice.duration || 10;
    const currentDurationMs = durationSec * 1000;

    // Meta Row: Priority
    const prio = (notice.priority || 'normal').toLowerCase();
    if (prio === 'urgent') {
      stagePriority.className = 'pill-urgent';
      stagePriority.textContent = 'Urgent';
      stagePriority.classList.remove('hidden');
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

    // Meta Row: Position (1 / 4)
    if (stageCounter) stageCounter.textContent = `${currentIndex + 1} / ${displayQueue.length}`;

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

  function showCard(cardType) {
    if (cardText) cardText.classList.toggle('hidden', cardType !== 'text');
    if (cardImage) cardImage.classList.toggle('hidden', cardType !== 'image');
    if (cardVideo) cardVideo.classList.toggle('hidden', cardType !== 'video');
    if (cardEmpty) cardEmpty.classList.toggle('hidden', cardType !== 'empty');

    // Rule 28: Clean up video resources when leaving video notice
    if (cardType !== 'video' && videoElement) {
      videoElement.pause();
      videoElement.removeAttribute('src');
      videoElement.load();
      isVideoPlaying = false;
    }
  }

  function renderTextNotice(notice) {
    isVideoPlaying = false;
    const title = notice.title || 'Untitled Notice';
    textHeadline.textContent = title;
    textBody.textContent = notice.body || '';

    // Responsive font sizing based on length
    textHeadline.className = 'notice-headline';
    if (title.length > 70) {
      textHeadline.classList.add('headline-xs');
    } else if (title.length > 40) {
      textHeadline.classList.add('headline-sm');
    }

    showCard('text');
  }

  function renderImageNotice(notice) {
    isVideoPlaying = false;
    const mediaUrl = `/media/${encodeURIComponent(notice.media)}`;
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
    isVideoPlaying = true;
    showCard('video');
    videoHeadline.textContent = notice.title || '';
    videoBody.textContent = notice.body || '';

    // Ambient frosted backdrop for video
    if (videoAmbient) {
      videoAmbient.style.background = 'radial-gradient(circle at center, rgba(47, 107, 255, 0.28) 0%, rgba(22, 34, 56, 0.95) 75%)';
    }

    const mediaSrc = `/media/${encodeURIComponent(notice.media)}`;
    if (videoElement.src !== window.location.origin + mediaSrc) {
      videoElement.src = mediaSrc;
    }

    videoElement.muted = true;
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
        isVideoPlaying = false;
        const durationSec = notice.duration || 10;
        rotationTimer = setTimeout(advanceNotice, durationSec * 1000);
      });
    }

    videoElement.onended = () => {
      isVideoPlaying = false;
      advanceNotice();
    };

    videoElement.onerror = () => {
      console.warn('Video failed to load');
      isVideoPlaying = false;
      advanceNotice();
    };
  }

  function advanceNotice() {
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

    displayQueue.forEach((_, idx) => {
      const dot = document.createElement('span');
      dot.className = `dot ${idx === currentIndex ? 'active' : ''}`;
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
      upcomingNotices.push({ notice: displayQueue[idx], position: i + 1 });
    }

    upNextCount.textContent = `${upcomingNotices.length}`;

    // Show up to 3 upcoming notices so none is cut off vertically at 480px height
    upcomingNotices.slice(0, 3).forEach(({ notice, position }) => {
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

      if (prio === 'urgent') {
        meta.innerHTML = `<span class="meta-urgent">Urgent</span> · ${typeText}`;
      } else {
        meta.textContent = `${prioText} · ${typeText}`;
      }

      info.appendChild(title);
      info.appendChild(meta);

      item.appendChild(pos);
      item.appendChild(info);

      upNextList.appendChild(item);
    });
  }

  // ==========================================================================
  // Bottom Marquee Ticker (Sentence case, seamless)
  // ==========================================================================
  function updateTicker(notices) {
    if (!tickerContent) return;
    if (!notices || notices.length === 0) {
      tickerContent.textContent = 'All college notices are up to date';
      return;
    }

    const headlines = notices.map(n => n.title || '').filter(Boolean);
    if (headlines.length === 0) {
      tickerContent.textContent = 'V Notice campus board';
      return;
    }

    // Build seamless string with muted bullet
    const bullet = '   •   ';
    const textStr = headlines.join(bullet);
    tickerContent.textContent = `${textStr}${bullet}${textStr}`;
  }

  // ==========================================================================
  // Initialization & Polling Interval (Every 10 seconds per PRD Section 4)
  // ==========================================================================
  fetchNotices();
  fetchCampusWeather();
  setInterval(fetchNotices, 3000); // Responsive fast live sync for instant deletion/addition
  setInterval(fetchNotices, 10000); // 10-second contract per PRD Section 4
  setInterval(fetchCampusWeather, 1800000); // Campus weather update every 30 minutes

})();

