# Academy notes: Learn the Academy Kit

Read this before you change anything in this academy.

## What this academy is

A small academy that teaches the Academy Kit itself. It is the kit's `example/` folder: a finished academy to look at or copy from. That is the one case where an academy lives inside the kit. Your own academies belong next to their documents, never inside the kit.

## The reader

A colleague who has never used the kit and wants to learn how to make and maintain an academy. They know Claude Code and the command line. They read English; their own language is German.

- Lessons are written in English.
- Reader language: German. Every key term has a German `tr`: the German word for the term, then a colon and a few German words that say what it is.

## The documents and their authority

| Document | What it is |
|---|---|
| `../SKILL.md` | The main document: what an academy is and the steps to make and maintain one. |
| `../references/CONFIG.md` | Every `academy.json` setting. |
| `../references/LESSON_BRIEF.md` | How one lesson file is written. |
| `../references/SYNC.md` | Keeping lessons in step with the documents. |
| `../references/VIDEO.md` | The optional videos. |

Authority order: `SKILL.md` decides the process and its order. For the detail of its own subject (settings, lesson format, sync, videos) the reference file wins. No disagreement between them was found when the lessons were written.

Out of scope: the kit's `README.md`, the engine scripts and the portal code. Do not teach from them. If a script behaves differently from the documents, report it; the lessons follow the documents.

## Lesson plan (approved)

| Id | Name | What it covers | Sources |
|---|---|---|---|
| `M0` | What an Academy Is | Overview: the kit and the academy folder, what the reader gets, the local model, privacy, the kit's files. | `SKILL.md` |
| `M1` | Making an Academy | The seven steps from the first questions to a checked site, and the `academy.json` settings. | `SKILL.md`, `CONFIG.md` |
| `M2` | Writing a Lesson | The ground rules, the lesson file field by field, repeating codes, the optional video block, the check before done. | `LESSON_BRIEF.md` |
| `K1` | Keeping It Current | Working on an existing academy, sync, videos and the other extras. | `SKILL.md`, `SYNC.md`, `VIDEO.md` |

Groups: "Make an academy" (`M0` overview, `M1`, `M2`; taken by prefix `M`) and "Keep it going" (`K1`; listed by id).

## Wording rules

- Plain words, short sentences, active voice.
- Keep the kit's own names exactly as written: `academy.json`, `ACADEMY_NOTES.md`, `sources.json`, `content/<ID>.json`, `<kit>`, the script names, the field names, Translate, Explain, Visualize, Mind map, Ask.
- Say "the kit" and "the academy folder" for the two parts. Say "the documents" for the source documents and "the reader" for the person who learns.
- Examples are made up and must say so ("for example, imagine…"). The library handbook in the examples is the same made-up academy that `CONFIG.md` uses.
- Sample codes: the documents have no real repeating codes. Use the documents' own samples, spelled the same way everywhere: `R12` for a decision, `P0` for a gate, `REQ-12` for a requirement. `codes` in `academy.json` is narrowed to these families, so the documents' sample lesson ids (`L3`, `L5`, `HR2`) are not underlined as codes.
- Block title: `gates` is shown as "Steps in order", because the lessons use it for steps, not milestones.

## Choices made for this academy

- No videos: there is no `video` key in `academy.json` and none in the lessons. Kokoro has no German voice anyway; the lessons would be narrated in English only.
- Sync is on. The source is the folder `../references`. Paths in `sources.json` are relative to that folder, and it lists only files inside it.
- `SKILL.md` is a source of `M0`, `M1` and `K1`, but it sits outside the watched folder. Sync does not watch it and `sources.json` does not list it. `M0` is built from `SKILL.md` alone, so its `sources` list is empty. When `SKILL.md` changes, check `M0`, `M1` and `K1` by hand. In every sync run, read `SKILL.md` as well.
- Everything stays on this computer. Nothing is uploaded, published or pushed.
