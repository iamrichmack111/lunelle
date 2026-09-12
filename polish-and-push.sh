#!/usr/bin/env bash
set -Eeuo pipefail

# Lunelle repo polish + demo + Docker + GitHub release
# Run this from the root of the Lunelle repository.
#
# Optional overrides:
#   REPO=iamrichmack111/lunelle VERSION=v1.5.1 ./polish-and-push.sh

REPO="${REPO:-iamrichmack111/lunelle}"
VERSION="${VERSION:-v1.5.1}"
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
IMAGE="ghcr.io/${OWNER}/${NAME}"
BASE_URL="${BASE_URL:-http://127.0.0.1:5055}"
DEMO_CONTAINER="lunelle-playwright-demo"

say()  { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is required"
command -v gh >/dev/null || die "GitHub CLI (gh) is required"
command -v docker >/dev/null || die "Docker is required"
command -v node >/dev/null || die "Node.js is required"
command -v npm >/dev/null || die "npm is required"
command -v curl >/dev/null || die "curl is required"

[ -f app.py ] || die "Run this from the Lunelle repo root (app.py not found)."
[ -f requirements.txt ] || die "requirements.txt not found."

gh auth status >/dev/null 2>&1 || die "Run: gh auth login"
gh auth setup-git >/dev/null 2>&1 || true

mkdir -p docs/screenshots docs/demo docs/brand tools/demo .github/workflows

###############################################################################
# .gitignore + Docker persistence
###############################################################################
say "Hardening ignored/private files"

touch .gitignore
for entry in \
  ".venv/" \
  "__pycache__/" \
  "*.pyc" \
  ".secret_key" \
  "period_tracker.db" \
  "node_modules/" \
  "tools/demo/node_modules/" \
  "tools/demo/.voice-venv/" \
  ".DS_Store"
do
  grep -qxF "$entry" .gitignore || echo "$entry" >> .gitignore
done

# Make the SQLite DB path Docker-friendly without breaking local runs.
python3 - <<'PY'
from pathlib import Path
p = Path("app.py")
s = p.read_text(encoding="utf-8")
old = 'DB_PATH = os.path.join(APP_DIR, "period_tracker.db")'
new = 'DB_PATH = os.environ.get("LUNELLE_DB_PATH", os.path.join(APP_DIR, "period_tracker.db"))'
if old in s:
    p.write_text(s.replace(old, new, 1), encoding="utf-8")
    print("Made DB path configurable through LUNELLE_DB_PATH.")
else:
    print("DB_PATH line already customized or not found; leaving app.py unchanged.")
PY

cat > docker-entrypoint.sh <<'EOF'
#!/usr/bin/env sh
set -eu

mkdir -p "$(dirname "${LUNELLE_DB_PATH:-/data/period_tracker.db}")"

python - <<'PY'
import app
for name in ("init_db", "migrate_db"):
    fn = getattr(app, name, None)
    if callable(fn):
        fn()
PY

exec gunicorn \
  --workers "${WEB_CONCURRENCY:-2}" \
  --bind "0.0.0.0:${PORT:-5055}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  app:app
EOF
chmod +x docker-entrypoint.sh

cat > Dockerfile <<'EOF'
# Build Python wheels in a compiler-equipped stage.
# pyswisseph 2.10.3.2 does not publish a Linux CPython 3.12 wheel,
# so pip must compile its C extension.
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip wheel setuptools \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# Small runtime image: compiler toolchain stays behind in the builder.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5055 \
    LUNELLE_DB_PATH=/data/period_tracker.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY --from=builder /wheels /wheels

RUN python -m pip install --no-cache-dir --no-index \
      --find-links=/wheels \
      -r requirements.txt \
    && rm -rf /wheels

COPY . .

RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data

VOLUME ["/data"]
EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5055/login >/dev/null || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
EOF

cat > .dockerignore <<'EOF'
.git
.github
.venv
__pycache__
*.pyc
node_modules
tools/demo/node_modules
tools/demo/.voice-venv
period_tracker.db
.secret_key
.DS_Store
docs/demo/*.webm
docs/demo/*.mp4
EOF

###############################################################################
# D2 architecture
###############################################################################
say "Creating D2 architecture diagram"

cat > docs/architecture.d2 <<'EOF'
direction: right

user: {
  label: "Lunelle User"
  shape: person
}

pwa: {
  label: "Lunelle PWA"
  icon: https://cdn.simpleicons.org/pwa/FFFFFF
  style.fill: "#17121b"
  style.stroke: "#d77aa8"
}

flask: {
  label: "Flask App"
  icon: https://cdn.simpleicons.org/flask/FFFFFF
  style.fill: "#17121b"
  style.stroke: "#b58ad9"
}

sqlite: {
  label: "Private SQLite"
  icon: https://cdn.simpleicons.org/sqlite/FFFFFF
  shape: cylinder
  style.fill: "#17121b"
  style.stroke: "#d77aa8"
}

ephemeris: {
  label: "Swiss Ephemeris"
  style.fill: "#17121b"
  style.stroke: "#8f7fe8"
}

sky: {
  label: "Sky Sync\nSun · Moon · Stars"
  style.fill: "#17121b"
  style.stroke: "#7289da"
}

docker: {
  label: "Docker / GHCR"
  icon: https://cdn.simpleicons.org/docker/FFFFFF
  style.fill: "#17121b"
  style.stroke: "#4da6ff"
}

actions: {
  label: "GitHub Actions"
  icon: https://cdn.simpleicons.org/githubactions/FFFFFF
  style.fill: "#17121b"
  style.stroke: "#8f7fe8"
}

playwright: {
  label: "Playwright Demo"
  icon: https://cdn.simpleicons.org/playwright/FFFFFF
  style.fill: "#17121b"
  style.stroke: "#57c78b"
}

user -> pwa: "tracks + journals"
pwa -> flask: "HTTPS / app routes"
flask -> sqlite: "private cycle data"
flask -> ephemeris: "planet + moon math"
flask -> sky: "sunrise / sunset / sky"
actions -> docker: "build + publish"
playwright -> pwa: "screenshots + video"
docker -> flask: "runs"
EOF

# Render through Docker so users do not need a local D2 install.
if docker run --rm \
    -v "$PWD:/workspace" \
    -w /workspace \
    terrastruct/d2:latest \
    docs/architecture.d2 docs/architecture.svg >/dev/null 2>&1; then
  ok "D2 architecture rendered to docs/architecture.svg"
else
  warn "D2 render failed. Source is still at docs/architecture.d2."
fi

###############################################################################
# Playwright demo
###############################################################################
say "Creating Playwright demo recorder"

cat > tools/demo/package.json <<'EOF'
{
  "name": "lunelle-demo-tools",
  "private": true,
  "scripts": {
    "demo": "node capture-demo.mjs"
  },
  "devDependencies": {
    "playwright": "^1.55.0"
  }
}
EOF

cat > tools/demo/capture-demo.mjs <<'EOF'
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL || "http://127.0.0.1:5055";
const root = path.resolve(process.cwd(), "../..");
const screenshots = path.join(root, "docs", "screenshots");
const demoDir = path.join(root, "docs", "demo");

fs.mkdirSync(screenshots, { recursive: true });
fs.mkdirSync(demoDir, { recursive: true });

const browser = await chromium.launch({ headless: true });

async function settle(page, ms = 900) {
  await page.waitForLoadState("domcontentloaded").catch(() => {});
  await page.waitForTimeout(ms);
}

async function screenshot(page, name, url) {
  const response = await page.goto(`${BASE}${url}`, { waitUntil: "domcontentloaded" }).catch(() => null);
  await settle(page);

  if (!response || response.status() >= 400) {
    console.log(`SKIP ${name}: ${url}`);
    return false;
  }

  if (url !== "/login" && page.url().includes("/login")) {
    console.log(`SKIP ${name}: redirected to login`);
    return false;
  }

  await page.screenshot({
    path: path.join(screenshots, `${name}.png`),
    fullPage: true
  });
  console.log(`SHOT ${name}`);
  return true;
}

async function addSceneCard(page, eyebrow, title, subtitle) {
  await page.evaluate(({ eyebrow, title, subtitle }) => {
    document.getElementById("__lunelle_demo_card")?.remove();

    const card = document.createElement("div");
    card.id = "__lunelle_demo_card";
    card.innerHTML = `
      <div style="
        font: 700 12px/1.2 system-ui,sans-serif;
        letter-spacing:.18em;
        text-transform:uppercase;
        color:#f0a7c7;
        margin-bottom:10px">${eyebrow}</div>
      <div style="
        font: 700 34px/1.05 Georgia,serif;
        color:#fff;
        letter-spacing:-.02em;
        margin-bottom:8px">${title}</div>
      <div style="
        max-width:540px;
        font: 500 16px/1.45 system-ui,sans-serif;
        color:rgba(255,255,255,.74)">${subtitle}</div>
    `;

    Object.assign(card.style, {
      position: "fixed",
      zIndex: "2147483647",
      left: "42px",
      bottom: "38px",
      width: "min(610px, calc(100vw - 84px))",
      padding: "24px 28px",
      borderRadius: "24px",
      background: "linear-gradient(135deg, rgba(24,14,28,.92), rgba(55,25,48,.82))",
      border: "1px solid rgba(255,155,203,.28)",
      boxShadow: "0 28px 90px rgba(0,0,0,.48), inset 0 1px 0 rgba(255,255,255,.08)",
      backdropFilter: "blur(22px)",
      WebkitBackdropFilter: "blur(22px)",
      transform: "translateY(18px)",
      opacity: "0",
      transition: "transform .55s cubic-bezier(.2,.8,.2,1), opacity .45s ease"
    });

    document.body.appendChild(card);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      card.style.transform = "translateY(0)";
      card.style.opacity = "1";
    }));
  }, { eyebrow, title, subtitle });
}

async function removeSceneCard(page) {
  await page.evaluate(() => {
    const card = document.getElementById("__lunelle_demo_card");
    if (!card) return;
    card.style.opacity = "0";
    card.style.transform = "translateY(12px)";
    setTimeout(() => card.remove(), 400);
  }).catch(() => {});
}

async function animatePage(page) {
  await page.mouse.move(1520, 260);
  await page.waitForTimeout(250);
  await page.mouse.move(980, 520, { steps: 16 });
  await page.waitForTimeout(350);

  const interactive = page.locator(
    "button:visible, a:visible, .card:visible, .panel:visible, [data-magnetic]:visible"
  );
  const count = Math.min(await interactive.count(), 4);
  for (let i = 0; i < count; i++) {
    const el = interactive.nth(i);
    await el.hover().catch(() => {});
    await page.waitForTimeout(220);
  }

  await page.mouse.wheel(0, 380).catch(() => {});
  await page.waitForTimeout(400);
  await page.mouse.wheel(0, -380).catch(() => {});
}

async function scene(page, name, route, eyebrow, title, subtitle, hold = 3200) {
  const response = await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" }).catch(() => null);
  await settle(page, 1100);

  if (!response || response.status() >= 400 || (route !== "/login" && page.url().includes("/login"))) {
    console.log(`SKIP ${name}: ${route}`);
    return false;
  }

  await page.screenshot({
    path: path.join(screenshots, `${name}.png`),
    fullPage: true
  });

  await addSceneCard(page, eyebrow, title, subtitle);
  await animatePage(page);
  await page.waitForTimeout(hold);
  await removeSceneCard(page);
  await page.waitForTimeout(450);
  console.log(`SCENE ${name}`);
  return true;
}

// First context: create a disposable account without putting signup mechanics in the product video.
const authContext = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  colorScheme: "dark"
});
const authPage = await authContext.newPage();
authPage.setDefaultTimeout(8000);

await screenshot(authPage, "01-login", "/login");

const username = `lunelle_demo_${Date.now()}`;
const password = "VelvetMotion!2026";

await authPage.goto(`${BASE}/signup`, { waitUntil: "domcontentloaded" });
await settle(authPage);

const usernameInput = authPage.locator('input[name="username"]');
const passwordInput = authPage.locator('input[name="password"]');
if (await usernameInput.count()) await usernameInput.fill(username);
if (await passwordInput.count()) await passwordInput.fill(password);

const confirm = authPage.locator(
  'input[name="confirm_password"], input[name="password_confirm"], input[name="confirm"]'
);
if (await confirm.count()) await confirm.first().fill(password);

const signupSubmit = authPage.locator('button[type="submit"], input[type="submit"]').first();
if (await signupSubmit.count()) {
  await signupSubmit.click();
  await settle(authPage);
}

if (authPage.url().includes("/login")) {
  const loginUser = authPage.locator('input[name="username"]');
  const loginPass = authPage.locator('input[name="password"]');
  if (await loginUser.count()) await loginUser.fill(username);
  if (await loginPass.count()) await loginPass.fill(password);
  await authPage.locator('button[type="submit"], input[type="submit"]').first().click();
  await settle(authPage);
}

const state = await authContext.storageState();
await authContext.close();

// Second context: clean 1080p product video.
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  colorScheme: "dark",
  storageState: state,
  recordVideo: {
    dir: demoDir,
    size: { width: 1920, height: 1080 }
  }
});

const page = await context.newPage();
page.setDefaultTimeout(8000);

// A deliberate product-story sequence.
await scene(
  page, "02-home", "/dashboard",
  "LUNELLE", "Your rhythm, at a glance.",
  "A private cycle and wellness home designed around clarity, motion, and your personal patterns.",
  3600
);

await scene(
  page, "03-calendar", "/calendar",
  "CYCLE CALENDAR", "See the month in context.",
  "Tracked periods, estimates, cycle phases, check-ins, and lunar context live in one view.",
  3300
);

await scene(
  page, "04-checkin", "/log",
  "DAILY CHECK-IN", "Capture how today actually feels.",
  "Log mood, pain, energy, sleep, stress, flow, symptoms, and personal notes.",
  3300
);

await scene(
  page, "05-journal", "/journal",
  "PRIVATE JOURNAL", "Keep the story behind the numbers.",
  "Reflections stay connected to your cycle without turning the experience into a spreadsheet.",
  3200
);

await scene(
  page, "06-sky", "/sky",
  "SKY SYNC", "Connect your rhythm to the real sky.",
  "Explore sunrise, sunset, moon phases, local darkness, stars, and bright planets.",
  3900
);

await scene(
  page, "07-insights", "/insights",
  "PERSONAL INSIGHTS", "Notice patterns over time.",
  "Compare cycles and surface descriptive trends without pretending to diagnose.",
  3500
);

await scene(
  page, "09-history", "/history",
  "PRIVATE HISTORY", "Your data stays yours.",
  "Review past cycles and check-ins, export your information, and keep control of your history.",
  3300
);

const video = page.video();
await context.close();
await browser.close();

if (video) {
  const oldPath = await video.path();
  const finalPath = path.join(demoDir, "lunelle-demo.webm");
  fs.copyFileSync(oldPath, finalPath);
  if (oldPath !== finalPath) fs.rmSync(oldPath, { force: true });
  console.log(`VIDEO ${finalPath}`);
}
EOF

pushd tools/demo >/dev/null
npm install --no-fund --no-audit
npx playwright install chromium
popd >/dev/null

###############################################################################
# Jinja template preflight
###############################################################################
say "Checking Jinja templates for duplicate blocks"

python3 - <<'PY'
from pathlib import Path
import re, sys

failed = False
for p in sorted(Path("templates").glob("*.html")):
    text = p.read_text(encoding="utf-8")
    names = re.findall(r"{%\s*block\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    dupes = sorted({name for name in names if names.count(name) > 1})
    if dupes:
        failed = True
        print(f"ERROR {p}: duplicate Jinja blocks: {', '.join(dupes)}")

if failed:
    print("\nFix duplicate Jinja blocks before Docker/Playwright.")
    sys.exit(1)

print("Jinja block preflight: PASS")
PY

###############################################################################
# Build demo Docker image + capture media
###############################################################################
say "Building local Docker image for the demo"

LOCAL_IMAGE="lunelle-demo:${VERSION#v}"
docker build -t "$LOCAL_IMAGE" .

cleanup() {
  docker rm -f "$DEMO_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker run -d \
  --name "$DEMO_CONTAINER" \
  -p 5055:5055 \
  -e SECRET_KEY="$(openssl rand -hex 32 2>/dev/null || echo demo-only-secret-key)" \
  "$LOCAL_IMAGE" >/dev/null

say "Waiting for Lunelle to become ready"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/login" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" -eq 1 ] || {
  docker logs "$DEMO_CONTAINER" || true
  die "Lunelle did not become ready on $BASE_URL"
}
ok "Lunelle is running"

say "Recording screenshots and Playwright video"
(
  cd tools/demo
  BASE_URL="$BASE_URL" npm run demo
)
ok "Playwright media captured"

cleanup
trap - EXIT

# Create a high-quality MP4 and narrated product demo.
if command -v ffmpeg >/dev/null 2>&1 && [ -f docs/demo/lunelle-demo.webm ]; then
  ffmpeg -y -loglevel error \
    -i docs/demo/lunelle-demo.webm \
    -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
    -movflags +faststart \
    docs/demo/lunelle-demo.mp4
  ok "Created HD docs/demo/lunelle-demo.mp4"

  cat > tools/demo/narration.txt <<'EOF'
Meet Lunelle, a private cycle and wellness companion built around your rhythm and your sky.

Track your cycle from a calm, animated home view. Explore predicted dates on the calendar, and capture mood, pain, energy, sleep, stress, flow, and symptoms with a daily check-in.

Keep the story behind the numbers in your private journal.

Sky Sync connects your experience to sunrise, sunset, moon phases, local darkness, bright stars, and planets.

Lunelle can compare cycles and surface descriptive patterns without pretending to diagnose.

Your history stays under your control, with local data storage, export tools, themes, PWA support, and Docker deployment.
EOF

  DEMO_VOICE="${DEMO_VOICE:-en-US-AvaMultilingualNeural}"
  DEMO_VOICE_RATE="${DEMO_VOICE_RATE:--4%}"

  say "Generating neural narration with ${DEMO_VOICE}"

  python3 -m venv tools/demo/.voice-venv
  tools/demo/.voice-venv/bin/python -m pip install -q --upgrade pip
  tools/demo/.voice-venv/bin/python -m pip install -q edge-tts

  if DEMO_VOICE="$DEMO_VOICE" DEMO_VOICE_RATE="$DEMO_VOICE_RATE" \
      tools/demo/.voice-venv/bin/python - <<'PY'
import asyncio, os
from pathlib import Path
import edge_tts

text = Path("tools/demo/narration.txt").read_text(encoding="utf-8").strip()
voice = os.environ.get("DEMO_VOICE", "en-US-AvaMultilingualNeural")
rate = os.environ.get("DEMO_VOICE_RATE", "-4%")

async def main():
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    await communicate.save("docs/demo/lunelle-narration.mp3")

asyncio.run(main())
PY
  then
    # Keep the full product video. If narration ends earlier, pad the remaining audio with silence.
    VIDEO_DURATION="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 docs/demo/lunelle-demo.mp4)"

    ffmpeg -y -loglevel error \
      -i docs/demo/lunelle-demo.mp4 \
      -i docs/demo/lunelle-narration.mp3 \
      -filter_complex "[1:a]loudnorm=I=-16:LRA=7:TP=-1.5,apad[a]" \
      -map 0:v:0 \
      -map "[a]" \
      -c:v copy \
      -c:a aac -b:a 192k \
      -t "$VIDEO_DURATION" \
      -movflags +faststart \
      docs/demo/lunelle-demo-narrated.mp4

    ok "Created narrated demo: docs/demo/lunelle-demo-narrated.mp4"
  else
    warn "Neural narration failed; keeping the silent HD demo."
    cp docs/demo/lunelle-demo.mp4 docs/demo/lunelle-demo-narrated.mp4
  fi
else
  warn "ffmpeg was not found; keeping the Playwright WebM recording."
fi

###############################################################################
# GitHub Actions
###############################################################################
say "Adding CI and GHCR workflows"

cat > .github/workflows/ci.yml <<'EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Compile Python
        run: python -m compileall -q .

      - name: Import application
        env:
          SECRET_KEY: ci-only-secret
          LUNELLE_DB_PATH: /tmp/lunelle-ci.db
        run: |
          python - <<'PY'
          import app
          for name in ("init_db", "migrate_db"):
              fn = getattr(app, name, None)
              if callable(fn):
                  fn()
          print("Lunelle import/database check passed")
          PY

      - name: Build Docker image
        run: docker build -t lunelle:ci .
EOF

cat > .github/workflows/docker.yml <<'EOF'
name: Publish Docker

on:
  push:
    branches: [main]
    tags:
      - "v*"

permissions:
  contents: read
  packages: write

jobs:
  docker:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=ref,event=tag
            type=sha

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64,linux/arm64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
EOF

###############################################################################
# README
###############################################################################
say "Generating polished README"

cat > README.md <<EOF
<div align="center">

# 🌙 Lunelle

### Private cycle intelligence with a living connection to your sky.

<p>
  <a href="docs/demo/lunelle-demo-narrated.mp4"><img alt="Watch Demo" src="https://img.shields.io/badge/▶_WATCH_DEMO-d45c95?style=for-the-badge"></a>
  <a href="https://github.com/${REPO}/wiki"><img alt="Wiki" src="https://img.shields.io/badge/📚_WIKI-7d64c8?style=for-the-badge"></a>
  <a href="https://github.com/${REPO}/pkgs/container/${NAME}"><img alt="Docker" src="https://img.shields.io/badge/🐳_DOCKER-2496ED?style=for-the-badge"></a>
  <a href="https://github.com/${REPO}/releases"><img alt="Releases" src="https://img.shields.io/badge/✨_RELEASES-a74c78?style=for-the-badge"></a>
</p>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-App-111111?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Private_Data-003B57?logo=sqlite&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Demo-2EAD33?logo=playwright&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-GHCR-2496ED?logo=docker&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa&logoColor=white)
![Visibility](https://img.shields.io/badge/Repository-Private-191919?logo=github&logoColor=white)

</div>

---

## ✦ What is Lunelle?

**Lunelle** is a private cycle and wellness companion that combines menstrual tracking, journaling, personal patterns, moon phases, planetary ephemeris data, sunrise/sunset timing, and an animated sky-aware interface.

It is designed as a personal wellness tool — not a diagnostic system and not a contraceptive method.

## 🎥 Product demo

[▶ **Watch the narrated Playwright demo**](docs/demo/lunelle-demo-narrated.mp4)

> If MP4 conversion was unavailable on the capture machine, use the [WebM recording](docs/demo/lunelle-demo.webm).

## 🖼️ Screens

<table>
<tr>
<td width="50%"><img src="docs/screenshots/01-login.png" alt="Lunelle login"></td>
<td width="50%"><img src="docs/screenshots/02-home.png" alt="Lunelle home"></td>
</tr>
<tr>
<td><img src="docs/screenshots/03-calendar.png" alt="Cycle calendar"></td>
<td><img src="docs/screenshots/06-sky.png" alt="Sky Sync"></td>
</tr>
<tr>
<td><img src="docs/screenshots/07-insights.png" alt="Insights"></td>
<td><img src="docs/screenshots/05-journal.png" alt="Private journal"></td>
</tr>
</table>

## ✨ Highlights

- 🩸 Period start/end tracking and personalized cycle estimates
- 🌙 Moon phase, lunar events and cycle × cosmos views
- 🌅 Sunrise, sunset, twilight and local Sky Sync
- ⭐ Stars/planet visibility and stargazing information
- 📓 Private journal and memory history
- 💗 Mood, pain, energy, sleep, stress and symptom check-ins
- 📊 Cycle Compare and descriptive pattern discovery
- 💊 Medication/supplement tracking
- 👜 Care-product inventory
- 🔐 Username/password authentication + optional PIN privacy layer
- 📦 CSV/JSON data export
- 📱 Installable PWA
- 🎨 Multiple dark feminine themes
- 🐳 Docker + GHCR delivery
- 🎭 Automated Playwright screenshots/video

## 🧭 Architecture

<img src="docs/architecture.svg" alt="Lunelle D2 architecture diagram" width="100%">

D2 source: [\`docs/architecture.d2\`](docs/architecture.d2)

## 🚀 Run locally

\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./start.sh
\`\`\`

Open:

\`\`\`text
http://127.0.0.1:5055
\`\`\`

## 🐳 Docker

Build:

\`\`\`bash
docker build -t lunelle .
\`\`\`

Run with persistent private data:

\`\`\`bash
docker run --rm \\
  -p 5055:5055 \\
  -v lunelle-data:/data \\
  -e SECRET_KEY="\$(openssl rand -hex 32)" \\
  lunelle
\`\`\`

Or pull this repository's private GHCR image:

\`\`\`bash
echo "\$(gh auth token)" | docker login ghcr.io -u ${OWNER} --password-stdin
docker pull ${IMAGE}:latest
docker run --rm -p 5055:5055 -v lunelle-data:/data ${IMAGE}:latest
\`\`\`

## 🧪 Capture the demo again

\`\`\`bash
cd tools/demo
npm install
npx playwright install chromium
BASE_URL=http://127.0.0.1:5055 npm run demo
\`\`\`

The recorder creates a disposable account against a fresh Docker database so **real user health data is never needed for repository screenshots or video**.

## 🔏 Privacy

Lunelle stores sensitive cycle data locally in SQLite by default. Database files and local secret keys are excluded from Git.

Before any public/commercial deployment, add production-grade HTTPS, secure secret storage, formal privacy documentation, account lifecycle controls, backups/encryption, and a security review.

## 📚 Documentation

- [Wiki](https://github.com/${REPO}/wiki)
- [Architecture](https://github.com/${REPO}/wiki/Architecture)
- [Docker](https://github.com/${REPO}/wiki/Docker)
- [Privacy](https://github.com/${REPO}/wiki/Privacy-and-Security)
- [Roadmap](https://github.com/${REPO}/wiki/Roadmap)

## ⚕️ Health disclaimer

Predictions and pattern summaries are estimates for personal awareness only. Lunelle does not diagnose health conditions and should not be used as contraception or as a replacement for medical advice.

---

<div align="center">

**Lunelle ${VERSION}**

Private by design · animated by the sky

</div>
EOF

###############################################################################
# GitHub repo settings, topics, labels
###############################################################################
say "Configuring GitHub repository"

gh repo edit "$REPO" \
  --description "Private cycle + wellness companion with Moon phases, Sky Sync, personal insights, Flask, PWA, Playwright and Docker." \
  --enable-issues \
  --enable-wiki

topics=(
  lunelle
  period-tracker
  menstrual-health
  wellness
  moon-phases
  astrology
  ephemeris
  sunrise-sunset
  sky-sync
  flask
  python
  sqlite
  pwa
  playwright
  docker
)

for topic in "${topics[@]}"; do
  gh repo edit "$REPO" --add-topic "$topic" >/dev/null
done
ok "Topics added"

declare -a labels=(
  "feature|Feature request|a855f7"
  "bug|Something is broken|d73a4a"
  "design|UI / motion / visual work|d876e3"
  "privacy|Privacy-related work|6f42c1"
  "security|Security hardening|b60205"
  "cycle-tracking|Cycle tracking|e85d9e"
  "sky-sync|Moon / sun / sky features|5d78d8"
  "astrology|Ephemeris and astrology|7658cf"
  "playwright|Browser automation and demos|39a85a"
  "docker|Containerization|2496ed"
  "pwa|Progressive web app|6b43bd"
  "documentation|Docs / README / Wiki|4e9ad6"
)

for item in "${labels[@]}"; do
  IFS='|' read -r label description color <<< "$item"

  if gh api "repos/$REPO/labels/$label" >/dev/null 2>&1; then
    gh api \
      --method PATCH \
      "repos/$REPO/labels/$label" \
      -f new_name="$label" \
      -f description="$description" \
      -f color="$color" >/dev/null
  else
    gh api \
      --method POST \
      "repos/$REPO/labels" \
      -f name="$label" \
      -f description="$description" \
      -f color="$color" >/dev/null
  fi
done
ok "Labels added via GitHub API"

###############################################################################
# Wiki
###############################################################################
say "Creating GitHub Wiki"

WIKI_DIR="$(mktemp -d)"
WIKI_URL="https://github.com/${REPO}.wiki.git"

if git clone "$WIKI_URL" "$WIKI_DIR" >/dev/null 2>&1; then
  :
else
  rm -rf "$WIKI_DIR"
  WIKI_DIR="$(mktemp -d)"
  git -C "$WIKI_DIR" init -b master >/dev/null
  git -C "$WIKI_DIR" remote add origin "$WIKI_URL"
fi

cat > "$WIKI_DIR/Home.md" <<EOF
# 🌙 Lunelle Wiki

Welcome to the private engineering and product wiki for **Lunelle**.

## Start here

- [[Features]]
- [[Architecture]]
- [[Docker]]
- [[Privacy-and-Security]]
- [[Playwright-Demo]]
- [[Roadmap]]

**Current release:** ${VERSION}
EOF

cat > "$WIKI_DIR/Features.md" <<'EOF'
# Features

## Cycle
- Period start/end history
- Cycle and period-length estimates
- Cycle calendar
- Same-day previous-cycle comparison
- Descriptive pattern discovery

## Wellness
- Mood, pain, energy, sleep and stress
- Symptoms and custom symptoms
- Medication/supplement reminders
- Care-product inventory
- Private journal

## Celestial
- Moon phase and illumination
- New/full moon timing
- Swiss Ephemeris planetary positions
- Sunrise/sunset/twilight
- Sky Sync
- Star and bright-planet visibility

## Product
- Username-only auth
- Optional PIN privacy layer
- PWA installation
- Theme system
- CSV / JSON export
- Docker deployment
EOF

cat > "$WIKI_DIR/Architecture.md" <<'EOF'
# Architecture

Lunelle is intentionally compact:

1. The browser/PWA renders the product UI.
2. Flask owns authentication, app routes and server-side logic.
3. SQLite stores private user and cycle data.
4. Swiss Ephemeris powers celestial calculations.
5. Sky Sync combines local browser location with astronomical timing.
6. Docker packages the runtime.
7. GitHub Actions validates and publishes GHCR images.
8. Playwright produces reproducible visual demos.

See the repository's `docs/architecture.d2` and rendered `docs/architecture.svg`.
EOF

cat > "$WIKI_DIR/Docker.md" <<EOF
# Docker

## Pull the private image

\`\`\`bash
echo "\$(gh auth token)" | docker login ghcr.io -u ${OWNER} --password-stdin
docker pull ${IMAGE}:latest
\`\`\`

## Run

\`\`\`bash
docker run --rm \\
  -p 5055:5055 \\
  -v lunelle-data:/data \\
  -e SECRET_KEY="\$(openssl rand -hex 32)" \\
  ${IMAGE}:latest
\`\`\`

The named volume keeps the SQLite database outside the replaceable container.
EOF

cat > "$WIKI_DIR/Privacy-and-Security.md" <<'EOF'
# Privacy and Security

Lunelle handles sensitive wellness information.

## Current local/private model

- SQLite data remains outside Git.
- `.secret_key` remains outside Git.
- Demo media is captured with a disposable test account.
- Docker supports a persistent `/data` volume.
- PIN/privacy features are additional UI protections, not a substitute for OS-level security.

## Before a commercial public deployment

- Enforce HTTPS.
- Use managed secret storage.
- Add CSRF protection everywhere appropriate.
- Add rate limiting and account lockout protections.
- Add secure password recovery.
- Encrypt backups.
- Define account/data deletion behavior.
- Publish a privacy policy and terms.
- Perform a security/privacy review.
EOF

cat > "$WIKI_DIR/Playwright-Demo.md" <<'EOF'
# Playwright Demo

The repository contains `tools/demo/capture-demo.mjs`.

The recorder:

1. Starts from a clean Docker database.
2. Captures the login screen.
3. Creates a disposable demo user.
4. Captures key authenticated screens.
5. Records the flow as WebM.
6. Optionally converts the recording to MP4 when `ffmpeg` is installed.

No real health profile is required.
EOF

cat > "$WIKI_DIR/Roadmap.md" <<'EOF'
# Roadmap

## Product
- Richer cycle timeline
- More accessible motion controls
- Better local notifications
- Deeper trend comparisons
- Encrypted backup / restore
- Optional partner sharing with granular permissions

## Engineering
- Dedicated automated test suite
- PostgreSQL option for hosted deployments
- Background notification worker
- Dependency/security scanning
- Release signing
- Full production deployment templates
EOF

git -C "$WIKI_DIR" add .
if ! git -C "$WIKI_DIR" diff --cached --quiet; then
  git -C "$WIKI_DIR" -c user.name="${GIT_AUTHOR_NAME:-Richmack}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-noreply@users.noreply.github.com}" \
    commit -m "Build Lunelle wiki for ${VERSION}" >/dev/null
fi

if git -C "$WIKI_DIR" push -u origin HEAD:master >/dev/null 2>&1; then
  ok "Wiki pushed"
else
  warn "Wiki push failed. Repo polish will continue; GitHub may require the Wiki to be initialized once in the web UI."
fi
rm -rf "$WIKI_DIR"

###############################################################################
# Commit / push / Docker publish / release
###############################################################################
say "Committing repository polish"

git add \
  .gitignore .dockerignore Dockerfile docker-entrypoint.sh \
  app.py README.md docs tools/demo .github/workflows

if git diff --cached --quiet; then
  warn "No new repository changes to commit."
else
  git commit -m "Polish Lunelle ${VERSION}: demo, Docker, README, D2, docs"
fi

git branch -M main
git push -u origin main

say "Publishing private GHCR image"

gh auth token | docker login ghcr.io -u "$OWNER" --password-stdin >/dev/null

docker tag "$LOCAL_IMAGE" "${IMAGE}:${VERSION}"
docker tag "$LOCAL_IMAGE" "${IMAGE}:latest"
docker push "${IMAGE}:${VERSION}"
docker push "${IMAGE}:latest"
ok "Docker image pushed: ${IMAGE}:${VERSION}"

say "Creating Git tag and GitHub release"

if git rev-parse "$VERSION" >/dev/null 2>&1; then
  warn "Tag ${VERSION} already exists locally; not recreating it."
else
  git tag -a "$VERSION" -m "Lunelle ${VERSION}"
fi

git push origin "$VERSION" 2>/dev/null || true

DEMO_ASSET=""
if [ -f docs/demo/lunelle-demo-narrated.mp4 ]; then
  DEMO_ASSET="docs/demo/lunelle-demo-narrated.mp4"
elif [ -f docs/demo/lunelle-demo.mp4 ]; then
  DEMO_ASSET="docs/demo/lunelle-demo.mp4"
elif [ -f docs/demo/lunelle-demo.webm ]; then
  DEMO_ASSET="docs/demo/lunelle-demo.webm"
fi

if gh release view "$VERSION" --repo "$REPO" >/dev/null 2>&1; then
  warn "Release ${VERSION} already exists; updating release assets is skipped."
else
  release_args=(
    "$VERSION"
    --repo "$REPO"
    --title "Lunelle ${VERSION} — Velvet Motion"
    --notes "Playwright demo + screenshots, D2 architecture, private GHCR Docker image, CI/CD, Wiki, labels/topics, and polished documentation."
  )
  if [ -n "$DEMO_ASSET" ]; then
    release_args+=("$DEMO_ASSET")
  fi
  gh release create "${release_args[@]}"
fi

say "Final repository status"
gh repo view "$REPO" \
  --json nameWithOwner,visibility,url,description \
  --jq '"\(.nameWithOwner) | \(.visibility)\n\(.url)\n\(.description)"'

printf '\n\033[1;32mDONE.\033[0m\n'
printf 'README: https://github.com/%s#readme\n' "$REPO"
printf 'Wiki:   https://github.com/%s/wiki\n' "$REPO"
printf 'Image:  %s:%s\n' "$IMAGE" "$VERSION"
printf 'Demo:   docs/demo/lunelle-demo-narrated.mp4\n'
