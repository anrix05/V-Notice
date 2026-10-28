# Contributing to V Notice

Thank you for contributing to V Notice. To keep the project stable, accessible, and fast on Raspberry Pi hardware, please follow these guidelines.

---

## 1. Development Workflow & Branching

* Create a descriptive feature branch from `main`:
  ```bash
  git checkout -b feature/your-feature-name
  ```
* Follow [Conventional Commits](https://www.conventionalcommits.org/):
  * `feat: ...` for new user-facing capabilities
  * `fix: ...` for bug fixes
  * `docs: ...` for documentation additions or changes
  * `refactor: ...` for restructuring without behavior changes
  * `test: ...` for test suite additions

---

## 2. Coding Principles & Style

1. **Lightweight & Framework-Free:**
   * Keep frontend code strictly Vanilla JavaScript (ES6+), standard CSS3 custom properties (`static/css/tokens.css`), and semantic HTML5.
   * Avoid introducing heavy frontend dependencies (no React, Vue, Angular, or CSS utility frameworks).
2. **Offline-First Resilience:**
   * Every core display feature must function without internet connectivity.
   * Do not make client-side network assumptions; utilize `localStorage` and Service Worker caching.
3. **Dual-Port Security Boundary:**
   * Never expose administrative or mutation endpoints on Port `5000` (Display).
   * All write APIs must belong strictly to Port `5001` (Admin) with session authentication and CSRF checks.
4. **Python Backend Standards:**
   * Follow PEP 8 guidelines.
   * Use type annotations where practical.
   * Avoid blocking calls inside WSGI request threads.

---

## 3. Running the Test Suite

1. **Unit & Integration Tests:**
   ```bash
   python -m pytest -q -k "not playwright"
   ```
2. **Full End-to-End Suite (Including Playwright):**
   * Start the dual servers first or run the integrated test runner:
   ```bash
   python app.py
   python -m pytest -q --timeout=60
   ```
3. **Shell Script Syntax Validation:**
   ```bash
   for f in deploy/raspberry-pi/*.sh deploy/tunnel/*.sh scripts/linux/*.sh; do bash -n "$f"; done
   ```
