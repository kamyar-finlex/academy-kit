# Keeping an academy in step with its documents

Documents change; lessons should follow. `engine/sync.py` answers two questions without any AI: *did the source change?* and *which lessons does that touch?* Rewriting the lessons is then a person's or an agent's job.

## Set it up

1. In academy.json, say where the documents are:

   ```json
   "source": { "type": "git", "repo": "https://github.com/org/docs", "docs_root": "docs" }
   ```
   or
   ```json
   "source": { "type": "folder", "path": "../handbook" }
   ```

   A git source is cloned once into `<academy>/source-repo` (read-only: never commit or push there). Optional keys: `label` (name on the badge), `clone`, `sources`, `state` (other file locations), `mentions` (phrases that mark a changed file as relevant), `shared_lessons` (lessons to flag when a shared source changes; default: the intro lessons).

2. In `<academy>/sources.json`, say which files each lesson is built from. Paths are relative to `docs_root` inside the repo for a git source, and to `path` for a folder source:

   ```json
   {
     "shared_sources": ["README.md"],
     "lessons": { "L3": { "sources": ["handbook/lending.md"] }, "L5": { "sources": ["handbook/events.md"] } }
   }
   ```

   Write this while writing the lessons; it is also the answer to "where does this lesson come from?".

   A source is one repository or one folder. A file outside it is not watched, so keep everything the lessons are built from under it. If a lesson also draws on a document elsewhere, leave that document out of sources.json (a lesson may have an empty `sources` list) and say so in ACADEMY_NOTES.md, so whoever changes that document knows to check the lesson by hand.

3. Run the first check. It records the starting point:

   ```bash
   python3 <kit>/engine/sync.py <academy-folder> check
   ```

## One sync run

1. `sync.py <academy> check`
   - Exit 0: nothing a lesson is built from changed. The home page badge says "In sync".
   - Exit 10: it prints the affected lessons (`lessons_from_sources`) and changed files that mention a lesson id or a `mentions` phrase but are not mapped yet (`files_mentioning_lessons`).
2. For each affected lesson, read the actual change (for git: `git -C <academy>/source-repo diff <from>..<to> -- <file>`), decide whether the lesson's facts changed, and edit `content/<ID>.json` following LESSON_BRIEF.md. A wording change in the source often needs no lesson change. A new document may need a new lesson and a new entry in sources.json.
3. `build.py <academy>` (it rebuilds the whole site and re-makes a video only when that lesson's `video` block changed)
4. `sync.py <academy> mark --lessons L3,L5 --note "what changed, in one line"`. If something failed: `sync.py <academy> fail "what went wrong"`; the badge shows it and the next check retries.

## Running it on a schedule

In the Claude desktop app, a scheduled task can do the whole run every morning. Its prompt, in substance:

> Run `python3 <kit>/engine/sync.py <academy> check`. If it exits 0, stop. If it exits 10, update the affected lessons following `<kit>/references/LESSON_BRIEF.md` and `<kit>/references/SYNC.md`, rebuild them, and mark the sync. Never push or write to the source repository. On any failure run `sync.py <academy> fail "<reason>"`.

Ask the user before creating a scheduled task; it runs unattended and uses their account.
