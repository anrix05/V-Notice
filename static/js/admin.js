/**
 * V NOTICE — Minimal Admin Management Engine (Port 5001)
 * Flat, quiet, type-led notice management and CRUD
 */

(function () {
  'use strict';

  // State
  let notices = [];
  let currentFilter = 'all';
  let noticeToDelete = null;

  // DOM Elements - Auth
  const loginModal = document.getElementById('login-modal');
  const loginForm = document.getElementById('login-form');
  const passwordInput = document.getElementById('admin-password-input');
  const btnTogglePassword = document.getElementById('btn-toggle-password');
  const loginError = document.getElementById('login-error');
  const btnLogout = document.getElementById('btn-logout');

  // DOM Elements - Navigation & Summary
  const countAll = document.getElementById('count-all');
  const countLive = document.getElementById('count-live');
  const countScheduled = document.getElementById('count-scheduled');
  const countExpired = document.getElementById('count-expired');
  const segmentTabs = document.querySelectorAll('.segment-tab');
  const btnRefresh = document.getElementById('btn-refresh');

  // DOM Elements - Dashboard
  const noticesContainer = document.getElementById('notices-container');
  const feedScreenFilter = document.getElementById('feed-screen-filter');
  const noticeScreen = document.getElementById('notice-screen');
  const noticeCreatedBy = document.getElementById('notice-created-by');
  const btnOpenCreate = document.getElementById('btn-open-create');

  // DOM Elements - Create Modal
  const noticeModal = document.getElementById('notice-modal');
  const modalHeading = document.getElementById('modal-heading');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnCancelCreate = document.getElementById('btn-cancel-create');
  const createNoticeForm = document.getElementById('create-notice-form');
  const btnSubmitCreate = document.getElementById('btn-submit-create');
  const btnSubmitText = document.getElementById('btn-submit-text');
  const uploadProgressTrack = document.getElementById('upload-progress-track');
  const uploadProgressFill = document.getElementById('upload-progress-fill');

  // Form Fields & Inline Errors
  const inputTitle = document.getElementById('notice-title');
  const titleCounter = document.getElementById('title-counter');
  const inputBody = document.getElementById('notice-body');
  const inputStartDate = document.getElementById('notice-start-date');
  const inputStartTime = document.getElementById('notice-start-time');
  const inputEndDate = document.getElementById('notice-end-date');
  const inputEndTime = document.getElementById('notice-end-time');
  const btnSetStartNow = document.getElementById('btn-set-start-now');
  const scheduleDiffBadge = document.getElementById('schedule-diff-badge');
  const scheduleSummaryBar = document.getElementById('schedule-summary-bar');
  const scheduleSummaryDot = document.getElementById('schedule-summary-dot');
  const scheduleSummaryText = document.getElementById('schedule-summary-text');
  const inputDuration = document.getElementById('notice-duration');
  const durationGroup = document.getElementById('duration-group');
  const typeRadios = document.querySelectorAll('input[name="type"]');
  const mediaUploadGroup = document.getElementById('media-upload-group');
  const mediaFileInput = document.getElementById('media-file-input');
  const fileDropArea = document.getElementById('file-drop-area');
  const dropPrompt = document.getElementById('drop-prompt');
  const dropSelected = document.getElementById('drop-selected');
  const fileName = document.getElementById('file-name');
  const fileSize = document.getElementById('file-size');
  const btnRemoveFile = document.getElementById('btn-remove-file');

  // Live Media Preview Elements
  const mediaLivePreview = document.getElementById('media-live-preview');
  const previewMediaWrapper = document.getElementById('preview-media-wrapper');
  const previewRatioPill = document.getElementById('preview-ratio-pill');
  const previewDimsLabel = document.getElementById('preview-dims-label');
  const aspectRecommendLabel = document.getElementById('aspect-recommend-label');
  const dropAspectHint = document.getElementById('drop-aspect-hint');
  let editingNoticeId = null;

  const errTitle = document.getElementById('err-title');
  const errMedia = document.getElementById('err-media');
  const errStart = document.getElementById('err-start');
  const errEnd = document.getElementById('err-end');
  const createNoticeError = document.getElementById('create-notice-error');

  // Delete Modal Elements
  const deleteModal = document.getElementById('delete-modal');
  const btnCloseDeleteModal = document.getElementById('btn-close-delete-modal');
  const btnCancelDelete = document.getElementById('btn-cancel-delete');
  const btnConfirmDelete = document.getElementById('btn-confirm-delete');
  const deleteNoticeTitle = document.getElementById('delete-notice-title');

  // Toast Container
  const toastContainer = document.getElementById('toast-container');

  // ==========================================================================
  // Auth Management
  // ==========================================================================
  let cachedCsrfToken = '';

  function getAdminPassword() {
    return sessionStorage.getItem('vnotice_admin_pass') || '';
  }

  function setAdminPassword(pass) {
    sessionStorage.setItem('vnotice_admin_pass', pass);
  }

  function clearAdminPassword() {
    sessionStorage.removeItem('vnotice_admin_pass');
    cachedCsrfToken = '';
  }

  async function checkAuthAndLoad() {
    const pass = getAdminPassword();
    if (!pass) {
      showLoginModal();
      return;
    }

    try {
      await fetchNotices();
      hideLoginModal();
    } catch (err) {
      if (err.status === 401) {
        clearAdminPassword();
        showLoginModal();
      }
    }
  }

  function showLoginModal() {
    loginModal.classList.remove('hidden');
    loginError.classList.add('hidden');
    passwordInput.value = '';
    passwordInput.focus();
  }

  function hideLoginModal() {
    loginModal.classList.add('hidden');
  }

  if (btnTogglePassword) {
    btnTogglePassword.addEventListener('click', () => {
      const isPw = passwordInput.type === 'password';
      passwordInput.type = isPw ? 'text' : 'password';
      btnTogglePassword.textContent = isPw ? 'Hide' : 'Show';
    });
  }

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pass = passwordInput.value.trim();
    if (!pass) return;

    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pass })
      });

      if (res.status === 429) {
        const data = await res.json().catch(() => ({}));
        let retrySeconds = parseInt(res.headers.get('Retry-After') || data.retry_after || 600, 10);
        loginError.classList.remove('hidden');
        passwordInput.disabled = true;
        const btnLogin = document.getElementById('btn-login');
        if (btnLogin) btnLogin.disabled = true;

        clearInterval(window._loginCountdown);
        const updateCountdown = () => {
          if (retrySeconds <= 0) {
            clearInterval(window._loginCountdown);
            loginError.textContent = 'Lockout period ended. You may now try again.';
            passwordInput.disabled = false;
            if (btnLogin) btnLogin.disabled = false;
            passwordInput.focus();
            return;
          }
          loginError.textContent = `Too many failed attempts. Try again in ${retrySeconds}s.`;
          retrySeconds--;
        };
        updateCountdown();
        window._loginCountdown = setInterval(updateCountdown, 1000);
        return;
      }

      if (!res.ok) {
        loginError.textContent = 'Incorrect password. Please try again.';
        loginError.classList.remove('hidden');
        passwordInput.select();
        return;
      }

      const loginResData = await res.json().catch(() => ({}));
      if (loginResData && loginResData.csrf_token) {
        cachedCsrfToken = loginResData.csrf_token;
      }

      clearInterval(window._loginCountdown);
      setAdminPassword(pass);
      hideLoginModal();
      if (feedScreenFilter) {
        feedScreenFilter.addEventListener('change', () => fetchNotices(true));
      }
      loadScreens();
      fetchNotices(true);
    } catch (err) {
      loginError.textContent = err.message || 'Connection error. Please retry.';
      loginError.classList.remove('hidden');
      passwordInput.select();
    }
  });

  btnLogout.addEventListener('click', async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
    } catch (e) {}
    clearAdminPassword();
    showLoginModal();
  });

  // ==========================================================================
  // Toast Notifications
  // ==========================================================================
  function showToast(message, isError = false) {
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'toast-error' : ''}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(6px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => { toast.remove(); }, 200);
    }, 3000);
  }

  // ==========================================================================

  // ==========================================================================
  // Screen Management (Phase 1)
  // ==========================================================================
  let availableScreens = [];

  async function loadScreens() {
    try {
      const res = await fetch('/api/screens');
      if (res.ok) {
        const data = await res.json();
        availableScreens = data.screens || data || [];
        populateScreenDropdowns(availableScreens);
      }
    } catch (e) {
      console.warn('Failed to load screens:', e);
    }
  }

  function populateScreenDropdowns(screens) {
    if (!screens || !screens.length) return;
    if (feedScreenFilter) {
      const cur = feedScreenFilter.value;
      feedScreenFilter.innerHTML = '<option value="all">All Screens</option>';
      screens.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name || s.id;
        feedScreenFilter.appendChild(opt);
      });
      feedScreenFilter.value = cur || 'all';
    }
    if (noticeScreen) {
      const cur = noticeScreen.value;
      noticeScreen.innerHTML = '';
      screens.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name || s.id;
        noticeScreen.appendChild(opt);
      });
      noticeScreen.value = cur || 'default';
    }
  }

  // ==========================================================================
  // CSRF Protection (Phase 2)
  // ==========================================================================
  async function getCsrfToken() {
    if (cachedCsrfToken) return cachedCsrfToken;
    try {
      const res = await fetch('/api/csrf-token');
      if (res.ok) {
        const d = await res.json();
        cachedCsrfToken = d.csrf_token || '';
        return cachedCsrfToken;
      }
    } catch (e) {}
    return '';
  }

  // Fetch Notices & Compute Status
  // ==========================================================================
  let adminNoticesEtag = null;

  async function fetchNotices(forceRefresh = false) {
    const pass = getAdminPassword();
    const selectedScreen = feedScreenFilter ? feedScreenFilter.value : 'all';
    const screenQuery = selectedScreen && selectedScreen !== 'all' ? `?screen=${encodeURIComponent(selectedScreen)}` : '';
    
    const headers = {
      'X-Password': pass,
      'Cache-Control': 'no-cache'
    };
    if (adminNoticesEtag && !forceRefresh) {
      headers['If-None-Match'] = adminNoticesEtag;
    }

    const res = await fetch(`/api/notices${screenQuery}`, {
      cache: 'no-cache',
      headers
    });

    if (res.status === 304) {
      // HTTP 304 Not Modified: notices unchanged, zero DOM rebuild
      return;
    }

    if (res.status === 401) {
      const err = new Error('Unauthorized');
      err.status = 401;
      throw err;
    }

    if (!res.ok) throw new Error(`Server returned ${res.status}`);

    const etag = res.headers.get('ETag');
    if (etag) adminNoticesEtag = etag;

    const data = await res.json();
    notices = Array.isArray(data) ? data : [];
    updateSummaryCounts();
    renderNoticesList();
  }

  function updateSummaryCounts() {
    let total = notices.length;
    let live = 0;
    let scheduled = 0;
    let expired = 0;

    notices.forEach(n => {
      const st = n.status || 'live';
      if (st === 'live') live++;
      else if (st === 'scheduled') scheduled++;
      else if (st === 'expired') expired++;
    });

    if (countAll) countAll.textContent = total;
    if (countLive) countLive.textContent = live;
    if (countScheduled) countScheduled.textContent = scheduled;
    if (countExpired) countExpired.textContent = expired;
  }

  // ==========================================================================
  // Render Notices List (Sorted: Live first, Scheduled by start, Expired by end)
  // ==========================================================================
  
  // Video poster cache and canvas generator
  const videoPosterCache = {};
  function requestVideoPoster(mediaUrl, callback) {
    if (videoPosterCache[mediaUrl]) {
      callback(videoPosterCache[mediaUrl]);
      return;
    }
    const video = document.createElement('video');
    video.src = mediaUrl;
    video.crossOrigin = 'anonymous';
    video.muted = true;
    video.preload = 'metadata';
    video.currentTime = 0.5;
    video.addEventListener('loadeddata', () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 160;
        canvas.height = 90;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const url = canvas.toDataURL('image/jpeg', 0.7);
        videoPosterCache[mediaUrl] = url;
        callback(url);
      } catch (e) {
        callback(null);
      }
    });
    video.addEventListener('error', () => callback(null));
  }

  // Format schedule dates with relative duration (ends in 3 days)
  function formatScheduleLine(startMs, endMs) {
    if (!startMs && !endMs) return 'Not scheduled';
    const now = Date.now();
    const currYear = new Date().getFullYear();

    const fmt = (ms) => {
      if (!ms) return '';
      const d = new Date(ms);
      const yr = d.getFullYear() !== currYear ? ` ${d.getFullYear()}` : '';
      const dateStr = d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' });
      const timeStr = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
      return `${dateStr}${yr}, ${timeStr}`;
    };

    let relativeHtml = '';
    if (endMs) {
      const diffMs = endMs - now;
      if (diffMs > 0) {
        const days = Math.ceil(diffMs / (86400000));
        const hours = Math.ceil(diffMs / (3600000));
        if (days > 1) {
          relativeHtml = `<span class="schedule-rel rel-active">ends in ${days} days</span>`;
        } else if (hours > 1) {
          relativeHtml = `<span class="schedule-rel rel-active">ends in ${hours} hours</span>`;
        } else {
          relativeHtml = `<span class="schedule-rel rel-ending">ends soon</span>`;
        }
      } else {
        const agoDays = Math.floor(Math.abs(diffMs) / 86400000);
        relativeHtml = `<span class="schedule-rel rel-expired">${agoDays > 0 ? `ended ${agoDays}d ago` : 'ended recently'}</span>`;
      }
    }

    const rangeStr = `${fmt(startMs)} – ${fmt(endMs)}`;
    return `${rangeStr} ${relativeHtml ? `· ${relativeHtml}` : ''}`;
  }

  // Gradient tile background for text notices
  function getNoticeTileBg(id) {
    const gradients = [
      'linear-gradient(135deg, #1E3A8A 0%, #172554 100%)',
      'linear-gradient(135deg, #312E81 0%, #1E1B4B 100%)',
      'linear-gradient(135deg, #064E3B 0%, #022C22 100%)',
      'linear-gradient(135deg, #334155 0%, #0F172A 100%)'
    ];
    if (!id) return gradients[0];
    let hash = 0;
    for (let i = 0; i < String(id).length; i++) hash = ((hash << 5) - hash) + String(id).charCodeAt(i);
    return gradients[Math.abs(hash) % gradients.length];
  }

  // Per-tab illustrated empty states
  const TAB_EMPTY_STATES = {
    all: {
      icon: `<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M8 7h8M8 11h8M8 15h5"></path></svg>`,
      title: 'No notices published yet',
      helper: 'Create your first campus notice to get started on the kiosk board.',
      action: true
    },
    live: {
      icon: `<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>`,
      title: 'No live notices right now',
      helper: 'Notices currently within their publication window appear here.',
      action: false
    },
    scheduled: {
      icon: `<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
      title: 'No scheduled notices queued',
      helper: 'Notices with future publication start times appear here.',
      action: false
    },
    expired: {
      icon: `<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
      title: 'No expired notices in history',
      helper: 'Notices that completed their publication run are archived here.',
      action: false
    }
  };

  function renderNoticesList() {
    noticesContainer.innerHTML = '';

    // Sort order per spec
    const sorted = [...notices].sort((a, b) => {
      const rank = { live: 1, scheduled: 2, expired: 3 };
      const rankA = rank[a.status || 'live'] || 2;
      const rankB = rank[b.status || 'live'] || 2;

      if (rankA !== rankB) return rankA - rankB;

      if (rankA === 2) {
        // Scheduled: earliest start time first
        return (a.start || 0) - (b.start || 0);
      }
      // Expired or Live: newest first
      return (b.start || 0) - (a.start || 0);
    });

    const filtered = sorted.filter(n => {
      if (currentFilter === 'all') return true;
      return (n.status || 'live') === currentFilter;
    });

        if (filtered.length === 0) {
      const emptyInfo = TAB_EMPTY_STATES[currentFilter] || TAB_EMPTY_STATES.all;
      noticesContainer.innerHTML = `
        <div class="notices-empty-view">
          <div class="empty-view-icon">${emptyInfo.icon}</div>
          <h2 class="empty-view-title">${emptyInfo.title}</h2>
          <p class="empty-view-helper">${emptyInfo.helper}</p>
          ${emptyInfo.action ? `<button type="button" class="btn btn-primary btn-lg" id="btn-empty-create">Create notice</button>` : ''}
        </div>
      `;
      const btnEmptyCreate = document.getElementById('btn-empty-create');
      if (btnEmptyCreate) {
        btnEmptyCreate.addEventListener('click', openCreateModal);
      }
      return;
    }

    filtered.forEach(notice => {
      const card = document.createElement('article');
      card.tabIndex = 0;
      const status = notice.status || 'live';
      const prio = (notice.priority || 'normal').toLowerCase();
      const ntype = notice.type || 'text';

      card.className = `notice-item-card status-${status} prio-${prio} ${status === 'expired' ? 'is-expired' : ''}`;

      // 1. Left Thumbnail Anatomy: Image, Video Poster, or Gradient Initial Tile
      let tileHtml = '';
      if (ntype === 'image' && notice.media) {
        const mediaUrl = `/media/${encodeURIComponent(notice.media)}`;
        tileHtml = `<div class="notice-media-tile"><img src="${mediaUrl}" alt="" class="notice-thumb-img" loading="lazy"></div>`;
      } else if (ntype === 'video' && notice.media) {
        const mediaUrl = `/media/${encodeURIComponent(notice.media)}`;
        tileHtml = `
          <div class="notice-media-tile video-tile" data-video-url="${mediaUrl}">
            <img class="notice-thumb-img video-poster-img hidden" alt="">
            <span class="poster-play-badge" aria-hidden="true">▶</span>
          </div>`;
      } else {
        const initial = (notice.title || 'T').trim().charAt(0).toUpperCase() || 'T';
        tileHtml = `
          <div class="notice-media-tile text-tile" style="background: ${getNoticeTileBg(notice.id)}">
            <span class="text-tile-initial">${escapeHtml(initial)}</span>
          </div>`;
      }

      // 2. Badges Row: Distinct Status Pill & Distinct Priority Pill (Color is never only signal)
      const statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
      const prioLabel = prio.charAt(0).toUpperCase() + prio.slice(1);
      const typeLabel = ntype.charAt(0).toUpperCase() + ntype.slice(1);
      const durationText = ntype !== 'video' ? ` · ${notice.duration || 10}s` : '';

      // 3. Formatted Schedule Line with Year Disambiguation and Relative Duration
      const scheduleLine = formatScheduleLine(notice.start, notice.end);

      card.innerHTML = `
        ${tileHtml}
        <div class="notice-content">
          <h3 class="notice-title">${escapeHtml(notice.title || 'Untitled notice')}</h3>
          ${notice.body ? `<p class="notice-body-snippet">${escapeHtml(notice.body)}</p>` : ''}
          <div class="notice-badges-row">
            <span class="badge-status badge-status-${status}">
              <span class="status-indicator-dot"></span>
              <span>${statusLabel}</span>
            </span>
            <span class="badge-priority badge-prio-${prio}">
              <span>${prioLabel}</span>
            </span>
            <span class="badge-type">
              <span>${typeLabel}</span>${durationText}
            </span>
          </div>
          <div class="notice-schedule-line">${scheduleLine}</div>
        </div>
        <div class="notice-actions">
          <button type="button" class="btn btn-secondary btn-action-edit btn-edit-row" data-id="${notice.id}" aria-label="Edit notice">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            <span class="btn-label-text">Edit</span>
          </button>
          <button type="button" class="btn btn-secondary btn-action-delete btn-delete-row" data-id="${notice.id}" aria-label="Delete notice">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            <span class="btn-label-text">Delete</span>
          </button>
        </div>
      `;

      // Async video poster rendering
      if (ntype === 'video' && notice.media) {
        const vTile = card.querySelector('.video-tile');
        const vImg = card.querySelector('.video-poster-img');
        if (vTile && vImg) {
          requestVideoPoster(`/media/${encodeURIComponent(notice.media)}`, (posterUrl) => {
            if (posterUrl) {
              vImg.src = posterUrl;
              vImg.classList.remove('hidden');
            }
          });
        }
      }

      const editBtn = card.querySelector('.btn-edit-row');
      editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openEditModal(notice);
      });

      const deleteBtn = card.querySelector('.btn-delete-row');
      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openDeleteModal(notice);
      });

      noticesContainer.appendChild(card);
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ==========================================================================
  // Segmented Filter Controls
  // ==========================================================================
  segmentTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      segmentTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentFilter = tab.getAttribute('data-filter') || 'all';
      renderNoticesList();
    });
  });

  btnRefresh.addEventListener('click', () => {
    fetchNotices(true);
  });

  // ==========================================================================
  // Schedule & Date/Time Management (Separate Date + Time for total clarity)
  // ==========================================================================
  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function toDateInputString(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  }

  function toTimeInputString(date) {
    return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }

  function formatTime12(date) {
    let hours = date.getHours();
    const minutes = pad2(date.getMinutes());
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    return `${hours}:${minutes} ${ampm}`;
  }

  function formatDateShort(date) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return `${days[date.getDay()]}, ${date.getDate()} ${months[date.getMonth()]}`;
  }

  function getStartTimestamp() {
    if (!inputStartDate || !inputStartDate.value) return Date.now();
    const timeVal = (inputStartTime && inputStartTime.value) ? inputStartTime.value : '00:00';
    const d = new Date(`${inputStartDate.value}T${timeVal}`);
    return isNaN(d.getTime()) ? Date.now() : d.getTime();
  }

  function getEndTimestamp() {
    if (!inputEndDate || !inputEndDate.value) return Date.now() + 7 * 86400000;
    const timeVal = (inputEndTime && inputEndTime.value) ? inputEndTime.value : '23:59';
    const d = new Date(`${inputEndDate.value}T${timeVal}`);
    return isNaN(d.getTime()) ? (Date.now() + 7 * 86400000) : d.getTime();
  }

  function setStartDateTime(date) {
    if (inputStartDate) inputStartDate.value = toDateInputString(date);
    if (inputStartTime) inputStartTime.value = toTimeInputString(date);
    updateScheduleSummary();
  }

  function setEndDateTime(date) {
    if (inputEndDate) inputEndDate.value = toDateInputString(date);
    if (inputEndTime) inputEndTime.value = toTimeInputString(date);
    updateScheduleSummary();
  }

  function updateScheduleSummary() {
    if (!scheduleSummaryText || !inputStartDate || !inputEndDate) return;
    const startMs = getStartTimestamp();
    const endMs = getEndTimestamp();
    const nowMs = Date.now();

    if (endMs <= startMs) {
      if (scheduleSummaryDot) {
        scheduleSummaryDot.className = 'summary-dot is-warning';
      }
      scheduleSummaryText.textContent = 'End date & time must be after start date & time.';
      if (scheduleDiffBadge) scheduleDiffBadge.textContent = 'Invalid';
      return;
    }

    const diffMs = endMs - startMs;
    const diffHours = Math.round(diffMs / 3600000);
    const diffDays = Math.round(diffMs / 86400000);

    let durationLabel = '';
    if (diffDays >= 1) {
      durationLabel = diffDays === 1 ? '1 day' : `${diffDays} days`;
    } else {
      durationLabel = `${diffHours} hours`;
    }
    if (scheduleDiffBadge) scheduleDiffBadge.textContent = durationLabel;

    const startDate = new Date(startMs);
    const endDate = new Date(endMs);

    const isFuture = (startMs - nowMs) > 2 * 60 * 1000;
    if (scheduleSummaryDot) {
      scheduleSummaryDot.className = `summary-dot ${isFuture ? 'is-scheduled' : ''}`;
    }

    const startText = isFuture ? `Starts ${formatDateShort(startDate)} at ${formatTime12(startDate)}` : 'Active immediately';
    const endText = `Ends ${formatDateShort(endDate)} at ${formatTime12(endDate)}`;
    scheduleSummaryText.textContent = `${startText} · ${endText} (${durationLabel})`;
  }

  function openCreateModal() {
    editingNoticeId = null;
    if (modalHeading) modalHeading.textContent = 'New notice';
    if (btnSubmitText) btnSubmitText.textContent = 'Publish';
    resetCreateForm();
    if (noticeScreen) noticeScreen.value = 'default';
    if (noticeCreatedBy) noticeCreatedBy.value = 'admin';
    noticeModal.classList.remove('hidden');
    inputTitle.focus();
  }

  function openEditModal(notice) {
    resetCreateForm();
    editingNoticeId = notice.id;

    if (modalHeading) modalHeading.textContent = 'Edit notice';
    if (btnSubmitText) btnSubmitText.textContent = 'Save changes';

    inputTitle.value = notice.title || '';
    const len = inputTitle.value.length;
    if (len > 80) {
      titleCounter.textContent = `${len} / 120`;
      titleCounter.classList.remove('hidden');
    } else {
      titleCounter.classList.add('hidden');
    }

    inputBody.value = notice.body || '';
    if (noticeScreen) noticeScreen.value = notice.screen_id || 'default';
    if (noticeCreatedBy) noticeCreatedBy.value = notice.created_by || 'admin';

    // Priority
    const prio = (notice.priority || 'normal').toLowerCase();
    const prioRadio = document.querySelector(`input[name="priority"][value="${prio}"]`);
    if (prioRadio) prioRadio.checked = true;

    // Type
    const type = (notice.type || 'text').toLowerCase();
    const typeRadio = document.querySelector(`input[name="type"][value="${type}"]`);
    if (typeRadio) typeRadio.checked = true;
    updateTypeState(type);

    // Dates
    if (notice.start) {
      setStartDateTime(new Date(notice.start));
    } else {
      setStartDateTime(new Date());
    }
    if (notice.end) {
      setEndDateTime(new Date(notice.end));
    } else {
      const nextWeek = new Date(Date.now() + 7 * 86400000);
      nextWeek.setHours(23, 59, 0, 0);
      setEndDateTime(nextWeek);
    }

    // Duration
    inputDuration.value = notice.duration || 10;

    // Existing media
    if (notice.media) {
      fileName.textContent = notice.media;
      fileSize.textContent = 'Current media';
      dropPrompt.classList.add('hidden');
      dropSelected.classList.remove('hidden');
      renderMediaPreviewFromUrl(`/media/${encodeURIComponent(notice.media)}`, type);
    }

    noticeModal.classList.remove('hidden');
    inputTitle.focus();
  }

  function closeCreateModal() {
    noticeModal.classList.add('hidden');
    clearValidationErrors();
    editingNoticeId = null;
  }

  function resetCreateForm() {
    createNoticeForm.reset();
    clearValidationErrors();
    clearSelectedFile();

    const scrollBody = createNoticeForm.querySelector('.modal-body-scroll');
    if (scrollBody) scrollBody.scrollTop = 0;

    const now = new Date();
    const nextWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    nextWeek.setHours(23, 59, 0, 0);

    setStartDateTime(now);
    setEndDateTime(nextWeek);
    inputDuration.value = '10';

    updateTypeState('text');
  }

  function clearValidationErrors() {
    [errTitle, errMedia, errStart, errEnd, createNoticeError].forEach(el => {
      if (el) {
        el.textContent = '';
        el.classList.add('hidden');
      }
    });
  }

  // Character counter appears only after 80 characters
  inputTitle.addEventListener('input', () => {
    const len = inputTitle.value.length;
    if (len > 80) {
      titleCounter.textContent = `${len} / 120`;
      titleCounter.classList.remove('hidden');
    } else {
      titleCounter.classList.add('hidden');
    }
  });

  function updateTypeState(type) {
    if (type === 'image' || type === 'video') {
      mediaUploadGroup.classList.remove('hidden');
      mediaFileInput.accept = type === 'image' ? 'image/*' : 'video/*';

      if (type === 'image') {
        if (aspectRecommendLabel) aspectRecommendLabel.textContent = 'Best: 16:9 or 3:4 / 4:3';
        if (dropAspectHint) {
          dropAspectHint.innerHTML = `
            <span class="badge-icon">🎯</span>
            <span class="badge-text">Recommended: <strong>16:9 Landscape</strong> (full-bleed) or <strong>3:4 / 4:3 Poster</strong> (ambient blur auto-fills sides)</span>
          `;
        }
      } else {
        if (aspectRecommendLabel) aspectRecommendLabel.textContent = 'Best: 16:9 Widescreen';
        if (dropAspectHint) {
          dropAspectHint.innerHTML = `
            <span class="badge-icon">🎯</span>
            <span class="badge-text">Recommended: <strong>16:9 Landscape</strong> (1920×1080 / 1280×720 MP4 or WEBM) for seamless full-screen playback</span>
          `;
        }
      }
    } else {
      mediaUploadGroup.classList.add('hidden');
      clearSelectedFile();
    }

    // Rule: Hide duration field when video
    if (durationGroup) {
      durationGroup.style.display = type === 'video' ? 'none' : 'flex';
    }
  }

  typeRadios.forEach(radio => {
    radio.addEventListener('change', (e) => {
      updateTypeState(e.target.value);
    });
  });

  // Quick presets for expiration
  document.querySelectorAll('.btn-quick-set').forEach(btn => {
    btn.addEventListener('click', () => {
      const preset = btn.getAttribute('data-preset');
      const startMs = getStartTimestamp();
      const baseDate = new Date(startMs);
      let targetDate = new Date(baseDate.getTime());

      if (preset === 'today') {
        targetDate.setHours(23, 59, 0, 0);
      } else if (preset === '3days') {
        targetDate.setDate(targetDate.getDate() + 3);
        targetDate.setHours(23, 59, 0, 0);
      } else if (preset === '7days') {
        targetDate.setDate(targetDate.getDate() + 7);
        targetDate.setHours(23, 59, 0, 0);
      } else if (preset === '14days') {
        targetDate.setDate(targetDate.getDate() + 14);
        targetDate.setHours(23, 59, 0, 0);
      } else if (preset === '30days') {
        targetDate.setDate(targetDate.getDate() + 30);
        targetDate.setHours(23, 59, 0, 0);
      }

      setEndDateTime(targetDate);
    });
  });

  if (btnSetStartNow) {
    btnSetStartNow.addEventListener('click', () => {
      setStartDateTime(new Date());
    });
  }

  [inputStartDate, inputStartTime, inputEndDate, inputEndTime].forEach(input => {
    if (input) {
      input.addEventListener('change', updateScheduleSummary);
      input.addEventListener('input', updateScheduleSummary);
    }
  });

  // Drop area drag & drop
  fileDropArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileDropArea.classList.add('dragover');
  });

  fileDropArea.addEventListener('dragleave', () => {
    fileDropArea.classList.remove('dragover');
  });

  fileDropArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileDropArea.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      mediaFileInput.files = e.dataTransfer.files;
      handleFileSelected();
    }
  });

  mediaFileInput.addEventListener('change', handleFileSelected);

  const MAX_FILE_SIZE_MB = 200;
  const ALLOWED_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4', 'webm'];

  function handleFileSelected() {
    if (mediaFileInput.files && mediaFileInput.files[0]) {
      const file = mediaFileInput.files[0];
      const ext = file.name.split('.').pop().toLowerCase();

      // Allowed extension check
      if (!ALLOWED_EXTS.includes(ext)) {
        errMedia.textContent = `Unsupported file type (.${ext}). Allowed: jpg, png, webp, gif, mp4, webm.`;
        errMedia.classList.remove('hidden');
        resetFileDrop();
        return;
      }

      // Max file size check
      const sizeMb = file.size / (1024 * 1024);
      if (sizeMb > MAX_FILE_SIZE_MB) {
        errMedia.textContent = `File size (${sizeMb.toFixed(1)} MB) exceeds limit of ${MAX_FILE_SIZE_MB} MB.`;
        errMedia.classList.remove('hidden');
        resetFileDrop();
        return;
      }

      errMedia.textContent = '';
      errMedia.classList.add('hidden');
      fileName.textContent = file.name;
      fileSize.textContent = `${sizeMb.toFixed(1)} MB`;
      dropPrompt.classList.add('hidden');
      dropSelected.classList.remove('hidden');

      // Live Media Preview with Aspect Ratio
      renderMediaPreviewFromFile(file);
    }
  }

  function renderMediaPreviewFromFile(file) {
    if (!file || !previewMediaWrapper) return;
    previewMediaWrapper.innerHTML = '';
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    const objectUrl = URL.createObjectURL(file);

    if (isImage) {
      const img = document.createElement('img');
      img.src = objectUrl;
      img.alt = 'Media preview';
      img.onload = () => {
        displayRatioAndDims(img.naturalWidth, img.naturalHeight);
      };
      previewMediaWrapper.appendChild(img);
    } else if (isVideo) {
      const video = document.createElement('video');
      video.src = objectUrl;
      video.muted = true;
      video.playsInline = true;
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        displayRatioAndDims(video.videoWidth, video.videoHeight);
      };
      previewMediaWrapper.appendChild(video);
    }
    if (mediaLivePreview) mediaLivePreview.classList.remove('hidden');
  }

  function renderMediaPreviewFromUrl(url, type) {
    if (!url || !previewMediaWrapper) return;
    previewMediaWrapper.innerHTML = '';
    if (type === 'image') {
      const img = document.createElement('img');
      img.src = url;
      img.alt = 'Media preview';
      img.onload = () => {
        displayRatioAndDims(img.naturalWidth, img.naturalHeight);
      };
      previewMediaWrapper.appendChild(img);
    } else if (type === 'video') {
      const video = document.createElement('video');
      video.src = url;
      video.muted = true;
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        displayRatioAndDims(video.videoWidth, video.videoHeight);
      };
      previewMediaWrapper.appendChild(video);
    }
    if (mediaLivePreview) mediaLivePreview.classList.remove('hidden');
  }

  function displayRatioAndDims(w, h) {
    if (!w || !h) return;
    if (previewDimsLabel) previewDimsLabel.textContent = `${w} × ${h} px`;

    const ratio = w / h;
    let ratioText = 'Custom';
    let fitText = '';
    if (ratio >= 1.65) {
      ratioText = '16:9 Landscape';
      fitText = '✓ Fits full screen';
    } else if (ratio >= 1.25 && ratio < 1.65) {
      ratioText = '4:3 Standard';
      fitText = '✓ Ambient backdrop enabled';
    } else if (ratio >= 0.9 && ratio < 1.25) {
      ratioText = '1:1 Square';
      fitText = '✓ Ambient backdrop enabled';
    } else if (ratio >= 0.5 && ratio < 0.9) {
      ratioText = '3:4 / Poster';
      fitText = '✓ Centered with ambient backdrop';
    } else {
      ratioText = `${ratio.toFixed(2)}:1`;
      fitText = '✓ Auto-scaled';
    }

    if (previewRatioPill) previewRatioPill.textContent = `${ratioText} · ${fitText}`;
  }

  btnRemoveFile.addEventListener('click', (e) => {
    e.stopPropagation();
    clearSelectedFile();
  });

  function clearSelectedFile() {
    mediaFileInput.value = '';
    dropPrompt.classList.remove('hidden');
    dropSelected.classList.add('hidden');
    if (previewMediaWrapper) previewMediaWrapper.innerHTML = '';
    if (mediaLivePreview) mediaLivePreview.classList.add('hidden');
  }

  btnOpenCreate.addEventListener('click', openCreateModal);
  btnCloseModal.addEventListener('click', closeCreateModal);
  btnCancelCreate.addEventListener('click', closeCreateModal);

  // Form submission with progress tracking (Create or Edit)
  createNoticeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearValidationErrors();

    const title = inputTitle.value.trim();
    if (!title) {
      errTitle.textContent = 'Please enter a headline.';
      errTitle.classList.remove('hidden');
      return;
    }

    const type = document.querySelector('input[name="type"]:checked')?.value || 'text';
    const isNewNotice = !editingNoticeId;

    // For new image/video notices, media file is required
    if (isNewNotice && (type === 'image' || type === 'video') && (!mediaFileInput.files || !mediaFileInput.files[0])) {
      errMedia.textContent = `Choose a ${type} file to upload.`;
      errMedia.classList.remove('hidden');
      return;
    }

    const startMs = getStartTimestamp();
    const endMs = getEndTimestamp();

    if (endMs <= startMs) {
      errEnd.textContent = 'Show until must be after show from.';
      errEnd.classList.remove('hidden');
      return;
    }

    const priority = document.querySelector('input[name="priority"]:checked')?.value || 'normal';
    const duration = parseInt(inputDuration.value, 10) || 10;

    const formData = new FormData();
    formData.append('title', title);
    if (noticeScreen) formData.append('screen_id', noticeScreen.value || 'default');
    if (noticeCreatedBy) formData.append('created_by', noticeCreatedBy.value || 'admin');
    formData.append('body', inputBody.value.trim());
    formData.append('priority', priority);
    formData.append('type', type);
    formData.append('duration', duration);
    formData.append('start', startMs);
    formData.append('end', endMs);

    if (mediaFileInput.files && mediaFileInput.files[0]) {
      formData.append('media_file', mediaFileInput.files[0]);
    }

    // Submit with XMLHttpRequest for progress bar support
    setSubmitting(true);

    const xhr = new XMLHttpRequest();
    const method = editingNoticeId ? 'PUT' : 'POST';
    const endpoint = editingNoticeId ? `/api/notices/${editingNoticeId}` : '/api/notices';

    xhr.open(method, endpoint, true);
    xhr.setRequestHeader('X-Password', getAdminPassword());
    const csrf = await getCsrfToken();
    if (csrf) xhr.setRequestHeader('X-CSRF-Token', csrf);

    if (uploadProgressTrack && uploadProgressFill) {
      uploadProgressTrack.classList.remove('hidden');
      uploadProgressFill.style.width = '0%';
    }

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && uploadProgressFill) {
        const pct = Math.round((evt.loaded / evt.total) * 100);
        uploadProgressFill.style.width = `${pct}%`;
      }
    };

    xhr.onload = async () => {
      setSubmitting(false);
      if (xhr.status >= 200 && xhr.status < 300) {
        closeCreateModal();
        showToast(editingNoticeId ? 'Notice updated' : 'Published');
        await fetchNotices(true);
      } else {
        let msg = editingNoticeId ? 'Failed to update notice.' : 'Failed to publish notice.';
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.error) msg = res.error;
        } catch (e) {}
        createNoticeError.textContent = msg;
        createNoticeError.classList.remove('hidden');
      }
    };

    xhr.onerror = () => {
      setSubmitting(false);
      createNoticeError.textContent = 'Network error while saving.';
      createNoticeError.classList.remove('hidden');
    };

    xhr.send(formData);
  });

  function setSubmitting(loading) {
    btnSubmitCreate.disabled = loading;
    btnSubmitText.textContent = loading ? 'Publishing…' : 'Publish';
    if (!loading && uploadProgressTrack) {
      uploadProgressTrack.classList.add('hidden');
    }
  }

  // ==========================================================================
  // Delete Dialog & Action
  // ==========================================================================
  function openDeleteModal(notice) {
    noticeToDelete = notice;
    deleteNoticeTitle.textContent = `"${notice.title || 'Untitled notice'}"`;
    deleteModal.classList.remove('hidden');
  }

  function closeDeleteModal() {
    deleteModal.classList.add('hidden');
    noticeToDelete = null;
  }

  btnCloseDeleteModal.addEventListener('click', closeDeleteModal);
  btnCancelDelete.addEventListener('click', closeDeleteModal);

  btnConfirmDelete.addEventListener('click', async () => {
    if (!noticeToDelete) return;
    const deletedId = noticeToDelete.id;
    btnConfirmDelete.disabled = true;

    try {
      const res = await fetch(`/api/notices/${deletedId}`, {
        method: 'DELETE',
        headers: {
          'X-Password': getAdminPassword(),
          'X-CSRF-Token': (await getCsrfToken()) || '',
          'Cache-Control': 'no-cache, no-store, must-revalidate'
        }
      });

      if (!res.ok) throw new Error('Failed to delete notice.');

      closeDeleteModal();
      showToast('Notice deleted');

      // Instantly remove notice from local array and re-render UI without waiting
      notices = notices.filter(n => n.id !== deletedId);
      updateSummaryCounts();
      renderNoticesList();

      // Refresh data from server to ensure complete sync
      await fetchNotices();
    } catch (err) {
      showToast(err.message || 'Error deleting notice.', true);
    } finally {
      btnConfirmDelete.disabled = false;
    }
  });

  // Escape key closes open dialogs
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (!noticeModal.classList.contains('hidden')) closeCreateModal();
      if (!deleteModal.classList.contains('hidden')) closeDeleteModal();
    }
  });

  // Initialize
  checkAuthAndLoad();

  // Background auto-sync in admin every 5 seconds (uses ETag 304); throttled when tab is hidden
  setInterval(() => {
    if (localStorage.getItem('vnotice_admin_pass') && !document.hidden) {
      fetchNotices(false).catch(() => {});
    }
  }, 5000);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && localStorage.getItem('vnotice_admin_pass')) {
      fetchNotices(false).catch(() => {});
    }
  });


  // ==========================================================================
  // Audit Logs Modal Controller (Phase 6)
  // ==========================================================================
  const btnViewAudit = document.getElementById('btn-view-audit');
  const auditModal = document.getElementById('audit-modal');
  const btnCloseAudit = document.getElementById('btn-close-audit');
  const auditLoading = document.getElementById('audit-loading');
  const auditTbody = document.getElementById('audit-tbody');

  function openAuditModal() {
    if (auditModal) {
      auditModal.classList.remove('hidden');
      loadAuditLogs();
    }
  }

  function closeAuditModal() {
    if (auditModal) auditModal.classList.add('hidden');
  }

  async function loadAuditLogs() {
    if (!auditTbody) return;
    if (auditLoading) auditLoading.classList.remove('hidden');
    auditTbody.innerHTML = '';

    try {
      const res = await fetch('/api/audit-logs?limit=50', {
        headers: {
          'X-Password': getAdminPassword(),
          'Cache-Control': 'no-cache'
        }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const logs = Array.isArray(data) ? data : (data.logs || []);

      if (auditLoading) auditLoading.classList.add('hidden');

      if (logs.length === 0) {
        auditTbody.innerHTML = '<tr><td colspan="5" class="audit-empty-row">No security or administrative activity recorded yet.</td></tr>';
        return;
      }

      auditTbody.innerHTML = logs.map(log => {
        const timeStr = log.created_at ? new Date(log.created_at).toLocaleString() : 'N/A';
        const actionCls = `audit-action-${(log.action || '').toLowerCase()}`;
        return `<tr>
          <td style="white-space: nowrap; color: var(--muted);">${escapeHtml(timeStr)}</td>
          <td><span class="audit-action-badge ${actionCls}">${escapeHtml(log.action || '')}</span></td>
          <td><strong>${escapeHtml(log.actor || 'admin')}</strong></td>
          <td style="font-family: monospace; font-size: 12px;">${escapeHtml(log.target_id || '-')}</td>
          <td style="color: var(--muted); font-family: monospace;">${escapeHtml(log.ip_address || '-')}</td>
        </tr>`;
      }).join('');
    } catch (err) {
      if (auditLoading) auditLoading.classList.add('hidden');
      auditTbody.innerHTML = `<tr><td colspan="5" class="audit-empty-row" style="color: var(--red);">Error loading audit logs: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  if (btnViewAudit) btnViewAudit.addEventListener('click', openAuditModal);
  if (btnCloseAudit) btnCloseAudit.addEventListener('click', closeAuditModal);
  if (auditModal) {
    auditModal.addEventListener('click', (e) => {
      if (e.target === auditModal) closeAuditModal();
    });
  }

})();
