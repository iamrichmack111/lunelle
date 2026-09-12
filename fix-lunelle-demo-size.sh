#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${REPO:-iamrichmack111/lunelle}"
VERSION="${VERSION:-v1.5.1}"
DEMO_DIR="docs/demo"
RELEASE_DIR=".release-assets"
PREVIEW="${DEMO_DIR}/lunelle-demo-preview.mp4"
HD_ASSET="${RELEASE_DIR}/lunelle-demo-hd-narrated.mp4"
TARGET_MIB="${TARGET_MIB:-18}"

say()  { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is required"
command -v gh >/dev/null || die "gh is required"
command -v ffmpeg >/dev/null || die "ffmpeg is required"
command -v ffprobe >/dev/null || die "ffprobe is required"
command -v python3 >/dev/null || die "python3 is required"

[ -d .git ] || die "Run this from the Lunelle Git repository root."
mkdir -p "$DEMO_DIR" "$RELEASE_DIR"

say "Finding the best existing demo source"

SOURCE=""
for candidate in \
  "$DEMO_DIR/lunelle-demo-narrated.mp4" \
  "$DEMO_DIR/lunelle-demo.mp4" \
  "$DEMO_DIR/lunelle-demo.webm"
do
  if [ -s "$candidate" ]; then
    SOURCE="$candidate"
    break
  fi
done

[ -n "$SOURCE" ] || die "No existing Lunelle demo found in docs/demo."

printf 'Source: %s\n' "$SOURCE"
du -h "$SOURCE"

say "Preserving an HD release copy"

if [[ "$SOURCE" == *.mp4 ]]; then
  cp -f "$SOURCE" "$HD_ASSET"
else
  ffmpeg -y -loglevel error \
    -i "$SOURCE" \
    -vf "scale=1920:-2:force_original_aspect_ratio=decrease,fps=30" \
    -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
    -c:a aac -b:a 192k \
    -movflags +faststart \
    "$HD_ASSET"
fi

ok "HD release asset saved outside Git: $HD_ASSET"
du -h "$HD_ASSET"

say "Creating a lightweight GitHub-safe preview"

DURATION="$(
  ffprobe -v error \
    -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 \
    "$SOURCE"
)"

VIDEO_KBPS="$(
  python3 - "$DURATION" "$TARGET_MIB" <<'PY'
import sys
duration = max(float(sys.argv[1]), 1.0)
target_mib = float(sys.argv[2])
target_bits = target_mib * 1024 * 1024 * 8
audio_bps = 96_000
video_bps = max(350_000, (target_bits / duration) - audio_bps)
# Leave safety margin for MP4 overhead and bitrate variance.
video_bps *= 0.88
print(max(350, min(4200, int(video_bps / 1000))))
PY
)"

printf 'Duration: %.1fs | target: %s MiB | video bitrate: %s kbps\n' \
  "$DURATION" "$TARGET_MIB" "$VIDEO_KBPS"

PASSLOG="$(mktemp -u /tmp/lunelle-x264-pass-XXXXXX)"

ffmpeg -y -loglevel error \
  -i "$SOURCE" \
  -vf "scale=1280:-2:force_original_aspect_ratio=decrease,fps=30" \
  -c:v libx264 -preset slow \
  -b:v "${VIDEO_KBPS}k" \
  -maxrate "$((VIDEO_KBPS * 12 / 10))k" \
  -bufsize "$((VIDEO_KBPS * 2))k" \
  -pass 1 -passlogfile "$PASSLOG" \
  -an -f mp4 /dev/null

ffmpeg -y -loglevel error \
  -i "$SOURCE" \
  -vf "scale=1280:-2:force_original_aspect_ratio=decrease,fps=30" \
  -c:v libx264 -preset slow \
  -b:v "${VIDEO_KBPS}k" \
  -maxrate "$((VIDEO_KBPS * 12 / 10))k" \
  -bufsize "$((VIDEO_KBPS * 2))k" \
  -pass 2 -passlogfile "$PASSLOG" \
  -pix_fmt yuv420p \
  -c:a aac -b:a 96k \
  -movflags +faststart \
  "$PREVIEW"

rm -f "${PASSLOG}"* 2>/dev/null || true

PREVIEW_BYTES="$(stat -c%s "$PREVIEW")"
PREVIEW_MIB="$(
  python3 - "$PREVIEW_BYTES" <<'PY'
import sys
print(f"{int(sys.argv[1]) / 1024 / 1024:.2f}")
PY
)"
printf 'Preview size: %s MiB\n' "$PREVIEW_MIB"

