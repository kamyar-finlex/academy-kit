(function () {
  // Everything specific to one academy (titles, groups, labels, languages, models) comes from
  // window.ACADEMY, which build.py writes into lessons.js from the academy's academy.json.
  const L = window.LESSONS || [];
  const A = window.ACADEMY || {};
  const byId = Object.fromEntries(L.map((l) => [l.id, l]));
  const NS = (A.storage || A.id || "academy") + ":";
  const store = {
    get(k, d) { try { const v = localStorage.getItem(NS + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(NS + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  const T = Object.assign({
    unit: "lesson", intro: "Introduction", start: "Start here", review: "Review",
    why: "Why this matters", components: "Parts", component_col: "Part", what_col: "What it does",
    boundary: "Scope", owns: "In scope", not_owns: "Out of scope",
    relationships: "Related to", with_col: "With", how_col: "How",
    gates: "Milestones", example: "Worked example", pitfalls: "Easy to get wrong",
    terms: "Key terms", quiz: "Check yourself", plain_toggle: "Plain-words notes",
    video_note: "Subtitles are part of the video. Voice: local AI narration.",
  }, A.labels || {});
  const H = A.home || {};
  const READER = A.reader && A.reader.name ? A.reader : null;  // the reader's own language, if it differs from the lessons'
  const LANG = (A.language && A.language.name) || "English";
  const AI = A.ai === false ? null : Object.assign({ models: ["gemma4:e4b", "gemma3:4b"], endpoint: "ai/chat" }, A.ai || {});
  const DOMAIN = A.domain || "internal company";
  const GROUPS = (A.groups || []).filter((g) => (g.lessons || []).some((id) => byId[id]));
  if (!GROUPS.length) GROUPS.push({ title: "Lessons", lessons: L.map((l) => l.id) });
  const groupOf = (l) => GROUPS.find((g) => g.lessons.includes(l.id)) || GROUPS[0];
  const escRx = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Codes that readers meet again and again (decisions, gates, requirement numbers…). false turns them off.
  const CODE = A.codes === false ? null : (A.codes || "[A-Z]{1,5}-?\\d{1,4}");
  const codeRx = (tail = "") => new RegExp(`(?<![\\w-])(${CODE})(?![\\w-])${tail}`, "g");
  const IDS = L.map((l) => l.id).sort((a, b) => b.length - a.length).map(escRx);
  const lessonRx = () => new RegExp(`(?<![\\w-])(${IDS.join("|")})(?![\\w-])`, "g");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const XREF = (() => {  // codes that show up in more than one lesson
    const seen = new Map();
    if (CODE) for (const l of L) for (const m of JSON.stringify(l).matchAll(codeRx())) { if (byId[m[1]]) continue; if (!seen.has(m[1])) seen.set(m[1], new Set()); seen.get(m[1]).add(l.id); }
    return new Set([...seen].filter(([, ls]) => ls.size > 1).map(([k]) => k));
  })();
  const xref = (html) => (XREF.size ? html.replace(codeRx("(?![^<]*>)"), (m) => (XREF.has(m) ? `<span class="xref" data-t="${m}" title="${m}: see everywhere it shows up">${m}</span>` : m)) : html);
  const inline = (s) => xref(esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>"));
  const plain = (s) => (s ? `<div class="plain">${inline(s)}</div>` : "");
  function prose(items) {
    const arr = Array.isArray(items) ? items : [items];
    let out = "", list = [];
    const flush = () => { if (list.length) { out += "<ul>" + list.map((x) => `<li>${inline(x)}</li>`).join("") + "</ul>"; list = []; } };
    for (const raw of arr) {
      const s = String(raw || "");
      if (/^\s*[-•]\s+/.test(s)) list.push(s.replace(/^\s*[-•]\s+/, ""));
      else { flush(); if (s.trim()) out += `<p>${inline(s)}</p>`; }
    }
    flush();
    return `<div class="en">${out}</div>`;
  }
  const isIntro = (l) => !!l.intro || GROUPS.some((g) => g.intro === l.id);
  const hasVideo = (l) => !!(A.videos && A.videos[l.id]);
  const done = () => store.get("done", {});
  const quizState = () => store.get("quiz", {});
  const words = () => store.get("words", []);
  // Changes on every build, so a browser never plays a video it stored before a rebuild.
  const ver = window.LESSONS_BUILD ? "?v=" + window.LESSONS_BUILD : "";

  // ---- chrome
  const side = document.getElementById("side");
  const main = document.getElementById("main");
  const plainToggle = document.getElementById("plainToggle");
  document.title = A.title || document.title;
  plainToggle.checked = store.get("plain", true);
  document.body.classList.toggle("no-plain", !plainToggle.checked);
  plainToggle.addEventListener("change", () => { store.set("plain", plainToggle.checked); document.body.classList.toggle("no-plain", !plainToggle.checked); });
  document.getElementById("menuBtn").addEventListener("click", () => side.classList.toggle("open"));

  const studio = { available: false, status: null, files: [], selected: new Set(), tab: "lessons", filter: "", includeCode: false, models: [], job: null, lastActive: "home" };

  function renderSide(active) {
    studio.lastActive = active || studio.lastActive || "home";
    const d = done();
    const link = (l) => `<a href="#/${l.id}" class="${l.id === active ? "active" : ""} ${d[l.id] ? "done" : ""}">
      <span class="id">${isIntro(l) ? "▶" : esc(l.id)}</span><span>${esc(l.name)}</span></a>`;
    const group = (g) => { const ls = g.lessons.map((id) => byId[id]).filter(Boolean); return ls.length ? `<h4>${esc(g.title)}</h4>${ls.map(link).join("")}` : ""; };
    const hasFiles = !!(studio.status?.connected || studio.files.length);
    const tabsHtml = hasFiles ? `<div class="side-tabs" role="tablist">
      <button type="button" role="tab" data-tab="lessons" aria-selected="${studio.tab === "lessons"}">Lessons (${L.length})</button>
      <button type="button" role="tab" data-tab="files" aria-selected="${studio.tab === "files"}">Repo Files (${studio.files.length})</button>
    </div>` : "";
    if (hasFiles && studio.tab === "files") {
      const q = studio.filter.toLowerCase();
      const shown = studio.files.filter((f) => !q || f.path.toLowerCase().includes(q) || (f.title || "").toLowerCase().includes(q));
      const repoName = studio.status?.connected?.repo || "Repository";
      const modelOpts = (studio.models.length ? studio.models : ["gemma4:e4b"]).map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
      side.innerHTML = `${tabsHtml}<div class="file-panel">
        <div class="file-head"><b title="${esc(repoName)}">${esc(repoName)}</b><button type="button" class="btn ghost small" id="filesRefresh" style="padding:2px 8px;font-size:12px">Sync</button></div>
        <input class="file-search" id="fileFilter" placeholder="Filter repo files…" value="${esc(studio.filter)}">
        <div class="file-links">
          <button type="button" id="selAll">All</button>
          <button type="button" id="selDocs">Docs only</button>
          <button type="button" id="selNone">None</button>
          <label style="margin-left:auto;display:flex;align-items:center;gap:4px;color:var(--fg3);cursor:pointer"><input type="checkbox" id="incCode" ${studio.includeCode ? "checked" : ""}> Code</label>
        </div>
        <div class="file-list" id="fileList">${shown.length ? shown.map((f) => `<div class="file-item">
          <input type="checkbox" class="fchk" data-p="${esc(f.path)}" ${studio.selected.has(f.path) ? "checked" : ""}>
          <button type="button" class="file-name" data-p="${esc(f.path)}">${esc(f.path)}${f.title ? `<small>${esc(f.title)}</small>` : ""}</button>
          <span class="file-badge ${esc(f.status)}">${esc(f.lessons?.length ? f.lessons.join(",") : f.status)}</span>
        </div>`).join("") : `<div class="simple">No matching files found.</div>`}</div>
        <div class="file-actions">
          <label>Local model<select id="genModel">${modelOpts}</select></label>
          ${studio.job && studio.job.status === "running"
            ? `<div class="lbl">${esc(studio.job.current || studio.job.stage)}</div><div class="bar"></div>`
            : `<button type="button" class="btn small" id="genBtn" ${studio.selected.size ? "" : "disabled"}>Create Academy (${studio.selected.size})</button>`}
          ${studio.job?.error ? `<div class="tp-err" style="font-size:12.5px">${esc(studio.job.error)}</div>` : ""}
        </div>
      </div>`;
      bindFilePanel();
    } else {
      side.innerHTML = `${tabsHtml}<a href="#/" class="${active === "home" ? "active" : ""}"><span class="id">⌂</span><span>${esc(T.start)}</span></a>
        ${GROUPS.map(group).join("")}
        <h4>${esc(T.review)}</h4><a href="#/terms" class="${active === "terms" ? "active" : ""}"><span class="id">Aa</span><span>All key terms</span></a>
        ${AI ? `<a href="#/words" class="${active === "words" ? "active" : ""}"><span class="id">${esc(READER?.badge || "✎")}</span><span>My words <small class="count">${words().length || ""}</small></span></a>
        <a href="#/diagrams" class="${active === "diagrams" ? "active" : ""}"><span class="id">◇</span><span>My diagrams <small class="count">${diagrams().length || ""}</small></span></a>` : ""}`;
    }
    side.querySelectorAll(".side-tabs button").forEach((b) => b.onclick = () => { studio.tab = b.dataset.tab; renderSide(studio.lastActive); });
    const n = L.filter((l) => d[l.id]).length;
    const qs = quizState();
    let right = 0, total = 0;
    for (const l of L) (l.quiz || []).forEach((_, i) => { total++; if (qs[l.id + ":" + i] === true) right++; });
    document.getElementById("score").textContent = `${n}/${L.length} learned · quiz ${right}/${total}`;
  }

  function home() {
    const d = done();
    const card = (l) => `<a class="mcard ${d[l.id] ? "done" : ""}" href="#/${l.id}"><span class="id">${isIntro(l) ? "Start · " + esc(l.id) : esc(l.id)}${d[l.id] ? " · learned ✓" : ""}</span><strong>${esc(l.name)}</strong><span>${esc(l.tagline)}</span></a>`;
    const grid = (g) => { const ls = g.lessons.map((id) => byId[id]).filter(Boolean); return ls.length ? `<h2 class="gridh">${esc(g.title)}</h2>${g.blurb ? `<p class="gridp">${inline(g.blurb)}</p>` : ""}<div class="home-grid">${ls.map(card).join("")}</div>` : ""; };
    const samples = (H.sample_terms || [...XREF].slice(0, 1).concat(TERMS.filter((t) => t.length <= 22 && t.split(" ").length <= 2).slice(0, 2))).slice(0, 3).map((t) => `<i>${esc(t)}</i>`);
    const sampleText = samples.length ? ` like ${samples.length > 1 ? samples.slice(0, -1).join(", ") + " or " + samples[samples.length - 1] : samples[0]}` : "";
    main.innerHTML = `<div class="hero"><div class="kicker">${esc(H.kicker || A.title || "Academy")}</div>
      <h1>${esc(H.heading || "Start here")}</h1>
      <p class="tag">${inline(H.intro || `${L.length} lessons. Each one has the full content in plain language, a plain-words note under every part and a short quiz.`)}</p>
      ${!AI ? "" : `<p class="hint"><b>Stuck on a word?</b> Select it with the mouse (or double-click it) and press <span class="kbd">${TR_LABEL}</span>. ${READER ? `You get the ${esc(READER.name)}, what it means in that sentence, and a simpler ${esc(LANG)} version.` : "You get what it means in that sentence, in simpler words."} Save it to <a href="#/words">My words</a> to review later.</p>
      <p class="hint"><b>Want to see it?</b> Select a paragraph or a list of steps and press <span class="kbd">Visualize</span>. The local model draws it as boxes and arrows; save the ones you like to <a href="#/diagrams">My diagrams</a>.</p>
      <p class="hint"><b>Keep meeting the same word?</b> Select a term${sampleText} and press <span class="kbd">Mind map</span>. You see every place the lessons use it, grouped by idea, and can ask a question about it. Press <span class="kbd">Ask</span> on any selection to ask about that part.</p>`}</div>
      ${SPEECH ? `<p class="hint"><b>Rather listen?</b> In a lesson, press the small speaker beside a paragraph, or <span class="kbd">Listen</span> on a part's heading, and your computer reads it aloud. Pause, speed and voice are in the bar at the bottom.</p>` : ""}
      ${GROUPS.map(grid).join("")}
      <section class="syncbox" id="syncInfo" aria-live="polite"></section>
      ${H.source_note ? `<p class="videonote" style="margin-top:24px">${inline(H.source_note)}</p>` : ""}`;
    if (A.sync) showSync();
  }

  // Sync badge: written by the kit's sync.py every time it checks the source documents.
  async function showSync() {
    const box = document.getElementById("syncInfo");
    if (!box) return;
    let s;
    try { s = await (await fetch("assets/sync.json", { cache: "no-store" })).json(); } catch { return; }
    const when = (iso) => { try { return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); } catch { return iso || ""; } };
    if (s.status === "new") { box.innerHTML = `<h3>Updates from ${esc(s.label || "the source documents")}</h3><p>Not checked yet. The first sync check records the starting point.</p>`; return; }
    const state = s.status === "in_sync" ? `<span class="ok">In sync</span> with ${esc(s.repo)} at <code>${esc((s.synced_commit || "").slice(0, 7))}</code>`
      : s.status === "updating" ? `<span class="warn">Updating</span> ${esc((s.pending_lessons || []).join(", "))} from <code>${esc((s.remote_commit || "").slice(0, 7))}</code>`
      : `<span class="warn">Sync problem</span>${s.error ? ": " + esc(s.error) : ""}`;
    box.innerHTML = `<h3>Updates from ${esc(s.label || "the source documents")}</h3><p>${state} · last checked ${esc(when(s.checked_at))}</p>
      ${(s.history || []).length ? `<ul>${s.history.slice(0, 5).map((h) => `<li><b>${esc(when(h.at))}</b> · <code>${esc(h.commit)}</code>${h.lessons?.length ? " · " + h.lessons.map((id) => byId[id] ? `<a href="#/${id}">${id}</a>` : esc(id)).join(", ") : ""}${h.note ? " · " + esc(h.note) : ""}</li>`).join("")}</ul>` : ""}`;
  }

  function terms() {
    const all = [];
    for (const l of L) for (const t of l.key_terms || []) all.push({ ...t, id: l.id });
    all.sort((a, b) => a.term.localeCompare(b.term));
    main.innerHTML = `<div class="hero"><div class="kicker">Review</div><h1>All key terms</h1><p class="tag">Every key term from every lesson. Open a term's mind map to see everywhere it shows up.</p></div>
      <input class="search" id="q" placeholder="Filter terms…" aria-label="Filter terms">
      <div class="terms" id="tl">${all.map((t) => `<div class="term" data-k="${esc((t.term + " " + t.text).toLowerCase())}"><b>${esc(t.term)} <small>· ${esc(t.id)}</small></b>${inline(t.text)}<button type="button" class="tmind" data-t="${esc(t.term.replace(/\s*\(.*?\)/g, ""))}">✳ Mind map</button></div>`).join("")}</div>`;
    main.querySelectorAll(".tmind").forEach((b) => b.addEventListener("click", () => mindMap(cleanTerm(b.dataset.t) || b.dataset.t)));
    document.getElementById("q").addEventListener("input", (e) => {
      const v = e.target.value.toLowerCase();
      document.querySelectorAll("#tl .term").forEach((el) => { el.style.display = el.dataset.k.includes(v) ? "" : "none"; });
    });
  }

  function myWords() {
    const w = words();
    main.innerHTML = `<div class="hero"><div class="kicker">Review</div><h1>My words</h1>
      <p class="tag">Words and phrases you saved from the lessons, newest first.</p></div>
      ${w.length ? `<input class="search" id="q" placeholder="Filter my words…" aria-label="Filter my words">
      <div class="wlist" id="wl">${w.map((x, i) => `<div class="wcard" data-k="${esc((x.w + " " + (x.simple || x.simple_en || "")).toLowerCase())}">
        <div class="wtop"><b>${esc(x.w)}</b>${x.lesson && byId[x.lesson] ? `<a href="#/${x.lesson}">${esc(x.lesson)}</a>` : ""}<button class="wdel" data-i="${i}" aria-label="Remove ${esc(x.w)}">Remove</button></div>
        ${trLines(x)}
        ${x.ctx ? `<div class="ctx">“${esc(x.ctx)}”</div>` : ""}</div>`).join("")}</div>`
      : `<div class="empty"><p>No saved words yet.</p><p>In any lesson, select a word you don't know, press <span class="kbd">${TR_LABEL}</span>, then <span class="kbd">Save to My words</span>.</p></div>`}`;
    const q = document.getElementById("q");
    if (q) q.addEventListener("input", (e) => {
      const v = e.target.value.toLowerCase();
      document.querySelectorAll("#wl .wcard").forEach((el) => { el.style.display = el.dataset.k.includes(v) ? "" : "none"; });
    });
    main.querySelectorAll(".wdel").forEach((b) => b.addEventListener("click", () => {
      const list = words(); list.splice(+b.dataset.i, 1); store.set("words", list); renderSide("words"); myWords();
    }));
  }

  function lesson(l) {
    const idx = L.indexOf(l);
    const prev = L[idx - 1], next = L[idx + 1];
    const d = done();
    const blocks = [];
    let n = 0;
    const block = (anchor, title, html) => { n++; blocks.push({ anchor, title, html: `<section class="block" id="${anchor}" data-title="${esc(title)}"><h2><span class="n">${String(n).padStart(2, "0")}</span>${esc(title)}</h2>${html}</section>` }); };

    if (l.why) block("why", T.why, prose([l.why]));
    (l.sections || []).forEach((s, i) => block("s" + i, s.heading, prose(s.body) + plain(s.explain)));
    if (l.components?.length) block("components", T.components, `<table><thead><tr><th>${esc(T.component_col)}</th><th>${esc(T.what_col)}</th></tr></thead><tbody>${l.components.map((c) => `<tr><td class="name">${esc(c.name)}</td><td>${inline(c.text)}</td></tr>`).join("")}</tbody></table>`);
    if (l.boundary) block("boundary", T.boundary, `<div class="two"><div class="box own"><h3>${esc(T.owns)}</h3><ul>${(l.boundary.owns || []).map((x) => `<li>${inline(x)}</li>`).join("")}</ul></div><div class="box not"><h3>${esc(T.not_owns)}</h3><ul>${(l.boundary.not_owns || []).map((x) => `<li>${inline(x)}</li>`).join("")}</ul></div></div>${plain(l.boundary.explain)}`);
    if (l.relationships?.length) block("relationships", T.relationships, `<table><thead><tr><th>${esc(T.with_col)}</th><th>${esc(T.how_col)}</th></tr></thead><tbody>${l.relationships.map((r) => `<tr><td class="name">${linkIds(r.with)}</td><td>${inline(r.text)}</td></tr>`).join("")}</tbody></table>`);
    if (l.gates?.length) block("gates", T.gates, `<div class="gates">${l.gates.map((g) => `<div class="gate"><div class="g${XREF.has(g.gate) ? " xref" : ""}" data-t="${esc(g.gate)}"${XREF.has(g.gate) ? ` title="${esc(g.gate)}: see everywhere it shows up"` : ""}>${esc(g.gate)}</div><div>${inline(g.text)}</div></div>`).join("")}</div>`);
    if (l.example) block("example", T.example + (l.example.title ? ": " + l.example.title : ""), `<ol class="steps">${(l.example.steps || []).map((s) => `<li>${inline(s)}</li>`).join("")}</ol>${plain(l.example.explain)}`);
    if (l.pitfalls?.length) block("pitfalls", T.pitfalls, l.pitfalls.map((p) => `<div class="pit">${inline(p.text)}</div>`).join(""));
    if (l.key_terms?.length) block("terms", T.terms, `<div class="terms">${l.key_terms.map((t) => `<div class="term"><b>${esc(t.term)}</b>${inline(t.text)}</div>`).join("")}</div>`);
    if (l.quiz?.length) block("quiz", T.quiz, `<div class="quiz">${l.quiz.map((q, qi) => `<div class="q" data-q="${qi}"><p class="qt"><strong>${qi + 1}.</strong> ${inline(q.q)}</p><div class="opts">${q.options.map((o, oi) => `<button class="opt" data-o="${oi}">${inline(o)}</button>`).join("")}</div><div class="why"><div class="verdict"></div>${prose([q.why])}</div></div>`).join("")}</div><div class="actions"><button class="btn ghost" id="resetQuiz">Reset quiz</button></div>`);

    main.innerHTML = `<div class="hero"><div class="kicker">${esc(groupOf(l).title)} · ${isIntro(l) ? esc(T.intro) : esc(T.unit) + " " + esc(l.id)}</div>
      <h1>${esc(isIntro(l) ? l.name : l.id + " · " + l.name)}</h1>
      <p class="tag">${inline(l.tagline)}</p></div>
      ${hasVideo(l) ? `<div class="video"><video controls preload="metadata" playsinline src="videos/${l.id}.mp4${ver}">
        ${A.videos[l.id].captions ? `<track kind="captions" srclang="${esc(A.language?.code || "en")}" label="${esc(LANG)}" src="videos/${esc(A.videos[l.id].captions)}${ver}">` : ""}</video></div>
      <div class="videonote">${esc(T.video_note)}</div>` : ""}
      <div class="chips">${blocks.map((b) => `<a href="#/${l.id}/${b.anchor}">${esc(b.anchor === "example" ? T.example : b.title)}</a>`).join("")}</div>
      ${blocks.map((b) => b.html).join("")}
      <div class="actions">
        <button class="btn ${d[l.id] ? "doneb" : ""}" id="markDone">${d[l.id] ? "Learned ✓ (click to undo)" : "Mark as learned"}</button>
        ${prev ? `<a class="btn ghost" href="#/${prev.id}">← ${esc(prev.id)} ${esc(prev.name)}</a>` : ""}
        ${next ? `<a class="btn ghost" href="#/${next.id}">${esc(next.id)} ${esc(next.name)} →</a>` : ""}
      </div>`;

    document.getElementById("markDone").addEventListener("click", () => { const x = done(); x[l.id] = !x[l.id]; store.set("done", x); route(); });
    const qs = quizState();
    main.querySelectorAll(".quiz .q").forEach((qEl) => {
      const qi = +qEl.dataset.q, q = l.quiz[qi], key = l.id + ":" + qi;
      const show = (picked) => {
        qEl.classList.add("answered");
        qEl.querySelectorAll(".opt").forEach((b) => { b.disabled = true; const o = +b.dataset.o; if (o === q.answer) b.classList.add("right"); else if (o === picked) b.classList.add("wrong"); });
        qEl.querySelector(".verdict").textContent = picked === q.answer ? "Correct." : "Not quite. The highlighted answer is right.";
      };
      const prevPick = store.get("pick:" + key, null);
      if (prevPick !== null && qs[key] !== undefined) show(prevPick);
      qEl.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => {
        const o = +b.dataset.o, st = quizState(); st[key] = o === q.answer; store.set("quiz", st); store.set("pick:" + key, o); show(o); renderSide(l.id);
      }));
    });
    if (speech) speech.decorate(main);
    const rq = document.getElementById("resetQuiz");
    if (rq) rq.addEventListener("click", () => { const st = quizState(); l.quiz.forEach((_, i) => delete st[l.id + ":" + i]); store.set("quiz", st); route(); });
  }

  // ---- listen: a paragraph, a whole part or a selection is read aloud, by a voice on this computer.
  // First choice is the kit's natural voice (a local neural model behind speak/, started by serve.py).
  // Without it, only the system's high-quality voices are used: the basic ones sound like a machine,
  // and a browser's online voices would send the text to their maker, which an academy must never do.
  const SPEECH = A.speech === false ? null : Object.assign({ rate: 1 }, A.speech || {});
  const ICON_SAY = `<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M3 7.5h3l4-3.5v12l-4-3.5H3z" fill="currentColor"/><path d="M13 7a4 4 0 0 1 0 6M15 4.5a7.5 7.5 0 0 1 0 11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;
  const speech = (() => {
    if (!SPEECH) return null;
    const synth = window.speechSynthesis || null, lang = (A.language?.code || "en").toLowerCase();
    const prefs = store.get("speech", {});
    let entries = [], nItems = 0, at = -1, run = 0, paused = false, label = "";
    const rate = () => +prefs.rate || +SPEECH.rate || 1;

    // The natural voice: asked for once, on the first click.
    let natural = null;  // null = not asked yet, false = not running, else { voices, default }
    const audio = new Audio(), clips = new Map();
    async function findNatural() {
      if (natural !== null) return natural;
      try { const r = await fetch("speak/voices", { cache: "no-store" }); const j = r.ok ? await r.json() : null; natural = j && j.voices && j.voices.length ? j : false; } catch { natural = false; }
      return natural;
    }
    const nvoice = () => (natural.voices.includes(prefs.nvoice) ? prefs.nvoice : natural.voices.includes(SPEECH.voice) ? SPEECH.voice : natural.default);
    const PLACE = { a: "US", b: "UK", e: "ES", f: "FR", h: "HI", i: "IT", j: "JA", p: "PT", z: "ZH" };
    const nname = (v) => { const [code, name] = v.split("_"); return `${name ? name[0].toUpperCase() + name.slice(1) : v} · ${PLACE[code[0]] || code[0]}${code[1] === "f" ? ", woman" : code[1] === "m" ? ", man" : ""}`; };
    function clip(text) {  // one sentence -> a playable address; fetched once, the next one while this one plays
      const v = nvoice(), key = v + "|" + text;
      if (!clips.has(key)) {
        clips.set(key, fetch("speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, voice: v }) })
          .then((r) => { if (!r.ok) throw new Error("speak " + r.status); return r.blob(); }).then((b) => URL.createObjectURL(b)));
        clips.get(key).catch(() => clips.delete(key));
        if (clips.size > 80) { const old = clips.keys().next().value; clips.get(old).then((u) => URL.revokeObjectURL(u)).catch(() => {}); clips.delete(old); }
      }
      return clips.get(key);
    }

    // The system's own voices, as a second choice: installed ones only, and only the good ones unless the academy says otherwise.
    let voices = [];
    const keep = [];  // Chrome drops an utterance's events if nothing else holds on to it
    const GOOD = /premium|enhanced|natural|neural/i;
    const loadSys = () => { voices = !synth ? [] : synth.getVoices().filter((v) => v.localService && v.lang.toLowerCase().startsWith(lang) && (SPEECH.basic_voices || GOOD.test(v.name)))
      .sort((x, y) => (/premium/i.test(y.name) - /premium/i.test(x.name)) || x.name.localeCompare(y.name)); };
    const svoice = () => voices.find((v) => v.name === prefs.voice) || voices.find((v) => v.name === SPEECH.voice) || voices[0] || null;
    synth?.addEventListener?.("voiceschanged", loadSys);

    const bar = document.createElement("div");
    bar.className = "sbar"; bar.hidden = true; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Read aloud");
    bar.innerHTML = `<button type="button" class="sb-play" aria-label="Pause">❚❚</button><button type="button" class="sb-stop" aria-label="Stop reading">■</button><span class="sb-what" aria-live="polite"></span>
      <select class="sb-rate" aria-label="Reading speed">${[0.8, 0.9, 1, 1.1, 1.25, 1.5].map((r) => `<option value="${r}">${r}×</option>`).join("")}</select><select class="sb-voice" aria-label="Voice"></select>`;
    document.body.append(bar);
    const btnPlay = bar.querySelector(".sb-play"), what = bar.querySelector(".sb-what"), selRate = bar.querySelector(".sb-rate"), selVoice = bar.querySelector(".sb-voice");
    selRate.value = String(rate());
    const fillVoices = () => {
      const list = natural ? natural.voices.map((v) => [v, nname(v)]) : voices.map((v) => [v.name, v.name.replace(/\s*\((?:Enhanced|Premium)\)/i, "")]);
      const now = natural ? nvoice() : svoice()?.name;
      selVoice.innerHTML = list.map(([v, n]) => `<option value="${esc(v)}"${v === now ? " selected" : ""}>${esc(n)}</option>`).join("");
      selVoice.hidden = list.length < 2;
    };
    const controls = (on) => { btnPlay.hidden = selRate.hidden = !on; if (!on) selVoice.hidden = true; };
    const showPlay = () => { btnPlay.textContent = paused ? "▶" : "❚❚"; btnPlay.setAttribute("aria-label", paused ? "Continue" : "Pause"); };

    // Text is spoken sentence by sentence: the first one starts quickly, and long passages cannot stall.
    const chunks = (text) => { const out = []; let cur = ""; for (const s of text.split(/(?<=[.!?:;])\s+/)) { if (cur && (cur + " " + s).length > 150) { out.push(cur); cur = s; } else cur = cur ? cur + " " + s : s; } if (cur) out.push(cur); return out; };
    const mark = (el) => { document.querySelectorAll(".speaking").forEach((x) => x.classList.remove("speaking")); if (el) { el.classList.add("speaking"); const r = el.getBoundingClientRect(); if (r.top < 70 || r.bottom > innerHeight - 90) el.scrollIntoView({ block: "center", behavior: "smooth" }); } };
    const quiet = () => { synth?.cancel(); audio.pause(); audio.removeAttribute("src"); };
    function stop() { run++; quiet(); entries = []; at = -1; paused = false; mark(null); bar.hidden = true; }
    function fail(msg) { run++; quiet(); entries = []; at = -1; mark(null); controls(false); what.textContent = msg; bar.hidden = false; }
    function next() {
      at++;
      if (at >= entries.length) return stop();
      const my = run, e = entries[at];
      mark(e.el);
      what.textContent = label + (nItems > 1 ? ` · ${e.item + 1}/${nItems}` : "");
      if (natural) {
        if (entries[at + 1]) clip(entries[at + 1].text).catch(() => {});
        clip(e.text).then((url) => { if (my !== run) return; audio.src = url; audio.playbackRate = rate(); return audio.play(); })
          .catch(() => { if (my === run) fail("The voice stopped answering. Check that the academy's voice is still running."); });
      } else {
        const u = new SpeechSynthesisUtterance(e.text), v = svoice();
        u.voice = v; u.lang = v.lang; u.rate = rate();
        u.onend = () => { if (my === run) next(); };
        u.onerror = (ev) => { if (my === run && ev.error !== "interrupted" && ev.error !== "canceled") next(); };
        keep.push(u); if (keep.length > 40) keep.shift();
        synth.speak(u);
      }
    }
    audio.addEventListener("ended", () => { if (at >= 0) next(); });
    async function play(list, name) {
      stop();
      list = list.filter((x) => x.text);
      if (!list.length) return;
      const my = run;
      paused = false; showPlay(); controls(false); what.textContent = "Getting the voice ready…"; bar.hidden = false;
      await findNatural();
      if (my !== run) return;
      if (!natural) {
        loadSys();
        if (!svoice()) return fail(`No natural ${LANG} voice is available on this computer. Start the academy with the kit's serve.py and a Kokoro setup, or install a high-quality system voice.`);
      }
      entries = list.flatMap((it, i) => chunks(it.text).map((text) => ({ el: it.el, text, item: i })));
      nItems = list.length; label = name || "Reading"; at = -1;
      controls(true); fillVoices();
      setTimeout(() => { if (my === run) next(); }, 60);  // give a cancelled sentence a moment to end, or the first one can be swallowed
    }
    const again = () => { if (at < 0) return; run++; quiet(); paused = false; showPlay(); at--; const my = run; setTimeout(() => { if (my === run) next(); }, 60); };
    btnPlay.onclick = () => { paused = !paused; if (natural) { if (paused) audio.pause(); else audio.play(); } else if (paused) synth.pause(); else synth.resume(); showPlay(); };
    bar.querySelector(".sb-stop").onclick = stop;
    selRate.onchange = () => { prefs.rate = +selRate.value; store.set("speech", prefs); if (natural) audio.playbackRate = rate(); else again(); };
    selVoice.onchange = () => { prefs[natural ? "nvoice" : "voice"] = selVoice.value; store.set("speech", prefs); again(); };
    window.addEventListener("hashchange", stop);
    window.addEventListener("pagehide", quiet);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !bar.hidden) stop(); });

    // What a voice should say: no symbols it would stumble on, codes spaced so "L12" is read as a letter and a number.
    const clean = (t) => String(t || "").replace(/\s+/g, " ").replace(/→/g, " to ").replace(/\s&\s/g, " and ").replace(/[·|]/g, ", ").replace(/\s\/\s/g, ", ")
      .replace(/\be\.g\./gi, "for example").replace(/\bi\.e\./gi, "that is").replace(/\b([A-Z]{1,3})(\d{1,3})\b/g, "$1 $2").trim();
    const textOf = (el) => (el.matches("tr") ? [...el.cells].map((c) => clean(c.textContent)).filter(Boolean).join(". ")
      : el.matches(".term, .gate") ? [...el.childNodes].map((n) => clean(n.textContent)).filter(Boolean).join(". ")
      : (el.matches(".plain") ? "In plain words. " : "") + clean(el.textContent));
    const itemsOf = (el) => (el.matches("ul, ol") ? [...el.children] : [el]).map((x) => ({ el: x, text: textOf(x) }));
    const PART = ".en > p, .en > ul > li, .plain, .pit, ol.steps > li, tbody tr, .gate, .term, .box h3, .box li";
    // A small speaker beside every paragraph, list and note; a "Listen" button on every part's heading.
    function decorate(root) {
      root.querySelectorAll(".block .en > p, .block .en > ul, .block .plain, .block .pit, .block ol.steps, .hero .tag").forEach((el) => {
        const host = el.matches("ul, ol") ? el.firstElementChild : el;  // a list's speaker sits in its first item: a list may only hold items
        if (!host || el.closest(".quiz") || host.querySelector(":scope > .sp")) return;
        const b = document.createElement("button");
        b.type = "button"; b.className = "sp"; b.setAttribute("aria-label", "Read this aloud"); b.title = "Read this aloud"; b.innerHTML = ICON_SAY;
        b.addEventListener("click", (e) => { e.stopPropagation(); if (el.classList.contains("speaking") || el.querySelector(".speaking")) return stop(); play(itemsOf(el), el.closest(".block")?.dataset.title || "Reading"); });
        el.classList.add("sp-unit"); host.prepend(b);
      });
      root.querySelectorAll("section.block").forEach((sec) => {
        const h = sec.querySelector(":scope > h2");
        if (!h || sec.id === "quiz" || h.querySelector(".sp-all")) return;
        const b = document.createElement("button");
        b.type = "button"; b.className = "sp-all"; b.setAttribute("aria-label", `Listen to: ${sec.dataset.title}`); b.innerHTML = ICON_SAY + "<span>Listen</span>";
        b.addEventListener("click", () => { if (sec.querySelector(".speaking")) return stop(); play([{ el: h, text: clean(sec.dataset.title) }, ...[...sec.querySelectorAll(PART)].map((x) => ({ el: x, text: textOf(x) }))], sec.dataset.title); });
        h.append(b);
      });
    }
    return { decorate, stop, say: (text) => play([{ el: null, text: clean(text) }], "Your selection") };
  })();

  function linkIds(s) {
    return IDS.length ? esc(s).replace(lessonRx(), (m) => (byId[m] ? `<a href="#/${m}">${m}</a>` : m)) : esc(s);
  }

  // ---- translate / explain: glossary first (key terms), then the local model through Ollama.
  // Models are tried in order; a 404 means "not installed", so the next one gets a turn.
  async function askModel(messages, temperature) {
    let last = new Error("ai off");
    for (const model of AI ? AI.models : []) {
      const r = await fetch(AI.endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages, stream: false, format: "json", think: false, keep_alive: "30m", options: { temperature } }),
      });
      if (r.ok) return JSON.parse((await r.json()).message.content);
      last = new Error("http " + r.status);
      if (r.status !== 404) throw last;  // 404 = model not installed: try the next one
    }
    throw last;
  }
  const norm = (s) => String(s || "").toLowerCase().replace(/[`*“”"'’.,:;!?()[\]]/g, " ").replace(/\s+/g, " ").trim();
  const GLOSS = new Map();
  for (const l of L) for (const t of l.key_terms || []) {
    const v = { term: t.term, text: t.text, tr: t.tr, id: l.id };
    const k1 = norm(t.term), k2 = norm(t.term.replace(/\(.*?\)/g, ""));
    for (const k of [k1, k2]) if (k && !GLOSS.has(k)) GLOSS.set(k, v);
  }
  const glossary = (sel) => {
    const k = norm(sel);
    return GLOSS.get(k) || GLOSS.get(k.replace(/(es|s)$/, "")) || null;
  };
  const TR_LABEL = READER ? "Translate" : "Explain", TR_KEY = READER ? "t" : "e";
  const RTL = READER?.rtl ? "rtl" : "trl";
  const SYSTEM = READER
    ? `You are a ${LANG}-to-${READER.name} dictionary for a ${READER.name}-speaking reader of ${DOMAIN} documentation written in ${LANG}. ` +
      "The user gives a sentence and a word or phrase selected from it. Reply with JSON only, with exactly these keys:\n" +
      `"tr": the ${READER.name} equivalent of ONLY the selected words, 1 to 6 words, never the whole sentence;\n` +
      `"meaning": one short sentence IN ${READER.name.toUpperCase()} explaining what the selected words mean in this sentence;\n` +
      `"simple": the meaning of the selected words in simple ${LANG}, at most 12 words.\n` +
      `Keep technical terms, product names and ids as they are inside the ${READER.name} text.`
    : `You explain words to a reader of ${DOMAIN} documentation written in ${LANG}. ` +
      "The user gives a sentence and a word or phrase selected from it. Reply with JSON only, with exactly these keys:\n" +
      `"simple": the meaning of ONLY the selected words in simple ${LANG}, at most 12 words;\n` +
      `"meaning": one short sentence in simple ${LANG} explaining what the selected words mean in this sentence.`;
  // One worked example keeps a small model from translating the whole sentence. The reader-language
  // half comes from academy.json (reader.example), because it must be written in that language.
  const EX = Object.assign({ sentence: "Each loan has only one due date.", selected: "due date", simple: "the day the book must be back",
    meaning: "The book has to be returned by that one day." }, READER ? READER.example || {} : {});
  const EXAMPLE = READER && !(READER.example && READER.example.tr) ? [] : [
    { role: "user", content: `Sentence: "${EX.sentence}"\nSelected: "${EX.selected}"` },
    { role: "assistant", content: JSON.stringify(READER ? { tr: EX.tr, meaning: EX.meaning, simple: EX.simple } : { simple: EX.simple, meaning: EX.meaning }) },
  ];
  // Answers saved by older versions used fa / meaning_fa / simple_en.
  const aiShape = (o) => ({ tr: o.tr ?? o.fa ?? "", meaning: o.meaning ?? o.meaning_fa ?? "", simple: o.simple ?? o.simple_en ?? "" });
  const trLines = (x, labelled) => { const o = aiShape(x); return `${o.tr ? `<div class="${RTL} big" dir="auto">${esc(o.tr)}</div>` : ""}${o.meaning ? `<div class="${RTL}" dir="auto">${esc(o.meaning)}</div>` : ""}${o.simple ? `<div class="simple">${labelled && READER ? `In simple ${esc(LANG)}: ` : ""}${esc(o.simple)}</div>` : ""}`; };
  const cache = store.get("tcache2", {});
  async function translate(sel, ctx) {
    const key = norm(sel) + "|" + norm(ctx).slice(0, 160);
    if (cache[key]) return aiShape(cache[key]);
    const out = aiShape(await askModel([{ role: "system", content: SYSTEM }, ...EXAMPLE, { role: "user", content: `Sentence: "${ctx}"\nSelected: "${sel}"` }], 0.1));
    const keys = Object.keys(cache);
    if (keys.length > 400) delete cache[keys[0]];
    cache[key] = out; store.set("tcache2", cache);
    return out;
  }
  function contextOf(range, sel) {
    let el = range.commonAncestorContainer;
    if (el.nodeType !== 1) el = el.parentElement;
    const blockEl = el.closest("p, li, td, .plain, .pit, .term, .qt, .opt, .tag, h1, h2, h3") || el;
    const text = (blockEl.textContent || "").replace(/\s+/g, " ").trim();
    const parts = text.split(/(?<=[.!?])\s+/);
    const hit = parts.find((p) => p.toLowerCase().includes(sel.toLowerCase())) || text;
    return hit.length > 320 ? hit.slice(0, 320) + "…" : hit;
  }

  // The floating bar over a selection: Translate for a word or phrase, Visualize for a passage.
  const pill = document.createElement("div");
  pill.className = "tpill"; pill.hidden = true;
  pill.innerHTML = `<button type="button" class="tb-tr">${READER?.badge ? `<span class="${RTL}">${esc(READER.badge)}</span> ` : ""}${TR_LABEL} <span class="k">${TR_KEY.toUpperCase()}</span></button><button type="button" class="tb-mind"><span aria-hidden="true">✳</span> Mind map <span class="k">M</span></button><button type="button" class="tb-viz"><span aria-hidden="true">◇</span> Visualize <span class="k">V</span></button><button type="button" class="tb-ask"><span aria-hidden="true">?</span> Ask <span class="k">A</span></button><button type="button" class="tb-say">${ICON_SAY} Listen <span class="k">L</span></button>`;
  const btnTr = pill.querySelector(".tb-tr"), btnViz = pill.querySelector(".tb-viz"), btnMind = pill.querySelector(".tb-mind"), btnAsk = pill.querySelector(".tb-ask"), btnSay = pill.querySelector(".tb-say");
  const pop = document.createElement("div");
  pop.className = "tpop"; pop.hidden = true; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "Translation");
  document.body.append(pill, pop);
  let pending = null;

  function place(el, rect) {
    el.hidden = false;
    const w = el.offsetWidth, h = el.offsetHeight;
    let x = rect.left + window.scrollX + rect.width / 2 - w / 2;
    x = Math.max(window.scrollX + 12, Math.min(x, window.scrollX + document.documentElement.clientWidth - w - 12));
    let y = rect.top + window.scrollY - h - 10;
    if (rect.top - h - 10 < 64) y = rect.bottom + window.scrollY + 10;
    el.style.left = x + "px"; el.style.top = y + "px";
  }
  function hideAll() { pill.hidden = true; pop.hidden = true; pending = null; }

  function readSelection() {
    const s = window.getSelection();
    if (!s || s.isCollapsed || !s.rangeCount) return null;
    const text = s.toString().replace(/\s+/g, " ").trim();
    if (!text || text.length > 4000 || !/[a-z]/i.test(text)) return null;
    const range = s.getRangeAt(0);
    const node = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
    if (!main.contains(node) || node.closest("input, textarea, video")) return null;
    const canTr = text.length <= 120 && text.split(" ").length <= 12 && (!!AI || !!glossary(text));
    const canViz = !!AI && text.length >= 30;
    const term = text.length <= 60 ? cleanTerm(text) : null;
    const canMind = !!term && mentionsOf(term).length > 0;
    return { text, term, rect: range.getBoundingClientRect(), ctx: canTr ? contextOf(range, text) : "", block: node.closest(".block")?.id || "", canTr, canViz, canMind };
  }

  document.addEventListener("mouseup", (e) => {
    if (pop.contains(e.target) || pill.contains(e.target)) return;
    setTimeout(() => {
      const s = readSelection();
      if (!s) { if (!pop.contains(document.activeElement)) pill.hidden = true; return; }
      pending = s; pop.hidden = true; btnTr.hidden = !s.canTr; btnViz.hidden = !s.canViz; btnMind.hidden = !s.canMind; btnAsk.hidden = !AI; btnSay.hidden = !speech;
      if (!s.canTr && !s.canViz && !s.canMind && !AI && !speech) { pill.hidden = true; return; }
      place(pill, s.rect);
    }, 10);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { hideAll(); return; }
    const free = !e.metaKey && !e.ctrlKey && !e.altKey && !pill.hidden && pending && !/input|textarea/i.test(document.activeElement?.tagName || "");
    if (free && e.key.toLowerCase() === TR_KEY && pending.canTr) { e.preventDefault(); open(pending); }
    if (free && (e.key === "v" || e.key === "V") && pending.canViz) { e.preventDefault(); visualize(pending); }
    if (free && (e.key === "m" || e.key === "M") && pending.canMind) { e.preventDefault(); mindMap(pending.term); }
    if (free && AI && (e.key === "a" || e.key === "A")) { e.preventDefault(); askSelection(pending); }
    if (free && speech && (e.key === "l" || e.key === "L")) { e.preventDefault(); const t = pending.text; hideAll(); speech.say(t); }
  });
  document.addEventListener("mousedown", (e) => { if (!pop.contains(e.target) && !pill.contains(e.target)) { pop.hidden = true; } });
  window.addEventListener("hashchange", hideAll);
  pill.addEventListener("mousedown", (e) => e.preventDefault());
  btnTr.addEventListener("click", () => pending && open(pending));
  btnViz.addEventListener("click", () => pending && visualize(pending));
  btnMind.addEventListener("click", () => pending && mindMap(pending.term));
  btnAsk.addEventListener("click", () => pending && askSelection(pending));
  btnSay.addEventListener("click", () => { if (!pending || !speech) return; const t = pending.text; hideAll(); speech.say(t); });

  const OLLAMA_DOWN = "The local model isn't answering. Check that Ollama is running on this computer and the model is installed.";
  async function open(s) {
    pill.hidden = true;
    const lessonId = (location.hash.split("/")[1] || "");
    const g = glossary(s.text);
    const saved = () => words().some((x) => norm(x.w) === norm(s.text));
    let ai = null;
    const render = (state, err) => {
      pop.innerHTML = `<div class="tp-h"><b>${esc(s.text)}</b><button class="tp-x" type="button" aria-label="Close">×</button></div>
        ${g ? `<div class="tp-g"><div class="lbl">Key term · ${esc(g.id)}</div><div>${inline(g.text)}</div>${g.tr ? `<div class="${RTL}" dir="auto">${esc(g.tr)}</div>` : ""}</div>` : ""}
        ${!AI ? "" : `<div class="tp-ai">${state === "load" ? `<div class="lbl">Working on this computer…</div><div class="bar"></div>`
          : state === "err" ? `<div class="lbl">Local model</div><div class="tp-err">${esc(err)}</div>`
          : trLines(ai, true)}</div>`}
        <div class="tp-a"><button class="btn small" type="button" id="tpSave" ${saved() ? "disabled" : ""}>${saved() ? "Saved ✓" : "Save to My words"}</button></div>`;
      pop.querySelector(".tp-x").onclick = hideAll;
      pop.querySelector("#tpSave").onclick = () => {
        const list = words().filter((x) => norm(x.w) !== norm(s.text));
        list.unshift({ w: s.text, tr: ai?.tr || g?.tr || "", meaning: ai?.meaning || "", simple: ai?.simple || (g ? g.text : ""), ctx: s.ctx, lesson: byId[lessonId] ? lessonId : "", at: Date.now() });
        store.set("words", list.slice(0, 500));
        renderSide(byId[lessonId] ? lessonId : "home");
        render(ai ? "ok" : state, err);
      };
      place(pop, s.rect);
    };
    render("load");
    if (!AI) return;
    try { ai = await translate(s.text, s.ctx); render("ok"); }
    catch (e) {
      const msg = /http 5|Failed to fetch|NetworkError|http 404/i.test(String(e.message || e))
        ? OLLAMA_DOWN
        : "Could not read the answer. Try selecting a shorter phrase.";
      render("err", msg);
    }
  }

  // ---- visualize: the local model turns a passage into nodes and edges; Mermaid lays them out
  const diagrams = () => store.get("diagrams", []);
  const VIZ_SYSTEM = `You turn a passage from ${DOMAIN} documentation into a small diagram. Reply with JSON only:\n` +
    '{"title": "short title, max 6 words", "type": "flow" | "hierarchy" | "relations", ' +
    '"nodes": [{"id": "n1", "label": "max 5 words"}], "edges": [{"from": "n1", "to": "n2", "label": "max 3 words, or empty"}]}\n' +
    "Rules: 3 to 10 nodes. A node label says what the thing IS or DOES, using the passage's own words: when the passage names something by an id or code, combine the id with its role, like \"R4 Late fee\", never a bare id. " +
    "An edge label is the action between the two nodes, taken from the passage (\"stores\", \"routes for review\"). " +
    "Follow the order of hand-offs in the passage; never draw an edge the passage does not describe and never loop back to the start. " +
    "Numbered or ordered steps become a flow in that order. A thing made of parts becomes a hierarchy. Otherwise relations. " +
    "Every edge must connect two node ids you listed. Do not add anything that is not in the passage.";
  const VIZ_EXAMPLE = [
    { role: "user", content: 'Passage: "A member hands the book to the front desk. The desk scans it and closes the loan record. The book goes onto the sorting cart, and a volunteer puts it back on its shelf."' },
    { role: "assistant", content: JSON.stringify({ title: "From return to shelf", type: "flow", nodes: [{ id: "n1", label: "Member with book" }, { id: "n2", label: "Front desk" }, { id: "n3", label: "Loan record" }, { id: "n4", label: "Sorting cart" }, { id: "n5", label: "Shelf" }], edges: [{ from: "n1", to: "n2", label: "hands over" }, { from: "n2", to: "n3", label: "closes" }, { from: "n2", to: "n4", label: "sends on" }, { from: "n4", to: "n5", label: "reshelved" }] }) },
  ];
  async function askDiagram(text, fresh) {
    const key = "viz|" + norm(text).slice(0, 400);
    if (!fresh && cache[key]) return cache[key];
    const spec = await askModel([{ role: "system", content: VIZ_SYSTEM }, ...VIZ_EXAMPLE, { role: "user", content: `Passage: "${text}"` }], fresh ? 0.6 : 0.1);
    cache[key] = spec; store.set("tcache2", cache);
    return spec;
  }
  // Model output -> safe Mermaid source. Labels are quoted and stripped of syntax characters.
  function toMermaid(spec) {
    const clean = (s, n) => String(s || "").replace(/["`<>{}[\]|#;]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
    const nodes = (spec.nodes || []).filter((n) => n && n.id && n.label).slice(0, 14);
    const ids = new Map(nodes.map((n, i) => [String(n.id), "n" + i]));
    const edges = (spec.edges || []).filter((e) => e && ids.has(String(e.from)) && ids.has(String(e.to)) && e.from !== e.to);
    if (nodes.length < 2) throw new Error("too small");
    const def = (n) => `  ${ids.get(String(n.id))}("${clean(n.label, 60)}")`;
    const edgeLines = edges.map((e) => { const l = clean(e.label, 40); return `  ${ids.get(String(e.from))} -->${l ? `|"${l}"|` : ""} ${ids.get(String(e.to))}`; });
    return [`flowchart ${spec.type === "hierarchy" || nodes.length > 6 ? "TB" : "LR"}`, ...nodes.map(def), ...edgeLines].join("\n");
  }
  let mermaidReady = null;
  function loadMermaid() {
    if (mermaidReady) return mermaidReady;
    mermaidReady = new Promise((ok, bad) => {
      const s = document.createElement("script");
      s.src = "assets/vendor/mermaid.min.js";
      s.onload = () => ok(window.mermaid); s.onerror = () => { mermaidReady = null; bad(new Error("mermaid")); };
      document.head.append(s);
    });
    return mermaidReady;
  }
  let vizN = 0;
  async function drawInto(el, src) {
    const m = await loadMermaid();
    const css = getComputedStyle(document.body);
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const v = (name) => css.getPropertyValue(name).trim();  // the academy's theme, so diagrams match the page
    m.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", flowchart: { curve: "basis", htmlLabels: false },
      themeVariables: { primaryColor: v("--tint-light"), primaryBorderColor: v(dark ? "--tint" : "--brand"), primaryTextColor: v("--fg"),
        lineColor: v(dark ? "--fg3" : "--brand-60"), textColor: v("--fg"), edgeLabelBackground: v("--card"), fontFamily: css.fontFamily, fontSize: "16px" } });
    const { svg } = await m.render("viz" + ++vizN, src);
    el.innerHTML = svg;
  }

  // Mostly-linear flows (steps in order, maybe a branch or two) are drawn as a snake: rows of
  // four that turn back at each row end, so long step lists fit the screen. Webs go to Mermaid.
  function snakeOf(spec) {
    const nodes = (spec.nodes || []).filter((n) => n && n.id && n.label).slice(0, 14);
    const idx = new Map(nodes.map((n, i) => [String(n.id), i]));
    const edges = (spec.edges || []).filter((x) => x && idx.has(String(x.from)) && idx.has(String(x.to)) && x.from !== x.to)
      .map((x) => ({ a: idx.get(String(x.from)), b: idx.get(String(x.to)), label: x.label || "" }));
    if (spec.type === "hierarchy" || nodes.length < 5 || edges.length > nodes.length + 1) return null;  // trees look better top-down
    // topological order, ties broken by the model's own order; a cycle means "not a flow"
    const indeg = nodes.map(() => 0); edges.forEach((x) => indeg[x.b]++);
    const ready = nodes.map((_, i) => i).filter((i) => !indeg[i]), order = [];
    while (ready.length) { ready.sort((p, q) => p - q); const i = ready.shift(); order.push(i); edges.filter((x) => x.a === i).forEach((x) => { if (!--indeg[x.b]) ready.push(x.b); }); }
    if (order.length !== nodes.length) return null;
    const at = new Map(order.map((n, k) => [n, k]));
    const steps = edges.filter((x) => at.get(x.b) === at.get(x.a) + 1).length;
    if (steps < edges.length * 0.7) return null;
    return { nodes: order.map((i) => nodes[i]), edges: edges.map((x) => ({ a: at.get(x.a), b: at.get(x.b), label: x.label })) };
  }
  function wrapText(s, max) {
    const out = []; let line = "";
    for (const w of String(s).split(/\s+/)) { if ((line + " " + w).trim().length > max && line) { out.push(line); line = w; } else line = (line + " " + w).trim(); }
    if (line) out.push(line);
    return out.slice(0, 3);
  }
  function drawSnake(el, g) {
    const W = 220, H = 76, GX = 130, GY = 80, n = g.nodes.length, cols = Math.min(4, n), rows = Math.ceil(n / cols);
    const pos = g.nodes.map((_, i) => { const r = Math.floor(i / cols), c0 = i % cols, c = r % 2 ? cols - 1 - c0 : c0; return { x: c * (W + GX), y: r * (H + GY), r }; });
    const vw = cols * W + (cols - 1) * GX, vh = rows * H + (rows - 1) * GY;
    let s = `<svg class="chain" viewBox="-10 -10 ${vw + 20} ${vh + 20}" width="${vw + 20}" role="img"><defs><marker id="cah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="cah"/></marker></defs>`;
    let labels = "";
    const fit = (s, n) => { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
    for (const x of g.edges) {
      const a = pos[x.a], b = pos[x.b];
      let d, lx, ly, anchor = "middle", side = false;
      if (a.r === b.r && Math.abs(a.x - b.x) === W + GX) {           // neighbours on one row
        const dir = b.x > a.x ? 1 : -1, x1 = a.x + (dir > 0 ? W : 0), x2 = b.x + (dir > 0 ? -3 : W + 3), y = a.y + H / 2;
        d = `M${x1},${y} L${x2},${y}`; lx = (x1 + x2) / 2; ly = y - 8;
      } else if (a.x === b.x && b.r === a.r + 1) {                    // straight down at a row turn
        const x0 = a.x + W / 2; d = `M${x0},${a.y + H} L${x0},${b.y - 3}`; lx = x0 + 10; ly = (a.y + H + b.y) / 2 + 5; anchor = "start";
      } else {                                                       // a branch that skips ahead: curve under the row
        const x1 = a.x + W / 2, y1 = a.y + H, x2 = b.x + W / 2, y2 = b.r > a.r ? b.y - 3 : b.y + H + 3;
        // to a later row: bend through the gap between the rows; same row: dip under the row
        const mid = b.r > a.r ? (y1 + y2) / 2 : Math.max(y1, y2) + GY * 0.55;
        d = `M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}`; lx = (x1 + x2) / 2; ly = mid - 4; side = true;
      }
      s += `<path class="cedge${side ? " side" : ""}" d="${d}" marker-end="url(#cah)"/>`;
      // labels go on top of everything; a label between two boxes in a row must fit the gap
      if (x.label) labels += `<text class="clabel" x="${lx}" y="${ly}" text-anchor="${anchor}">${esc(fit(x.label, anchor === "start" ? 30 : side ? 26 : 17))}</text>`;
    }
    g.nodes.forEach((node, i) => {
      const p = pos[i], lines = wrapText(node.label, 24), y0 = p.y + H / 2 - (lines.length - 1) * 9;
      s += `<rect class="cnode${i === 0 ? " first" : ""}" x="${p.x}" y="${p.y}" width="${W}" height="${H}" rx="14"/>` +
        `<text class="cnum" x="${p.x + 12}" y="${p.y + 18}">${i + 1}</text>` +
        lines.map((l, k) => `<text class="ctext" x="${p.x + W / 2}" y="${y0 + k * 18 + 5}" text-anchor="middle">${esc(l)}</text>`).join("");
    });
    el.innerHTML = s + labels + "</svg>";
  }
  async function renderDiagram(el, spec) {
    const snake = snakeOf(spec);
    if (snake) drawSnake(el, snake);
    else await drawInto(el, toMermaid(spec));
  }

  const modal = document.createElement("div");
  modal.className = "vmodal"; modal.hidden = true; modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true"); modal.setAttribute("aria-label", "Diagram");
  document.body.append(modal);
  modal.addEventListener("mousedown", (e) => { if (e.target === modal) closeViz(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) closeViz(); });
  function closeViz() { modal.hidden = true; modal.innerHTML = ""; document.body.classList.remove("noscroll"); }
  window.addEventListener("hashchange", () => { if (!modal.hidden) closeViz(); });
  main.addEventListener("click", (e) => {
    const x = e.target.closest(".xref");
    if (!x || x.closest(".opt") || !window.getSelection()?.isCollapsed) return;
    mindMap(x.dataset.t);
  });

  async function visualize(s, fresh) {
    hideAll(); window.getSelection()?.removeAllRanges();
    const lessonId = (location.hash.split("/")[1] || "");
    modal.hidden = false; document.body.classList.add("noscroll");
    let spec = null, src = "";
    const frame = (body, actions) => {
      modal.innerHTML = `<div class="vbox"><div class="vh"><div><div class="lbl">Diagram of your selection · drawn on this computer</div><h2>${esc(spec?.title || "Reading the passage…")}</h2></div><button class="tp-x" type="button" aria-label="Close">×</button></div>
        <div class="vbody">${body}</div>
        <details class="vsrc"><summary>Selected text</summary><p>${esc(s.text)}</p></details>
        <div class="tp-a">${actions || ""}</div></div>`;
      modal.querySelector(".tp-x").onclick = closeViz;
    };
    frame(`<div class="vload"><div class="lbl">Turning the text into boxes and arrows…</div><div class="bar"></div><p class="simple">Usually 5–15 seconds.</p></div>`);
    try {
      spec = await askDiagram(s.text, fresh);
      src = toMermaid(spec);
      const saved = diagrams().some((d) => norm(d.src) === norm(s.text));
      frame(`<div class="vsvg" id="vsvg"></div>`,
        `<button class="btn small" type="button" id="vSave" ${saved ? "disabled" : ""}>${saved ? "Saved ✓" : "Save to My diagrams"}</button>
         <button class="btn small ghost" type="button" id="vAgain">Try another layout</button>
         <button class="btn small ghost" type="button" id="vCopy">Copy as Mermaid</button>`);
      await renderDiagram(document.getElementById("vsvg"), spec);
      modal.querySelector("#vAgain").onclick = () => visualize(s, true);
      modal.querySelector("#vCopy").onclick = async (e) => { try { await navigator.clipboard.writeText(src); e.target.textContent = "Copied ✓"; } catch { e.target.textContent = "Copy failed"; } };
      modal.querySelector("#vSave").onclick = (e) => {
        const list = diagrams().filter((d) => norm(d.src) !== norm(s.text));
        list.unshift({ title: spec.title || "Diagram", spec, mermaid: src, src: s.text, lesson: byId[lessonId] ? lessonId : "", at: Date.now() });
        store.set("diagrams", list.slice(0, 200));
        e.target.textContent = "Saved ✓"; e.target.disabled = true;
        renderSide(byId[lessonId] ? lessonId : "home");
      };
    } catch (e) {
      const down = /http 5|Failed to fetch|NetworkError|http 404/i.test(String(e.message || e));
      frame(`<div class="tp-err">${down ? OLLAMA_DOWN
        : e.message === "mermaid" ? "The diagram library did not load. Reload the page and try again."
        : "The model's answer could not be drawn. Try again, or select a shorter, more concrete passage."}</div>`,
        `<button class="btn small" type="button" id="vAgain">Try again</button>`);
      modal.querySelector("#vAgain").onclick = () => visualize(s, true);
    }
  }

  // ---- mind map: every place the lessons mention a term, grouped by idea, drawn as a two-sided tree.
  // The mentions are found here (exact text search); the model only groups them and must cite them.
  const md = (s) => String(s || "").replace(/\*\*|`/g, "").replace(/\s+/g, " ").trim();
  function* piecesOf(l) {  // [anchor, section title, text, probe = text as the page shows it]
    yield ["why", T.why, l.why];
    for (const [i, s] of (l.sections || []).entries()) { for (const b of [].concat(s.body || [])) yield ["s" + i, s.heading, b]; yield ["s" + i, s.heading, s.explain]; }
    for (const c of l.components || []) yield ["components", T.components, `${c.name}: ${c.text}`, c.text];
    for (const x of l.boundary?.owns || []) yield ["boundary", T.owns, x];
    for (const x of l.boundary?.not_owns || []) yield ["boundary", T.not_owns, x];
    yield ["boundary", T.boundary, l.boundary?.explain];
    for (const r of l.relationships || []) yield ["relationships", T.relationships, `${r.with}: ${r.text}`, r.text];
    for (const g of l.gates || []) yield ["gates", T.gates, `${g.gate}: ${g.text}`, g.text];
    for (const s of l.example?.steps || []) yield ["example", T.example, s];
    yield ["example", T.example, l.example?.explain];
    for (const p of l.pitfalls || []) yield ["pitfalls", T.pitfalls, p.text];
    for (const t of l.key_terms || []) yield ["terms", T.terms, `${t.term}: ${t.text}`, t.text];
  }
  const sentences = (text) => (text.length > 300 ? text.split(/(?<=[.!?])\s+/) : [text]);
  const isIdLike = (t) => /^[A-Z]{1,3}\d{1,3}[a-z]?$/.test(t);
  function termRx(term, flags = "") {
    const e = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
    return isIdLike(term) ? new RegExp(`(?<![\\w-])${e}(?![\\w-])`, "g" + flags) : new RegExp(`(?<![\\w-])${e}(?:s|es)?(?![\\w-])`, "gi" + flags);
  }
  function mentionsOf(term) {
    const rx = termRx(term), out = [], seen = new Set();
    for (const l of L) for (const [anchor, where, raw, probe] of piecesOf(l)) {
      for (const s of sentences(md(raw))) {
        rx.lastIndex = 0;
        if (!s || !rx.test(s) || seen.has(s)) continue;
        seen.add(s);
        out.push({ lesson: l.id, anchor, where, text: s.length > 300 ? s.slice(0, 299) + "…" : s, probe: sentences(md(probe || raw)).find((p) => s.includes(p.slice(0, 30))) || md(probe || raw) });
      }
    }
    return out;
  }
  // "Loans" and "Loan" are one term; trim punctuation the mouse picked up.
  function cleanTerm(text) {
    const t = text.replace(/^[^\w]+|[^\w)]+$/g, "").replace(/\s+/g, " ");
    if (!t || t.length > 60 || t.split(" ").length > 6) return null;
    const one = t.replace(/(?<=\w{3})(es|s)$/, "");
    return one !== t && mentionsOf(one).length > mentionsOf(t).length ? one : t;
  }
  // At most 45 notes for the model, taken in turn from each lesson so no lesson is dropped.
  function pickNotes(all, max = 45) {
    if (all.length <= max) return all;
    const by = new Map(); all.forEach((m, i) => { if (!by.has(m.lesson)) by.set(m.lesson, []); by.get(m.lesson).push(i); });
    const keep = new Set(), lists = [...by.values()];
    for (let k = 0; keep.size < max; k++) for (const li of lists) { if (li[k] !== undefined && keep.size < max) keep.add(li[k]); }
    return all.filter((_, i) => keep.has(i));
  }
  const noteLines = (notes) => notes.map((n, i) => `[${i + 1}] (${n.lesson} ${byId[n.lesson]?.name || ""}, ${n.where}) ${n.text}`).join("\n");
  const refsOf = (r, n) => [...new Set((String(JSON.stringify(r ?? "")).match(/\d+/g) || []).map(Number).filter((x) => x >= 1 && x <= n).map((x) => x - 1))];
  const MIND_SYSTEM = `You build a mind map that helps a reader see how one term connects to everything around it. The reader studies ${DOMAIN} lessons and remembers relations, not lists.\n` +
    "You get the term and numbered notes: every sentence in the lessons that mentions it, each with its lesson and section.\nReply with JSON only:\n" +
    '{"gist": "one plain sentence: what the term is, in general",\n "branches": [{"label": "max 4 words: one idea, role or aspect of the term", "children": [{"label": "max 7 words: a concrete fact, as a short phrase with a verb", "refs": [note numbers]}]}],\n' +
    ' "related": ["up to 6 other terms or ids that the notes connect to this term"]}\n' +
    "Rules: 3 to 6 branches, 2 to 5 children each. Group by MEANING, not by lesson: when the same term plays a different role in different lessons, make that visible (for example, one branch per kind of duty, with the lessons as children). " +
    'A child label names the lesson id when the fact belongs to one (like "L3: three extensions at most"). Every child cites the note numbers it comes from. Use only facts from the notes; never invent.\n' +
    'Never use vague labels like "General aspects" or "Operational role": say the actual fact ("fee stops after thirty days").';
  // One worked example (made-up notes) keeps the labels concrete.
  const MIND_EXAMPLE = [
    { role: "user", content: 'Term: "late fee"\nNotes:\n[1] (L3 Lending & Returns, Rules) A late fee starts the day after the due date and grows every day.\n[2] (L5 Membership, Rules) A member with unpaid late fees cannot borrow until they are paid.\n[3] (L3 Lending & Returns, Easy to get wrong) The late fee stops growing after thirty days, when the book counts as lost.\n[4] (L6 Children\'s Section, Rules) A child\'s card never gets a late fee; a reminder is sent instead.\n[5] (L7 Front Desk, Parts) The front desk may waive a late fee once a year for each member.' },
    { role: "assistant", content: JSON.stringify({ gist: "Money a member owes when a book comes back after its due date.", branches: [
      { label: "How it is charged", children: [{ label: "starts the day after the due date", refs: [1] }, { label: "stops growing after thirty days", refs: [3] }] },
      { label: "What it leads to", children: [{ label: "no borrowing until fees are paid", refs: [2] }, { label: "book counts as lost after thirty days", refs: [3] }] },
      { label: "Who is spared", children: [{ label: "L6: children get a reminder instead", refs: [4] }, { label: "L7: desk may waive it once a year", refs: [5] }] }],
      related: ["due date", "lost book", "L5", "reminder"] }) },
  ];
  async function askMind(term, notes) {
    const key = "mind|" + (window.LESSONS_BUILD || "") + "|" + term;
    if (cache[key]) return cache[key];
    const out = await askModel([{ role: "system", content: MIND_SYSTEM }, ...MIND_EXAMPLE, { role: "user", content: `Term: "${term}"\nNotes:\n${noteLines(notes)}` }], 0.1);
    const spec = {
      term, gist: String(out.gist || ""), related: [],
      branches: (Array.isArray(out.branches) ? out.branches : []).slice(0, 6).map((b) => ({ label: String(b?.label || ""),
        children: (Array.isArray(b?.children) ? b.children : []).slice(0, 5).map((c) => ({ label: String(c?.label || ""), refs: refsOf(c?.refs, notes.length) })).filter((c) => c.label) }))
        .filter((b) => b.label && b.children.length),
    };
    if (spec.branches.length < 2) throw new Error("too small");
    cache[key] = spec; store.set("tcache2", cache);
    return spec;
  }
  // Neighbours in the graph: lesson ids, codes and key terms that share sentences with the term.
  const TERMS = [...new Set(L.flatMap((l) => (l.key_terms || []).map((t) => t.term.replace(/\s*\(.*?\)/g, "").trim())))].filter((t) => t.length > 2);
  function neighbours(term, notes) {
    const count = new Map(), add = (k, i) => { if (!count.has(k)) count.set(k, new Set()); count.get(k).add(i); };
    const self = norm(term);
    notes.forEach((n, i) => {
      if (IDS.length) for (const m of n.text.matchAll(lessonRx())) if (m[1] !== term) add(m[1], i);
      if (CODE) for (const m of n.text.matchAll(codeRx())) if (m[1] !== term && !byId[m[1]]) add(m[1], i);
      for (const t of TERMS) if (norm(t) !== self && !norm(t).includes(self) && !self.includes(norm(t)) && termRx(t).test(n.text)) add(t, i);
    });
    return [...count].filter(([, s]) => s.size > 1 || notes.length < 6).sort((a, b) => b[1].size - a[1].size).slice(0, 10).map(([k, s]) => ({ term: k, n: s.size }));
  }
  // The instant view, no model: one branch per lesson, one leaf per section.
  function byLesson(term, notes) {
    const by = new Map();
    notes.forEach((n, i) => { if (!by.has(n.lesson)) by.set(n.lesson, new Map()); const g = by.get(n.lesson); if (!g.has(n.where)) g.set(n.where, []); g.get(n.where).push(i); });
    const short = (s, n) => (s.length > n ? s.slice(0, n - 1).replace(/\s+\S*$/, "") + "…" : s);
    return { term, gist: "", related: [], branches: [...by].slice(0, 12).map(([id, g]) => ({ label: `${id} ${byId[id]?.name || ""}`, lesson: id,
      children: [...g].slice(0, 4).map(([where, refs]) => ({ refs, label: refs.length > 1 ? `${where} (${refs.length})` : short(notes[refs[0]].text.replace(/^[A-Z]\d{1,2}: /, ""), 46) })) })) };
  }

  const measure = document.createElement("canvas").getContext("2d");
  const textW = (s, px) => { measure.font = `${px}px ${getComputedStyle(document.body).fontFamily}`; return measure.measureText(s).width; };
  // Two-sided tree: the term in the middle, ideas around it, facts at the ends with the lessons they come from.
  function drawMind(el, spec, notes, onPick) {
    const RH = 30, BG = 18, GAP = 60, fit = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
    const tagsOf = (refs) => { const ids = [...new Set(refs.map((r) => notes[r]?.lesson).filter(Boolean))]; return ids.length > 3 ? ids.slice(0, 3).join(" ") + " +" + (ids.length - 3) : ids.join(" "); };
    const bs = spec.branches.map((b, i) => ({ i, label: fit(b.label, 36), kids: b.children.map((c, j) => ({ j, label: fit(c.label, 50), tags: b.lesson ? "" : tagsOf(c.refs) })) }));
    const half = Math.ceil(bs.length / 2), cw = Math.max(120, textW(spec.term, 20) + 48);
    let edges = "", nodes = "";
    [bs.slice(0, half), bs.slice(half)].forEach((list, side) => {
      const dir = side ? -1 : 1, rows = list.reduce((a, b) => a + Math.max(1, b.kids.length), 0);
      let y = -(rows * RH + (list.length - 1) * BG) / 2;
      for (const b of list) {
        const k = Math.max(1, b.kids.length), by = y + (k * RH) / 2, bw = textW(b.label, 15) + 30;
        const x0 = dir * (cw / 2 + GAP), x1 = x0 + dir * bw, c = `--c:var(--m${b.i % 6})`;
        edges += `<path class="medge" style="${c}" d="M${dir * cw / 2},0 C${dir * (cw / 2 + GAP * 0.6)},0 ${x0 - dir * GAP * 0.6},${by} ${x0},${by}"/>`;
        nodes += `<g class="mbranch" data-b="${b.i}" style="${c}" tabindex="0" role="button"><rect x="${Math.min(x0, x1)}" y="${by - 15}" width="${bw}" height="30" rx="15"/><text x="${(x0 + x1) / 2}" y="${by + 5}" text-anchor="middle">${esc(b.label)}</text></g>`;
        b.kids.forEach((kid) => {
          const cy = y + kid.j * RH + RH / 2, cx = x1 + dir * 44, tag = kid.tags ? `<tspan class="mtag">${dir > 0 ? "  " : ""}${esc(kid.tags)}${dir > 0 ? "" : "  "}</tspan>` : "";
          edges += `<path class="medge thin" style="${c}" d="M${x1},${by} C${x1 + dir * 24},${by} ${cx - dir * 24},${cy} ${cx - dir * 6},${cy}"/>`;
          nodes += `<g class="mleaf" data-b="${b.i}" data-c="${kid.j}" style="${c}" tabindex="0" role="button"><circle cx="${cx}" cy="${cy}" r="4.5"/>` +
            `<text x="${cx + dir * 11}" y="${cy + 5}" text-anchor="${dir > 0 ? "start" : "end"}">${dir > 0 ? esc(kid.label) + tag : tag + esc(kid.label)}</text></g>`;
        });
        y += k * RH + BG;
      }
    });
    nodes += `<g class="mroot" tabindex="0" role="button"><rect x="${-cw / 2}" y="-24" width="${cw}" height="48" rx="24"/><text x="0" y="7" text-anchor="middle">${esc(spec.term)}</text></g>`;
    el.innerHTML = `<svg class="mind" role="img" aria-label="Mind map of ${esc(spec.term)}">${edges}${nodes}</svg>`;
    const svg = el.querySelector("svg"), bb = svg.getBBox();
    svg.setAttribute("viewBox", `${bb.x - 14} ${bb.y - 14} ${bb.width + 28} ${bb.height + 28}`);
    svg.setAttribute("width", Math.round(bb.width + 28));
    if (!onPick) return;
    const pick = (g) => {
      svg.querySelectorAll(".on").forEach((x) => x.classList.remove("on")); g.classList.add("on");
      if (g.classList.contains("mroot")) return onPick({ title: spec.term, refs: notes.map((_, i) => i) });
      const b = spec.branches[+g.dataset.b];
      if (g.dataset.c === undefined) return onPick({ title: b.label, refs: [...new Set(b.children.flatMap((c) => c.refs))] });
      const c = b.children[+g.dataset.c]; onPick({ title: c.label, refs: c.refs });
    };
    svg.querySelectorAll(".mroot, .mbranch, .mleaf").forEach((g) => {
      g.addEventListener("click", () => pick(g));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(g); } });
    });
  }

  // Where the lessons say it: each note links to its section and lights up the sentence there.
  let flashText = "";
  function notesHtml(refs, notes, term) {
    const rx = term ? termRx(term) : null;
    return `<ol class="mnotes">${refs.map((r) => notes[r]).filter(Boolean).map((n) => `<li><a href="#/${n.lesson}/${n.anchor}" data-probe="${esc(n.probe || n.text)}">${esc(n.lesson)} · ${esc(n.where)}</a> <span>${rx ? esc(n.text).replace(rx, (m) => `<mark>${m}</mark>`) : esc(n.text)}</span></li>`).join("")}</ol>`;
  }
  function wireNoteLinks(root) {
    root.querySelectorAll("a[data-probe]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); flashText = a.dataset.probe; const h = a.getAttribute("href");
      closeViz(); if (location.hash === h) route(); else location.hash = h;
    }));
  }

  // Ask: a question answered by the local model from the given notes only, with its sources.
  const ASK_SYSTEM = `You answer a learner's question about ${DOMAIN} lessons using ONLY the numbered notes. Reply with JSON only:\n` +
    '{"answer": "2 to 5 short, plain sentences", "refs": [the note numbers you used]}\n' +
    "Answer in the language of the question; keep technical terms and ids exactly as the notes write them. Explain simply, like a friendly senior colleague. " +
    "If the notes do not answer it, say what they do say and that the lessons do not cover the rest. Never invent facts, names, dates or numbers.";
  function askBox(root, notes, term, hint) {
    root.innerHTML = `<form class="ask"><input type="text" placeholder="${esc(hint)}" aria-label="Your question" autocomplete="off"><button class="btn small" type="submit">Ask</button></form><div class="athread"></div>`;
    const form = root.querySelector("form"), input = form.querySelector("input"), thread = root.querySelector(".athread");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = input.value.trim(); if (!q) return;
      input.value = "";
      const item = document.createElement("div"); item.className = "aitem";
      item.innerHTML = `<div class="aq" dir="auto">${esc(q)}</div><div class="aa"><div class="lbl">Thinking on this computer…</div><div class="bar"></div></div>`;
      thread.prepend(item);
      const aa = item.querySelector(".aa");
      try {
        const out = await askModel([{ role: "system", content: ASK_SYSTEM }, { role: "user", content: `Notes:\n${noteLines(notes)}\n\nQuestion: ${q}${READER?.detect && new RegExp(READER.detect).test(q) ? `\n\nThe question is in ${READER.name}: write the answer in ${READER.name} (keep ids and technical terms as they are).` : ""}` }], 0.2);
        const refs = refsOf(out.refs, notes.length);
        aa.innerHTML = `<p dir="auto">${esc(String(out.answer || "").replace(/\s*\[(?:\d+[,\s]*)+\]/g, ""))}</p>${refs.length ? `<details><summary>From ${refs.length} place${refs.length > 1 ? "s" : ""} in the lessons</summary>${notesHtml(refs, notes, term)}</details>` : ""}`;
        wireNoteLinks(aa);
      } catch (err) {
        aa.innerHTML = `<div class="tp-err">${/http 5|Failed to fetch|NetworkError|http 404/i.test(String(err.message || err)) ? OLLAMA_DOWN : "Could not read the answer. Try asking it another way."}</div>`;
      }
    });
    return input;
  }

  let trail = [];
  async function mindMap(term, opts = {}) {
    hideAll(); window.getSelection()?.removeAllRanges();
    if (!opts.keepTrail) trail = [];
    const all = opts.notes ? null : mentionsOf(term);
    const notes = opts.notes || pickNotes(all);
    const lessons = [...new Set(notes.map((n) => n.lesson))];
    const g = glossary(term), lessonSpec = byLesson(term, notes), rel = neighbours(term, notes);
    let idea = opts.idea || null, view = "lesson", touched = false;
    modal.hidden = false; document.body.classList.add("noscroll");
    modal.innerHTML = `<div class="vbox mbox"><div class="vh">${trail.length ? `<button class="btn small ghost" type="button" id="mBack">← ${esc(trail[trail.length - 1])}</button>` : ""}
        <div><div class="lbl">Mind map · ${all && all.length > notes.length ? `${notes.length} of ${all.length}` : notes.length} mentions in ${lessons.length} lesson${lessons.length > 1 ? "s" : ""}</div><h2>${esc(term)}</h2></div><button class="tp-x" type="button" aria-label="Close">×</button></div>
      <p class="mgist" id="mGist"></p>
      <div class="mtabs" role="tablist"><button type="button" role="tab" data-v="idea">By idea <span id="mIdeaState"></span></button><button type="button" role="tab" data-v="lesson">By lesson</button></div>
      <div class="vsvg" id="mSvg"></div>
      <div class="mdet" id="mDet"></div>
      <div class="mrel" id="mRel"></div>
      <div class="mask" id="mAsk"></div>
      <div class="tp-a"><button class="btn small" type="button" id="mSave">Save to My diagrams</button></div></div>`;
    modal.querySelector(".tp-x").onclick = closeViz;
    const back = modal.querySelector("#mBack");
    if (back) back.onclick = () => mindMap(trail.pop(), { keepTrail: true });
    const det = modal.querySelector("#mDet"), state = modal.querySelector("#mIdeaState");
    const showDet = (p) => { det.innerHTML = `<div class="lbl">${esc(p.title)} · where the lessons say it</div>${notesHtml(p.refs, notes, term)}`; wireNoteLinks(det); };
    const idle = () => { det.innerHTML = `<p class="simple">Click the term, an idea or a fact to see the sentences behind it. Each one links to its place in the lesson.</p>`; };
    const draw = () => {
      modal.querySelectorAll(".mtabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.v === view)));
      const spec = view === "idea" && idea ? idea : lessonSpec;
      modal.querySelector("#mGist").innerHTML = g ? `<b>Key term (${esc(g.id)}):</b> ${inline(g.text)}` : idea?.gist ? `<b>In general:</b> ${esc(idea.gist)}` : "";
      if (view === "idea" && !idea) modal.querySelector("#mSvg").innerHTML = state.dataset.err ? `<div class="tp-err">${esc(state.dataset.err)}</div>` : `<div class="vload"><div class="lbl">Grouping ${notes.length} mentions by idea…</div><div class="bar"></div><p class="simple">Usually 10–25 seconds. The lesson view is ready now.</p></div>`;
      else drawMind(modal.querySelector("#mSvg"), spec, notes, showDet);
      idle();
      modal.querySelector("#mRel").innerHTML = rel.length ? `<span class="lbl">Often together with</span> ${rel.map((r) => `<button type="button" class="chip" data-t="${esc(r.term)}" title="In ${r.n} of the same sentences">${esc(r.term)} <small>${r.n}</small></button>`).join("")}` : "";
      modal.querySelectorAll("#mRel .chip").forEach((b) => b.onclick = () => { trail.push(term); mindMap(b.dataset.t.replace(/\s*\(.*?\)/g, ""), { keepTrail: true }); });
    };
    modal.querySelectorAll(".mtabs button").forEach((b) => b.onclick = () => { touched = true; view = b.dataset.v; draw(); });
    if (AI) askBox(modal.querySelector("#mAsk"), notes, term, `Ask about ${term}, e.g. "Why does it differ between lessons?"`);
    const saved = () => diagrams().some((d) => d.kind === "mind" && norm(d.title) === norm(term));
    const saveBtn = modal.querySelector("#mSave");
    const syncSave = () => { saveBtn.disabled = saved(); saveBtn.textContent = saved() ? "Saved ✓" : "Save to My diagrams"; };
    syncSave();
    saveBtn.onclick = () => {
      const lessonId = location.hash.split("/")[1] || "";
      const list = diagrams().filter((d) => !(d.kind === "mind" && norm(d.title) === norm(term)));
      list.unshift({ kind: "mind", title: term, idea, notes, src: term, lesson: byId[lessonId] ? lessonId : "", at: Date.now() });
      store.set("diagrams", list.slice(0, 200)); syncSave(); renderSide(byId[lessonId] ? lessonId : location.hash.split("/")[1] || "home");
    };
    if (idea) { view = "idea"; draw(); return; }
    if (!AI) {  // no local model: the exact-search view is the whole mind map
      modal.querySelector(".mtabs").hidden = true; saveBtn.hidden = true; draw(); return;
    }
    state.textContent = "…"; draw();
    try {
      idea = await askMind(term, notes);
      state.textContent = "";
      if (!modal.hidden && modal.querySelector("h2")?.textContent === term && (!touched || view === "idea")) { view = "idea"; draw(); }
    } catch (e) {
      state.textContent = "!";
      state.dataset.err = /http 5|Failed to fetch|NetworkError|http 404/i.test(String(e.message || e)) ? OLLAMA_DOWN + " The lesson view still works." : "The model's grouping could not be read. The lesson view still works.";
      if (view === "idea") draw();
    }
  }

  // Ask about a passage: the selection plus the rest of its section are the notes.
  function askSelection(s) {
    hideAll(); window.getSelection()?.removeAllRanges();
    const l = byId[location.hash.split("/")[1] || ""];
    const notes = [{ lesson: l?.id || "", anchor: s.block || "", where: "Your selection", text: s.text, probe: s.text }];
    if (l) for (const [anchor, where, raw, probe] of piecesOf(l)) if (anchor === s.block) for (const t of sentences(md(raw))) if (t && !s.text.includes(t)) notes.push({ lesson: l.id, anchor, where, text: t, probe: md(probe || raw) });
    modal.hidden = false; document.body.classList.add("noscroll");
    modal.innerHTML = `<div class="vbox abox"><div class="vh"><div><div class="lbl">Ask about your selection · answered on this computer from the lesson text</div><h2>${esc(s.text.length > 90 ? s.text.slice(0, 89) + "…" : s.text)}</h2></div><button class="tp-x" type="button" aria-label="Close">×</button></div>
      <div id="aBox"></div><p class="simple">The answer uses only this part of ${l ? esc(l.id) : "the lesson"}. For how a term works across all lessons, select just the term and press <span class="kbd">Mind map</span>.</p></div>`;
    modal.querySelector(".tp-x").onclick = closeViz;
    askBox(modal.querySelector("#aBox"), notes.slice(0, 40), null, s.text.length < 40 ? `What do you want to know about "${s.text}"?` : "What is unclear about this part?").focus();
  }

  function myDiagrams() {
    const list = diagrams();
    main.innerHTML = `<div class="hero"><div class="kicker">Review</div><h1>My diagrams</h1>
      <p class="tag">Diagrams and mind maps you saved, newest first.</p></div>
      ${list.length ? `<div class="dlist">${list.map((d, i) => `<section class="block dcard"><div class="wtop"><b>${esc(d.title)}</b>${d.lesson && byId[d.lesson] ? `<a href="#/${d.lesson}">${esc(d.lesson)}</a>` : ""}<button class="wdel" data-i="${i}" aria-label="Remove ${esc(d.title)}">Remove</button></div>
        <div class="vsvg" data-i="${i}"><div class="bar"></div></div>${d.kind === "mind" ? `<p class="simple">Mind map of ${d.notes.length} mentions. Click it to open, explore and ask.</p>` : `<details class="vsrc"><summary>Selected text</summary><p>${esc(d.src)}</p></details>`}</section>`).join("")}</div>`
      : `<div class="empty"><p>No saved diagrams yet.</p><p>In any lesson, select a paragraph or a list of steps, press <span class="kbd">Visualize</span>, then <span class="kbd">Save to My diagrams</span>.</p></div>`}`;
    main.querySelectorAll(".wdel").forEach((b) => b.addEventListener("click", () => { const l = diagrams(); l.splice(+b.dataset.i, 1); store.set("diagrams", l); renderSide("diagrams"); myDiagrams(); }));
    (async () => { for (const el of main.querySelectorAll(".vsvg[data-i]")) { try { const d = list[+el.dataset.i];
      if (d.kind === "mind") { drawMind(el, d.idea || byLesson(d.title, d.notes), d.notes, () => mindMap(d.title, { notes: d.notes, idea: d.idea })); }
      else if (d.spec) await renderDiagram(el, d.spec); else await drawInto(el, d.mermaid); } catch { el.textContent = "Could not draw this diagram."; } } })();
  }

  // ---- GitHub App Studio: Connect org repo, list doc files in left sidebar, generate academy
  const connectBtn = document.getElementById("connectBtn");
  const connectLabel = document.getElementById("connectLabel");
  async function apiJson(url, opts) {
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  function updateConnectBadge() {
    if (!connectBtn) return;
    const repo = studio.status?.connected?.repo;
    connectBtn.classList.toggle("connected", !!repo);
    connectLabel.textContent = repo ? repo : "Connect";
  }

  async function refreshRepoFiles() {
    if (!studio.available) return;
    const d = await apiJson(`/api/github/files?include_code=${studio.includeCode ? 1 : 0}`);
    studio.files = d.files || [];
    if (!studio.selected.size) studio.files.filter((f) => f.is_doc).forEach((f) => studio.selected.add(f.path));
    renderSide(studio.lastActive);
  }

  function bindFilePanel() {
    const qEl = document.getElementById("fileFilter");
    if (qEl) qEl.oninput = (e) => { studio.filter = e.target.value; renderSide(studio.lastActive); document.getElementById("fileFilter")?.focus(); };
    document.getElementById("incCode")?.addEventListener("change", async (e) => {
      studio.includeCode = e.target.checked;
      await refreshRepoFiles().catch(() => {});
    });
    document.getElementById("filesRefresh")?.addEventListener("click", () => refreshRepoFiles().catch(() => {}));
    document.getElementById("selAll")?.addEventListener("click", () => { studio.files.forEach((f) => studio.selected.add(f.path)); renderSide(studio.lastActive); });
    document.getElementById("selDocs")?.addEventListener("click", () => { studio.selected = new Set(studio.files.filter((f) => f.is_doc).map((f) => f.path)); renderSide(studio.lastActive); });
    document.getElementById("selNone")?.addEventListener("click", () => { studio.selected.clear(); renderSide(studio.lastActive); });
    side.querySelectorAll(".fchk").forEach((c) => c.onchange = () => {
      if (c.checked) studio.selected.add(c.dataset.p); else studio.selected.delete(c.dataset.p);
      const b = document.getElementById("genBtn");
      if (b) { b.disabled = !studio.selected.size; b.textContent = `Create Academy (${studio.selected.size})`; }
    });
    side.querySelectorAll(".file-name").forEach((b) => b.onclick = () => previewRepoFile(b.dataset.p));
    document.getElementById("genBtn")?.addEventListener("click", () => generateFromSelected());
  }

  async function previewRepoFile(relPath) {
    try {
      const f = await apiJson(`/api/github/file?path=${encodeURIComponent(relPath)}`);
      main.innerHTML = `<div class="hero"><div class="kicker">Repository Document · ${esc(studio.status?.connected?.repo || "")}</div>
        <h1>${esc(relPath)}</h1></div>
        <div class="actions"><button type="button" class="btn small" id="prevToggle">${studio.selected.has(relPath) ? "Included in build ✓" : "Include in build"}</button>
        <button type="button" class="btn small ghost" id="prevBack">Back to Academy</button></div>
        <pre class="gh-preview">${esc(f.content)}${f.truncated ? "\n\n… (truncated for preview)" : ""}</pre>`;
      document.getElementById("prevToggle").onclick = () => {
        if (studio.selected.has(relPath)) studio.selected.delete(relPath); else studio.selected.add(relPath);
        renderSide(studio.lastActive); previewRepoFile(relPath);
      };
      document.getElementById("prevBack").onclick = () => route();
    } catch (e) {
      main.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    }
  }

  async function generateFromSelected() {
    const files = [...studio.selected];
    if (!files.length) return;
    const model = document.getElementById("genModel")?.value || "";
    try {
      const res = await apiJson("/api/academy/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files, model }),
      });
      studio.job = { id: res.job_id, status: "running", stage: "starting", current: "Starting…", logs: [] };
      renderSide(studio.lastActive);
      const poll = async () => {
        const j = await apiJson(`/api/jobs/${res.job_id}`);
        studio.job = j;
        renderSide(studio.lastActive);
        if (j.status === "running") { setTimeout(poll, 1000); return; }
        if (j.status === "done") {
          studio.tab = "lessons";
          location.hash = "#/";
          location.reload();
        }
      };
      setTimeout(poll, 700);
    } catch (e) {
      studio.job = { status: "error", error: e.message };
      renderSide(studio.lastActive);
    }
  }

  function downloadIconPng() {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = 512; c.height = 512;
      c.getContext("2d").drawImage(img, 0, 0, 512, 512);
      c.toBlob((blob) => {
        if (!blob) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "academy-kit-icon.png";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      }, "image/png");
    };
    img.src = "assets/icon.svg";
  }

  async function openConnectModal() {
    hideAll();
    modal.hidden = false; document.body.classList.add("noscroll");
    try { studio.status = await apiJson("/api/github/status"); studio.available = true; } catch { studio.available = false; }
    if (!studio.available) {
      modal.innerHTML = `<div class="vbox gh-modal"><div class="vh"><div class="gh-brand"><img src="assets/icon.svg" alt="" width="44" height="44"><div><div class="lbl">GitHub Studio</div><h2>Local Server Required</h2></div></div><button class="tp-x" type="button" aria-label="Close">×</button></div>
        <p class="simple">Start this academy with <code>python3 skills/academy/engine/serve.py</code> to connect GitHub organizations, browse files, and build academies locally.</p></div>`;
      modal.querySelector(".tp-x").onclick = closeViz;
      return;
    }
    const app = studio.status?.app || {};
    const defWs = studio.status?.default_workspace || "~/academies";
    const langs = studio.status?.languages || ["German", "Persian", "Arabic", "French", "Spanish", "Turkish", "Polish", "Russian", "Ukrainian", "Hindi", "Chinese", "Hebrew", "English"];
    const langOptions = `<option value="">None (lessons only)</option>` + langs.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("");
    const workspaces = studio.status?.workspaces || [];
    const wsHtml = workspaces.length > 1 ? `<div class="gh-card">
      <div class="gh-row"><strong>Workspaces</strong><span class="simple">Each repository lives in its own isolated academy folder</span></div>
      <div class="gh-row"><select id="wsSel" style="flex:1;min-width:0;font:inherit;font-size:14px;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)">${workspaces.map((w) => `<option value="${esc(w.dir)}" ${w.active ? "selected" : ""}>${esc(w.title)}${w.repo ? ` · ${esc(w.repo)}` : ""} (${w.lessons} lessons)</option>`).join("")}</select>
        <button type="button" class="btn small ghost" id="wsOpenBtn">Switch Workspace</button></div>
    </div>` : "";
    const urlInner = `<div class="gh-grid">
      <label class="gh-field full">Repository URL<input id="urlRepo" placeholder="https://github.com/org/docs-repo" value="${esc(studio.status?.connected?.repo_url || "")}"></label>
      <label class="gh-field">Branch (optional)<input id="urlBranch" placeholder="main" value="${esc(studio.status?.connected?.branch || "")}"></label>
      <label class="gh-field">Docs subfolder (optional)<input id="urlDocs" placeholder="docs" value="${esc(studio.status?.connected?.docs_root || "")}"></label>
      <label class="gh-field">Reader language<select id="urlReader">${langOptions}</select></label>
      <label class="gh-field">Workspace folder (auto-filled)<input id="urlOut" placeholder="${esc(defWs)}/org/repo" value="${esc(studio.status?.connected?.academy_dir || "")}"></label>
    </div>
    <div class="gh-row"><span class="tp-err" id="urlErr"></span><button type="button" class="btn small" id="urlConnectBtn">Fetch Repository Files</button></div>`;
    const urlBlock = app.configured
      ? `<details class="gh-card" id="ghUrlCard"><summary style="cursor:pointer;font-size:14px;color:var(--fg2)">Or connect by custom Git URL</summary>${urlInner}</details>`
      : `<div class="gh-card" id="ghUrlCard"><div class="gh-row"><strong>Or connect by repository URL</strong><span class="simple">Works for public repos or local git credentials</span></div>${urlInner}</div>`;
    modal.innerHTML = `<div class="vbox gh-modal"><div class="vh"><div class="gh-brand"><img src="assets/icon.svg" alt="" width="44" height="44"><div><div class="lbl">GitHub App Integration · Private &amp; Local-First</div><h2>Connect GitHub Repository</h2></div></div><button class="tp-x" type="button" aria-label="Close">×</button></div>
      ${wsHtml}<div id="ghAppArea"></div>${urlBlock}</div>`;
    modal.querySelector(".tp-x").onclick = closeViz;

    modal.querySelector("#wsOpenBtn")?.addEventListener("click", async () => {
      const dir = modal.querySelector("#wsSel").value;
      const res = await apiJson("/api/academies/switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ academy_dir: dir }) });
      if (res.built) { location.reload(); return; }
      studio.status = res.status;
      await refreshRepoFiles().catch(() => {});
      studio.tab = "files";
      updateConnectBadge();
      closeViz();
      renderSide(studio.lastActive);
    });

    const urlRepoEl = modal.querySelector("#urlRepo");
    const urlOutEl = modal.querySelector("#urlOut");
    let urlOutTouched = false;
    urlOutEl?.addEventListener("input", () => { urlOutTouched = true; });
    urlRepoEl?.addEventListener("input", () => {
      if (urlOutTouched) return;
      const parts = urlRepoEl.value.trim().replace(/^https?:\/\/[^/]+\/|\.git$/g, "").split("/").filter(Boolean);
      if (parts.length >= 2) urlOutEl.value = `${defWs}/${parts[parts.length - 2].toLowerCase()}/${parts[parts.length - 1].toLowerCase()}`;
      else if (parts.length === 1) urlOutEl.value = `${defWs}/${parts[0].toLowerCase()}`;
    });

    const appArea = modal.querySelector("#ghAppArea");
    const renderAppArea = async () => {
      if (!app.configured) {
        appArea.innerHTML = `<div class="gh-card">
          <div class="gh-row"><div class="gh-brand"><img src="assets/icon.svg" alt="" width="36" height="36"><div><strong>Register GitHub App in your Organization</strong><div class="simple">Avoids user API limits, supports org-wide repo selection &amp; webhooks. Secrets stay in <code>~/.config/academy-kit/</code>.</div></div></div>
            <button type="button" class="btn small ghost" id="dlIconBtn">Download PNG Icon</button></div>
          <div class="gh-grid">
            <label class="gh-field">GitHub Organization (or blank for personal)<input id="ghOrg" placeholder="your-org-name"></label>
            <label class="gh-field">App Name<input id="ghAppName" value="Academy Kit"></label>
            <label class="gh-field full">Webhook URL (optional, leave blank on localhost)<input id="ghHookUrl" placeholder="https://your-domain.example/api/github/webhook"></label>
          </div>
          <div class="gh-row"><span class="tp-err" id="mfErr"></span><button type="button" class="btn small" id="mfCreateBtn">Create GitHub App in Org →</button></div>
          <details class="vsrc"><summary>Already created an App? Enter App ID &amp; PEM key</summary>
            <div class="gh-grid" style="margin-top:8px">
              <label class="gh-field">App ID<input id="manId" placeholder="123456"></label>
              <label class="gh-field">Webhook Secret (optional)<input id="manSec" type="password" placeholder="optional"></label>
              <label class="gh-field full">Private Key (.pem)<textarea id="manPem" rows="4" placeholder="Paste your GitHub App .pem private key here"></textarea></label>
            </div>
            <div class="gh-row" style="margin-top:8px"><span class="tp-err" id="manErr"></span><button type="button" class="btn small" id="manSaveBtn">Verify &amp; Save App</button></div>
          </details>
        </div>`;
        appArea.querySelector("#dlIconBtn").onclick = downloadIconPng;
        appArea.querySelector("#mfCreateBtn").onclick = async () => {
          const err = appArea.querySelector("#mfErr"); err.textContent = "";
          try {
            const res = await apiJson("/api/github/manifest", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                org: appArea.querySelector("#ghOrg").value.trim(),
                name: appArea.querySelector("#ghAppName").value.trim(),
                webhook_url: appArea.querySelector("#ghHookUrl").value.trim(),
              }),
            });
            const f = document.createElement("form");
            f.method = "POST"; f.action = res.action_url;
            const inp = document.createElement("input");
            inp.type = "hidden"; inp.name = "manifest"; inp.value = JSON.stringify(res.manifest);
            f.appendChild(inp); document.body.appendChild(f); f.submit();
          } catch (e) { err.textContent = e.message; }
        };
        appArea.querySelector("#manSaveBtn").onclick = async () => {
          const err = appArea.querySelector("#manErr"); err.textContent = "";
          try {
            const st = await apiJson("/api/github/app", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ app_id: appArea.querySelector("#manId").value, pem: appArea.querySelector("#manPem").value, webhook_secret: appArea.querySelector("#manSec").value }),
            });
            studio.status.app = st; Object.assign(app, st); renderAppArea();
          } catch (e) { err.textContent = e.message; }
        };
        return;
      }

      appArea.innerHTML = `<div class="gh-card">
        <div class="gh-row"><div class="gh-brand"><img src="assets/icon.svg" alt="" width="34" height="34"><div><strong>${esc(app.name)}</strong> <span class="file-badge synced">App #${esc(app.app_id)}</span><div class="simple">Select one repository below to create or update its own isolated academy workspace.</div></div></div>
          <div style="display:flex;gap:8px">${app.install_url ? `<a class="btn small ghost" href="${esc(app.install_url)}" target="_blank" rel="noopener">Install on Org / Repos</a>` : ""}
          <button type="button" class="btn small ghost" id="appDiscBtn">Reset App</button></div></div>
        <div id="instArea"><div class="bar"></div></div>
      </div>`;
      appArea.querySelector("#appDiscBtn").onclick = async () => {
        const st = await apiJson("/api/github/app/disconnect", { method: "POST", body: "{}" });
        Object.keys(app).forEach((k) => delete app[k]); Object.assign(app, st); studio.status.app = st; renderAppArea();
      };
      try {
        const { installations } = await apiJson("/api/github/installations");
        const instArea = appArea.querySelector("#instArea");
        if (!installations.length) {
          instArea.innerHTML = `<p class="simple">No organization has installed this App yet. Click <b>Install on Org / Repos</b> above, select your repositories, then reopen Connect.</p>`;
          return;
        }
        instArea.innerHTML = `<div class="gh-grid">
          <label class="gh-field">Organization / Account<select id="instSel">${installations.map((i) => `<option value="${esc(i.id)}">${esc(i.account)} (${esc(i.type)})</option>`).join("")}</select></label>
          <label class="gh-field">Repository (isolated workspace)<select id="repoSel"><option>Loading…</option></select></label>
          <label class="gh-field">Branch<select id="branchSel"><option value="">default</option></select></label>
          <label class="gh-field">Docs folder<select id="appDocs"><option value="">/ (Root — entire repository)</option></select></label>
          <label class="gh-field">Reader language<select id="appReader">${langOptions}</select></label>
          <label class="gh-field">Workspace path (auto)<input id="appOut" readonly></label>
        </div>
        <details class="vsrc"><summary>Custom workspace path</summary><label class="gh-field" style="margin-top:6px"><input id="appOutCustom" placeholder="${esc(defWs)}/org/repo"></label></details>
        <div class="gh-row"><label class="gh-check"><input type="checkbox" id="appIncCode"> Include code files alongside markdown docs</label>
          <span class="tp-err" id="appErr"></span><button type="button" class="btn small" id="appFetchBtn">Fetch Repository Files</button></div>`;

        const instSel = instArea.querySelector("#instSel");
        const repoSel = instArea.querySelector("#repoSel");
        const branchSel = instArea.querySelector("#branchSel");
        const docsSel = instArea.querySelector("#appDocs");
        const appOut = instArea.querySelector("#appOut");
        const appOutCustom = instArea.querySelector("#appOutCustom");
        let reposList = [];
        const loadFolders = async () => {
          const full = repoSel.value, br = branchSel.value;
          if (!full) return;
          docsSel.innerHTML = `<option value="">Loading folders…</option>`;
          const d = await apiJson(`/api/github/folders?installation_id=${encodeURIComponent(instSel.value)}&repo=${encodeURIComponent(full)}&branch=${encodeURIComponent(br)}`).catch(() => ({ folders: [""] }));
          const raw = d.folders?.length ? d.folders : [""];
          const list = raw.includes("") ? raw : ["", ...raw];
          const savedDocs = studio.status?.connected?.repo === full ? (studio.status?.connected?.docs_root || "") : "";
          const preferDocs = list.includes(savedDocs) ? savedDocs : "";
          docsSel.innerHTML = list.map((p) => `<option value="${esc(p)}" ${p === preferDocs ? "selected" : ""}>${p ? esc(p + "/") : "/ (Root — entire repository)"}</option>`).join("");
        };
        const loadBranches = async () => {
          const full = repoSel.value;
          const rObj = reposList.find((x) => x.full_name === full);
          if (rObj) {
            const parts = full.toLowerCase().split("/");
            const autoPath = parts.length >= 2 ? `${defWs}/${parts[0]}/${parts[1]}` : `${defWs}/${rObj.name.toLowerCase()}`;
            appOut.value = autoPath;
            appOutCustom.placeholder = autoPath;
          }
          if (!full) return;
          const b = await apiJson(`/api/github/branches?installation_id=${encodeURIComponent(instSel.value)}&repo=${encodeURIComponent(full)}`).catch(() => ({ branches: [] }));
          const list = b.branches?.length ? b.branches : [rObj?.default_branch || "main"];
          branchSel.innerHTML = list.map((name) => `<option value="${esc(name)}" ${name === rObj?.default_branch ? "selected" : ""}>${esc(name)}</option>`).join("");
          await loadFolders();
        };
        const loadRepos = async () => {
          repoSel.innerHTML = `<option>Loading…</option>`;
          const d = await apiJson(`/api/github/repos?installation_id=${encodeURIComponent(instSel.value)}`);
          reposList = d.repos || [];
          const curRepo = studio.status?.connected?.repo || "";
          repoSel.innerHTML = reposList.length
            ? reposList.map((r) => `<option value="${esc(r.full_name)}" ${r.full_name === curRepo ? "selected" : ""}>${esc(r.full_name)}${r.private ? " (private)" : ""}</option>`).join("")
            : `<option value="">No repositories granted</option>`;
          if (reposList.length) await loadBranches();
        };
        instSel.onchange = loadRepos;
        repoSel.onchange = loadBranches;
        branchSel.onchange = loadFolders;
        await loadRepos();

        instArea.querySelector("#appFetchBtn").onclick = async () => {
          const err = instArea.querySelector("#appErr"); err.textContent = "";
          const btn = instArea.querySelector("#appFetchBtn"); btn.disabled = true; btn.textContent = "Cloning…";
          try {
            const res = await apiJson("/api/github/connect", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                installation_id: Number(instSel.value),
                full_name: repoSel.value,
                branch: branchSel.value,
                docs_root: docsSel.value,
                academy_dir: appOutCustom.value.trim() || appOut.value.trim(),
                reader: instArea.querySelector("#appReader").value,
                include_code: instArea.querySelector("#appIncCode").checked,
              }),
            });
            studio.status = res.status;
            studio.files = res.files || [];
            studio.includeCode = instArea.querySelector("#appIncCode").checked;
            studio.selected = new Set(studio.files.filter((f) => f.is_doc).map((f) => f.path));
            studio.tab = "files";
            updateConnectBadge();
            closeViz();
            renderSide(studio.lastActive);
          } catch (e) {
            err.textContent = e.message;
          } finally { btn.disabled = false; btn.textContent = "Fetch Repository Files"; }
        };
      } catch (e) {
        appArea.querySelector("#instArea").innerHTML = `<div class="tp-err">${esc(e.message)}</div>`;
      }
    };
    renderAppArea();

    modal.querySelector("#urlConnectBtn").onclick = async () => {
      const err = modal.querySelector("#urlErr"); err.textContent = "";
      const btn = modal.querySelector("#urlConnectBtn"); btn.disabled = true; btn.textContent = "Cloning…";
      try {
        const res = await apiJson("/api/github/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repo_url: modal.querySelector("#urlRepo").value.trim(),
            branch: modal.querySelector("#urlBranch").value.trim(),
            docs_root: modal.querySelector("#urlDocs").value.trim(),
            academy_dir: modal.querySelector("#urlOut").value.trim(),
            reader: modal.querySelector("#urlReader").value.trim(),
          }),
        });
        studio.status = res.status;
        studio.files = res.files || [];
        studio.selected = new Set(studio.files.filter((f) => f.is_doc).map((f) => f.path));
        studio.tab = "files";
        updateConnectBadge();
        closeViz();
        renderSide(studio.lastActive);
      } catch (e) {
        err.textContent = e.message;
      } finally { btn.disabled = false; btn.textContent = "Fetch Repository Files"; }
    };
  }

  if (connectBtn) connectBtn.onclick = openConnectModal;
  (async () => {
    try {
      studio.status = await apiJson("/api/github/status");
      studio.available = true;
      updateConnectBadge();
      const [mRes, fRes] = await Promise.all([
        apiJson("/api/ai/models").catch(() => ({ models: [] })),
        studio.status?.connected ? apiJson("/api/github/files").catch(() => ({ files: [] })) : Promise.resolve({ files: [] }),
      ]);
      studio.models = mRes.models || [];
      studio.files = fRes.files || [];
      if (studio.files.length) {
        studio.selected = new Set(studio.files.filter((f) => f.is_doc).map((f) => f.path));
        renderSide(studio.lastActive);
      }
      if (/[?&]github_(?:installed|setup)=/.test(location.search)) {
        history.replaceState({}, "", location.pathname + location.hash);
        openConnectModal();
      }
    } catch { studio.available = false; }
  })();

  function route() {
    const [, id, anchor] = (location.hash || "#/").split("/");
    side.classList.remove("open");
    if (id && byId[id]) { renderSide(id); lesson(byId[id]); }
    else if (id === "terms") { renderSide("terms"); terms(); }
    else if (id === "words") { renderSide("words"); myWords(); }
    else if (id === "diagrams") { renderSide("diagrams"); myDiagrams(); }
    else { renderSide("home"); home(); }
    if (anchor) { const el = document.getElementById(anchor); if (el) el.scrollIntoView(); } else window.scrollTo(0, 0);
    if (flashText && anchor) {
      const want = flashText.slice(0, 40); flashText = "";
      const hit = [...(document.getElementById(anchor)?.querySelectorAll("p, li, td, .gate, .term, .pit, .plain") || [])].reverse().find((x) => md(x.textContent).includes(want));
      if (hit) { hit.scrollIntoView({ block: "center" }); hit.classList.add("flash"); setTimeout(() => hit.classList.remove("flash"), 2600); }
    }
  }
  window.addEventListener("hashchange", route);
  route();
})();
