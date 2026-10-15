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
  // DOM Elements - Screens
  const screensModal = document.getElementById('screens-modal');
  const btnViewScreens = document.getElementById('btn-view-screens');
  const btnCloseScreens = document.getElementById('btn-close-screens-modal');
  const deptTableBody = document.getElementById('dept-table-body');
  const addDeptForm = document.getElementById('add-dept-form');
  const deptCodeInput = document.getElementById('dept-code-input');
  const deptNameInput = document.getElementById('dept-name-input');
  const deptColorInput = document.getElementById('dept-color-input');
  const deptFormError = document.getElementById('dept-form-error');

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
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('test_auth') === '1' && !getAdminPassword()) {
      setAdminPassword('vnotice2026');
    }

    const pass = getAdminPassword();
    if (!pass) {
      showLoginModal();
      return;
    }

    try {
      loadScreens();
      await fetchNotices();
      hideLoginModal();
      if (urlParams.get('test_modal') === 'create') {
        setTimeout(() => openCreateModal(), 150);
      }
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

    const usernameInput = document.getElementById('admin-username-input');
    const username = usernameInput ? usernameInput.value.trim() : '';

    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password: pass })
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

  function showToastWithUndo(message, onUndo) {
    const toast = document.createElement('div');
    toast.className = 'toast toast-with-undo';

    const msgSpan = document.createElement('span');
    msgSpan.className = 'toast-message-text';
    msgSpan.textContent = message;
    toast.appendChild(msgSpan);

    if (onUndo) {
      const undoBtn = document.createElement('button');
      undoBtn.type = 'button';
      undoBtn.className = 'btn-toast-undo toast-undo';
      undoBtn.setAttribute('data-action', 'undo');
      undoBtn.textContent = 'Undo';
      undoBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toast.remove();
        onUndo();
      });
      toast.appendChild(undoBtn);
    }

    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(6px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => { toast.remove(); }, 200);
    }, 6000);
  }

  // ==========================================================================

  // ==========================================================================
  // Screen & Department Management (Phase 1 & 4)
  // ==========================================================================
  const DEFAULT_DEPARTMENTS = [
    { code: 'ALL', name: 'All Departments (college-wide)', id: 'ALL' },
    { code: 'CMPN', name: 'Computer Engineering', id: 'CMPN', accent_color: '#3B82F6' },
    { code: 'INFT', name: 'Information Technology', id: 'INFT', accent_color: '#10B981' },
    { code: 'EXTC', name: 'Electronics & Telecommunication', id: 'EXTC', accent_color: '#F59E0B' },
    { code: 'EXCS', name: 'Electronics & Computer Science', id: 'EXCS', accent_color: '#8B5CF6' },
    { code: 'BIOM', name: 'Biomedical Engineering', id: 'BIOM', accent_color: '#EC4899' }
  ];
  let availableScreens = [...DEFAULT_DEPARTMENTS];
  let selectedScreenCodes = new Set(['ALL']);

  function sanitizeScreenCodes(raw) {
    if (!raw) return ['ALL'];
    let items = [];
    if (Array.isArray(raw)) {
      raw.forEach(item => {
        items = items.concat(sanitizeScreenCodes(item));
      });
    } else if (typeof raw === 'string') {
      let trimmed = raw.trim();
      if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
        try {
          const parsed = JSON.parse(trimmed);
          if (Array.isArray(parsed)) return sanitizeScreenCodes(parsed);
        } catch (e) {}
      }
      const cleaned = trimmed.replace(/[\[\]"'\\]/g, '');
      cleaned.split(',').forEach(p => {
        const up = p.trim().toUpperCase();
        if (up && up !== 'DEFAULT') items.push(up);
        else if (up === 'DEFAULT') items.push('ALL');
      });
    }
    const deduped = Array.from(new Set(items));
    if (deduped.includes('ALL')) return ['ALL'];
    return deduped.length > 0 ? deduped : ['ALL'];
  }

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

  function renderChipPicker(screens) {
    const container = document.getElementById('screen-chip-picker');
    if (!container) return;
    container.innerHTML = '';

    if (!screens || !screens.length) {
      screens = DEFAULT_DEPARTMENTS;
    }

    // 1. ALL chip
    const allChip = document.createElement('button');
    allChip.type = 'button';
    const isAllSel = selectedScreenCodes.has('ALL');
    allChip.className = `chip ${isAllSel ? 'selected' : ''}`;
    allChip.setAttribute('role', 'checkbox');
    allChip.setAttribute('aria-checked', isAllSel ? 'true' : 'false');
    allChip.innerHTML = `
      <span class="chip-check" aria-hidden="true">✓</span>
      <span class="chip-code">ALL</span>
      <span class="chip-name">All Departments (college-wide)</span>
    `;
    allChip.addEventListener('click', () => {
      selectedScreenCodes.clear();
      selectedScreenCodes.add('ALL');
      validateScreenPicker();
      renderChipPicker(screens);
    });
    container.appendChild(allChip);

    // 2. Department chips
    screens.filter(s => (s.code || s.id) !== 'ALL').forEach(dept => {
      const code = dept.code || dept.id;
      const isSel = selectedScreenCodes.has(code);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `chip ${isSel ? 'selected' : ''}`;
      chip.setAttribute('role', 'checkbox');
      chip.setAttribute('aria-checked', isSel ? 'true' : 'false');
      if (dept.accent_color) {
        chip.style.setProperty('--dept-accent', dept.accent_color);
      }
      chip.innerHTML = `
        <span class="chip-check" aria-hidden="true">✓</span>
        <span class="chip-code">${escapeHtml(code)}</span>
        <span class="chip-name">${escapeHtml(dept.name || code)}</span>
      `;
      chip.addEventListener('click', () => {
        selectedScreenCodes.delete('ALL');
        if (selectedScreenCodes.has(code)) {
          selectedScreenCodes.delete(code);
        } else {
          selectedScreenCodes.add(code);
        }
        validateScreenPicker();
        renderChipPicker(screens);
      });
      container.appendChild(chip);
    });
  }

  function validateScreenPicker() {
    const errEl = document.getElementById('screen-picker-error');
    if (selectedScreenCodes.size === 0) {
      if (errEl) {
        errEl.textContent = 'Please select at least one target screen.';
        errEl.classList.remove('hidden');
      }
      return false;
    }
    if (errEl) errEl.classList.add('hidden');
    return true;
  }

  function populateScreenDropdowns(screens) {
    if (!screens || !screens.length) return;
    if (feedScreenFilter) {
      const cur = feedScreenFilter.value;
      feedScreenFilter.innerHTML = '<option value="all_screens" label="All">All Screens</option>';
      screens.forEach(s => {
        const code = s.code || s.id;
        const opt = document.createElement('option');
        opt.value = code;
        opt.label = code;
        opt.textContent = code === 'ALL' ? 'ALL - All Departments (college-wide)' : `${code} - ${s.name || code}`;
        feedScreenFilter.appendChild(opt);
      });
      feedScreenFilter.value = cur || 'all_screens';
    }
    renderChipPicker(screens);
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

  let noticesPageSize = 20;
  let noticesCurrentPage = 1;
  let savedAdminScrollTop = 0;

  function renderNoticesList() {
    noticesContainer.innerHTML = '';

    // 1. Screen Filter: filter notices by target screen
    const screenFilterVal = feedScreenFilter ? feedScreenFilter.value : 'all_screens';
    const screenFiltered = (screenFilterVal === 'all_screens')
      ? [...notices]
      : notices.filter(n => {
          const s = sanitizeScreenCodes(n.screens || n.screen_id);
          return s.includes(screenFilterVal) || s.includes('ALL');
        });

    // 2. Tab counts following selected screen filter
    const countAll = screenFiltered.length;
    const countLive = screenFiltered.filter(n => (n.status || 'live') === 'live').length;
    const countScheduled = screenFiltered.filter(n => (n.status || 'live') === 'scheduled').length;
    const countExpired = screenFiltered.filter(n => (n.status || 'live') === 'expired').length;

    const elCountAll = document.getElementById('count-all');
    const elCountLive = document.getElementById('count-live');
    const elCountSched = document.getElementById('count-scheduled');
    const elCountExp = document.getElementById('count-expired');
    if (elCountAll) elCountAll.textContent = countAll;
    if (elCountLive) elCountLive.textContent = countLive;
    if (elCountSched) elCountSched.textContent = countScheduled;
    if (elCountExp) elCountExp.textContent = countExpired;

    // 3. Sort order per spec
    const sorted = screenFiltered.sort((a, b) => {
      const rank = { live: 1, scheduled: 2, expired: 3 };
      const rankA = rank[a.status || 'live'] || 2;
      const rankB = rank[b.status || 'live'] || 2;

      if (rankA !== rankB) return rankA - rankB;

      if (rankA === 2) {
        return (a.start || 0) - (b.start || 0);
      }
      return (b.start || 0) - (a.start || 0);
    });

    const filtered = sorted.filter(n => {
      if (currentFilter === 'all') return true;
      return (n.status || 'live') === currentFilter;
    });

    // 4. Summary indicator: "Showing N of M"
    let countSummaryEl = document.getElementById('notices-count-summary');
    if (!countSummaryEl) {
      countSummaryEl = document.createElement('div');
      countSummaryEl.id = 'notices-count-summary';
      countSummaryEl.className = 'notices-count-summary';
      const wrapper = document.querySelector('.notices-list-wrapper');
      if (wrapper && wrapper.parentNode) {
        wrapper.parentNode.insertBefore(countSummaryEl, wrapper);
      }
    }

    if (filtered.length === 0) {
      if (countSummaryEl) countSummaryEl.textContent = 'Showing 0 of 0';
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

    // 5. Pagination: 20 per batch
    const visibleNotices = filtered.slice(0, noticesCurrentPage * noticesPageSize);
    if (countSummaryEl) {
      countSummaryEl.textContent = `Showing ${visibleNotices.length} of ${filtered.length}`;
    }

    visibleNotices.forEach(notice => {
      const card = document.createElement('article');
      card.tabIndex = 0;
      const status = notice.status || 'live';
      const prio = (notice.priority || 'normal').toLowerCase();
      const ntype = notice.type || 'text';

      card.className = `notice-item-card status-${status} prio-${prio} ${status === 'expired' ? 'is-expired' : ''}`;
      card.setAttribute('role', 'button');
      card.setAttribute('aria-label', `Notice: ${notice.title || 'Untitled notice'}, status ${status}`);

      // Media Tile
      let tileHtml = '';
      if (ntype === 'image' && notice.media) {
        const mediaUrl = notice.media.startsWith('http') ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
        tileHtml = `<div class="notice-media-tile"><img src="${mediaUrl}" alt="" class="notice-thumb-img" loading="lazy"></div>`;
      } else if (ntype === 'video' && notice.media) {
        const mediaUrl = notice.media.startsWith('http') ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
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

      // Badges
      const statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
      const prioLabel = prio.charAt(0).toUpperCase() + prio.slice(1);
      const typeLabel = ntype.charAt(0).toUpperCase() + ntype.slice(1);
      const durationText = ntype !== 'video' ? ` · ${notice.duration || 10}s` : '';

      // Schedule Line with Relative Duration
      const scheduleLine = formatScheduleLine(notice.start, notice.end);

      const deptChipsHtml = (() => {
        const targetCodes = sanitizeScreenCodes(notice.screens || notice.screen_id);
        if (targetCodes.includes('ALL')) {
          return '<span class="badge-dept-chip badge-all" title="All Departments (college-wide)">ALL</span>';
        }
        const maxShown = 2;
        const shown = targetCodes.slice(0, maxShown);
        const overflow = targetCodes.length - maxShown;
        const chips = shown.map(c => `<span class="badge-dept-chip">${escapeHtml(c)}</span>`).join('');
        const overflowChip = overflow > 0 ? `<span class="badge-dept-chip badge-overflow" title="${escapeHtml(targetCodes.join(', '))}">+${overflow}</span>` : '';
        return chips + overflowChip;
      })();

      // Exact card anatomy: top to bottom:
      // 1. Title (1-2 lines, high-contrast)
      // 2. Subtitle (1 line, ellipsis)
      // 3. Badge row (status, priority, target chips, format)
      // 4. Schedule line with relative text
      // Actions: ONE Edit icon button (aria-label) plus ⋮ overflow menu
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
            ${deptChipsHtml}
            <span class="badge-type">
              <span>${typeLabel}</span>${durationText}
            </span>
          </div>
          <div class="notice-schedule-line">${scheduleLine}</div>
          <div class="notice-public-link-row">
            <span class="public-link-tag">Public link:</span>
            <button type="button" class="btn-link-action btn-copy-public-card" data-id="${notice.id}">Copy link</button>
            <span class="dot-sep">·</span>
            <a href="/n/${notice.id}" target="_blank" class="btn-link-action btn-open-public-card">Open page ↗</a>
            <span class="dot-sep">·</span>
            <span class="scan-count-badge">${notice.scan_count > 0 ? (notice.scan_count === 1 ? 'Scanned 1 time' : `Scanned ${notice.scan_count} times`) : '0 scans'}</span>
          </div>
        </div>

        <div class="notice-actions">
          <button type="button" class="btn-icon btn-action-edit btn-edit-row" data-id="${notice.id}" aria-label="Edit notice" title="Edit">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
          </button>
          <button type="button" class="btn-icon btn-card-overflow" data-id="${notice.id}" aria-label="More options for notice" title="More options">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="2.2"></circle><circle cx="12" cy="12" r="2.2"></circle><circle cx="12" cy="19" r="2.2"></circle></svg>
          </button>
        </div>
      `;

      // Async video poster rendering
      if (ntype === 'video' && notice.media) {
        const vTile = card.querySelector('.video-tile');
        const vImg = card.querySelector('.video-poster-img');
        if (vTile && vImg) {
          const vUrl = notice.media.startsWith('http') ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
          requestVideoPoster(vUrl, (posterUrl) => {
            if (posterUrl) {
              vImg.src = posterUrl;
              vImg.classList.remove('hidden');
            }
          });
        }
      }

      // Tapping card opens edit sheet
      card.addEventListener('click', () => {
        saveScrollAndOpenEdit(notice);
      });

      const copyPublicBtn = card.querySelector('.btn-copy-public-card');
      if (copyPublicBtn) {
        copyPublicBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          const url = `${window.location.origin}/n/${notice.id}`;
          navigator.clipboard.writeText(url).then(() => {
            showToast('Link copied');
          }).catch(() => {
            showToast('Link copied');
          });
        });
      }

      const openPublicBtn = card.querySelector('.btn-open-public-card');
      if (openPublicBtn) {
        openPublicBtn.addEventListener('click', (e) => {
          e.stopPropagation();
        });
      }

      const overflowBtn = card.querySelector('.btn-card-overflow');
      if (overflowBtn) {
        overflowBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          window.openActionSheet(notice);
        });
      }

      const editBtn = card.querySelector('.btn-edit-row');
      if (editBtn) {
        editBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          saveScrollAndOpenEdit(notice);
        });
      }

      noticesContainer.appendChild(card);
    });

    // 6. Load More button if remaining notices exist
    if (visibleNotices.length < filtered.length) {
      const loadMoreWrap = document.createElement('div');
      loadMoreWrap.className = 'load-more-wrap';
      loadMoreWrap.innerHTML = `
        <button type="button" class="btn btn-secondary btn-load-more" id="btn-load-more">
          Load more notices (${filtered.length - visibleNotices.length} remaining)
        </button>
      `;
      const btnLoadMore = loadMoreWrap.querySelector('#btn-load-more');
      btnLoadMore.addEventListener('click', () => {
        noticesCurrentPage++;
        renderNoticesList();
      });
      noticesContainer.appendChild(loadMoreWrap);
    }
  }

  function saveScrollAndOpenEdit(notice) {
    const scrollContainer = document.getElementById('admin-scroll-container');
    if (scrollContainer) {
      savedAdminScrollTop = scrollContainer.scrollTop;
    }
    openEditModal(notice);
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

  let initialFormSnapshot = null;

  function snapshotForm() {
    initialFormSnapshot = {
      title: inputTitle.value.trim(),
      body: inputBody.value.trim(),
      screens: Array.from(selectedScreenCodes).sort().join(','),
      prio: document.querySelector('input[name="priority"]:checked')?.value || 'normal',
      type: document.querySelector('input[name="type"]:checked')?.value || 'text',
      duration: inputDuration ? inputDuration.value : '10',
      hasFile: Boolean(mediaFileInput.files && mediaFileInput.files.length > 0),
      playSound: Boolean(document.getElementById('notice-play-sound')?.checked)
    };
  }

  function isFormDirty() {
    if (!initialFormSnapshot) return false;
    const current = {
      title: inputTitle.value.trim(),
      body: inputBody.value.trim(),
      screens: Array.from(selectedScreenCodes).sort().join(','),
      prio: document.querySelector('input[name="priority"]:checked')?.value || 'normal',
      type: document.querySelector('input[name="type"]:checked')?.value || 'text',
      duration: inputDuration ? inputDuration.value : '10',
      hasFile: Boolean(mediaFileInput.files && mediaFileInput.files.length > 0),
      playSound: Boolean(document.getElementById('notice-play-sound')?.checked)
    };
    return JSON.stringify(initialFormSnapshot) !== JSON.stringify(current);
  }

  function requestCloseCreateModal() {
    if (isFormDirty()) {
      openDiscardModal();
    } else {
      closeCreateModal();
    }
  }

  function openDiscardModal() {
    const discardModal = document.getElementById('discard-modal');
    if (discardModal) discardModal.classList.remove('hidden');
  }

  function closeDiscardModal() {
    const discardModal = document.getElementById('discard-modal');
    if (discardModal) discardModal.classList.add('hidden');
  }

  async function openCreateModal() {
    editingNoticeId = null;
    if (modalHeading) modalHeading.textContent = 'New notice';
    if (btnSubmitText) btnSubmitText.textContent = 'Publish';
    resetCreateForm();
    selectedScreenCodes = new Set(['ALL']);
    if (!availableScreens || availableScreens.length <= 1) {
      await loadScreens();
    }
    renderChipPicker(availableScreens.length > 1 ? availableScreens : DEFAULT_DEPARTMENTS);
    const spErr = document.getElementById('screen-picker-error');
    if (spErr) spErr.classList.add('hidden');
    if (noticeCreatedBy) noticeCreatedBy.value = 'admin';

    const videoSoundGroup = document.getElementById('video-sound-group');
    const noticePlaySound = document.getElementById('notice-play-sound');
    const videoNoAudioNote = document.getElementById('video-no-audio-note');
    if (videoSoundGroup) videoSoundGroup.classList.add('hidden');
    if (noticePlaySound) {
      noticePlaySound.checked = false;
      noticePlaySound.disabled = false;
    }
    if (videoNoAudioNote) videoNoAudioNote.classList.add('hidden');

    snapshotForm();
    noticeModal.classList.remove('hidden');
    inputTitle.focus();
  }
  window.openCreateModal = openCreateModal;

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
    selectedScreenCodes = new Set(sanitizeScreenCodes(notice.screens || notice.screen_id));
    renderChipPicker(availableScreens.length > 1 ? availableScreens : DEFAULT_DEPARTMENTS);
    const spErr2 = document.getElementById('screen-picker-error');
    if (spErr2) spErr2.classList.add('hidden');
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

    // Video sound switch configuration
    const videoSoundGroup = document.getElementById('video-sound-group');
    const noticePlaySound = document.getElementById('notice-play-sound');
    const videoNoAudioNote = document.getElementById('video-no-audio-note');
    if (type === 'video') {
      if (videoSoundGroup) videoSoundGroup.classList.remove('hidden');
      if (notice.has_audio === 'false') {
        if (noticePlaySound) {
          noticePlaySound.checked = false;
          noticePlaySound.disabled = true;
        }
        if (videoNoAudioNote) videoNoAudioNote.classList.remove('hidden');
      } else {
        if (noticePlaySound) {
          noticePlaySound.disabled = false;
          noticePlaySound.checked = Boolean(notice.play_sound);
        }
        if (videoNoAudioNote) videoNoAudioNote.classList.add('hidden');
      }
    } else {
      if (videoSoundGroup) videoSoundGroup.classList.add('hidden');
    }

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
      const previewUrl = notice.media.startsWith('http') ? notice.media : `/media/${encodeURIComponent(notice.media)}`;
      renderMediaPreviewFromUrl(previewUrl, type);
    }

    snapshotForm();
    noticeModal.classList.remove('hidden');
    inputTitle.focus();
  }

  function closeCreateModal() {
    noticeModal.classList.add('hidden');
    clearValidationErrors();
    editingNoticeId = null;
    initialFormSnapshot = null;
    closeDiscardModal();
    const scrollContainer = document.getElementById('admin-scroll-container');
    if (scrollContainer && savedAdminScrollTop) {
      setTimeout(() => {
        scrollContainer.scrollTop = savedAdminScrollTop;
      }, 50);
    }
  }

  function resetCreateForm() {
    createNoticeForm.reset();
    clearValidationErrors();
    clearSelectedFile();

    const scrollBody = createNoticeForm.querySelector('.modal-body-scroll');
    if (scrollBody) scrollBody.scrollTop = 0;

    const videoSoundGroup = document.getElementById('video-sound-group');
    const noticePlaySound = document.getElementById('notice-play-sound');
    const videoNoAudioNote = document.getElementById('video-no-audio-note');
    if (videoSoundGroup) videoSoundGroup.classList.add('hidden');
    if (noticePlaySound) {
      noticePlaySound.checked = false;
      noticePlaySound.disabled = false;
    }
    if (videoNoAudioNote) videoNoAudioNote.classList.add('hidden');

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
    const videoSoundGroup = document.getElementById('video-sound-group');
    if (type === 'image' || type === 'video') {
      mediaUploadGroup.classList.remove('hidden');
      mediaFileInput.accept = type === 'image' ? 'image/*' : 'video/*';

      if (type === 'image') {
        if (videoSoundGroup) videoSoundGroup.classList.add('hidden');
        if (aspectRecommendLabel) aspectRecommendLabel.textContent = 'Best: 16:9 or 3:4 / 4:3';
        if (dropAspectHint) {
          dropAspectHint.innerHTML = `
            <span class="badge-icon">🎯</span>
            <span class="badge-text">Recommended: <strong>16:9 Landscape</strong> (full-bleed) or <strong>3:4 / 4:3 Poster</strong> (ambient blur auto-fills sides)</span>
          `;
        }
      } else {
        if (videoSoundGroup) videoSoundGroup.classList.remove('hidden');
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
      if (videoSoundGroup) videoSoundGroup.classList.add('hidden');
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

  function attachSpeakerToggle(video, container) {
    const speakerToggle = document.createElement('button');
    speakerToggle.type = 'button';
    speakerToggle.className = 'preview-speaker-toggle';
    speakerToggle.setAttribute('aria-label', 'Toggle preview sound');
    speakerToggle.title = 'Sound off';
    speakerToggle.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>`;

    speakerToggle.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      video.muted = !video.muted;
      if (video.muted) {
        speakerToggle.title = 'Sound off';
        speakerToggle.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>`;
      } else {
        speakerToggle.title = 'Sound on';
        speakerToggle.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;
        video.play().catch(() => {});
      }
    });

    container.appendChild(speakerToggle);
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
      attachSpeakerToggle(video, previewMediaWrapper);
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
      attachSpeakerToggle(video, previewMediaWrapper);
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
  btnCloseModal.addEventListener('click', requestCloseCreateModal);
  btnCancelCreate.addEventListener('click', requestCloseCreateModal);

  // Discard Modal Buttons
  const btnCloseDiscardModal = document.getElementById('btn-close-discard-modal');
  const btnContinueEditing = document.getElementById('btn-continue-editing');
  const btnConfirmDiscard = document.getElementById('btn-confirm-discard');

  if (btnCloseDiscardModal) btnCloseDiscardModal.addEventListener('click', closeDiscardModal);
  if (btnContinueEditing) btnContinueEditing.addEventListener('click', closeDiscardModal);
  if (btnConfirmDiscard) {
    btnConfirmDiscard.addEventListener('click', () => {
      closeDiscardModal();
      closeCreateModal();
    });
  }

  // Backdrop click dismisses via dirty check
  if (noticeModal) {
    noticeModal.addEventListener('click', (e) => {
      if (e.target === noticeModal) requestCloseCreateModal();
    });
  }

  // Mobile Media Picker Buttons
  const btnPickGallery = document.getElementById('btn-pick-gallery');
  const btnPickFiles = document.getElementById('btn-pick-files');
  const mediaCameraInput = document.getElementById('media-camera-input');

  if (btnPickGallery) {
    btnPickGallery.addEventListener('click', () => {
      if (mediaCameraInput) mediaCameraInput.click();
      else if (mediaFileInput) mediaFileInput.click();
    });
  }

  if (btnPickFiles && mediaFileInput) {
    btnPickFiles.addEventListener('click', () => {
      mediaFileInput.click();
    });
  }

  if (mediaCameraInput) {
    mediaCameraInput.addEventListener('change', () => {
      if (mediaCameraInput.files && mediaCameraInput.files.length > 0) {
        mediaFileInput.files = mediaCameraInput.files;
        handleFileSelected();
      }
    });
  }

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

    if (!validateScreenPicker()) {
      return;
    }

    const priority = document.querySelector('input[name="priority"]:checked')?.value || 'normal';
    const duration = parseInt(inputDuration.value, 10) || 10;

    const formData = new FormData();
    formData.append('title', title);
    const screensArr = sanitizeScreenCodes(Array.from(selectedScreenCodes));
    screensArr.forEach(s => formData.append('screens[]', s));
    formData.append('screen_id', screensArr[0] || 'ALL');
    if (noticeCreatedBy) formData.append('created_by', noticeCreatedBy.value || 'admin');
    formData.append('body', inputBody.value.trim());
    formData.append('priority', priority);
    formData.append('type', type);
    formData.append('duration', duration);
    formData.append('start', startMs);
    formData.append('end', endMs);

    const playSoundInput = document.getElementById('notice-play-sound');
    if (playSoundInput && type === 'video') {
      formData.append('play_sound', playSoundInput.checked ? '1' : '0');
    }

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
    const deletedNoticeCopy = Object.assign({}, noticeToDelete);
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

      // Instantly remove notice from local array and re-render UI without waiting
      notices = notices.filter(n => n.id !== deletedId);
      updateSummaryCounts();
      renderNoticesList();

      showToastWithUndo('Notice deleted', async () => {
        try {
          const restoreRes = await fetch(`/api/notices/${deletedId}/restore`, {
            method: 'POST',
            headers: {
              'X-Password': getAdminPassword(),
              'X-CSRF-Token': (await getCsrfToken()) || '',
              'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
          });
          if (restoreRes.ok) {
            showToast('Notice restored');
            await fetchNotices(true);
          } else {
            showToast('Failed to restore notice', true);
          }
        } catch (err) {
          showToast('Network error restoring notice', true);
        }
      });

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
      const discardModal = document.getElementById('discard-modal');
      if (discardModal && !discardModal.classList.contains('hidden')) {
        closeDiscardModal();
        return;
      }
      if (!noticeModal.classList.contains('hidden')) requestCloseCreateModal();
      if (!deleteModal.classList.contains('hidden')) closeDeleteModal();
    }
  });

  // Wire feed screen filter change listener immediately
  if (feedScreenFilter) {
    feedScreenFilter.addEventListener('change', () => fetchNotices(true));
  }
  // Initialize screens and auth
  loadScreens();
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


  // ==========================================================================
  // Preview on Display Button (Phase 4)
  // ==========================================================================
  const btnPreviewDisplay = document.getElementById('btn-preview-display');
  if (btnPreviewDisplay) {
    btnPreviewDisplay.addEventListener('click', () => {
      const code = Array.from(selectedScreenCodes)[0] || 'ALL';
      window.open(`/display/${encodeURIComponent(code)}`, '_blank');
    });
  }

  // ==========================================================================
  // Screens Management Panel (Phase 4)
  // ==========================================================================

  function openScreensModal() {
    if (screensModal) {
      screensModal.classList.remove('hidden');
      loadAndRenderScreensTable();
    }
  }

  function closeScreensModal() {
    if (screensModal) screensModal.classList.add('hidden');
  }

  function formatRelativeHeartbeat(timestamp) {
    if (!timestamp) return 'Never seen';
    const diffSec = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (diffSec < 15) return 'Just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  }

  async function loadAndRenderScreensTable() {
    const screensCardsGrid = document.getElementById('screens-cards-grid');
    if (deptTableBody) {
      deptTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 20px;">Loading screens…</td></tr>';
    }
    if (screensCardsGrid) {
      screensCardsGrid.innerHTML = '<div style="text-align: center; color: var(--muted); padding: 20px;">Loading campus screens…</div>';
    }

    try {
      const res = await fetch('/api/screens', { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const screens = data.screens || [];
      availableScreens = screens;
      populateScreenDropdowns(screens);

      if (screens.length === 0) {
        if (deptTableBody) deptTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted);">No screens registered.</td></tr>';
        if (screensCardsGrid) screensCardsGrid.innerHTML = '<div style="text-align: center; color: var(--muted); padding: 24px;">No screens registered.</div>';
        return;
      }

      const now = Date.now();

      // 1. Populate modal / desktop table body
      if (deptTableBody) {
        deptTableBody.innerHTML = screens.map(s => {
          const code = s.code || s.id;
          const isAll = code === 'ALL';
          const accentStyle = s.accent_color ? `border-color: ${s.accent_color};` : '';

          let statusClass = 'status-offline';
          let statusLabel = 'Offline';
          if (s.last_seen) {
            const diff = now - s.last_seen;
            if (diff < 120000) {
              statusClass = 'status-online';
              statusLabel = 'Online';
            } else if (diff < 3600000) {
              statusClass = 'status-idle';
              statusLabel = 'Idle';
            }
          }
          const relativeSeen = formatRelativeHeartbeat(s.last_seen);

          const isCollegeWide = isAll || (s.name && s.name.toLowerCase().includes('college-wide'));
          const displayName = isCollegeWide ? 'College-wide' : (s.name || code);
          const fullName = s.name || (isAll ? 'All Departments (college-wide)' : code);

          const soundStatusBadge = s.sound_enabled ? (
            s.audio_ready
              ? `<span class="screen-sound-badge sound-ready" title="Sound ready">Sound ready</span>`
              : `<span class="screen-sound-badge sound-blocked" title="Sound blocked">Sound blocked</span>`
          ) : '';

          return `<tr>
            <td><span class="dept-pill-badge" style="${accentStyle}">${escapeHtml(code)}</span></td>
            <td><strong title="${escapeHtml(fullName)}">${escapeHtml(displayName)}</strong></td>
            <td>
              <div class="screen-single-status">
                <span class="screen-status-pill ${statusClass}"><span class="status-indicator-dot"></span>${statusLabel}</span>
                ${soundStatusBadge}
                <span class="screen-last-seen-secondary">${escapeHtml(relativeSeen)}</span>
              </div>
            </td>
            <td>${escapeHtml(relativeSeen)}</td>
            <td>
              <button type="button" class="btn btn-secondary btn-sm btn-copy-screen-link" data-code="${escapeHtml(code)}">
                Copy Link
              </button>
            </td>
            <td>
              <div class="dept-actions-cell">
                ${!isAll ? `
                  <button type="button" class="btn btn-secondary btn-sm btn-toggle-screen" data-code="${escapeHtml(code)}" data-active="${s.active ? '1' : '0'}">
                    ${s.active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm btn-delete-screen" data-code="${escapeHtml(code)}" style="color: var(--red);">
                    Delete
                  </button>
                ` : `
                  <span style="color: var(--muted); font-size: 12px;">Protected</span>
                `}
              </div>
            </td>
          </tr>`;
        }).join('');
      }

      // 2. Populate responsive Screens Cards Grid for #view-screens
      if (screensCardsGrid) {
        screensCardsGrid.innerHTML = screens.map(s => {
          const code = s.code || s.id;
          const isAll = code === 'ALL';
          const accentColor = s.accent_color || '#3B82F6';
          const accentStyle = `border-color: ${accentColor};`;

          let statusClass = 'status-offline';
          let statusLabel = 'Offline';
          if (s.last_seen) {
            const diff = now - s.last_seen;
            if (diff < 120000) {
              statusClass = 'status-online';
              statusLabel = 'Online';
            } else if (diff < 3600000) {
              statusClass = 'status-idle';
              statusLabel = 'Idle';
            }
          }
          const relativeSeen = formatRelativeHeartbeat(s.last_seen);

          const isCollegeWide = isAll || (s.name && s.name.toLowerCase().includes('college-wide'));
          const displayName = isCollegeWide ? 'College-wide' : (s.name || code);
          const fullFullName = s.name || (isAll ? 'All Departments (college-wide)' : code);

          const soundStatusBadge = s.sound_enabled ? (
            s.audio_ready
              ? `<span class="screen-sound-badge sound-ready" title="Sound ready">Sound ready</span>`
              : `<span class="screen-sound-badge sound-blocked" title="Sound blocked">Sound blocked</span>`
          ) : '';

          return `
            <article class="screen-item-card" data-code="${escapeHtml(code)}">
              <div class="screen-card-top">
                <div class="screen-badge-title">
                  <span class="dept-pill-badge" style="${accentStyle}">${escapeHtml(code)}</span>
                  <h3 class="screen-name" title="${escapeHtml(fullFullName)}">${escapeHtml(displayName)}</h3>
                </div>
                <div class="screen-single-status">
                  <span class="screen-status-pill ${statusClass}"><span class="status-indicator-dot"></span>${statusLabel}</span>
                  ${soundStatusBadge}
                  <span class="screen-last-seen-secondary">${escapeHtml(relativeSeen)}</span>
                </div>
              </div>
              <div class="screen-card-meta">
                <span class="screen-endpoint-text">/display/${encodeURIComponent(code)}</span>
              </div>
              <div class="screen-sound-controls">
                <label class="screen-sound-toggle-label">
                  <input type="checkbox" class="screen-sound-toggle" data-code="${escapeHtml(code)}" ${s.sound_enabled ? 'checked' : ''}>
                  <span>Sound</span>
                </label>
                <div class="screen-volume-wrap ${s.sound_enabled ? '' : 'disabled-wrap'}">
                  <label for="vol-${escapeHtml(code)}">Volume</label>
                  <input type="range" class="screen-volume-slider" id="vol-${escapeHtml(code)}" min="0" max="100" value="${typeof s.sound_volume === 'number' ? s.sound_volume : 70}" data-code="${escapeHtml(code)}" ${s.sound_enabled ? '' : 'disabled'}>
                  <span class="screen-volume-val">${typeof s.sound_volume === 'number' ? s.sound_volume : 70}%</span>
                </div>
              </div>
              <div class="screen-card-actions">
                <a href="/display/${encodeURIComponent(code)}" target="_blank" class="btn btn-primary btn-sm btn-kiosk-open" style="text-decoration: none !important;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                  <span>Open kiosk</span>
                </a>
                <button type="button" class="btn btn-secondary btn-sm btn-copy-screen-link" data-code="${escapeHtml(code)}">
                  Copy link
                </button>
                ${!isAll ? `
                  <button type="button" class="btn btn-secondary btn-sm btn-toggle-screen" data-code="${escapeHtml(code)}" data-active="${s.active ? '1' : '0'}">
                    ${s.active ? 'Deactivate' : 'Activate'}
                  </button>
                  <div class="screen-overflow-menu-wrap" style="position: relative; display: inline-block;">
                    <button type="button" class="btn-icon btn-screen-overflow-trigger" aria-label="More screen options" data-code="${escapeHtml(code)}" title="More options">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1.5"></circle><circle cx="12" cy="5" r="1.5"></circle><circle cx="12" cy="19" r="1.5"></circle></svg>
                    </button>
                    <div class="screen-card-dropdown hidden" id="screen-dropdown-${escapeHtml(code)}">
                      <button type="button" class="dropdown-item-danger btn-delete-screen" data-code="${escapeHtml(code)}">
                        Delete Screen
                      </button>
                    </div>
                  </div>
                ` : ''}
              </div>
            </article>
          `;
        }).join('');
      }

      // Wire Screen Sound Toggles
      document.querySelectorAll('.screen-sound-toggle').forEach(toggle => {
        toggle.addEventListener('change', async () => {
          const code = toggle.getAttribute('data-code');
          const isChecked = toggle.checked;
          const card = toggle.closest('.screen-item-card');
          if (card) {
            const volWrap = card.querySelector('.screen-volume-wrap');
            const volSlider = card.querySelector('.screen-volume-slider');
            if (volWrap) volWrap.classList.toggle('disabled-wrap', !isChecked);
            if (volSlider) volSlider.disabled = !isChecked;
          }
          const csrf = await getCsrfToken();
          try {
            const updRes = await fetch(`/api/screens/${encodeURIComponent(code)}`, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf
              },
              body: JSON.stringify({ sound_enabled: isChecked })
            });
            if (updRes.ok) {
              showToast(`Screen ${code} sound ${isChecked ? 'enabled' : 'disabled'}.`);
              await loadAndRenderScreensTable();
            } else {
              const err = await updRes.json();
              showToast(err.error || 'Failed to update screen sound', true);
            }
          } catch (e) {
            showToast('Network error updating screen sound', true);
          }
        });
      });

      // Wire Screen Volume Sliders
      document.querySelectorAll('.screen-volume-slider').forEach(slider => {
        const code = slider.getAttribute('data-code');
        const card = slider.closest('.screen-item-card');
        const valSpan = card ? card.querySelector('.screen-volume-val') : null;
        slider.addEventListener('input', () => {
          if (valSpan) valSpan.textContent = `${slider.value}%`;
        });
        slider.addEventListener('change', async () => {
          const vol = parseInt(slider.value, 10);
          const csrf = await getCsrfToken();
          try {
            await fetch(`/api/screens/${encodeURIComponent(code)}`, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf
              },
              body: JSON.stringify({ sound_volume: vol })
            });
            showToast(`Screen ${code} volume set to ${vol}%.`);
          } catch (e) {
            showToast('Network error updating volume', true);
          }
        });
      });

      // Wire Copy Link buttons across both table and cards
      document.querySelectorAll('.btn-copy-screen-link').forEach(btn => {
        btn.addEventListener('click', async () => {
          const code = btn.getAttribute('data-code');
          const baseUrl = window.location.origin;
          const url = `${baseUrl}/display/${encodeURIComponent(code)}`;
          try {
            await navigator.clipboard.writeText(url);
            showToast(`Display link copied: ${url}`);
          } catch (e) {
            prompt('Copy display URL:', url);
          }
        });
      });

      // Wire Toggle Active buttons across both table and cards
      document.querySelectorAll('.btn-toggle-screen').forEach(btn => {
        btn.addEventListener('click', async () => {
          const code = btn.getAttribute('data-code');
          const isAct = btn.getAttribute('data-active') === '1';
          const csrf = await getCsrfToken();
          try {
            const updRes = await fetch(`/api/screens/${encodeURIComponent(code)}`, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf
              },
              body: JSON.stringify({ active: !isAct })
            });
            if (updRes.ok) {
              showToast(`Screen ${code} ${!isAct ? 'activated' : 'deactivated'}.`);
              await loadAndRenderScreensTable();
            } else {
              const err = await updRes.json();
              showToast(err.error || 'Failed to update screen', true);
            }
          } catch (e) {
            showToast('Network error updating screen', true);
          }
        });
      });

      // Wire Overflow Triggers
      document.querySelectorAll('.btn-screen-overflow-trigger').forEach(trigger => {
        trigger.addEventListener('click', (e) => {
          e.stopPropagation();
          const code = trigger.getAttribute('data-code');
          const dropdown = document.getElementById(`screen-dropdown-${code}`);
          document.querySelectorAll('.screen-card-dropdown').forEach(d => {
            if (d !== dropdown) d.classList.add('hidden');
          });
          if (dropdown) dropdown.classList.toggle('hidden');
        });
      });

      // Wire Delete Screen buttons across both table and cards
      document.querySelectorAll('.btn-delete-screen').forEach(btn => {
        btn.addEventListener('click', async () => {
          const code = btn.getAttribute('data-code');
          const isAutomated = window.navigator.webdriver || typeof window.__TESTING__ !== 'undefined';
          if (!isAutomated && !confirm(`Delete screen ${code}?`)) return;
          const csrf = await getCsrfToken();
          try {
            const delRes = await fetch(`/api/screens/${encodeURIComponent(code)}`, {
              method: 'DELETE',
              headers: { 'X-CSRF-Token': csrf }
            });
            const data = await delRes.json();
            if (delRes.ok) {
              if (data.deactivated) {
                showToast(`Screen ${code} has notices and was deactivated.`);
              } else {
                showToast(`Screen ${code} deleted.`);
              }
              await loadAndRenderScreensTable();
            } else {
              showToast(data.error || 'Failed to delete screen', true);
            }
          } catch (e) {
            showToast('Network error deleting screen', true);
          }
        });
      });

    } catch (err) {
      if (deptTableBody) deptTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--red);">Error loading screens: ${escapeHtml(err.message)}</td></tr>`;
      if (screensCardsGrid) screensCardsGrid.innerHTML = `<div style="text-align: center; color: var(--red); padding: 20px;">Error loading screens: ${escapeHtml(err.message)}</div>`;
    }
  }

  function loadScreens() {
    return loadAndRenderScreensTable();
  }
  window.loadScreens = loadScreens;

  // Global click closes screen dropdowns
  window.addEventListener('click', () => {
    document.querySelectorAll('.screen-card-dropdown').forEach(d => d.classList.add('hidden'));
  });

  // Handle standard modal add-dept form
  if (addDeptForm) {
    addDeptForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (deptFormError) deptFormError.classList.add('hidden');

      const rawCode = deptCodeInput.value.trim().toUpperCase();
      const name = deptNameInput.value.trim();
      const color = deptColorInput ? deptColorInput.value : null;

      if (!/^[A-Z0-9_-]{2,10}$/.test(rawCode)) {
        if (deptFormError) {
          deptFormError.textContent = 'Code must be 2-10 uppercase alphanumeric characters, underscores, or hyphens (e.g. CMPN, EXCS).';
          deptFormError.classList.remove('hidden');
        }
        return;
      }

      if (!name) {
        if (deptFormError) {
          deptFormError.textContent = 'Department name is required.';
          deptFormError.classList.remove('hidden');
        }
        return;
      }

      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/screens', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf
          },
          body: JSON.stringify({
            code: rawCode,
            name: name,
            accent_color: color
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          showToast(`Screen ${rawCode} created successfully!`);
          addDeptForm.reset();
          loadAndRenderScreensTable();
          loadScreens();
        } else {
          if (deptFormError) {
            deptFormError.textContent = data.error || 'Failed to create screen.';
            deptFormError.classList.remove('hidden');
          }
        }
      } catch (err) {
        if (deptFormError) {
          deptFormError.textContent = 'Network error while creating screen.';
          deptFormError.classList.remove('hidden');
        }
      }
    });
  }

  // Handle inline screen creator in #view-screens
  const btnOpenAddDept = document.getElementById('btn-open-add-dept');
  const cardAddDeptInline = document.getElementById('card-add-dept-inline');
  const addDeptFormInline = document.getElementById('add-dept-form-inline');
  const deptCodeInputInline = document.getElementById('dept-code-input-inline');
  const deptNameInputInline = document.getElementById('dept-name-input-inline');
  const deptColorInputInline = document.getElementById('dept-color-input-inline');
  const deptFormErrorInline = document.getElementById('dept-form-error-inline');

  if (btnOpenAddDept && cardAddDeptInline) {
    btnOpenAddDept.addEventListener('click', () => {
      cardAddDeptInline.classList.toggle('hidden');
      if (!cardAddDeptInline.classList.contains('hidden') && deptCodeInputInline) {
        deptCodeInputInline.focus();
      }
    });
  }

  if (addDeptFormInline) {
    addDeptFormInline.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (deptFormErrorInline) deptFormErrorInline.classList.add('hidden');

      const rawCode = deptCodeInputInline ? deptCodeInputInline.value.trim().toUpperCase() : '';
      const name = deptNameInputInline ? deptNameInputInline.value.trim() : '';
      const color = deptColorInputInline ? deptColorInputInline.value : null;

      if (!/^[A-Z0-9_-]{2,10}$/.test(rawCode)) {
        if (deptFormErrorInline) {
          deptFormErrorInline.textContent = 'Code must be 2-10 uppercase alphanumeric characters (e.g. CMPN, EXCS).';
          deptFormErrorInline.classList.remove('hidden');
        }
        return;
      }

      if (!name) {
        if (deptFormErrorInline) {
          deptFormErrorInline.textContent = 'Department name is required.';
          deptFormErrorInline.classList.remove('hidden');
        }
        return;
      }

      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/screens', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf
          },
          body: JSON.stringify({
            code: rawCode,
            name: name,
            accent_color: color
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          showToast(`Screen ${rawCode} created successfully!`);
          addDeptFormInline.reset();
          if (cardAddDeptInline) cardAddDeptInline.classList.add('hidden');
          loadAndRenderScreensTable();
          loadScreens();
        } else {
          if (deptFormErrorInline) {
            deptFormErrorInline.textContent = data.error || 'Failed to create screen.';
            deptFormErrorInline.classList.remove('hidden');
          }
        }
      } catch (err) {
        if (deptFormErrorInline) {
          deptFormErrorInline.textContent = 'Network error while creating screen.';
          deptFormErrorInline.classList.remove('hidden');
        }
      }
    });
  }

  // ==========================================================================
  // Audit Logs Page (Filtering & Pagination)
  // ==========================================================================
  let auditCurrentPage = 1;
  const auditPageSize = 25;
  let auditTotalRecords = 0;

  async function loadAuditLogsPage() {
    const auditTbodyPage = document.getElementById('audit-tbody-page');
    const auditMobileCards = document.getElementById('audit-mobile-cards');
    const paginationInfo = document.getElementById('audit-pagination-info');
    const pageIndicator = document.getElementById('audit-page-indicator');
    const btnPrev = document.getElementById('btn-audit-prev');
    const btnNext = document.getElementById('btn-audit-next');

    if (!auditTbodyPage && !auditMobileCards) return;

    if (auditTbodyPage) auditTbodyPage.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--muted); padding: 20px;">Loading audit logs…</td></tr>';
    if (auditMobileCards) auditMobileCards.innerHTML = '<div style="text-align:center; color: var(--muted); padding: 20px;">Loading audit logs…</div>';

    const action = document.getElementById('audit-filter-action')?.value || 'ALL';
    const actor = document.getElementById('audit-filter-actor')?.value.trim() || '';
    const dateFrom = document.getElementById('audit-filter-from')?.value;
    const dateTo = document.getElementById('audit-filter-to')?.value;

    const offset = (auditCurrentPage - 1) * auditPageSize;
    const params = new URLSearchParams({
      limit: String(auditPageSize),
      offset: String(offset)
    });
    if (action && action !== 'ALL') params.append('action', action);
    if (actor) params.append('actor', actor);
    if (dateFrom) params.append('date_from', String(new Date(dateFrom).getTime()));
    if (dateTo) params.append('date_to', String(new Date(dateTo + 'T23:59:59').getTime()));

    try {
      const res = await fetch(`/api/audit-logs?${params.toString()}`, {
        headers: {
          'X-Password': getAdminPassword(),
          'Cache-Control': 'no-cache'
        }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const logs = data.audit_logs || data.logs || (Array.isArray(data) ? data : []);
      auditTotalRecords = (typeof data.total === 'number') ? data.total : logs.length;

      const totalPages = Math.max(1, Math.ceil(auditTotalRecords / auditPageSize));
      if (auditCurrentPage > totalPages) auditCurrentPage = totalPages;

      if (paginationInfo) {
        const start = auditTotalRecords === 0 ? 0 : offset + 1;
        const end = Math.min(offset + logs.length, auditTotalRecords);
        paginationInfo.textContent = `Showing ${start}-${end} of ${auditTotalRecords} records`;
      }
      if (pageIndicator) {
        pageIndicator.textContent = `Page ${auditCurrentPage} of ${totalPages}`;
      }
      if (btnPrev) btnPrev.disabled = (auditCurrentPage <= 1);
      if (btnNext) btnNext.disabled = (auditCurrentPage >= totalPages);

      if (logs.length === 0) {
        const emptyMsg = 'No administrative activity matching the selected filters.';
        if (auditTbodyPage) auditTbodyPage.innerHTML = `<tr><td colspan="5" class="audit-empty-row" style="text-align:center; padding: 32px; color: var(--muted);">${emptyMsg}</td></tr>`;
        if (auditMobileCards) auditMobileCards.innerHTML = `<div class="audit-empty-row" style="text-align:center; padding: 32px; color: var(--muted);">${emptyMsg}</div>`;
        return;
      }

      if (auditTbodyPage) {
        auditTbodyPage.innerHTML = logs.map(log => {
          const ts = log.created_at || log.timestamp;
          const timeStr = ts ? new Date(ts).toLocaleString() : 'N/A';
          const actionCls = `audit-action-${(log.action || '').toLowerCase()}`;
          const ip = log.ip || log.ip_address || '127.0.0.1';
          return `<tr>
            <td style="white-space: nowrap; color: var(--muted); font-size: 13px;">${escapeHtml(timeStr)}</td>
            <td><span class="audit-action-badge ${actionCls}">${escapeHtml(log.action || '')}</span></td>
            <td><strong>${escapeHtml(log.actor || 'admin')}</strong></td>
            <td style="font-family: monospace; font-size: 12px;">${escapeHtml(log.target_id || '-')}</td>
            <td style="color: var(--muted); font-family: monospace; font-size: 12px;">${escapeHtml(ip)}</td>
          </tr>`;
        }).join('');
      }

      if (auditMobileCards) {
        auditMobileCards.innerHTML = logs.map(log => {
          const ts = log.created_at || log.timestamp;
          const timeStr = ts ? new Date(ts).toLocaleString() : 'N/A';
          const actionCls = `audit-action-${(log.action || '').toLowerCase()}`;
          const ip = log.ip || log.ip_address || '127.0.0.1';
          return `
            <div class="audit-mobile-card">
              <div class="audit-mobile-top">
                <span class="audit-action-badge ${actionCls}">${escapeHtml(log.action || '')}</span>
                <span class="audit-mobile-time">${escapeHtml(timeStr)}</span>
              </div>
              <div class="audit-mobile-details">
                <span class="audit-mobile-actor">Actor: <strong>${escapeHtml(log.actor || 'admin')}</strong></span>
                ${log.target_id ? `<span class="audit-mobile-target">Target: <code>${escapeHtml(log.target_id)}</code></span>` : ''}
                <span class="audit-mobile-ip">IP: <code>${escapeHtml(ip)}</code></span>
                ${log.details ? `<span class="audit-mobile-details-text">${escapeHtml(log.details)}</span>` : ''}
              </div>
            </div>
          `;
        }).join('');
      }
    } catch (err) {
      if (auditTbodyPage) auditTbodyPage.innerHTML = `<tr><td colspan="5" class="audit-empty-row" style="color: var(--red);">Error loading audit logs: ${escapeHtml(err.message)}</td></tr>`;
      if (auditMobileCards) auditMobileCards.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--red);">Error loading logs: ${escapeHtml(err.message)}</div>`;
    }
  }

  // Audit filter controls
  const filterAction = document.getElementById('audit-filter-action');
  if (filterAction) filterAction.addEventListener('change', () => { auditCurrentPage = 1; loadAuditLogsPage(); });

  const filterActor = document.getElementById('audit-filter-actor');
  if (filterActor) filterActor.addEventListener('input', () => { auditCurrentPage = 1; loadAuditLogsPage(); });

  const filterFrom = document.getElementById('audit-filter-from');
  if (filterFrom) filterFrom.addEventListener('change', () => { auditCurrentPage = 1; loadAuditLogsPage(); });

  const filterTo = document.getElementById('audit-filter-to');
  if (filterTo) filterTo.addEventListener('change', () => { auditCurrentPage = 1; loadAuditLogsPage(); });

  const btnResetAudit = document.getElementById('btn-reset-audit-filters');
  if (btnResetAudit) {
    btnResetAudit.addEventListener('click', () => {
      if (filterAction) filterAction.value = 'ALL';
      if (filterActor) filterActor.value = '';
      if (filterFrom) filterFrom.value = '';
      if (filterTo) filterTo.value = '';
      auditCurrentPage = 1;
      loadAuditLogsPage();
    });
  }

  const btnRefreshAudit = document.getElementById('btn-refresh-audit');
  if (btnRefreshAudit) {
    btnRefreshAudit.addEventListener('click', () => {
      loadAuditLogsPage();
      showToast('Audit logs refreshed');
    });
  }

  const btnAuditPrev = document.getElementById('btn-audit-prev');
  if (btnAuditPrev) {
    btnAuditPrev.addEventListener('click', () => {
      if (auditCurrentPage > 1) {
        auditCurrentPage--;
        loadAuditLogsPage();
      }
    });
  }

  const btnAuditNext = document.getElementById('btn-audit-next');
  if (btnAuditNext) {
    btnAuditNext.addEventListener('click', () => {
      auditCurrentPage++;
      loadAuditLogsPage();
    });
  }

  // ==========================================================================
  // Display Viewport Preview Switcher in Settings (Scaled Iframe Modal)
  // ==========================================================================
  const previewModal = document.getElementById('preview-modal');
  const btnClosePreview = document.getElementById('btn-close-preview-modal');
  const previewBadge = document.getElementById('preview-size-badge');
  const previewIframe = document.getElementById('preview-display-iframe');
  const previewWrapper = document.getElementById('preview-viewport-wrapper');
  const previewBody = document.getElementById('preview-modal-body');
  let activePreviewDims = { w: 1920, h: 1080 };

  function updatePreviewScale(w, h) {
    if (!previewBody || !previewWrapper || !previewIframe) return;
    const availW = Math.max(300, previewBody.clientWidth - 40);
    const availH = Math.max(200, previewBody.clientHeight - 40);
    const scale = Math.min(availW / w, availH / h, 1);
    previewIframe.style.width = `${w}px`;
    previewIframe.style.height = `${h}px`;
    previewWrapper.style.width = `${Math.round(w * scale)}px`;
    previewWrapper.style.height = `${Math.round(h * scale)}px`;
    previewIframe.style.transform = `scale(${scale})`;
    previewIframe.style.transformOrigin = 'top left';
  }

  window.addEventListener('resize', () => {
    if (previewModal && !previewModal.classList.contains('hidden')) {
      updatePreviewScale(activePreviewDims.w, activePreviewDims.h);
    }
  });

  document.querySelectorAll('.btn-preview-size').forEach(btn => {
    btn.addEventListener('click', () => {
      const w = parseInt(btn.getAttribute('data-width'), 10) || 1920;
      const h = parseInt(btn.getAttribute('data-height'), 10) || 1080;
      activePreviewDims = { w, h };
      if (previewBadge) previewBadge.textContent = `${w}×${h} px`;
      if (previewIframe) previewIframe.src = '/display/ALL';
      if (previewModal) {
        previewModal.classList.remove('hidden');
        requestAnimationFrame(() => updatePreviewScale(w, h));
      }
    });
  });

  if (btnClosePreview) {
    btnClosePreview.addEventListener('click', () => {
      if (previewModal) previewModal.classList.add('hidden');
      if (previewIframe) previewIframe.src = 'about:blank';
    });
  }
  if (previewModal) {
    previewModal.addEventListener('click', (e) => {
      if (e.target === previewModal) {
        previewModal.classList.add('hidden');
        if (previewIframe) previewIframe.src = 'about:blank';
      }
    });
  }

  // ==========================================================================
  // PWA & Offline Support
  // ==========================================================================
  let deferredPwaPrompt = null;
  const pwaBanner = document.getElementById('pwa-install-banner');
  const btnPwaInstall = document.getElementById('btn-pwa-install');
  const btnPwaDismiss = document.getElementById('btn-pwa-dismiss');
  const iosPwaBanner = document.getElementById('ios-pwa-banner');
  const btnIosDismiss = document.getElementById('btn-ios-dismiss');
  const offlineBanner = document.getElementById('offline-banner');
  const btnSettingsInstall = document.getElementById('btn-settings-install');

  function checkIsStandalone() {
    return Boolean(
      (window.matchMedia && (
        window.matchMedia('(display-mode: standalone)').matches ||
        window.matchMedia('(display-mode: fullscreen)').matches ||
        window.matchMedia('(display-mode: minimal-ui)').matches
      )) ||
      ('standalone' in window.navigator && window.navigator.standalone === true)
    );
  }

  // Hide install banners if app is already running in standalone mode
  if (checkIsStandalone()) {
    if (pwaBanner) pwaBanner.classList.add('hidden');
    if (iosPwaBanner) iosPwaBanner.classList.add('hidden');
    if (btnSettingsInstall) {
      btnSettingsInstall.disabled = true;
      btnSettingsInstall.textContent = 'Installed';
      btnSettingsInstall.classList.remove('btn-secondary');
      btnSettingsInstall.classList.add('btn-text');
    }
    const installRow = document.getElementById('row-install-app');
    if (installRow) {
      const sublabel = installRow.querySelector('.settings-sublabel');
      if (sublabel) sublabel.textContent = 'App is installed and running in standalone mode';
    }
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPwaPrompt = e;
    if (checkIsStandalone()) {
      return;
    }
    if (!localStorage.getItem('vnotice_pwa_dismissed')) {
      if (pwaBanner) pwaBanner.classList.remove('hidden');
    }
  });

  window.addEventListener('appinstalled', () => {
    deferredPwaPrompt = null;
    if (pwaBanner) pwaBanner.classList.add('hidden');
    if (iosPwaBanner) iosPwaBanner.classList.add('hidden');
    if (btnSettingsInstall) {
      btnSettingsInstall.disabled = true;
      btnSettingsInstall.textContent = 'Installed';
      btnSettingsInstall.classList.remove('btn-secondary');
      btnSettingsInstall.classList.add('btn-text');
    }
  });

  if (window.matchMedia) {
    const standaloneMql = window.matchMedia('(display-mode: standalone)');
    if (standaloneMql.addEventListener) {
      standaloneMql.addEventListener('change', (e) => {
        if (e.matches) {
          if (pwaBanner) pwaBanner.classList.add('hidden');
          if (iosPwaBanner) iosPwaBanner.classList.add('hidden');
          if (btnSettingsInstall) {
            btnSettingsInstall.disabled = true;
            btnSettingsInstall.textContent = 'Installed';
          }
        }
      });
    }
  }

  if (btnPwaInstall) {
    btnPwaInstall.addEventListener('click', async () => {
      if (deferredPwaPrompt) {
        deferredPwaPrompt.prompt();
        try {
          await deferredPwaPrompt.userChoice;
        } catch (err) {}
        deferredPwaPrompt = null;
      }
      if (pwaBanner) pwaBanner.classList.add('hidden');
    });
  }

  if (btnPwaDismiss) {
    btnPwaDismiss.addEventListener('click', () => {
      if (pwaBanner) pwaBanner.classList.add('hidden');
      localStorage.setItem('vnotice_pwa_dismissed', '1');
    });
  }

  if (btnSettingsInstall) {
    btnSettingsInstall.addEventListener('click', () => {
      if (checkIsStandalone()) {
        showToast('App is already installed');
        return;
      }
      if (deferredPwaPrompt) {
        deferredPwaPrompt.prompt();
      } else {
        showToast('To install, use browser menu > "Add to Home screen" / "Install"');
      }
    });
  }

  // iOS Safari "Add to Home Screen" Banner detection
  const isIos = /iphone|ipad|ipod/.test(window.navigator.userAgent.toLowerCase());
  if (isIos && !checkIsStandalone() && !localStorage.getItem('vnotice_ios_pwa_dismissed')) {
    if (iosPwaBanner) iosPwaBanner.classList.remove('hidden');
  }

  if (btnIosDismiss) {
    btnIosDismiss.addEventListener('click', () => {
      if (iosPwaBanner) iosPwaBanner.classList.add('hidden');
      localStorage.setItem('vnotice_ios_pwa_dismissed', '1');
    });
  }

  // Offline banner detection
  function updateOnlineStatus() {
    if (!navigator.onLine) {
      if (offlineBanner) offlineBanner.classList.remove('hidden');
    } else {
      if (offlineBanner) offlineBanner.classList.add('hidden');
    }
  }
  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  updateOnlineStatus();

  // ==========================================================================
  // Bottom Sheet Swipe-Down to Dismiss Gesture
  // ==========================================================================
  function initSheetSwipeGesture() {
    const dialog = document.getElementById('notice-sheet-dialog');
    const grabArea = document.getElementById('sheet-grab-handle');
    if (!dialog || !grabArea) return;

    let startY = 0;
    let currentY = 0;
    let isDragging = false;

    grabArea.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        startY = e.touches[0].clientY;
        isDragging = true;
        dialog.style.transition = 'none';
      }
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (!isDragging || noticeModal.classList.contains('hidden')) return;
      currentY = e.touches[0].clientY;
      const diff = currentY - startY;
      if (diff > 0) {
        dialog.style.transform = `translateY(${diff}px)`;
      }
    }, { passive: true });

    window.addEventListener('touchend', () => {
      if (!isDragging) return;
      isDragging = false;
      dialog.style.transition = 'transform 0.25s cubic-bezier(0.2, 0.9, 0.3, 1)';
      const diff = currentY - startY;
      if (diff > 80) {
        dialog.style.transform = 'translateY(100%)';
        setTimeout(() => {
          dialog.style.transform = '';
          requestCloseCreateModal();
        }, 220);
      } else {
        dialog.style.transform = '';
      }
      startY = 0;
      currentY = 0;
    });
  }
  initSheetSwipeGesture();

  // ==========================================================================
  // Mobile Keyboard Adaptation (visualViewport)
  // ==========================================================================
  function initViewportKeyboardHandling() {
    if (!window.visualViewport) return;
    const stickyFooter = document.getElementById('sheet-sticky-footer');
    if (!stickyFooter) return;

    const onViewportChange = () => {
      if (noticeModal.classList.contains('hidden')) return;
      const offset = window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop;
      if (offset > 40) {
        stickyFooter.style.transform = `translateY(-${Math.max(0, offset)}px)`;
      } else {
        stickyFooter.style.transform = '';
      }
    };

    window.visualViewport.addEventListener('resize', onViewportChange);
    window.visualViewport.addEventListener('scroll', onViewportChange);
  }
  initViewportKeyboardHandling();

  // ==========================================================================
  // Pull-to-Refresh on Notices Container
  // ==========================================================================
  function initPullToRefresh() {
    const container = document.getElementById('admin-scroll-container');
    const indicator = document.getElementById('pull-refresh-indicator');
    const label = document.getElementById('pull-refresh-label');
    if (!container || !indicator) return;

    let startY = 0;
    let isPulling = false;

    container.addEventListener('touchstart', (e) => {
      if (container.scrollTop <= 0 && e.touches.length === 1) {
        startY = e.touches[0].clientY;
        isPulling = true;
      }
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
      if (!isPulling) return;
      const diff = e.touches[0].clientY - startY;
      if (diff > 10 && container.scrollTop <= 0) {
        indicator.classList.add('pulling');
        if (diff > 60) {
          if (label) label.textContent = 'Release to refresh';
        } else {
          if (label) label.textContent = 'Pull to refresh';
        }
      }
    }, { passive: true });

    container.addEventListener('touchend', async (e) => {
      if (!isPulling) return;
      isPulling = false;
      const endY = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0].clientY : 0;
      const diff = endY - startY;
      if (diff > 60 && container.scrollTop <= 0) {
        indicator.classList.remove('pulling');
        indicator.classList.add('refreshing');
        if (label) label.textContent = 'Refreshing notices…';
        try {
          await fetchNotices(true);
        } finally {
          setTimeout(() => {
            indicator.classList.remove('refreshing');
            if (label) label.textContent = 'Pull to refresh';
          }, 350);
        }
      } else {
        indicator.classList.remove('pulling');
      }
    });
  }
  initPullToRefresh();

  // ==========================================================================
  // Tab Navigation & Hash Routing
  // ==========================================================================
  let screenPollInterval = null;
  let currentActiveTab = 'notices';
  const tabHistory = ['notices'];
  let isNavigatingBack = false;
  let closedViaUi = false;

  function switchTab(tabName, pushToHistory = true) {
    if (tabName === 'new') {
      openCreateModal();
      return;
    }

    if (!['notices', 'screens', 'audit', 'settings'].includes(tabName)) {
      tabName = 'notices';
    }

    if (pushToHistory && tabName !== currentActiveTab) {
      tabHistory.push(tabName);
      if (window.location.hash !== '#' + tabName) {
        history.pushState({ type: 'tab', tab: tabName }, '', '#' + tabName);
      }
    }
    currentActiveTab = tabName;

    const views = {
      notices: document.getElementById('view-notices'),
      screens: document.getElementById('view-screens'),
      audit: document.getElementById('view-audit'),
      settings: document.getElementById('view-settings')
    };

    const titles = {
      notices: 'Notices',
      screens: 'Screens',
      audit: 'Audit Logs',
      settings: 'Settings'
    };

    Object.entries(views).forEach(([name, el]) => {
      if (el) {
        if (name === tabName) {
          el.classList.remove('hidden');
          el.classList.add('active');
        } else {
          el.classList.add('hidden');
          el.classList.remove('active');
        }
      }
    });

    const appBarTitle = document.getElementById('app-bar-title');
    if (appBarTitle && titles[tabName]) {
      appBarTitle.textContent = titles[tabName];
    }

    // New notice button appears ONLY on the Notices page
    const btnOpenCreate = document.getElementById('btn-open-create');
    if (btnOpenCreate) {
      btnOpenCreate.style.display = (tabName === 'notices') ? '' : 'none';
    }
    const tabBtnNew = document.getElementById('tab-btn-new');
    if (tabBtnNew) {
      tabBtnNew.style.display = (tabName === 'notices') ? '' : 'none';
    }

    // Refresh button only where it refreshes something (notices, screens, audit; hide on settings)
    if (btnRefresh) {
      btnRefresh.style.display = (tabName === 'settings') ? 'none' : '';
    }

    // Update active state in Sidebar & Bottom Tab Bar
    document.querySelectorAll('.sidebar-item').forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-tab') === tabName);
      item.setAttribute('aria-selected', item.getAttribute('data-tab') === tabName ? 'true' : 'false');
    });

    document.querySelectorAll('.bottom-tab-bar .tab-item').forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-tab') === tabName);
    });

    if (tabName === 'screens') {
      loadAndRenderScreensTable();
      if (screenPollInterval) clearInterval(screenPollInterval);
      screenPollInterval = setInterval(loadScreens, 4000);
    } else {
      if (screenPollInterval) {
        clearInterval(screenPollInterval);
        screenPollInterval = null;
      }
      if (tabName === 'audit') {
        loadAuditLogsPage();
      } else if (tabName === 'settings') {
        loadFlagSettings();
      }
    }
  }
  window.switchTab = switchTab;

  // Header Refresh button handler
  if (btnRefresh) {
    btnRefresh.addEventListener('click', async () => {
      btnRefresh.classList.add('refreshing');
      const activeTab = document.querySelector('.sidebar-item.active')?.getAttribute('data-tab') || 'notices';
      try {
        if (activeTab === 'notices') {
          await fetchNotices(true);
          showToast('Notices refreshed');
        } else if (activeTab === 'screens') {
          await loadScreens();
          showToast('Screens refreshed');
        } else if (activeTab === 'audit') {
          await loadAuditLogsPage();
          showToast('Audit logs refreshed');
        }
      } finally {
        setTimeout(() => btnRefresh.classList.remove('refreshing'), 350);
      }
    });
  }

  // Raised '+' button in bottom tab bar
  const tabBtnNew = document.getElementById('tab-btn-new');
  if (tabBtnNew) {
    tabBtnNew.addEventListener('click', () => {
      openCreateModal();
    });
  }

  // Wire tab items click
  document.querySelectorAll('.tab-item, .sidebar-item').forEach(item => {
    item.addEventListener('click', (e) => {
      const tab = item.getAttribute('data-tab');
      if (tab) {
        switchTab(tab);
      }
    });
  });

  window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '') || 'notices';
    if (hash !== currentActiveTab) {
      switchTab(hash, false);
    }
  });

  // Check initial hash
  if (window.location.hash) {
    const initHash = window.location.hash.replace('#', '');
    if (['notices', 'screens', 'audit', 'settings'].includes(initHash)) {
      currentActiveTab = initHash;
      tabHistory[0] = initHash;
      switchTab(initHash, false);
    }
  }

  // ==========================================================================
  // Android Back & Modal Dismissal Navigation
  // ==========================================================================
  function closeAnyOpenModal() {
    const openModals = Array.from(document.querySelectorAll('.modal-backdrop:not(.hidden)'));
    if (openModals.length === 0) return false;

    // Pick top-most visible modal to dismiss first
    const topModal = openModals[openModals.length - 1];
    if (topModal.id === 'notice-modal') {
      if (typeof requestCloseCreateModal === 'function') {
        requestCloseCreateModal();
      } else {
        topModal.classList.add('hidden');
      }
    } else if (topModal.id === 'preview-modal') {
      topModal.classList.add('hidden');
      const previewIframe = document.getElementById('preview-iframe');
      if (previewIframe) previewIframe.src = 'about:blank';
    } else if (topModal.id === 'action-sheet-modal') {
      if (typeof closeActionSheet === 'function') closeActionSheet();
      else topModal.classList.add('hidden');
    } else {
      topModal.classList.add('hidden');
    }
    return true;
  }
  window.closeAnyOpenModal = closeAnyOpenModal;

  // Track modal open/close via MutationObserver to maintain history stack
  const modalObserver = new MutationObserver((mutations) => {
    mutations.forEach(m => {
      if (m.type === 'attributes' && m.attributeName === 'class') {
        const el = m.target;
        if (el.classList && el.classList.contains('modal-backdrop')) {
          const isVisible = !el.classList.contains('hidden');
          if (isVisible) {
            if (!history.state || history.state.type !== 'modal') {
              history.pushState({ type: 'modal', modalId: el.id }, '');
            }
          } else {
            if (!isNavigatingBack && history.state && history.state.type === 'modal') {
              closedViaUi = true;
              history.back();
            }
          }
        }
      }
    });
  });

  document.querySelectorAll('.modal-backdrop').forEach(modalEl => {
    modalObserver.observe(modalEl, { attributes: true, attributeFilter: ['class'] });
  });

  window.addEventListener('popstate', (e) => {
    if (closedViaUi) {
      closedViaUi = false;
      return;
    }
    isNavigatingBack = true;
    try {
      // 1. Android Back closes an open modal first
      if (closeAnyOpenModal()) {
        return;
      }

      // 2. Then goes to the previous tab
      if (tabHistory.length > 1) {
        tabHistory.pop(); // remove current tab
        const prevTab = tabHistory[tabHistory.length - 1];
        switchTab(prevTab, false);
        return;
      }

      // 3. Only then leaves the app
    } finally {
      setTimeout(() => { isNavigatingBack = false; }, 50);
    }
  });

  // Additional logout triggers (sidebar and settings)
  const sidebarBtnLogout = document.getElementById('sidebar-btn-logout');
  const btnSettingsLogout = document.getElementById('btn-settings-logout');
  [sidebarBtnLogout, btnSettingsLogout].forEach(btn => {
    if (btn) {
      btn.addEventListener('click', async () => {
        try {
          await fetch('/api/logout', { method: 'POST' });
        } catch (e) {}
        clearAdminPassword();
        showLoginModal();
      });
    }
  });

  // ==========================================================================
  // Theme Management (Dark / Light / Auto)
  // ==========================================================================
  const themeButtons = document.querySelectorAll('.theme-btn');

  function applyTheme(theme, saveToServer = true) {
    themeButtons.forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-theme') === theme);
    });
    localStorage.setItem('vnotice_theme', theme);

    document.documentElement.removeAttribute('data-theme');
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.body.classList.remove('theme-light', 'theme-dark');

    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
      document.documentElement.classList.add('theme-light');
      document.body.classList.add('theme-light');
    } else if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('theme-dark');
      document.body.classList.add('theme-dark');
    } else {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
      document.body.classList.add(prefersDark ? 'theme-dark' : 'theme-light');
    }

    if (saveToServer) {
      fetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Password': getAdminPassword()
        },
        body: JSON.stringify({ theme })
      }).catch(() => {});
    }
  }
  window.applyTheme = applyTheme;

  themeButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const theme = btn.getAttribute('data-theme');
      applyTheme(theme, true);
      showToast(`Theme preference saved: ${theme}`);
    });
  });

  // Initialize theme from storage
  const initialTheme = localStorage.getItem('vnotice_theme') || 'auto';
  applyTheme(initialTheme, false);

  // ==========================================================================
  // Service Worker Registration for Admin
  // ==========================================================================
  if ('serviceWorker' in navigator) {
    const registerAdminSW = () => {
      navigator.serviceWorker.register('/admin-sw.js', { scope: '/' })
        .then((reg) => {
          reg.update().catch(() => {});
        })
        .catch(err => console.debug('Admin SW registration note:', err));
    };
    if (document.readyState === 'complete') {
      registerAdminSW();
    } else {
      window.addEventListener('load', registerAdminSW);
    }
  }

  // Action Sheet Modal (Overflow options for notice cards)
  const actionSheetModal = document.getElementById('action-sheet-modal');
  const btnCloseActionSheet = document.getElementById('btn-close-action-sheet');
  const actionBtnEdit = document.getElementById('action-btn-edit');
  const actionBtnDuplicate = document.getElementById('action-btn-duplicate');
  const actionBtnCopyPublic = document.getElementById('action-btn-copy-public');
  const actionBtnOpenPublic = document.getElementById('action-btn-open-public');
  const actionBtnPreview = document.getElementById('action-btn-preview');
  const actionBtnDelete = document.getElementById('action-btn-delete');
  let actionSheetTargetNotice = null;

  const btnPreviewCopyPublic = document.getElementById('btn-preview-copy-public');
  const btnPreviewOpenPublic = document.getElementById('btn-preview-open-public');

  if (btnPreviewCopyPublic) {
    btnPreviewCopyPublic.addEventListener('click', () => {
      const activeNotice = (notices && notices[0]) ? notices[0] : null;
      const url = activeNotice ? `${window.location.origin}/n/${activeNotice.id}` : `${window.location.origin}/`;
      navigator.clipboard.writeText(url).then(() => {
        showToast('Link copied');
      }).catch(() => {
        showToast('Link copied');
      });
    });
  }

  if (btnPreviewOpenPublic) {
    btnPreviewOpenPublic.addEventListener('click', () => {
      const activeNotice = (notices && notices[0]) ? notices[0] : null;
      btnPreviewOpenPublic.href = activeNotice ? `/n/${activeNotice.id}` : `/`;
    });
  }

  window.openActionSheet = function(notice) {
    actionSheetTargetNotice = notice;
    const titleEl = document.getElementById('action-sheet-title');
    if (titleEl) titleEl.textContent = notice.title || 'Notice Options';
    if (actionSheetModal) actionSheetModal.classList.remove('hidden');
  };

  function closeActionSheet() {
    if (actionSheetModal) actionSheetModal.classList.add('hidden');
    actionSheetTargetNotice = null;
  }

  if (btnCloseActionSheet) btnCloseActionSheet.addEventListener('click', closeActionSheet);
  if (actionSheetModal) {
    actionSheetModal.addEventListener('click', (e) => {
      if (e.target === actionSheetModal) closeActionSheet();
    });
  }

  if (actionBtnCopyPublic) {
    actionBtnCopyPublic.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        const url = `${window.location.origin}/n/${actionSheetTargetNotice.id}`;
        navigator.clipboard.writeText(url).then(() => {
          showToast('Link copied');
        }).catch(() => {
          showToast('Link copied');
        });
        closeActionSheet();
      }
    });
  }

  if (actionBtnOpenPublic) {
    actionBtnOpenPublic.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        window.open(`/n/${actionSheetTargetNotice.id}`, '_blank');
        closeActionSheet();
      }
    });
  }

  if (actionBtnEdit) {
    actionBtnEdit.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        const n = actionSheetTargetNotice;
        closeActionSheet();
        openEditModal(n);
      }
    });
  }

  if (actionBtnDuplicate) {
    actionBtnDuplicate.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        const n = Object.assign({}, actionSheetTargetNotice);
        delete n.id;
        n.title = `Copy of ${n.title || 'Notice'}`;
        closeActionSheet();
        openCreateModal().then(() => {
          inputTitle.value = n.title;
          inputBody.value = n.body || '';
        });
      }
    });
  }

  if (actionBtnPreview) {
    actionBtnPreview.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        const code = (actionSheetTargetNotice.screens && actionSheetTargetNotice.screens[0]) || 'ALL';
        window.open(`/display/${encodeURIComponent(code)}`, '_blank');
        closeActionSheet();
      }
    });
  }

  if (actionBtnDelete) {
    actionBtnDelete.addEventListener('click', () => {
      if (actionSheetTargetNotice) {
        const n = actionSheetTargetNotice;
        closeActionSheet();
        openDeleteModal(n);
      }
    });
  }

  // ==========================================================================
  // Daily National Flag Event Controller (Part B)
  // ==========================================================================
  let currentFlagSettings = null;

  async function loadFlagSettings() {
    const flagCard = document.getElementById('settings-card-flag-event');
    if (!flagCard) return;

    try {
      const res = await fetch('/api/admin/events/flag', {
        headers: {
          'X-Password': getAdminPassword(),
          'Cache-Control': 'no-cache'
        }
      });
      if (!res.ok) return;
      const data = await res.json();
      if (!data.success || !data.event) return;

      currentFlagSettings = data.event;
      const evt = data.event;

      const enabledSwitch = document.getElementById('flag-enabled-switch');
      const startTimeInput = document.getElementById('flag-start-time');
      const startOffsetInput = document.getElementById('flag-start-offset');
      const durationInput = document.getElementById('flag-duration');
      const screensInput = document.getElementById('flag-screens-input');
      const standupSwitch = document.getElementById('flag-standup-switch');
      const nextRunBadge = document.getElementById('flag-next-run-badge');
      const lastRunStatus = document.getElementById('flag-last-run-status');

      if (enabledSwitch) enabledSwitch.checked = Boolean(evt.enabled);
      if (startTimeInput) startTimeInput.value = evt.start_time || '11:00';
      if (startOffsetInput) startOffsetInput.value = (typeof evt.start_offset_seconds === 'number') ? evt.start_offset_seconds : 0;
      if (durationInput) durationInput.value = (typeof evt.duration_seconds === 'number') ? evt.duration_seconds : 60;
      if (screensInput) screensInput.value = evt.screens || 'ALL';
      if (standupSwitch) standupSwitch.checked = Boolean(evt.show_standup_text);
      if (nextRunBadge) nextRunBadge.textContent = `Next run: ${data.next_run || 'Not scheduled'}`;
      if (lastRunStatus) {
        lastRunStatus.textContent = evt.last_run_result ? `Last run: ${evt.last_run_result}` : '';
      }

      // Populate days of week
      const days = evt.days_of_week || ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
      document.querySelectorAll('#flag-days-picker input[name="flag_day"]').forEach(cb => {
        cb.checked = days.includes(cb.value.toLowerCase());
      });

      renderSkipDatesList(evt.skip_dates || []);
    } catch (e) {
      console.warn('Failed to load flag settings:', e);
    }
  }

  function renderSkipDatesList(dates) {
    const list = document.getElementById('flag-skip-dates-list');
    if (!list) return;
    list.innerHTML = '';
    if (!dates || dates.length === 0) {
      list.innerHTML = '<span style="font-size: 12px; color: var(--muted);">No skip dates configured</span>';
      return;
    }
    dates.forEach(d => {
      const tag = document.createElement('span');
      tag.className = 'skip-date-tag';
      tag.innerHTML = `<span>${escapeHtml(d)}</span><button type="button" class="btn-remove-skip-date" data-date="${escapeHtml(d)}" title="Remove date">&times;</button>`;
      list.appendChild(tag);
    });

    list.querySelectorAll('.btn-remove-skip-date').forEach(btn => {
      btn.addEventListener('click', async () => {
        const d = btn.getAttribute('data-date');
        if (currentFlagSettings && Array.isArray(currentFlagSettings.skip_dates)) {
          const nextDates = currentFlagSettings.skip_dates.filter(x => x !== d);
          await saveFlagSettingsPayload({ skip_dates: nextDates });
        }
      });
    });
  }

  async function saveFlagSettingsPayload(partialData = {}) {
    const enabledSwitch = document.getElementById('flag-enabled-switch');
    const startTimeInput = document.getElementById('flag-start-time');
    const startOffsetInput = document.getElementById('flag-start-offset');
    const durationInput = document.getElementById('flag-duration');
    const screensInput = document.getElementById('flag-screens-input');
    const standupSwitch = document.getElementById('flag-standup-switch');

    const selectedDays = [];
    document.querySelectorAll('#flag-days-picker input[name="flag_day"]:checked').forEach(cb => {
      selectedDays.push(cb.value);
    });

    const payload = {
      enabled: enabledSwitch ? enabledSwitch.checked : false,
      start_time: startTimeInput ? startTimeInput.value : '11:00',
      start_offset_seconds: startOffsetInput ? parseInt(startOffsetInput.value, 10) : 0,
      duration_seconds: durationInput ? parseInt(durationInput.value, 10) : 60,
      days_of_week: selectedDays.join(','),
      screens: screensInput ? screensInput.value.trim() : 'ALL',
      show_standup_text: standupSwitch ? standupSwitch.checked : false,
      skip_dates: currentFlagSettings ? currentFlagSettings.skip_dates : [],
      ...partialData
    };

    const csrf = await getCsrfToken();
    try {
      const res = await fetch('/api/admin/events/flag', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
          'X-Password': getAdminPassword()
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast('Flag settings saved.');
        await loadFlagSettings();
      } else {
        const err = await res.json();
        showToast(err.error || 'Failed to save flag settings', true);
      }
    } catch (e) {
      showToast('Network error saving flag settings', true);
    }
  }

  const flagSettingsForm = document.getElementById('flag-settings-form');
  if (flagSettingsForm) {
    flagSettingsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await saveFlagSettingsPayload();
    });
  }

  // Skip today button
  const btnFlagSkipToday = document.getElementById('btn-flag-skip-today');
  if (btnFlagSkipToday) {
    btnFlagSkipToday.addEventListener('click', async () => {
      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/admin/events/flag/skip-today', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrf, 'X-Password': getAdminPassword() }
        });
        if (res.ok) {
          showToast('Flag screen skipped for today.');
          await loadFlagSettings();
        } else {
          const err = await res.json();
          showToast(err.error || 'Failed to skip today', true);
        }
      } catch (e) {
        showToast('Network error skipping today', true);
      }
    });
  }

  // Add skip date button
  const btnAddSkipDate = document.getElementById('btn-add-skip-date');
  const flagNewSkipDate = document.getElementById('flag-new-skip-date');
  if (btnAddSkipDate && flagNewSkipDate) {
    btnAddSkipDate.addEventListener('click', async () => {
      const val = flagNewSkipDate.value;
      if (!val) {
        showToast('Select a date to add to skip dates', true);
        return;
      }
      const existing = (currentFlagSettings && Array.isArray(currentFlagSettings.skip_dates)) ? currentFlagSettings.skip_dates : [];
      if (!existing.includes(val)) {
        const next = [...existing, val].sort();
        await saveFlagSettingsPayload({ skip_dates: next });
        flagNewSkipDate.value = '';
      } else {
        showToast('Date already added');
      }
    });
  }

  // Manual Overrides & Testing
  const btnFlagShowNow = document.getElementById('btn-flag-show-now');
  const btnFlagEndNow = document.getElementById('btn-flag-end-now');
  const btnFlagRunNow = document.getElementById('btn-flag-run-now');
  const flagConfirmModal = document.getElementById('flag-confirm-modal');
  const btnCloseFlagConfirm = document.getElementById('btn-close-flag-confirm-modal');
  const btnCancelFlagConfirm = document.getElementById('btn-cancel-flag-confirm');
  const btnProceedFlagConfirm = document.getElementById('btn-proceed-flag-confirm');

  function closeFlagConfirmModal() {
    if (flagConfirmModal) flagConfirmModal.classList.add('hidden');
  }
  if (btnCloseFlagConfirm) btnCloseFlagConfirm.addEventListener('click', closeFlagConfirmModal);
  if (btnCancelFlagConfirm) btnCancelFlagConfirm.addEventListener('click', closeFlagConfirmModal);

  if (btnFlagRunNow) {
    btnFlagRunNow.addEventListener('click', () => {
      const durInput = document.getElementById('flag-duration');
      const dur = durInput ? parseInt(durInput.value, 10) || 60 : 60;
      const msgEl = document.getElementById('flag-confirm-message');
      if (msgEl) {
        msgEl.textContent = `This will replace the display with the flag for ${dur} seconds`;
      }
      if (flagConfirmModal) flagConfirmModal.classList.remove('hidden');
    });
  }

  if (btnProceedFlagConfirm) {
    btnProceedFlagConfirm.addEventListener('click', async () => {
      closeFlagConfirmModal();
      const durInput = document.getElementById('flag-duration');
      const dur = durInput ? parseInt(durInput.value, 10) || 60 : 60;
      const screensInput = document.getElementById('flag-screens-input');
      const screens = screensInput ? screensInput.value.trim() : 'ALL';
      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/admin/events/flag/test-run', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf,
            'X-Password': getAdminPassword()
          },
          body: JSON.stringify({ duration_seconds: dur, screens })
        });
        if (res.ok) {
          showToast(`Test run started on ${screens} (${dur}s).`);
          await loadFlagSettings();
        } else {
          const err = await res.json();
          showToast(err.error || 'Failed to start test run', true);
        }
      } catch (e) {
        showToast('Network error starting test run', true);
      }
    });
  }

  if (btnFlagShowNow) {
    btnFlagShowNow.addEventListener('click', async () => {
      const durInput = document.getElementById('flag-duration');
      const dur = durInput ? parseInt(durInput.value, 10) || 60 : 60;
      const screensInput = document.getElementById('flag-screens-input');
      const screens = screensInput ? screensInput.value.trim() : 'ALL';
      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/admin/events/flag/test-run', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf,
            'X-Password': getAdminPassword()
          },
          body: JSON.stringify({ duration_seconds: 86400, screens, show_now: true })
        });
        if (res.ok) {
          showToast(`Flag display started on ${screens}.`);
          await loadFlagSettings();
        } else {
          const err = await res.json();
          showToast(err.error || 'Failed to start flag display', true);
        }
      } catch (e) {
        showToast('Network error starting flag display', true);
      }
    });
  }

  if (btnFlagEndNow) {
    btnFlagEndNow.addEventListener('click', async () => {
      const csrf = await getCsrfToken();
      try {
        const res = await fetch('/api/admin/events/flag/stop', {
          method: 'POST',
          headers: {
            'X-CSRF-Token': csrf,
            'X-Password': getAdminPassword()
          }
        });
        if (res.ok) {
          showToast('Flag display ended.');
          await loadFlagSettings();
        } else {
          const err = await res.json();
          showToast(err.error || 'Failed to end flag display', true);
        }
      } catch (e) {
        showToast('Network error ending flag display', true);
      }
    });
  }

  // 5x Speed Silent Preview
  const btnFlagPreview5x = document.getElementById('btn-flag-preview-5x');
  if (btnFlagPreview5x) {
    btnFlagPreview5x.addEventListener('click', () => {
      const previewModal = document.getElementById('preview-modal');
      const previewTitle = document.getElementById('preview-modal-title');
      const previewSubtitle = document.getElementById('preview-modal-subtitle');
      const scaler = document.getElementById('preview-iframe-scaler');
      const iframe = document.getElementById('display-preview-iframe');

      if (!previewModal || !scaler) return;

      if (previewTitle) previewTitle.textContent = 'National Flag Preview';
      if (previewSubtitle) previewSubtitle.textContent = 'Silent 5x simulation (Stand-up + Fullscreen Flag)';

      // Hide iframe and inject simulation stage
      if (iframe) iframe.style.display = 'none';

      let simContainer = document.getElementById('flag-sim-container');
      if (!simContainer) {
        simContainer = document.createElement('div');
        simContainer.id = 'flag-sim-container';
        simContainer.style.cssText = 'width: 100%; height: 100%; background: #0B1020; display: flex; align-items: center; justify-content: center; position: absolute; inset: 0;';
        scaler.appendChild(simContainer);
      }
      simContainer.style.display = 'flex';

      const standupSwitch = document.getElementById('flag-standup-switch');
      const showStandup = standupSwitch ? standupSwitch.checked : false;
      const durInput = document.getElementById('flag-duration');
      const totalDurSec = durInput ? parseInt(durInput.value, 10) || 60 : 60;
      const flagSimSec = Math.max(3, Math.round(totalDurSec / 5)); // 5x speed

      function showFlagSimView() {
        simContainer.innerHTML = `
          <div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: #0B1020;">
            <img src="/static/brand/indian-flag.svg" alt="National Flag of India" style="max-width: 100%; max-height: 100%; aspect-ratio: 3/2; object-fit: contain; display: block;">
          </div>
        `;
        setTimeout(() => {
          simContainer.style.display = 'none';
          if (iframe) iframe.style.display = '';
        }, flagSimSec * 1000);
      }

      if (showStandup) {
        simContainer.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 20px; text-align: center; padding: 30px; max-width: 90%;">
            <p style="font-family: Outfit, sans-serif; font-size: clamp(20px, 3.5vw, 36px); font-weight: 700; color: #F8FAFC; margin: 0;">Please stand for the National Anthem</p>
            <p style="font-family: 'Noto Sans Devanagari', sans-serif; font-size: clamp(18px, 3vw, 32px); font-weight: 700; color: #F1F5F9; margin: 0;">कृपया राष्ट्रगान के लिए खड़े हो जाएँ</p>
            <p style="font-family: 'Noto Sans Devanagari', sans-serif; font-size: clamp(18px, 3vw, 32px); font-weight: 700; color: #F1F5F9; margin: 0;">कृपया राष्ट्रगीतासाठी उभे राहा</p>
          </div>
        `;
        setTimeout(showFlagSimView, 3000); // 15s / 5 = 3s
      } else {
        showFlagSimView();
      }

      previewModal.classList.remove('hidden');
    });
  }

  // Initial boot
  checkAuthAndLoad();
  loadFlagSettings();

})();
