# Changelog

All notable changes to the "V Notice" Smart Digital Notice Board system are documented in this file.

## [2.1.0] - 2026-10-11

### Added
- **Department-Level Permissions & Role Boundaries (Phase 6)**:
  - Added `users` table supporting `super_admin` and `dept_admin` roles.
  - Per-user credential authentication with hashed passwords (`generate_password_hash` / `check_password_hash`).
  - Shared `ADMIN_PASSWORD` retained for `super_admin`.
  - Permission boundaries: `dept_admin` restricted to creating, editing, and deleting notices targeted only to their assigned departments.
  - College-wide (`ALL`) broadcast restriction for `dept_admin` unless explicitly granted `can_target_all`.
  - Screen management restricted to `super_admin` only.
  - Automatic `created_by` attribution from authenticated username.
- **Department-Wise Display Screens**:
  - `departments` table seeded with `CMPN`, `INFT`, `EXTC`, `EXCS`, `BIOM`, and `ALL` (college-wide audience).
  - Multi-target notice broadcast using `notice_screens` join table.
  - Admin Screen Management API: `GET /api/screens` (public and admin views), `POST /api/screens`, `PUT /api/screens/<code>`, and `DELETE /api/screens/<code>` (with deactivation fallback protection).
- **Dedicated Display Routing**:
  - `/display/<code>` endpoint with case-insensitive 301 canonical redirects.
  - Branded 404 "Screen Not Found" page listing active department display links.
  - Root `/display` defaults to `ALL` (college-wide board).
  - Legacy `/display?screen=<id>` 301 permanent redirects to `/display/<CODE>`.
- **Display UI & PWA**:
  - Department header pill displaying code and full name (e.g., `EXCS | Electronics & Computer Science`) with custom accent color styling.
  - "College-wide" subtle badge on stage and rail for college-wide notices.
  - Contextual empty state message: `No announcements for <CODE> right now`.
  - Department-isolated Service Worker caching and offline fallback.
  - Per-screen heartbeat telemetry via `POST /api/heartbeat`.
- **Real-Time Sync Isolation**:
  - Per-screen ETag generation and SSE event stream filtering (`/api/events?screen=<CODE>`).
  - Mutations to department-specific notices only wake screens displaying that department, while `ALL` notices broadcast to all connected displays.
- **Admin UI Enhancements**:
  - Accessible multi-select chip picker for target screens with one-handed mobile support and keyboard navigation.
  - Compact notice card target badges with `+N` overflow badge.
  - "Screens" management panel with online/offline heartbeat status indicator, activate/deactivate toggle, and one-click "Copy display link" button.
  - "Preview on display" action directly opening the selected screen.
  - Comprehensive rename of legacy "Default Screen" to "All Departments (college-wide)".
- **Raspberry Pi Deployment**:
  - Updated `install_rpi.sh` to accept configurable `DEPARTMENT_CODE` environment variable.
  - Updated Chromium kiosk launcher (`systemd/kiosk.sh`) with dedicated department URL `https://v-notice.onrender.com/display/EXCS`.

## [2.0.0] - 2026-09-29
- Initial 2.0 release with dual-mode architecture, high-density kiosk layout, SSE real-time sync, PWA offline resilience, and administrative portal.
