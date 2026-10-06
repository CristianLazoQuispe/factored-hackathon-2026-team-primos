"""Write index.html from the scene list: sequential slots with a 0.2 s crossfade overlap, one voice-over per scene."""
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FADE = 0.2
# (scene id, duration, [(vo file, offset within the scene), ...])
SCENES = [
    ("s01-intro", 10.0, [("01-intro", 0.4)]),
    ("s02-numbers", 19.0, [("02-numbers", 0.3)]),
    ("s03-phone", 8.0, [("03-phone", 0.5)]),
    ("s04-voice", 12.5, [("04-voice", 0.3)]),
    ("s05-resolved", 13.0, [("05-resolved", 0.3)]),
    ("s06-tour", 29.0, [("06a-tour", 0.3), ("06b-tour", 16.6)]),
    ("s07-architecture", 22.0, [("07-architecture", 0.3)]),
    ("s07b-engineering", 21.0, [("07b-engineering", 0.3)]),
    ("s08-evidence", 16.0, [("08-evidence", 0.3)]),
    ("s09-close", 10.0, [("09-close", 1.0)]),
]
MUSIC = ROOT / "assets" / "bgm" / "track-long.wav"


def wav_seconds(name):
    with wave.open(str(ROOT / "public" / "vo" / f"{name}.wav")) as w:
        return round(w.getnframes() / w.getframerate(), 2)


slots, audios, t = [], [], 0.0
for cid, dur, vos in SCENES:
    slots.append(f'      <div id="el-{cid}" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" data-start="{t:g}" data-duration="{dur:g}" data-track-index="1" data-width="1920" data-height="1080"></div>')
    for vo, off in vos:
        audios.append(f'      <audio id="vo-{vo}" src="public/vo/{vo}.wav" data-start="{t + off:g}" data-duration="{wav_seconds(vo)}" data-track-index="8" data-volume="1"></audio>')
    t += dur - FADE
total = round(t + FADE)
if MUSIC.exists():
    audios.append(f'      <audio id="bgm" src="assets/bgm/track-long.wav" data-start="0" data-duration="{total}" data-track-index="9" data-volume="0.14"></audio>')

html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: #071316; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #071316; }}
      #root > div[data-composition-src] {{ position: absolute; inset: 0; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-fps="24" data-start="0" data-duration="{total}">
{chr(10).join(slots)}
{chr(10).join(audios)}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
(ROOT / "index.html").write_text(html)
print("total", total, "s; music", MUSIC.exists())
for cid, dur, _ in SCENES:
    pass
