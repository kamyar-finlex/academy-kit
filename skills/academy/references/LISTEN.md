# Listen (read aloud)

Every paragraph, list and note in a lesson has a small speaker button; every part has a **Listen** button on its heading; and a selection can be read with **Listen** (or the L key). A bar at the bottom has pause, stop, speed and the choice of voice. Some people take a text in better when someone reads it to them.

The voice is always a voice on the reader's own computer. Lesson text is never sent to a speech service.

## Where the voice comes from

1. **The kit's natural voice** (first choice). `engine/speak_server.py` runs [Kokoro](https://github.com/hexgrad/kokoro), a small neural voice model, on this computer. It sounds like a person. `serve.py` starts it by itself when it finds a Python that has Kokoro, and stops it again on exit.
2. **A high-quality system voice** (second choice). If the natural voice is not running, the page uses the system's own voices, but only those the system marks as premium, enhanced, natural or neural, and only ones installed on the computer.
3. **Otherwise nothing.** The basic system voices sound like a machine, so they are not used; the bar says that no natural voice is available. An academy can allow them with `"speech": {"basic_voices": true}`.

A browser's online voices are never used: they would send the text to the browser's maker.

## Setting up the natural voice (once per computer)

It is the same setup the videos use (VIDEO.md).

```bash
python3 -m venv ~/.local/share/academy-kit/tts
```

```bash
~/.local/share/academy-kit/tts/bin/pip install kokoro soundfile numpy
```

Start it once by hand with downloads allowed, so it can fetch the model (about 330 MB) and the default voice; stop it with Ctrl+C when it prints "voice ready":

```bash
HF_HUB_OFFLINE=0 ~/.local/share/academy-kit/tts/bin/python <kit>/engine/speak_server.py
```

From then on `serve.py` starts it offline. To add another voice, run the same command once with `--voice bf_emma` (names: `a…` American and `b…` British English, `e…` Spanish, `f…` French, `i…` Italian, `p…` Portuguese; the second letter is `f` for a woman's voice, `m` for a man's). There is no German voice; for German lessons the page falls back to a high-quality system voice.

A Python somewhere else: `"speech": {"python": "<path>/bin/python"}` in academy.json, or the `ACADEMY_TTS_PYTHON` variable.

## Settings (academy.json)

```json
"speech": { "voice": "af_heart", "rate": 1 }
```

| Key | Default | What it does |
|---|---|---|
| `voice` | `af_heart` | The voice readers start with. Each reader can pick another in the bar; the browser remembers it. |
| `rate` | 1 | The starting speed. |
| `python`, `espeak_data` | — | Where the Kokoro setup is, if not in the default place. |
| `basic_voices` | false | Allow the basic system voices when nothing better is installed. |

`"speech": false` removes the speaker buttons.

## Good to know

- **Speed.** Text is spoken sentence by sentence: the first sentence starts in about a second, and the next one is prepared while the current one plays. Sentences heard before are kept in `~/.cache/academy-kit/speech` and play at once.
- **Memory.** The voice model needs 1–2 GB while in use. It lets go of the model after 15 minutes without a request (`--idle-minutes`), and loads it again in a few seconds when someone listens.
- **Always-on setup.** With the Docker setup in `engine/docker/`, nothing starts the voice for you: run `speak_server.py` on the computer yourself (for example as a login item). The bundled nginx settings already pass `/speak` to it.
- **Codes and symbols.** Before speaking, the page spaces codes ("L12" is read as "L 12") and replaces symbols a voice stumbles on ("→", "&", "e.g.").
