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
  const inputStart = document.getElementById('notice-start');
  const inputEnd = document.getElementById('notice-end');
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
        <button type="button" class="btn-icon btn-delete-row" data-id="${notice.id}" aria-label="Delete notice" title="Delete notice">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      `;

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
  // Create Notice Dialog
  // ==========================================================================
  function toLocalDatetimeString(date) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function openCreateModal() {
    resetCreateForm();
    noticeModal.classList.remove('hidden');
    inputTitle.focus();
  }

  function closeCreateModal() {
    noticeModal.classList.add('hidden');
    clearValidationErrors();
  }

  function resetCreateForm() {
    createNoticeForm.reset();
    clearValidationErrors();
    clearSelectedFile();

    const now = new Date();
    const nextWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);

    inputStart.value = toLocalDatetimeString(now);
    inputEnd.value = toLocalDatetimeString(nextWeek);
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

  // Quick-set buttons
  document.querySelectorAll('.btn-quick-set').forEach(btn => {
    btn.addEventListener('click', () => {
      const hours = parseInt(btn.getAttribute('data-hours'), 10);
      const days = parseInt(btn.getAttribute('data-days'), 10);
      const startDate = inputStart.value ? new Date(inputStart.value) : new Date();

      let targetTime = startDate.getTime();
      if (hours) targetTime += hours * 3600 * 1000;
      else if (days) targetTime += days * 86400 * 1000;

      inputEnd.value = toLocalDatetimeString(new Date(targetTime));
    });
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
    }
  }

  btnRemoveFile.addEventListener('click', (e) => {
    e.stopPropagation();
    clearSelectedFile();
  });

  function clearSelectedFile() {
    mediaFileInput.value = '';
    dropPrompt.classList.remove('hidden');
    dropSelected.classList.add('hidden');
  }

  btnOpenCreate.addEventListener('click', openCreateModal);
  btnCloseModal.addEventListener('click', closeCreateModal);
  btnCancelCreate.addEventListener('click', closeCreateModal);

  // Form submission with progress tracking
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
    if ((type === 'image' || type === 'video') && (!mediaFileInput.files || !mediaFileInput.files[0])) {
      errMedia.textContent = `Choose a ${type} file to upload.`;
      errMedia.classList.remove('hidden');
      return;
    }

    const startMs = inputStart.value ? new Date(inputStart.value).getTime() : Date.now();
    const endMs = inputEnd.value ? new Date(inputEnd.value).getTime() : Date.now() + 7 * 86400000;

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
    xhr.open('POST', '/api/notices', true);
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
        showToast('Published');
        await fetchNotices();
      } else {
        let msg = 'Failed to publish notice.';
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
      createNoticeError.textContent = 'Network error while publishing.';
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
