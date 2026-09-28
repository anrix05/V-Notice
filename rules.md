# V Notice Development Rules

## 1. Project Identity

Project Name: V Notice

Project Type: Smart Digital Notice Board

Platform: Raspberry Pi + Web Application

Primary Display: 7-inch 800×480 display

Backend: Flask

Frontend: HTML, CSS, JavaScript

Storage: JSON + local media files

Display Port: 5000

Admin Port: 5001


## 2. Core Project Goal

V Notice is a campus digital notice board.

Faculty or authorized staff publish notices from a phone or laptop.

The Raspberry Pi automatically displays active notices.

The system must prioritize:

1. Reliability
2. Simple administration
3. Fast notice updates
4. Readability from a distance
5. Raspberry Pi compatibility
6. Simple deployment
7. Basic security


## 3. Architecture Rules

Use a Flask backend.

Maintain two separate interfaces:

- Display application on port 5000
- Admin application on port 5001

The display interface must be read-only.

The admin interface handles notice creation, deletion, scheduling, and media uploads.

Do not expose admin write operations through the display interface.

Keep the architecture simple enough to run reliably on Raspberry Pi hardware.


## 4. Storage Rules

Use:

```text
notices.json
media/
```

Do not introduce a database unless explicitly requested.

Each notice must contain:

```json
{
  "id": "unique-id",
  "title": "Notice title",
  "body": "Notice details",
  "priority": "normal",
  "type": "text",
  "media": "",
  "duration": 10,
  "start": 0,
  "end": 0
}
```

Valid priorities:

```text
normal
urgent
info
```

Valid content types:

```text
text
image
video
```

Notice IDs must be unique.

Deleting a notice must also remove its associated media file.

## 5. Notice Scheduling Rules

A notice is active only when:

```text
start <= current_time <= end
```

Future notices must not appear on the display.

Expired notices must not appear on the display.

The admin panel must show:

```text
Live
Scheduled
Expired
```

The display API must return active notices only.

Do not require manual deletion when a notice expires.

## 6. Priority Rules

Urgent notices have the highest priority.

When one or more urgent notices are active:

* Display only urgent notices.
* Hide normal notices.
* Hide info notices.
* Show a clear red urgent indicator.
* Continue rotating urgent notices according to their duration.

When no urgent notice is active, display normal and info notices.

## 7. Display Rules

The display must work at:

```text
800 × 480
```

The interface must remain readable from several metres away.

The display must include:

* Current date
* Current time
* Main notice stage
* Up Next section
* Progress indicators
* Scrolling headline ticker

The display must automatically rotate notices.

Do not require user interaction.

Do not show unnecessary controls on the public display.

## 8. Notice Duration Rules

Text notices use their configured duration.

Image notices use their configured duration.

Video notices play until the video ends.

After a video ends, move to the next notice.

If only one video notice is active, loop the video.

Never wait for the configured text duration after a video has already ended.

## 9. Offline Rules

The display must cache the last successfully loaded notices.

If the server becomes temporarily unreachable:

* Do not clear the display.
* Continue showing cached notices.
* Continue rotating cached notices.
* Continue showing the clock.
* Continue showing the date.

When the server becomes available again, refresh the notice data automatically.

Do not display technical errors to students.

## 10. API Rules

Use REST-style endpoints.

Required endpoints:

```text
GET    /api/notices
POST   /api/notices
DELETE /api/notices/<id>
GET    /media/<file>
```

Display requests must not require authentication.

Admin API requests must require authentication.

The admin password must be supplied using:

```text
X-Password
```

Never expose the admin password in frontend JavaScript.

Never store the admin password directly in source code.

## 11. Authentication Rules

Read the admin password from:

```text
ADMIN_PASSWORD
```

environment variable.

Reject requests with:

* Missing password
* Incorrect password

Return an appropriate HTTP error status.

Never log passwords.

Never include passwords in API responses.

Do not store passwords in localStorage.

## 12. Upload Rules

Only allow:

```text
.jpg
.jpeg
.png
.webp
.gif
.mp4
.webm
```

Maximum upload size:

```text
200 MB
```

Validate file extensions.

Validate MIME types where possible.

Generate safe filenames.

Do not trust the original filename.

Never allow uploaded filenames to contain path traversal sequences.

Store uploads only inside:

```text
media/
```

Never execute uploaded files.

## 13. Frontend Rules

Use plain HTML, CSS, and JavaScript unless another framework is explicitly requested.

Avoid unnecessary frontend dependencies.

Keep JavaScript modular.

Avoid duplicated logic.

Use semantic HTML.

Use accessible labels for admin controls.

Use clear validation messages.

Avoid browser features that have poor Raspberry Pi Chromium support.

## 14. Mobile Admin Rules

The admin panel must work on small screens.

Minimum target width:

```text
360px
```

Forms must remain usable without horizontal scrolling.

Buttons must have comfortable touch targets.

File upload controls must work on mobile browsers.

Notice creation should require minimal steps.

Important actions must be visually clear.

## 15. Visual Design Rules

Use the V Notice color palette:

```text
Background: #0F172A
Panel:      #162238
Blue:       #2F6BFF
Urgent Red: #E5484D
Text:       #F8FAFC
```

Maintain strong contrast.

Do not use excessive gradients.

Do not use excessive animations.

Keep the public display professional and suitable for a college campus.

