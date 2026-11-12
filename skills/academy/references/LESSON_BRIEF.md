# Lesson brief

How to write one lesson. Each lesson is ONE JSON file, `content/<ID>.json`, in the academy folder. It feeds the lesson page and, if videos are on, a narrated explainer video.

Give this file to any agent that writes or updates lessons, together with the academy's own notes (who the reader is, which documents are the authority).

## Ground rules

- **Only state what the source documents say.** Teaching examples and analogies are welcome but must be clearly illustrative ("for example, imagine…") and must not invent decisions, owners, dates or numbers. A reader will trust the lesson as much as the original.
- **When sources disagree, the academy's notes say which wins** (usually the newest). Teach that version; do not mix wordings.
- **Plain words, short sentences, active voice,** in the academy's lesson language. Keep the documents' own terms (product names, technical terms, ids) exactly as written, because the reader will meet them again at work.
- **Coverage.** The sections together cover everything the lesson's sources say about the topic: purpose, every part, the rules, the first outcome, the conditions. A reader who finishes the lesson should not need the original to know what it says. When a source is a long reference table (many settings, many fields), put its rows into `components` rather than squeezing them into section bodies; if it still does not fit, split the lesson.

## The file

```json
{
  "id": "L3",
  "name": "Lending & Returns",
  "tagline": "one sentence: what this topic is",
  "why": "2–4 sentences: the problem it solves and why it matters to the reader",
  "sections": [
    {"heading": "…", "body": ["a paragraph", "- a bullet", "- another bullet"], "explain": "plain-words note"}
  ],
  "components": [{"name": "Name as in the source", "text": "what it does, 1–2 sentences"}],
  "boundary": {"owns": ["…"], "not_owns": ["… (owner: X)"], "explain": "…"},
  "relationships": [{"with": "L2 | Front desk | …", "text": "how they work together"}],
  "gates": [{"gate": "P1", "text": "what happens at this milestone"}],
  "example": {"title": "…", "steps": ["step 1", "…"], "explain": "walk through the example"},
  "pitfalls": [{"text": "a rule that is easy to get wrong"}],
  "key_terms": [{"term": "…", "text": "definition", "tr": "the term in the reader's language, then a short gloss (optional)"}],
  "quiz": [{"q": "…", "options": ["A", "B", "C", "D"], "answer": 0, "why": "…"}],
  "video": {"scenes": []}
}
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Same as the file name. A short code works best (`L3`, `HR2`, `S01`): readers and other lessons refer to it. |
| `name`, `tagline` | yes | `name` 2–5 words; `tagline` one sentence. |
| `why` | recommended | Shown first. |
| `sections` | yes, 3–9 | The body of the lesson. `body` is a list of 1–6 strings (or one string); a string starting with `- ` is a bullet. `**bold**` and `` `code` `` work. |
| `sections[].explain` | recommended | The "in plain words" box: a friendly teacher's explanation of the part above it, 2–6 sentences, with the *why* and an intuition. Not a repeat of the body. This is what readers say helps most. |
| `components` | if the topic has named parts | Every part the sources name. |
| `boundary` | if scope matters | What is in and out of scope, and who owns what is out. |
| `relationships` | if it works with other things | `with` can name another lesson by id; it becomes a link. |
| `gates` | if there are milestones, phases or stages | `gate` is a short code. |
| `example` | recommended | One worked example, 4–8 steps. |
| `pitfalls` | recommended | 3–6 rules that are easy to get wrong. |
| `key_terms` | recommended, 6–12 | These feed the glossary, the mind maps and the translate popup. When the academy has a reader language, add `tr`: the term in that language, then a short gloss if it helps ("Sperrfrist: Zeit, in der nichts geändert werden darf"). It is shown in the translate popup, not on the lesson page. |
| `quiz` | recommended, 5–8 | Test understanding, not recall of wording. Spread the right answers across positions. `answer` is 0-based. |
| `video` | optional | See below. Leave the key out if the academy has no videos. |

Blocks you leave out are not shown. The block titles ("Why this matters", "Parts", "Scope", "Milestones"…) are the academy's `labels` in `academy.json`, so one academy can call them "Components" and "Roadmap by gate" and another "Roles" and "Phases".

Older lesson files use suffixed names (`name_en`, `body_en`, `{"en": …, "fa": …}`). They still build; new files use the names above.

## Codes that repeat

If the documents use codes that come back again and again (rules `R12`, phases `P0`, requirements `REQ-12`), write them exactly as the documents do, everywhere. The portal finds every code that appears in more than one lesson, underlines it, and opens a mind map of every place it is used. That only works when the spelling is identical.

## Video (optional)

Total narration 280–380 words (about 2.5 minutes), 6–9 scenes, 18–30 segments. Every scene has `kind`, `heading` (max 6 words, shown on screen) and `segments: [{"say": "…", "focus": n}]`.

**Show, don't list.** At least THREE visual scenes from `diagram`, `layers`, `timeline`, `flow`, `split`; at most TWO plain `bullets` scenes besides the closing recap. Prefer a `diagram` whenever the narration talks about things that talk to each other.

| kind | fields | use it for | `focus` |
|---|---|---|---|
| `title` | `items: [tagline]` | always scene 1; heading = "<ID> · <name>" | -1 |
| `diagram` | `nodes: [{"label", "sub"?, "col", "row", "shape"?: "box\|pill\|db\|hub"}]`, `edges: [{"from", "to", "label"?, "dashed"?, "both"?}]` (`from`/`to` are node indexes) | how parts connect. Up to 4 columns × 3 rows, max 8 nodes; labels ≤ 3 words, `sub` ≤ 5 words, edge labels 1–2 words. `db` = a store, `hub` = the central piece. | node index; its edges light up |
| `layers` | `layers: [{"title", "items": [≤5 short chips]}]` (2–4, top to bottom) | a pyramid: what sits on what | layer index |
| `timeline` | `items: ["P0 Pick the tool", …]` (3–6) | milestones, lifecycles. Start an item with a short code to show it in the dot. | item index; earlier ones show done |
| `flow` | `items` (3–5 steps) | an ordered process | step index |
| `split` | `left/right: {"title", "items"}` | in scope vs out, do vs don't | index in left, then right |
| `cards` | `items` (2–9) | a set of peers | card index |
| `bullets` | `items` (2–5) | the closing recap; little else | item index |

Narration (`say`) is read by a text-to-speech voice: ONE sentence per segment, 8–28 words; spell ids and acronyms the way they are spoken ("L three", "P one", "A P I"); no symbols like "&", "/", "→", parentheses or quotes; numbers as words. Captions are made from `say` automatically (ids shown as L3, P1). Screen text (`heading`, `items`, labels) uses normal spelling.

## Before you call a lesson done

```bash
python3 <kit>/engine/validate.py <academy-folder> L3
```

Errors must be fixed. Read the warnings: they are things a reader would miss. Then build and look at the page.
