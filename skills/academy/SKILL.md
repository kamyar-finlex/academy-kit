---
name: academy
description: Turn a set of documents (a docs folder, a git repo, handbooks, design docs, policies, process descriptions, specs) into a private learning website, an "academy" - one lesson per topic with plain-words notes, a worked example, key terms and a quiz, plus select-to-translate into the reader's own language, diagrams, mind maps of terms that keep coming back, and an Ask box, all answered by a local model so nothing leaves the computer. Optional narrated videos and a sync check for when the documents change. Use this whenever someone wants to learn, study, onboard on, or teach from documents - "make an academy / course / e-learning / training from these docs", "help me learn this repo's documentation", "turn the handbook into lessons", "onboarding material for new joiners" - and for any work on an existing academy (add or update a lesson, rebuild, serve, add a language, sync, videos), even when they do not say "academy".
---

# Academy

An academy is a small website someone reads to learn a set of documents properly. It has two parts that never mix:

- **The kit** (this skill's folder): the portal, the build, serve, check and sync scripts. The same for everyone.
- **An academy folder** (the user's): `academy.json` (title, groups, languages, wording) and `content/<ID>.json` (one file per lesson). This is the only thing you write.

That split is why colleagues can share the kit: nobody's documents or lessons are inside it.

`<kit>` below means this skill's folder (the one holding this SKILL.md). The scripts need only Python 3.9+; no packages.

## What the reader gets

- A lesson per topic: why it matters, sections with an "in plain words" note under each, parts, scope, a worked example, easy-to-get-wrong rules, key terms, a quiz. Progress and quiz scores are remembered in their browser.
- **Translate / Explain**: select a word, get it in their own language (or in simpler words), in the context of that sentence.
- **Visualize**: select a paragraph, get it as boxes and arrows.
- **Mind map**: select a term, or click an underlined code such as `R12`, and see every place the lessons use it, grouped by idea, with the source sentences one click away. People remember relations, not lists; this is the feature that saves them from flipping back.
- **Ask**: a question about a selection or a term, answered only from the lesson text, with its sources.
- **Listen**: a speaker beside every paragraph and a Listen button on every part; the text is read aloud by a natural voice on their computer. Some people understand a text better when it is read to them.
- Optional: a 2.5-minute narrated video per lesson, and a badge that shows whether the lessons are in step with the documents.

The four AI features run on a local model through [Ollama](https://ollama.com). Without Ollama the academy still works; those buttons report that the model is not answering. Nothing is sent to an outside service, which is what makes it safe for internal documents.

## Making a new academy

### 1. Find out what is needed

From the conversation or by asking, briefly:

- **Which documents**, and which win when they disagree (usually the newest).
- **Who reads it**: what they already know, and their own language if the documents are not in it. A reader language turns on Translate.
- **Where the academy folder should live.** Default: next to the documents, named `<topic>-academy`. Not inside the kit (the bundled `example/` is the one exception).

Do not ask about videos or sync up front; offer them at the end.

### 2. Create the folder

```bash
python3 <kit>/engine/init.py <academy-folder> --title "…" --docs <folder-or-git-url> --reader German
```

`--docs` and `--reader` are optional. `--docs` records where the documents are (the `source` block), so the home page shows a "not checked yet" sync note until you set sync up or remove that block.

### 3. Read the documents and propose a lesson plan

Read everything in scope before planning; a plan made from file names misses what the documents actually spend their words on. Then propose, in the chat, a short table: lesson id, name, one line on what it covers, which files it comes from. Guidance:

- One lesson per topic a person would ask about by name, not one per file. 5 to 20 lessons is typical.
- Give lessons short code ids (`L3`, `HR2`). If the documents already number things, use their numbers, so the lesson id is the name people use at work.
- Group lessons the way the documents are organized (2 to 4 groups). An overview lesson per group (`L0`) helps: it is where a reader starts.
- Note the codes that repeat across the documents (decisions, phases, requirement numbers). They become the clickable mind-map codes.

Wait for the user to agree to the plan. It decides everything after it, and it is cheap to change now and expensive later.

### 4. Fill in academy.json and write the academy's notes

Read `<kit>/references/CONFIG.md`. Set at least `title`, `subtitle`, `domain`, `groups`, `home`, and `labels` where the generic block titles do not fit the subject (an HR academy wants "Roles" and "Phases", not "Parts" and "Milestones"). If there is a reader language, write `reader.example` in that language; without it a small model translates the whole sentence instead of the selected word.

Write `<academy-folder>/ACADEMY_NOTES.md`: who the reader is, the authority order of the documents, the lesson plan, and any wording rules ("keep product names in English"). Every agent that touches this academy later reads it first, so the tenth lesson sounds like the first.

### 5. Write the lessons

Read `<kit>/references/LESSON_BRIEF.md` first; it has the file format and the rules that make a lesson trustworthy (only what the sources say; plain words; full coverage).

- Write one lesson yourself first and build it, so problems with the plan show up early.
- For the rest, when subagents are available, give each lesson to one subagent: the brief, ACADEMY_NOTES.md, the lesson's row from the plan, its source files, and the finished first lesson as a model. Run them in parallel. Exactly one agent writes each file; two writers on the same lesson silently overwrite each other.
- Record each lesson's source files in `sources.json` as you go (see `<kit>/references/SYNC.md`). It costs a line now and is what makes sync possible later.

### 6. Check, build, look

```bash
python3 <kit>/engine/validate.py <academy-folder>
```

```bash
python3 <kit>/engine/build.py <academy-folder>
```

```bash
python3 <kit>/engine/serve.py <academy-folder> --open
```

The build refuses to run on errors and prints warnings for things a reader would miss. `serve.py` serves the site on this computer only (default port 8765, `--port` to change) and passes the AI requests to Ollama; opening `index.html` straight from disk does not work, because the AI features need the server.

Then look at it in a browser yourself before saying it is done: the home page, one lesson top to bottom, one quiz answer, and (if Ollama is running) a translation, a diagram and a mind map of a repeated term. Check the browser console for errors. A lesson that validates can still read badly; skim each one once.

### 7. Offer the extras

- **AI features**: need Ollama running and one of the models in `ai.models` installed (`ollama pull <model>`). Say so if it is missing; do not install it unasked.
- **Listen**: `<kit>/references/LISTEN.md`. Works once the natural voice is set up on the computer (a one-time install), or with a high-quality system voice. Say so if neither is there; do not install it unasked, and never switch on the robotic basic voices as a shortcut.
- **Videos**: `<kit>/references/VIDEO.md`. Heavy (2–3 minutes per lesson, extra tools). Offer, do not assume.
- **Sync**: `<kit>/references/SYNC.md`. Worth it when the documents are still changing.
- **Always on**: `<kit>/engine/docker/` has a Docker Compose file that serves the site permanently on localhost.

## Working on an existing academy

Read its `ACADEMY_NOTES.md` and `academy.json` first.

- **Change or add a lesson**: edit `content/<ID>.json` per the brief, then `validate.py`, then `build.py <academy>`. The build always rebuilds the whole site; naming ids (`build.py <academy> L3`) only forces those lessons' videos to be re-made. Add a new lesson to a group in academy.json and to sources.json.
- **The documents changed**: follow `<kit>/references/SYNC.md`.
- **Look or wording**: `labels`, `home`, `theme` in academy.json, then rebuild. Change the kit's portal files only for something every academy should get.
- **A reader in another language**: set `reader` in academy.json and add `tr` to the key terms; nothing else changes.

## What is public and what is private

This is the rule to hold on to, because getting it wrong leaks someone's documents:

| | Public (the kit) | Private (an academy) |
|---|---|---|
| What | The tool: scripts, the portal, this skill, the guides, the small bundled example. | Everything made from the user's documents: `academy.json`, `content/`, `sources.json`, `ACADEMY_NOTES.md`, the built `site/`, videos, the cloned `source-repo/`, a brand font. |
| Where | The kit's repository, which may be public. | A folder outside the kit, as confidential as the documents themselves. |

- A lesson restates its source. If the document is internal, so is the lesson, the quiz, the mind map and the video made from it.
- Never create, copy or move an academy into the kit, and never paste document text, real names, internal hostnames or customer data into the kit's guides, examples, tests or commit messages. `init.py` and `build.py` refuse an academy inside the kit; `tools/check_public.py` in the kit's repository refuses to let one be committed.
- When you improve the kit while working on someone's academy (a portal fix, a clearer guide), carry over the change only, with a made-up example, never the academy's own text.
- No passwords, keys or tokens in `academy.json` or anywhere else you write. For a private git source, let git's own credential helper sign in.
- Keep everything on the user's machine: do not upload, publish, push or share an academy, its lessons, its site or the documents unless they ask in so many words, and then only to a place where the documents themselves are allowed.
- A git source is cloned read-only; never commit or push there.
- The portal's AI calls go to the local Ollama only. Do not point `ai` at an outside service unless the user asks for that, because every selection and question would leave their machine.

## Files in this skill

| Path | What |
|---|---|
| `engine/init.py` | Start an academy folder. |
| `engine/validate.py` | Check lesson files. |
| `engine/build.py` | Build the site (and videos, if on). |
| `engine/serve.py` | Serve it locally with the AI features. |
| `engine/sync.py` | Did the source change, and which lessons does it touch? |
| `engine/speak_server.py` | The natural voice for Listen. `serve.py` starts it when a Kokoro setup exists. |
| `engine/portal/`, `engine/video/` | The website and the video renderer. Shared by every academy. |
| `engine/docker/` | Optional always-on server. |
| `references/LESSON_BRIEF.md` | How to write a lesson. Read before writing any. |
| `references/CONFIG.md` | Every academy.json setting. |
| `references/LISTEN.md`, `references/VIDEO.md`, `references/SYNC.md` | Read aloud, videos, sync. |
| `example/` | A small finished academy to look at or copy from. |