The display should prioritize information over decoration.

## 16. Typography Rules

Public display headlines must be large.

Target headline size:

```text
60px
```

at 800px display width.

Body text must remain readable from several metres away.

Avoid excessively thin fonts.

Do not use decorative fonts for important notices.

Admin typography should prioritize readability and mobile usability.

## 17. Animation Rules

Use short fade transitions when notices change.

Use a slow ticker animation.

Respect:

```text
prefers-reduced-motion
```

When reduced motion is enabled:

* Reduce transitions.
* Reduce unnecessary animation.
* Keep notice changes functional.

Do not use distracting animations.

## 18. Polling Rules

The display should request:

```text
/api/notices
```

every 10 seconds.

Do not reload the entire webpage during polling.

Update only the notice data required by the display.

Avoid unnecessary API requests.

Prevent multiple polling timers from running simultaneously.

## 19. Time Rules

Store notice timestamps consistently.

Use Unix timestamps in milliseconds.

Example:

```text
1790000000000
```

The frontend must correctly convert timestamps into local display time.

The system must handle scheduled start and expiry without requiring a page refresh.

## 20. Error Handling Rules

The application must fail gracefully.

For API failures:

* Keep cached notices.
* Do not crash the display.
* Retry automatically.

For invalid admin input:

* Show a clear error.
* Preserve valid entered information where practical.

For failed uploads:

* Do not create an incomplete notice.
* Remove partially uploaded files.

For missing media:

* Do not crash the display.
* Show an appropriate fallback.

## 21. Raspberry Pi Rules

The application must remain lightweight.

Avoid unnecessary CPU and RAM usage.

Optimize videos for Raspberry Pi.

Recommended video format:

```text
MP4
H.264
720p
```

Avoid unnecessary background services.

The system must support Chromium kiosk mode:

```bash
chromium-browser --kiosk http://localhost:5000
```

The application must automatically start after Raspberry Pi boot.

## 22. Deployment Rules

The Flask backend must run as a systemd service.

Chromium must start automatically.

Screen blanking must be disabled.

The system must recover after reboot.

The application must store all required data locally.

Do not require internet access for basic operation.

## 23. Security Rules

Never expose admin write endpoints without authentication.

Do not place secrets inside Git repositories.

Use environment variables for secrets.

Add:

```text
.env
```

to `.gitignore`.

Do not expose port 5001 outside the intended campus network.

Validate all user input.

Sanitize filenames.

Limit upload sizes.

Do not expose internal server errors to public users.

## 24. Code Quality Rules

Use meaningful variable names.

Use small, focused functions.

Avoid duplicated code.

Add comments for non-obvious logic.

Keep frontend and backend responsibilities separate.

Do not introduce complex architecture without a clear requirement.

Do not add dependencies without a reason.

Prefer maintainable code over clever code.

## 25. File Structure

Use a structure similar to:

```text
v-notice/
│
├── app.py
├── notices.json
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── rules.md
│
├── media/
│
├── templates/
│   ├── display.html
│   └── admin.html
│
├── static/
│   ├── css/
│   │   ├── display.css
│   │   └── admin.css
│   │
│   └── js/
│       ├── display.js
│       └── admin.js
│
└── systemd/
    └── v-notice.service
```

## 26. Git Rules

Do not commit:

```text
.env
media/
__pycache__/
*.pyc
```

Commit source code and configuration templates.

Use meaningful commit messages.

Example:

```text
feat: add notice scheduling
fix: handle offline display cache
feat: add video notice support
fix: validate media uploads
```

## 27. Testing Rules

Every major feature must be tested before deployment.

Required tests:

* Create text notice
* Create image notice
* Create video notice
* Schedule notice
* Expire notice
* Delete notice
* Urgent notice
* Wrong admin password
* Invalid upload
* Large upload
* Missing media
* Network failure
* Raspberry Pi reboot
* Mobile admin interface
* Video playback
* Single video looping
* Notice rotation

## 28. Performance Rules

The display must remain responsive during notice rotation.

Avoid unnecessary DOM updates.

Do not repeatedly reload media files.

Cache previously loaded data where appropriate.

Avoid memory leaks caused by:

* Timers
* Event listeners
* Video elements
* Object URLs

Clean up resources when changing notices.

## 29. Development Priority

When implementing new features, follow this order:

1. Reliability
2. Security
3. Core functionality
4. Raspberry Pi performance
5. Accessibility
6. UI consistency
7. Visual enhancements

## 30. Scope Rules

Version 1 must remain focused on the core notice-board system.

Do not add the following unless explicitly requested:

* Multiple screen management
* Cloud hosting
* Complex user roles
* Analytics
* Weather integration
* ERP integration
* Push notifications
* QR-code systems
* GPIO emergency systems

These belong to future versions.

## 31. Definition of Done

A feature is complete only when:

* It works on desktop.
* It works on a mobile screen where relevant.
* It works on Raspberry Pi where relevant.
* Errors are handled.
* Security requirements are satisfied.
* Existing features continue working.
* The feature matches the V Notice UI.
* The feature does not introduce unnecessary dependencies.
* The feature has been tested with realistic notice data.

## 32. Final Development Principle

Keep V Notice simple, reliable, fast, and easy to operate.

Every feature should serve one of three purposes:

1. Help staff publish notices.
2. Help students read notices.
3. Keep the system reliable on Raspberry Pi.
