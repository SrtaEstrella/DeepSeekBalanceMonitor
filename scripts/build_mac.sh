#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
#  scripts/build_mac.sh  —  Build DeepSeek Balance Monitor as a macOS .app
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_FILE="$ROOT_DIR/scripts/DeepSeekBalanceMonitor.spec"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="DeepSeek Balance Monitor.app"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  DeepSeek Balance Monitor — macOS Build   ${NC}"
echo -e "${BLUE}============================================${NC}"

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON="/Users/chwong/miniforge3/envs/opencode/bin/python"
[ ! -f "$PYTHON" ] && PYTHON="$(which python3 || true)"
[ -z "$PYTHON"  ] && { echo -e "${RED}Error: python3 not found${NC}"; exit 1; }
echo -e " - Python : ${GREEN}$PYTHON${NC}"

# ── Regenerate icon (always up-to-date) ───────────────────────────────────────
echo -e "\n${BLUE}[1/4] Generating app icon...${NC}"
ROOT_DIR="$ROOT_DIR" "$PYTHON" - << PYEOF
from PIL import Image, ImageDraw, ImageFont
import struct, io, os

root = os.environ['ROOT_DIR']
FONT    = os.path.join(root, 'assets/font/ShareTech-Regular.ttf')
OUT_PNG = os.path.join(root, 'assets/AppIcon.png')
OUT_ICS = os.path.join(root, 'assets/AppIcon.icns')
SIZE, RADIUS, BG = 1024, int(1024*0.18), (13, 74, 69)
PAD, FS = int(1024*0.09), int(1024*0.185)

img  = Image.new('RGBA', (SIZE, SIZE), (0,0,0,0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle([0,0,SIZE,SIZE], radius=RADIUS, fill=BG)
font = ImageFont.truetype(FONT, FS)
draw.text((PAD, PAD),                   'Balance', fill=(255,255,255,255), font=font)
draw.text((PAD, PAD + FS + int(FS*0.1)),'Monitor', fill=(255,255,255,255), font=font)
img.save(OUT_PNG)

types = {16:b'icp4',32:b'icp5',64:b'icp6',128:b'ic07',256:b'ic08',512:b'ic09',1024:b'ic10'}
chunks = []
for sz, tag in types.items():
    buf = io.BytesIO(); img.resize((sz,sz), Image.LANCZOS).save(buf, 'PNG')
    chunks.append((tag, buf.getvalue()))
total = 8 + sum(8+len(d) for _,d in chunks)
with open(OUT_ICS,'wb') as f:
    f.write(b'icns'); f.write(struct.pack('>I', total))
    for tag, data in chunks:
        f.write(tag); f.write(struct.pack('>I', 8+len(data))); f.write(data)
print(f'   Icon OK: {os.path.getsize(OUT_ICS):,} bytes')
PYEOF
echo -e " - Icon   : ${GREEN}assets/AppIcon.icns${NC}"

# ── Check PyInstaller ─────────────────────────────────────────────────────────
echo -e "\n${BLUE}[2/4] Checking PyInstaller...${NC}"
if ! "$PYTHON" -m PyInstaller --version &>/dev/null; then
  echo -e "${RED}Error: PyInstaller not found in $PYTHON environment.${NC}"
  echo -e "Install with:  mamba install -c conda-forge pyinstaller"
  exit 1
fi
echo -e " - PyInstaller : ${GREEN}$("$PYTHON" -m PyInstaller --version)${NC}"

# ── Build ─────────────────────────────────────────────────────────────────────
echo -e "\n${BLUE}[3/4] Building .app bundle...${NC}"
cd "$ROOT_DIR"

TEMP_LOG=$(mktemp)
"$PYTHON" -m PyInstaller --clean --noconfirm --log-level=WARN "$SPEC_FILE" > "$TEMP_LOG" 2>&1 &
PID=$!

SPIN='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'; i=0
while kill -0 $PID 2>/dev/null; do
  i=$(( (i+1) % ${#SPIN} ))
  printf "\r - Building... ${YELLOW}${SPIN:$i:1}${NC} "
  sleep 0.1
done
wait $PID; EXIT=$?; printf "\r"

if [ $EXIT -ne 0 ]; then
  echo -e "${RED}Build failed! Log:${NC}"
  cat "$TEMP_LOG" | head -30
  rm -f "$TEMP_LOG"; exit 1
fi
rm -f "$TEMP_LOG"

# ── Verify ────────────────────────────────────────────────────────────────────
echo -e "\n${BLUE}[4/4] Verifying output...${NC}"
APP_BUNDLE="$DIST_DIR/$APP_NAME"
if [ ! -d "$APP_BUNDLE" ]; then
  echo -e "${RED}Error: .app bundle not found at $APP_BUNDLE${NC}"; exit 1
fi

APP_SIZE=$(du -sh "$APP_BUNDLE" | cut -f1 | xargs)

# ── Ad-hoc Sign (Helps with permissions) ──────────────────────────────────────
echo -e " - Signing: ${YELLOW}Ad-hoc codesign...${NC}"
codesign --force --deep --sign - "$APP_BUNDLE"

echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}           Build Complete! 🎉              ${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e " App  : ${GREEN}${APP_SIZE}${NC} → dist/${APP_NAME}"
echo -e " Run  : open \"$APP_BUNDLE\""
