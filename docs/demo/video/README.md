# Quipu demo video (HyperFrames)

~159 s, 1920×1080, 24 fps, English narration. Built with [HyperFrames](https://hyperframes.dev): each scene is an HTML sub-composition in `compositions/`, mounted from `index.html`.

| Scene | File | Source |
|---|---|---|
| 1 Intro | `s01-intro.html` | `public/clips/intro.mp4` = `../intro-final-night-maria.mov` 5.0–15.2 s, upscaled to 1080p |
| 2 Numbers | `s02-numbers.html` | deck copy (slides 1–2), design tokens from `public/ds/` |
| 3–5 Phone story | `s03-phone.html`, `s04-voice.html`, `s05-resolved.html` | the mock phone from `../runway/`, animated |
| 6 Real web tour | `s06-tour.html` | Playwright recordings and screenshots in `public/screens/` |
| 7 Architecture | `s07-architecture.html` | the real components, in the video palette |
| 7b Engineering | `s07b-engineering.html` | git flow dev → main, GitHub Actions (lint + tests, eval gate, deploy to Cloud Run) |
| 8 Evidence | `s08-evidence.html` | README evaluation numbers |
| 9 Close | `s09-close.html` | the web's animated logo, team, GitHub and live URL |

## Regenerate

```bash
# narration (Kokoro, local) — from the repo root
uv run python docs/demo/video/scripts/narrate.py af_heart

# real web captures — with the stack up (make up, Gemini configured)
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 docs/demo/video/scripts/capture.py all
for n in landing corona khipu; do ffmpeg -y -i public/screens/$n.webm -an -c:v libx264 -crf 18 -pix_fmt yuv420p -r 24 public/screens/$n.mp4; done

# timeline + music carve — from docs/demo/video (build_index.py rewrites index.html; carve after it)
python3 scripts/build_index.py
npm i -D @hyperframes/core@0.8.137
node ~/.claude/plugins/cache/hyperframes/hyperframes/0.8.137/skills/hyperframes-audio/scripts/carve.mjs --comp index.html --bed bgm --strength 0.5

# check, preview, render
npm run check
npx hyperframes preview --background     # Studio on http://localhost:3002
npm run render -- --output out/quipu-demo.mp4 --fps 24
```

Music: `assets/bgm/track.wav` (30 s seed, looped to `track-long.wav`) is generated locally with MusicGen through media-use (no HeyGen account). With a HeyGen login (`npx hyperframes auth login`) a catalog track can replace it:
`npx hyperframes media-use resolve --type bgm --intent "calm confident fintech underscore" --project .`
