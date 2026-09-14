# ARVEN Diagnostics

- Generated: 2026-09-06T17:43:54.836574
- Platform: Windows-11-10.0.26200-SP0
- Python: 3.13.15

## Disk
- **workspace**: AVAILABLE free=250429698048 used=229994602496
- **temp**: AVAILABLE free=250429698048 used=229994602496

## Memory / CPU
- Memory: 63.9% used (6125887488 free)
- CPU: 10.4% across 16 cores

## Network
- Online: True

## Core Module Health
- core.kv: AVAILABLE
- core.output: AVAILABLE
- core.selftest: AVAILABLE
- core.health: AVAILABLE
- core.safety: AVAILABLE
- core.confirmation: AVAILABLE
- core.security: AVAILABLE
- core.recovery: AVAILABLE

## Providers
- android: NOT_CONFIGURED (android/ADB not installed — install Android platform-tools and add adb to PATH)
- browser: NOT_CONFIGURED (playwright not installed; install with: pip install playwright && playwright install)
- camera: AVAILABLE (capture backends available)
- finance: AVAILABLE (local finance ledger available (offline-capable))
- home: AVAILABLE (home routines (0) + simulated device control (0 device(s)) are available locally; no external smart-home integration is configured (honest))
- image_gen: NOT_CONFIGURED (IMAGE_GENERATION_PROVIDER is empty)
- iot: AVAILABLE (device registry operational (2 device(s)); no external smart-home bridge configured — live sensors/actuators over the network are NOT_CONFIGURED)
- location: AVAILABLE (manual location store operational (1 place(s)); no geocoding/live-GPS backend configured — geocode is honest NOT_CONFIGURED/OFFLINE)
- messaging: NOT_CONFIGURED (no email/SMTP or messaging hub backend configured — draft and template capabilities still work locally, sends are refused)
- navigation: AVAILABLE (offline deterministic route planning available (haversine + speed table); live traffic / turn-by-turn map backend NOT_CONFIGURED)
- shopping: AVAILABLE (local shopping store available (offline-capable))
- travel: AVAILABLE (trip planning (local itinerary builder) available; no external booking provider configured — travel_book is NOT_CONFIGURED)
- vehicle: AVAILABLE (vehicle store operational (1 vehicle(s)); live OBD/telemetry connection is NOT_CONFIGURED — all values are user-entered)
- video_gen: NOT_CONFIGURED (VIDEO_GENERATION_PROVIDER is empty)
- vision: NOT_CONFIGURED (No ML vision provider configured (VISION_PROVIDER is empty or backend not installed). Set VISION_PROVIDER and install the corresponding package.)
- world_actions: AVAILABLE (action/rule store operational (0 action(s)); real-world executive backend NOT_CONFIGURED — only simulated local targets can execute)

## System Check
- Overall: healthy

## Selftest
- total=9 passed=9 failed=0 status=AVAILABLE