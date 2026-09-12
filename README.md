# Lunelle v1.5 — Velvet Motion


## v1.5 visual rebuild

- Dark-pop / luxury Y2K visual direction
- Animated cycle orbit on Home
- Glossy bento statistics and richer mood controls
- Pointer-reactive card lighting
- Magnetic buttons and small tap spark effects
- Animated ambient color fields and navigation states
- More dramatic login/signup visuals
- PWA cache bumped to v15 so the new design replaces older assets

Lunelle now uses **username + password only** for local accounts. The app opens directly to login when signed out and directly to Home when signed in. The public marketing shell, forced onboarding flow, giant Universe dashboard, command palette, and floating action UI were removed in favor of a simpler app-style navigation shell.

Existing databases remain compatible. The legacy database column used by older versions is retained internally so upgrades do not require destructive migration, but it is no longer part of signup, login, reset, or the user interface.

# Lunelle v1.3 — Atelier

## Visual redesign

- Replaced the neon sci-fi dashboard with a restrained dark editorial interface
- New cycle dial and time scrubber with softer motion and less visual noise
- New luxury typography, spacing, form controls, navigation and buttons
- Rebuilt landing page, login and signup screens in the same visual system
- Existing themes now use muted rose, plum, cherry, violet and sage palettes instead of neon colors
- Removed persistent starfield/cursor-glow visuals from the main presentation
- Updated PWA cache and icon for the new design

All existing cycle, wellness, journal, sky, astrology, comparison, discovery and Wrapped features remain available.

# Lunelle v1.2 — Universe

Lunelle now opens into an interactive personal universe instead of a static dashboard.

## New in v1.2

- **Lunelle Universe** home screen with an animated orbital canvas
- Time scrubber from two weeks back to three weeks ahead
- Cycle phase, cycle day, date and lunar state animate together as time moves
- Unified personal timeline for period events, daily check-ins and journal entries
- **Cycle Compare** for the same cycle day across previous tracked cycles
- **Pattern Discovery** with descriptive observations from the user's own logs
- **Lunelle Wrapped** animated monthly story with mood, energy, sleep, symptoms and cycle rhythm
- **Memory Constellation** turns private journal entries into a living star map
- Landing page and navigation updated around Universe, Compare, Discoveries and Wrapped
- PWA shell bumped to v12 so older cached UI is replaced

Pattern Discovery and Cycle Compare are descriptive summaries only. They do not diagnose conditions or explain causation.

---

# Lunelle v1.1 — Sky Sync

Lunelle now links the cycle/wellness experience to the real sky using Swiss Ephemeris plus browser geolocation.

## New in v1.1

- New **Sky Tonight** experience with a live animated sky dome
- Location-aware sunrise, sunset, astronomical dawn/dusk, moonrise and moonset
- Exact upcoming New Moon, First Quarter, Full Moon and Last Quarter calculations
- Visible bright-star map and star list calculated for the local horizon
- Stargazing score based on astronomical darkness + moonlight (not weather/clouds)
- **Sky Sync** mode that shifts Lunelle's ambient glow through dawn, sunrise, day, golden hour, twilight and starlight
- Optional device-only remembered sky location, rounded before storage; exact coordinates are never saved in the Lunelle database
- Live lunar-event countdowns
- Sunrise Intention, Sunset Reset, New Moon Page and Starlight Reflection journal starters
- New Sky entry in desktop navigation, mobile dock and Cmd/Ctrl+K command palette
- PWA cache bumped to v11 so the new visuals replace older cached assets

## Sky privacy

Lunelle does not write sky coordinates to SQLite. When the user taps **Use my location**, coordinates are used for the sky calculation. If **Keep Sky Sync on this device** is enabled, only rounded coordinates are stored in that browser's local storage so Sky Sync can refresh automatically.

---

# Lunelle v1.0 — Nightglass

A premium dark cycle + wellness companion built with Flask, SQLite, vanilla JavaScript, and Swiss Ephemeris.

## What changed in v1.0

- Completely redesigned premium dark interface
- Animated canvas starfield and orbital light system
- Reactive card spotlights, magnetic buttons, ripples, parallax, scroll reveals, animated counters, and smoother page transitions
- New commercial landing page with product mockup, privacy story, feature bento, and conversion sections
- Three-step onboarding for display name, focus, and theme
- Rebuilt login and signup experience
- Command palette with `Ctrl/Cmd + K`
- Quick-add sheet and mobile bottom navigation
- Six dark atmosphere themes retained and polished
- Pricing page structured for Free and Plus ($4.99/mo launch concept)
- Technical privacy page
- Downloadable JSON backup in addition to CSV export
- Updated PWA shell and cache version
- Auth startup self-test updated to cover signup → onboarding → logout → login
- Personal database and `.secret_key` are not included in release ZIPs

## Commerce status

The product UI is subscription-ready, but **payment checkout is not wired into this local build**. Connect Stripe (or another processor), add server-side entitlement checks, and complete legal/privacy review before charging users.

