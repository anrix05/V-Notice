# Security Policy

## Supported Versions

| Version | Supported | Notes |
| :---: | :---: | :--- |
| 2.2.x | Yes | Active production release |
| < 2.2 | No | Legacy versions |

---

## Reporting a Vulnerability

If you discover a security vulnerability or potential disclosure in V Notice, please report it responsibly:

* **Contact Email:** `[SECURITY CONTACT EMAIL / PLACEHOLDER]`
* Please **do not** open a public GitHub issue for sensitive security vulnerabilities.
* Provide a detailed summary, reproducible steps, affected endpoints, and potential impact.
* We will acknowledge receipt within 48 hours and work with you on a resolution prior to public disclosure.

---

## Security Architecture Overview

* **Dual-Port Isolation:** Port `5000` (read-only kiosk display) exposes zero write APIs or token endpoints. Port `5001` (admin) is isolated and password-protected.
* **Authentication:** Password validation uses Werkzeug constant-time cryptographic hashes or HMAC constant-time comparisons.
* **Brute-Force Protection:** In-process rate limiting locks out IPs exceeding 5 failed attempts per 10 minutes.
* **Zero-Leakage 404 Responses:** All non-existent, expired, or deleted notice IDs return byte-for-byte invariant HTTP 404 responses to eliminate ID enumeration attacks.
* **CSRF Protection:** State-changing POST/PUT/DELETE administrative requests require valid session CSRF tokens.
