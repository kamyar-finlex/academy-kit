# academy.json

One file per academy. It holds everything that is specific to that academy, so the kit itself stays the same for everyone. Only `title` is required.

It is part of the academy, so it is private like the documents. Never put a password or token in it.

```json
{
  "id": "library-academy",
  "title": "Library Handbook Academy",
  "subtitle": "How the library works, step by step",
  "logo": "L",
  "domain": "public library operations",
  "language": { "code": "en", "name": "English" },
  "reader": {
    "code": "de", "name": "German", "rtl": false, "badge": "DE",
    "example": { "tr": "Fälligkeitsdatum", "meaning": "Der Tag, an dem das Buch zurück sein muss." }
  },
  "ai": { "models": ["gemma4:e4b", "gemma3:4b"] },
  "speech": { "voice": "af_heart" },
  "codes": "(?:REQ-|[RP])\\d{1,3}",
  "groups": [
    { "title": "Basics", "prefix": "L", "intro": "L0", "blurb": "What every new colleague needs first." },
    { "title": "Special cases", "lessons": ["S1", "S2", "S3"] }
  ],
  "home": { "kicker": "Library team", "heading": "Learn how a loan moves", "intro": "…", "sample_terms": ["due date", "REQ-12"], "source_note": "Source: the Library handbook, 2026 edition." },
  "labels": { "unit": "chapter", "components": "Roles", "gates": "Phases" },
  "theme": { "accent": "#0A7", "brand": "#123", "dark": { "accent": "#3C9" } },
  "video": { "enabled": false },
  "source": { "type": "folder", "path": "../library-handbook" }
}
```

| Key | Default | What it does |
|---|---|---|
| `title`, `subtitle`, `logo` | — , "", first letter | The top bar. |
| `id` | folder name | Names this academy. Each reader's progress, saved words and diagrams are kept in the browser under it. |
| `storage` | `id` | Set only to keep readers' saved progress after renaming `id`. |
| `domain` | "internal company" | A few words on the subject. It goes into the AI prompts ("…a passage from *public library operations* documentation…"), which makes diagrams and mind maps noticeably better. |
| `language` | English | The language the lessons are written in. |
| `reader` | none | The reader's own language, when it differs. Turns **Explain** into **Translate**: the popup shows the word in that language, what it means in the sentence, and a simpler wording. `badge` is the 1–3 characters shown on the button (e.g. `DE`). `rtl: true` for right-to-left scripts. `detect` is a regex for the script (e.g. `"[\\u0600-\\u06FF]"`), so a question typed in it is answered in it. `example.tr` and `example.meaning` are the reader-language translation of *"due date"* in *"Each loan has only one due date."* and one sentence explaining it. Write them: small models translate the whole sentence without an example. |
| `ai` | gemma4:e4b, then gemma3:4b | Ollama models to try, in order. `"ai": false` hides every AI button; the lessons, quiz, glossary and the "by lesson" mind map still work. |
| `codes` | `[A-Z]{1,5}-?\d{1,4}` | A regex for codes that repeat across lessons (rules, phases, requirement numbers). Each one found in more than one lesson is underlined and opens its mind map on click. `false` turns it off. The default catches any capital-letters-plus-number token; if it underlines things that are not codes (product names like `S3`), narrow it to the academy's real codes, as in the example above. Lesson ids are never treated as codes. |
| `groups` | one group with everything | Sidebar and home-page groups, in this order. A group takes lessons by `prefix` (ids that start with it, then a digit) or an explicit `lessons` list. `intro` names the group's overview lesson. |
| `lesson_order` | "groups" | Order for previous/next: by group, or `"id"` for id order. |
| `home` | generic text | `kicker`, `heading`, `intro`, `sample_terms` (examples in the mind-map hint), `source_note`. |
| `labels` | generic | Block titles and small words. Keys: `unit` ("lesson"), `intro`, `start`, `review`, `why`, `components`, `component_col`, `what_col`, `boundary`, `owns`, `not_owns`, `relationships`, `with_col`, `how_col`, `gates`, `example`, `pitfalls`, `terms`, `quiz`, `plain_toggle`, `video_note`. |
| `theme` | the kit's default colors | CSS variables to override: `brand` (top bar, buttons), `accent` (highlights), `tint`, `bg`, `card`, `fg`, `line`… The full list is at the top of `engine/portal/assets/style.css`. `dark` holds the dark-mode overrides: if you change `bg`, `card`, `fg`, `line` or `accent`, set their dark values too, or dark mode shows your light colors. For videos also set `brand-rgb` and `accent-rgb` (the same colors as `r,g,b`). |
| `speech` | the natural voice, if set up | Read aloud. `{"voice": "af_heart", "rate": 1}` sets the starting voice and speed; `false` removes the speaker buttons. Basic (robotic) system voices are never used unless `"basic_voices": true`. See LISTEN.md. |
| `font` | the system font | `{"family": "Inter"}` for a font readers already have, or `{"family": "Brand Sans", "file": "fonts/BrandSans.woff2"}` for a font file kept in the academy folder. The kit ships no fonts; a licensed brand font belongs in the (private) academy. |
| `content`, `out`, `build` | `content`, `site`, `build` | Folders, relative to the academy folder. |
| `video` | off | `{"enabled": true, "voice": "af_heart", "python": "<path>", "espeak_data": "<path>"}`. See VIDEO.md. |
| `source` | none | Where the documents live, for sync. See SYNC.md. |