## Run

```bash
./start.sh
```

Then open `http://127.0.0.1:5055`.

## Upgrade without losing your account

Unzip the release over your existing `richmack-period-tracker` folder. Your account and health data live in `period_tracker.db`, which is intentionally excluded from release ZIPs.

---

# Lunelle v0.7

A redesigned private cycle, wellness, moon and astrology tracker.

## Login reliability changes

- `./start.sh` now runs an isolated signup/logout/login self-test before launching.
- Login uses username + password only.
- Local password reset is available at `/reset-password` when accessed from the computer running Lunelle.
- The service worker now clears old Lunelle caches and uses network-first static assets, preventing stale CSS/JS after upgrades.
- Existing `period_tracker.db` data is preserved when unzipping over the same project folder.


## Login fix in v0.6.1

- Log in with your **username + password**
- Clearer errors distinguish "account not found" from "wrong password"
- Signup signs you in immediately
- Session secret is saved locally in `.secret_key`, so restarting the app no longer invalidates login sessions
- Normal `./start.sh` launch no longer uses Flask's debug reloader

### Important when upgrading

User accounts live in `period_tracker.db`.

If you unzip this into the **same existing app folder**, your database is left alone and your account remains available.

If you deleted the old app folder or installed into a brand-new folder, the old account database is not present. In that case, use **Sign up** once to create a new local account.


# Lunelle by Richmack OS

A feminine, private, local-first cycle + wellness tracker built with Flask, SQLite, and Swiss Ephemeris.

## Features

- Signup/login with hashed passwords
- Period start/end tracking
- Estimated next period and current period end
- Estimated cycle phase and cycle day
- Monthly visual cycle calendar
- Recorded vs predicted period days
- Estimated fertile window + ovulation marker for cycle awareness only
- Moon phase on every calendar day
- Detailed daily check-ins: mood, cramps/pain, energy, stress, sleep, hydration, flow, libido, discharge, exercise, temperature, medication/supplements, symptoms and notes
- Editable same-day / historical check-ins
- Check-in streaks
- Glow Insights: cycle variability, symptoms, moods, sleep, stress, energy and phase summaries
- Private Glow Journal
- In-app reminder preferences and optional browser notification permission
- CSV export including periods, detailed logs and journal entries
- Data wipe controls
- Astrology Lab powered by Swiss Ephemeris
- Planetary positions, zodiac placements, retrogrades, moon phase/illumination
- Birth profile + natal planetary snapshot
- Cycle-start moon-phase history
- Six saved themes: Blush Bloom, Lavender Dream, Rose Gold, Cherry Kiss, Soft Sage, Midnight Moon
- Responsive mobile-friendly feminine UI

## Important health note

Cycle, ovulation, fertile-window and period predictions are estimates only. They can shift for many reasons. Do not use this app as contraception, to diagnose a medical condition, or as a substitute for professional medical advice. Astrology features are for reflection/entertainment and do not drive medical predictions.

## Run

```bash
./start.sh
```

Then open `http://127.0.0.1:5055`.

## Production notes

Before putting this on the public internet, set a strong `SECRET_KEY`, disable Flask debug mode, use HTTPS + gunicorn, add CSRF protection and a production-grade account recovery flow, consider database encryption, and review applicable privacy requirements for health data.


## v0.6 daily companion features

- Optional 4–8 digit in-app PIN lock
- Custom symptoms in daily check-ins
- Medication / supplement reminder list with daily taken status
- Sleep and hydration goals on the dashboard
- Printable doctor-share summary (print or save as PDF from the browser)
- 30-check-in energy / pain / stress trend chart
- Installable PWA support with manifest, icon, and service worker
- Privacy-conscious service worker: authenticated pages are not cached offline

Medication, fertility, ovulation, cycle-phase, astrology, and wellness features are for tracking/awareness only and are not medical advice or contraception.

## v0.8 — Dark Universe redesign

Lunelle now defaults to a dark, animated interface with six dark themes:
Noir Rose, Velvet Plum, Black Cherry, Cosmic Grape, Emerald Night, and Ultraviolet.

New in v0.8:

- Animated aurora + star field
- Moon/orbit animations and interactive hover tilt
- Privacy Blur button for quickly obscuring sensitive dashboard details
- Daily Glow Score (a non-medical reflection from sleep, hydration, energy, and stress)
- One-tap Mood Pulse
- Personalized non-medical daily ritual card
- Seven-day cycle + moon forecast
- Care Cabinet inventory with low-stock warnings
- Monthly Recap for mood, symptoms, sleep, energy, pain, and cycle averages
- Refreshed login, signup, dashboard, landing page, navigation, and mobile layouts
- PWA cache bumped to v8 so older styles are removed on activation

Glow Score and cycle forecasts are informational reflections/estimates only and are not medical diagnosis, treatment, or contraception.