if [ "$PREVIEW_BYTES" -ge $((95 * 1024 * 1024)) ]; then
  die "Preview is still too large for normal Git. Lower TARGET_MIB and rerun."
fi
ok "Git-safe preview created: $PREVIEW"

say "Keeping raw/HD demo files out of normal Git"

touch .gitignore
for entry in \
  "docs/demo/lunelle-demo.webm" \
  "docs/demo/lunelle-demo.mp4" \
  "docs/demo/lunelle-demo-narrated.mp4" \
  ".release-assets/"
do
  grep -qxF "$entry" .gitignore || echo "$entry" >> .gitignore
done

git rm --cached --ignore-unmatch \
  docs/demo/lunelle-demo.webm \
  docs/demo/lunelle-demo.mp4 \
  docs/demo/lunelle-demo-narrated.mp4 >/dev/null 2>&1 || true

say "Pointing the README to the lightweight preview"

python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
if not p.exists():
    raise SystemExit("README.md not found")

s = p.read_text(encoding="utf-8")

for old in (
    "docs/demo/lunelle-demo-narrated.mp4",
    "docs/demo/lunelle-demo.mp4",
    "docs/demo/lunelle-demo.webm",
):
    s = s.replace(old, "docs/demo/lunelle-demo-preview.mp4")

marker = "## 🎥 Product demo"
if marker in s and "Full HD narrated demo" not in s:
    s = s.replace(
        marker,
        marker + "\n\n"
        "The repository contains a compressed web preview for fast cloning. "
        "The **full HD narrated demo** is attached to the GitHub Release."
    )

p.write_text(s, encoding="utf-8")
PY

say "Removing oversized demo blobs from unpushed Git history"

git fetch origin main

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_BRANCH="backup/pre-demo-size-fix-${STAMP}"
git branch "$BACKUP_BRANCH" HEAD
ok "Local backup branch created: $BACKUP_BRANCH"

# Collapse any local/unpushed commits back onto the current remote main.
# Working-tree content is preserved, but oversized binary blobs disappear
# from the history that will be pushed.
git reset --soft origin/main

# Make sure ignored raw video files cannot re-enter the new commit.
git rm --cached --ignore-unmatch \
  docs/demo/lunelle-demo.webm \
  docs/demo/lunelle-demo.mp4 \
  docs/demo/lunelle-demo-narrated.mp4 >/dev/null 2>&1 || true

git add -A
git add -f "$PREVIEW"

if git diff --cached --quiet; then
  warn "Nothing new to commit."
else
  git commit -m "Fix demo delivery: web preview + HD release asset"
fi

say "Verifying there are no >100 MiB blobs in the commits being pushed"

python3 - <<'PY'
import subprocess, sys

remote = "origin/main"
rev = subprocess.run(
    ["git", "rev-list", "--objects", f"{remote}..HEAD"],
    capture_output=True, text=True, check=True
).stdout.splitlines()

bad = []
for line in rev:
    oid, *rest = line.split(" ", 1)
    kind = subprocess.run(
        ["git", "cat-file", "-t", oid],
        capture_output=True, text=True
    ).stdout.strip()
    if kind != "blob":
        continue
    size = int(subprocess.run(
        ["git", "cat-file", "-s", oid],
        capture_output=True, text=True, check=True
    ).stdout.strip())
    if size >= 100 * 1024 * 1024:
        bad.append((size, rest[0] if rest else oid))

if bad:
    for size, name in bad:
        print(f"OVERSIZED: {size/1024/1024:.1f} MiB  {name}")
    sys.exit(1)

print("Git blob size preflight: PASS")
PY

say "Pushing the lightweight repository demo"
git push -u origin main
ok "Repository push succeeded"

say "Uploading the full HD narrated demo to the GitHub Release"

if gh release view "$VERSION" --repo "$REPO" >/dev/null 2>&1; then
  gh release upload "$VERSION" "$HD_ASSET" \
    --repo "$REPO" \
    --clobber
else
  gh release create "$VERSION" "$HD_ASSET" \
    --repo "$REPO" \
    --title "Lunelle ${VERSION}" \
    --notes "Full HD narrated Playwright product demo and Lunelle release assets."
fi

ok "HD narrated demo uploaded to release ${VERSION}"

say "Done"
printf 'Repo preview: %s\n' "$PREVIEW"
printf 'HD release:   %s on GitHub Release %s\n' "$HD_ASSET" "$VERSION"
printf 'Backup branch: %s\n' "$BACKUP_BRANCH"
