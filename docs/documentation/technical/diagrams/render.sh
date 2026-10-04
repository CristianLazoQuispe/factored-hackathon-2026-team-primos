#!/usr/bin/env sh
# Render every *.mmd in this folder to SVG and a 300-dpi PNG (uses the local Chrome, no Chromium download).
# architecture.svg is drawn by hand (no .mmd): only its PNG is rendered.
set -e
cd "$(dirname "$0")"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=3.125 --window-size=1480,820 \
  --screenshot="$PWD/architecture.png" "file://$PWD/architecture.svg" 2>/dev/null
sips -s dpiWidth 300 -s dpiHeight 300 architecture.png >/dev/null
echo "ok   architecture.png (300 dpi)"
for src in *.mmd; do
  name="${src%.mmd}"
  npx -y @mermaid-js/mermaid-cli@11 -p puppeteer.json -i "$src" -o "$name.svg" -b white -q
  npx -y @mermaid-js/mermaid-cli@11 -p puppeteer.json -i "$src" -o "$name.png" -b white -s 3.125 -q
  sips -s dpiWidth 300 -s dpiHeight 300 "$name.png" >/dev/null
  echo "ok   $name.svg $name.png (300 dpi)"
done
