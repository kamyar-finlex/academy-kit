# Videos (optional)

Each lesson can have a narrated explainer video of about 2.5 minutes, drawn from the lesson's `video.scenes` (see LESSON_BRIEF.md). Everything is made on this computer: Chrome draws the frames, a local voice model reads the narration, ffmpeg joins them.

Videos are the heavy part of the kit. An academy is complete without them; suggest them only when the reader wants them.

## What it needs

| Tool | Check | Notes |
|---|---|---|
| Google Chrome | `/Applications/Google Chrome.app` | Other path: set `CHROME_BIN`. |
| Node 22 or newer | `node --version` | No packages to install. |
| ffmpeg | `ffmpeg -version` | `brew install ffmpeg` |
| A Python with `kokoro`, `soundfile`, `numpy` | — | Kokoro is the local voice. The build looks in `~/.local/share/academy-kit/tts` (the setup below); for another place, set `"video": {"python": "<path>/bin/python"}` in academy.json or the `ACADEMY_TTS_PYTHON` variable. |

Setting up the voice once:

```bash
python3 -m venv ~/.local/share/academy-kit/tts
```

```bash
~/.local/share/academy-kit/tts/bin/pip install kokoro soundfile numpy
```

The first run downloads the Kokoro model (about 330 MB). After that, set `HF_HUB_OFFLINE=1` (the build does this by default; set `HF_HUB_OFFLINE=0` for that first run).

## Turning it on

In academy.json: `"video": {"enabled": true}`. Then:

```bash
python3 <kit>/engine/build.py <academy-folder>
```

The build makes only the videos that are missing or whose `video` block changed. Name lessons to force them (`build.py <academy> L3 L5`), or `--all-videos` for everything. One video takes 2–3 minutes; `--no-video` skips them.

If a tool is missing or a render fails, the build says so, skips the videos and still builds the site.

## Limits

- **Language.** Kokoro speaks English well and a few other languages (`KOKORO_LANG` / `"lang_code"`: `a` American English, `b` British English, `e` Spanish, `f` French, `i` Italian, `p` Portuguese…). It has no German voice. For other languages, leave videos off.
- **Look.** Frames use the academy's `theme` colors and `font` from academy.json, or the kit's defaults.
- **Check the frames.** After a render, look at a few frames in `<academy>/build/<ID>/frames/`, the diagram scenes especially: a label that is too long overflows its box.
