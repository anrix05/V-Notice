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
  function getAdminPassword() {
    return sessionStorage.getItem('vnotice_admin_pass') || '';
  }

  function setAdminPassword(pass) {
    sessionStorage.setItem('vnotice_admin_pass', pass);
  }

  function clearAdminPassword() {
    sessionStorage.removeItem('vnotice_admin_pass');
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

      if (!res.ok) throw new Error('Incorrect password');

      setAdminPassword(pass);
      hideLoginModal();
      fetchNotices();
    } catch (err) {
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
  // Fetch Notices & Compute Status
  // ==========================================================================
  async function fetchNotices() {
    const pass = getAdminPassword();
    const res = await fetch(`/api/notices?_t=${Date.now()}`, {
      cache: 'no-store',
      headers: {
        'X-Password': pass,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
      }
    });

    if (res.status === 401) {
      const err = new Error('Unauthorized');
      err.status = 401;
      throw err;
    }

    if (!res.ok) throw new Error(`Server returned ${res.status}`);

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
      noticesContainer.innerHTML = `
        <div class="notices-empty-view">
          <p>No notices yet</p>
          <button type="button" class="btn btn-primary" id="btn-empty-create">New notice</button>
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
      const status = notice.status || 'live';
      const prio = (notice.priority || 'normal').toLowerCase();
      const ntype = notice.type || 'text';

      card.className = `notice-item-card ${status === 'expired' ? 'is-expired' : ''}`;

      // Left tile: image thumbnail or clean SVG icon
      let tileHtml = '';
      if (notice.media && (ntype === 'image' || ntype === 'video')) {
        const mediaUrl = `/media/${encodeURIComponent(notice.media)}`;
        if (ntype === 'image') {
          tileHtml = `<div class="notice-media-tile"><img src="${mediaUrl}" alt="" class="notice-thumb-img" loading="lazy"></div>`;
        } else {
          tileHtml = `
            <div class="notice-media-tile">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </div>`;
        }
      } else {
        tileHtml = `
          <div class="notice-media-tile">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <line x1="4" y1="7" x2="20" y2="7"></line>
              <line x1="4" y1="12" x2="20" y2="12"></line>
              <line x1="4" y1="17" x2="12" y2="17"></line>
            </svg>
          </div>`;
      }

      // Status indicator dot
      let dotClass = 'dot-live';
      if (status === 'scheduled') dotClass = 'dot-scheduled';
      else if (status === 'expired') dotClass = 'dot-expired';

      // Priority label
      let prioHtml = prio.charAt(0).toUpperCase() + prio.slice(1);
      if (prio === 'urgent') {
        prioHtml = `<span class="meta-urgent-text">Urgent</span>`;
      }

      // Type in sentence case
      const typeLabel = ntype.charAt(0).toUpperCase() + ntype.slice(1);

      // Duration: only relevant for text & image
      const durationPart = ntype !== 'video' ? ` · ${notice.duration || 10} s` : '';

      // Formatted schedule range: d MMM, h:mm am – d MMM, h:mm am
      const formatDate = (ms) => {
        if (!ms) return '';
        const d = new Date(ms);
        return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' }) + ', ' +
               d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
      };
      const scheduleRange = `${formatDate(notice.start)} – ${formatDate(notice.end)}`;

      card.innerHTML = `
        ${tileHtml}
        <div class="notice-content">
          <h3 class="notice-title">${escapeHtml(notice.title || 'Untitled notice')}</h3>
          ${notice.body ? `<p class="notice-body-snippet">${escapeHtml(notice.body)}</p>` : ''}
          <div class="notice-meta-line">
            <span class="status-dot ${dotClass}"></span>
            <span>${status.charAt(0).toUpperCase() + status.slice(1)}</span>
            <span>·</span>
            <span>${prioHtml}</span>
            <span>·</span>
            <span>${typeLabel}</span>
            ${durationPart}
          </div>
          <div class="notice-schedule-line">${scheduleRange}</div>
        </div>
        <div class="notice-actions">
          <button type="button" class="btn-icon btn-edit-row" data-id="${notice.id}" aria-label="Edit notice" title="Edit notice">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
          </button>
          <button type="button" class="btn-icon btn-delete-row" data-id="${notice.id}" aria-label="Delete notice" title="Delete notice">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      `;

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
    fetchNotices();
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

  function handleFileSelected() {
    if (mediaFileInput.files && mediaFileInput.files[0]) {
      const file = mediaFileInput.files[0];
      fileName.textContent = file.name;
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      fileSize.textContent = `${sizeMb} MB`;
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
        await fetchNotices();
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

  // Background auto-sync in admin every 5 seconds so updates appear without manual refresh
  setInterval(() => {
    if (localStorage.getItem('vnotice_admin_pass') && !document.hidden) {
      fetchNotices().catch(() => {});
    }
  }, 5000);

})();
