/* start-small front end. No framework, no build step.
   State lives on the server; this file only renders and calls /api. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
let settings = {};
let session = null;   // {id, mode, startedAt, done: n, current: activityPayload, hintLevel, tried:[]}

// ------------------------------------------------------------------ utils
async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  let res;
  try { res = await fetch(path, opts); }
  catch (e) { toast("The app can't reach its local server. Is `python app.py` still running?"); throw e; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { toast(data.error || `Error ${res.status}`); throw new Error(data.error || res.status); }
  return data;
}
function h(str) { return String(str ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function el(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._t); t._t = setTimeout(() => t.hidden = true, ms); }
function minutesSince(ts) { return Math.max(0, Math.round((Date.now() - ts) / 60000)); }
function confetti() {
  if (!settings.animations || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = $("#confetti"); c.innerHTML = ""; c.hidden = false;
  const colors = ["#1f6f5f", "#e8955b", "#5fbfa6", "#b3541e", "#2c7a4b"];
  for (let i = 0; i < 40; i++) {
    const p = document.createElement("i");
    p.style.left = Math.random() * 100 + "vw"; p.style.background = colors[i % colors.length];
    p.style.animationDelay = (Math.random() * .4) + "s"; p.style.animationDuration = (1.1 + Math.random() * .8) + "s";
    c.appendChild(p);
  }
  setTimeout(() => { c.hidden = true; c.innerHTML = ""; }, 2200);
}
function setNav(name) { document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === name)); }
function render(node) { view.innerHTML = ""; node.classList.add("fade"); view.appendChild(node); window.scrollTo({ top: 0 }); }

// ------------------------------------------------------------------ routing
window.addEventListener("hashchange", route);
async function route() {
  const name = (location.hash || "#home").slice(1);
  setNav(name);
  if (name === "activity" || name === "finish") { if (!session) location.hash = "#home"; return; }
  if (session) { api("/api/session/finish", { session_id: session.id }).catch(() => {}); session = null; }
  const pages = { home, collection, tasks, evaluation, settings: settingsPage };
  (pages[name] || home)();
}

// ------------------------------------------------------------------ home
async function home() {
  const d = await api("/api/home");
  settings = d.settings;
  document.body.classList.toggle("no-anim", !settings.animations);
  const n = d.next, a = n.activity;
  const reasonText = { learn: "Next new idea", review: "Quick review", restart: "Welcome back", micro: "Tiny", maintenance: "Keep it warm", chosen: "" }[n.reason] || "";
  const kindText = { predict: "predict an output", fix: "fix one thing", explain: "say it in your words", build: "build something small", write: "write a little code" }[a.kind];
  const page = el(`<div>
    ${!settings.onboarded ? `<div class="card soft">
      <div class="eyebrow">How this works</div>
      <p>One prepared action at a time. Predict something, get honest feedback, learn one idea, use it once, stop. About two minutes to start; you can always do one more.</p>
      <p class="small muted">Everything is stored on this computer only. Nothing needs an account. You can change any of this in Settings.</p>
      <button class="btn tiny" id="onb">Got it</button>
    </div>` : ""}
    <section class="card hero">
      <div class="eyebrow">${h(reasonText)} · ${h(n.concept.title)}</div>
      <h1>${h(a.title)}</h1>
      <p class="minutes">≈ ${a.minutes} min · ${kindText}</p>
      ${n.note ? `<p class="small">${h(n.note)}</p>` : ""}
      <p class="muted">${h(a.hook)}</p>
      <div class="actions row">
        <button class="btn primary big" id="start">Start small</button>
        <button class="btn ghost" id="meh">I don't feel like it</button>
      </div>
    </section>

    <section class="card quiet">
      <div class="row between">
        <div class="chips">
          ${d.mastered.map(t => `<span class="chip on">${h(t)}</span>`).join("")}
          ${d.in_progress.map(t => `<span class="chip">${h(t)} · in progress</span>`).join("")}
          ${!d.mastered.length && !d.in_progress.length ? `<span class="chip">${d.concepts_total} ideas ahead, one at a time</span>` : ""}
        </div>
        ${d.sparks !== null ? `<span class="small muted" title="One spark per activity passed with no hints — first pass and one review. Repeats earn nothing. Cosmetic; turn off in Settings.">✦ ${d.sparks}</span>` : ""}
      </div>
      ${d.due_reviews ? `<p class="small muted" style="margin-top:8px">${d.due_reviews} idea${d.due_reviews > 1 ? "s" : ""} ready for a quick review — they come up naturally, nothing to manage.</p>` : ""}
    </section>

    ${d.collection.length ? `<section class="card quiet">
      <div class="eyebrow">Things you can now do</div>
      <ul class="collection-list">${d.collection.slice(0, 4).map(c => `<li><span class="kind">${h(c.kind)}</span><span>${h(c.title)}</span></li>`).join("")}</ul>
      ${d.collection_count > 4 ? `<p class="small" style="margin:8px 0 0"><a href="#collection">All ${d.collection_count} →</a></p>` : ""}
    </section>` : ""}

    ${d.tasks.length ? `<section class="card quiet">
      <div class="eyebrow">Everyday task, ready to start</div>
      <p class="next" style="margin:0 0 4px">${h(d.tasks[0].next_action)}</p>
      <p class="small muted" style="margin:0 0 10px">Stop when: ${h(d.tasks[0].stop_when)} · ≈ ${d.tasks[0].minutes} min</p>
      <a class="btn tiny" href="#tasks">Open tasks</a>
    </section>` : ""}

    <p class="small muted">Cue: <em>${h(settings.cue)}</em> → open this and press Start small. <a href="#settings">Edit</a></p>
  </div>`);
  page.querySelector("#start").onclick = () => startSession("small");
  page.querySelector("#meh").onclick = () => startSession("micro");
  const onb = page.querySelector("#onb");
  if (onb) onb.onclick = async () => { await api("/api/settings", { onboarded: true }); home(); };
  render(page);
}

// ------------------------------------------------------------------ session
async function startSession(mode, activityId) {
  const d = await api("/api/session/start", { mode, activity_id: activityId });
  session = { id: d.session_id, mode, startedAt: Date.now(), done: 0 };
  location.hash = "#activity";
  showActivity(d);
}

async function serveActivity(activityId, opts = {}) {
  const d = await api("/api/session/serve", { session_id: session.id, activity_id: activityId, ...opts });
  showActivity(d);
}

async function serveNext() {
  const d = await api("/api/session/next", { session_id: session.id });
  showActivity(d);
}

function showActivity(d) {
  session.current = d; session.hintLevel = 0; session.tried = []; session.followUp = null;
  const a = d.activity;
  const isCode = ["fix", "write", "build"].includes(a.kind);
  const page = el(`<div>
    <div class="steps"><span class="done"></span><span id="s2"></span><span id="s3"></span><span id="s4"></span></div>
    <section class="card">
      <div class="row between">
        <div class="eyebrow">${h(d.concept.title)} · ${a.kind}${d.is_review ? " · review" : ""}${d.is_micro ? " · tiny" : ""}</div>
        <button class="btn ghost tiny" id="stop" title="Leave now. Progress so far is saved.">Stop</button>
      </div>
      <h2>${h(a.title)}</h2>
      ${d.note ? `<p class="small muted">${h(d.note)}</p>` : ""}
      <p>${h(a.hook)}</p>
    </section>

    <section class="card" id="attempt">
      <p style="white-space:pre-wrap">${h(a.prompt)}</p>
      ${a.kind === "predict" ? `<pre>${h(a.code)}</pre>
        <div class="field" style="margin-top:12px"><label for="ans">Your prediction (one line per printed line)</label>
        <textarea id="ans" class="code" spellcheck="false" placeholder="Type what will appear on screen…"></textarea></div>` : ""}
      ${isCode ? `<div class="field"><label for="ans">Your code</label>
        <textarea id="ans" class="code" spellcheck="false">${h(a.code || "")}</textarea></div>
        ${a.tests_preview.length ? `<p class="small muted">Checked with: ${a.tests_preview.map(t => `<code>${h(t)}</code>`).join(", ")}</p>` : ""}
        <div class="row"><button class="btn tiny" id="run">Run it</button>
          <input type="text" id="stdin" placeholder="input lines (optional, comma-separated)" style="max-width:280px">
        </div><pre id="runout" hidden></pre>` : ""}
      ${a.kind === "explain" ? `<div class="field"><label for="ans">In your own words</label>
        <textarea id="ans" placeholder="Two sentences are plenty."></textarea></div>` : ""}
      <div class="row" style="margin-top:8px">
        <button class="btn primary" id="submit">${a.kind === "explain" ? "Compare" : "Check"}</button>
        <button class="btn" id="hint" ${a.kind === "explain" ? "hidden" : ""}>Hint <span class="muted small">1 of ${a.hint_levels}</span></button>
        <button class="btn ghost tiny" id="hard">Too hard</button>
        <button class="btn ghost tiny" id="easy">Too easy</button>
      </div>
      <div id="hints"></div>
      <div id="fb"></div>
    </section>
    <section id="after"></section>
  </div>`);
  const ans = page.querySelector("#ans");
  if (ans) {
    ans.addEventListener("keydown", e => {
      if (e.key === "Tab") { e.preventDefault(); const s = ans.selectionStart; ans.setRangeText("    ", s, ans.selectionEnd, "end"); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) page.querySelector("#submit").click();
    });
    setTimeout(() => ans.focus(), 50);
  }
  page.querySelector("#stop").onclick = () => finish(true);
  page.querySelector("#submit").onclick = () => submit(page);
  page.querySelector("#hint").onclick = () => hint(page);
  page.querySelector("#hard").onclick = () => feedback(page, "too_hard");
  page.querySelector("#easy").onclick = () => feedback(page, "too_easy");
  const run = page.querySelector("#run");
  if (run) run.onclick = async () => {
    const out = page.querySelector("#runout"); out.hidden = false; out.textContent = "running…";
    const stdin = page.querySelector("#stdin").value.split(",").map(s => s.trim()).filter(Boolean).join("\n") + "\n";
    const r = await api("/api/run", { code: ans.value, stdin });
    out.textContent = ((r.stdout || "") + (r.error ? "\n⚠ " + r.error : "")).trim() || "(no output)";
  };
  render(page);
}

async function hint(page) {
  const a = session.current.activity;
  if (a.kind === "explain") { toast("For this one, just write what you think — you'll see the model answer next."); return; }
  const level = Math.min(session.hintLevel + 1, a.hint_levels);
  const r = await api("/api/hint", { session_id: session.id, activity_id: a.id, level });
  session.hintLevel = r.level;
  const box = page.querySelector("#hints");
  if (r.is_solution) {
    box.appendChild(el(`<div class="hint"><div class="eyebrow">Worked solution</div><pre>${h(r.text)}</pre>
      <p class="small muted" style="margin:8px 0 0">Read it, then ${r.follow_up ? "you'll get a fresh small version to do on your own — that's what makes it stick." : "try it once more."}</p></div>`));
    session.followUp = r.follow_up ? { id: r.follow_up, title: r.follow_up_title } : null;
  } else {
    box.appendChild(el(`<div class="hint"><div class="eyebrow">Hint ${r.level}</div>${h(r.text)}</div>`));
  }
  const btn = page.querySelector("#hint");
  if (r.level >= r.levels) btn.disabled = true;
  else btn.innerHTML = `Hint <span class="muted small">${r.level + 1} of ${r.levels}</span>`;
}

async function feedback(page, signal) {
  const a = session.current.activity;
  const r = await api("/api/feedback", { session_id: session.id, activity_id: a.id, signal });
  if (r.action === "switch") {
    toast(r.reason, 3500);
    await serveActivity(r.activity_id, { is_variation: true });
  } else if (r.action === "hint") { toast(r.reason, 3500); hint(page); }
  else if (r.text) { page.querySelector("#after").appendChild(el(`<div class="card soft"><div class="eyebrow">Another way to see it</div><p>${h(r.text)}</p></div>`)); }
  else toast(r.reason || "Noted.");
}

async function submit(page) {
  const a = session.current.activity;
  const ans = page.querySelector("#ans");
  const answer = ans ? ans.value : "";
  if (a.kind !== "fix" && !answer.trim()) { toast("Type something first — a guess is fine. Guessing then seeing is the whole point."); return; }
  const btn = page.querySelector("#submit"); btn.disabled = true; btn.textContent = "Checking…";
  let r;
  try { r = await api("/api/attempt", { session_id: session.id, activity_id: a.id, answer }); }
  finally { btn.disabled = false; btn.textContent = a.kind === "explain" ? "Compare" : "Check"; }
  session.lastResult = r;
  page.querySelector("#s2").classList.add("done");
  const fb = page.querySelector("#fb"); fb.innerHTML = "";
  const after = page.querySelector("#after"); after.innerHTML = "";

  if (a.kind === "explain") {
    session.done++;
    btn.disabled = true;
    fb.appendChild(el(`<div class="feedback ok" style="margin-top:14px">
      <div class="eyebrow">Model answer</div><p>${h(r.model_answer)}</p>
      <div class="checklist"><div class="eyebrow">Tick what you covered</div>
        ${r.checklist.map((c, i) => `<label><input type="checkbox" data-i="${i}"> ${h(c)}</label>`).join("")}
      </div>
      ${settings.ai_enabled ? `<button class="btn tiny" id="react" style="margin-top:8px">Ask for a reaction to my words</button><div id="reactout"></div>` : ""}
    </div>`));
    const react = fb.querySelector("#react");
    if (react) react.onclick = async () => {
      react.disabled = true; const out = fb.querySelector("#reactout");
      const rr = await api("/api/ai/react", { activity_id: a.id, text: answer });
      out.innerHTML = rr.ok ? `<p class="small" style="margin-top:8px">${h(rr.text)}</p>` : `<p class="small muted" style="margin-top:8px">${h(rr.error)}</p>`;
    };
    fb.querySelectorAll("input[type=checkbox]").forEach(cb => cb.onchange = () => {
      const ticked = [...fb.querySelectorAll("input:checked")].map(c => +c.dataset.i);
      api("/api/attempt", { session_id: session.id, activity_id: a.id, answer, self_check: ticked }).catch(() => {});
    });
    showExplanation(page, r);
    return;
  }

  if (r.correct) {
    session.done++;
    fb.appendChild(el(`<div class="feedback ok" style="margin-top:14px"><b>${h(r.feedback)}</b>${r.assisted ? ` <span class="small muted">(with help — that counts as practice, not yet as independent)</span>` : ""}
      ${testList(r.detail)}</div>`));
    if (!r.assisted) confetti();
    if (r.outcome && r.outcome.new_collection) toast("Added to your collection: " + r.outcome.new_collection.title, 3200);
    page.querySelector("#submit").disabled = true; page.querySelector("#hint").disabled = true;
    showExplanation(page, r);
  } else {
    fb.appendChild(el(`<div class="feedback no" style="margin-top:14px"><b>${h(r.feedback)}</b>${testList(r.detail)}
      <p class="small muted" style="margin:8px 0 0">Wrong first guesses are useful — the feedback lands better after one. Adjust and check again, or take a hint.</p></div>`));
    page.querySelector("#s2").classList.remove("done");
  }
}

function testList(detail) {
  if (!detail || !detail.tests) return "";
  return `<ul class="tests">${detail.tests.map(t => `<li class="${t.ok ? "ok" : "no"}">${h(t.label)} → ${t.ok ? h(t.expected) : `expected ${h(t.expected)}, got ${h(t.got)}`}</li>`).join("")}</ul>`;
}

function showExplanation(page, r) {
  const a = session.current.activity;
  const after = page.querySelector("#after");
  page.querySelector("#s3").classList.add("done");
  session.tried = [r.explain];
  const card = el(`<div>
    <section class="card">
      <div class="eyebrow">The idea</div>
      <p>${h(r.explain)}</p>
      ${r.why ? `<p class="small"><b>Why this works:</b> ${h(r.why)}</p>` : ""}
      <div id="alts"></div>
      <div class="row"><button class="btn tiny" id="diff">Explain differently</button></div>
    </section>
    ${r.can_now ? `<section class="card good"><div class="eyebrow">You can now</div><p style="margin:0"><b>${h(r.can_now)}</b>${r.assisted ? ` <span class="small muted">— with a hint this time; the next fresh version is where it becomes yours.</span>` : ""}</p></section>` : ""}
    <section class="card quiet" id="nextcard"></section>
  </div>`);
  card.querySelector("#diff").onclick = async () => {
    const alts = card.querySelector("#alts");
    if (r.explain_alt && !session.tried.includes(r.explain_alt)) {
      session.tried.push(r.explain_alt);
      alts.appendChild(el(`<div class="hint"><div class="eyebrow">Another angle</div>${h(r.explain_alt)}</div>`)); return;
    }
    if (settings.ai_enabled) {
      const rr = await api("/api/ai/explain", { activity_id: a.id, tried: session.tried });
      if (rr.ok) { session.tried.push(rr.text); alts.appendChild(el(`<div class="hint"><div class="eyebrow">A third angle (AI)</div>${h(rr.text)}</div>`)); return; }
      toast(rr.error, 3500);
    }
    const fbk = await api("/api/feedback", { session_id: session.id, activity_id: a.id, signal: "explain_differently" });
    alts.appendChild(el(`<div class="hint"><div class="eyebrow">Once more, simpler</div>${h(fbk.text)}</div>`));
  };
  after.appendChild(card);
  page.querySelector("#s4").classList.add("done");

  // what next?
  const nextcard = card.querySelector("#nextcard");
  const elapsed = minutesSince(session.startedAt);
  const overBudget = elapsed >= (settings.session_minutes || 8);
  const fu = r.follow_up || session.followUp;
  let html = `<div class="eyebrow">Finish point</div>`;
  if (fu) {
    html += `<p>You saw the solution, so here is a <b>fresh small version</b> to do without it: <em>${h(fu.title)}</em>.</p>
      <div class="row"><button class="btn primary" id="fresh">Do the fresh version</button><button class="btn" id="fin">Finish here</button></div>`;
  } else if (session.mode === "micro") {
    html += `<p>That was the tiny action. It counts. You're done.</p>
      <div class="row"><button class="btn primary" id="fin">Finish</button><button class="btn ghost" id="more">One more, if you want</button></div>`;
  } else {
    html += `<p>${elapsed} min in. ${overBudget ? "That's a full session — a clean stop now is the right call." : "Stop here, or do one more (about " + (settings.entry_minutes || 2) + "–4 min)."}</p>
      <div class="row">${overBudget ? `<button class="btn primary" id="fin">Finish here</button><button class="btn ghost" id="more">One more anyway</button>` : `<button class="btn primary" id="more">One more</button><button class="btn" id="fin">Finish here</button>`}</div>`;
  }
  nextcard.innerHTML = html;
  const fresh = nextcard.querySelector("#fresh"); if (fresh) fresh.onclick = () => { session.followUp = null; serveActivity(fu.id, { is_variation: true }); };
  const more = nextcard.querySelector("#more"); if (more) more.onclick = () => serveNext();
  nextcard.querySelector("#fin").onclick = () => finish(false);
  nextcard.scrollIntoView({ behavior: settings.animations ? "smooth" : "auto", block: "center" });
}

async function finish(early) {
  if (!session) { location.hash = "#home"; return; }
  const sid = session.id, done = session.done;
  let enjoyment = null, frustration = null;
  const page = el(`<div>
    <section class="card hero">
      <div class="eyebrow">Finished</div>
      <h1>${done ? (done === 1 ? "One thing, done." : done + " things, done.") : "Stopped. That's fine."}</h1>
      <p class="muted">${done ? "Your progress is saved and the next step is prepared." : "Nothing is lost — the same prepared action will be waiting."}</p>
      <div id="preview" class="small"></div>
    </section>
    ${done ? `<section class="card quiet">
      <div class="eyebrow">Optional · how did that feel?</div>
      <div class="row" style="gap:24px">
        <div><div class="small muted">Enjoyable</div><div class="rating" id="enj">${[1,2,3,4,5].map(n => `<button>${n}</button>`).join("")}</div></div>
        <div><div class="small muted">Frustrating</div><div class="rating" id="fru">${[1,2,3,4,5].map(n => `<button>${n}</button>`).join("")}</div></div>
      </div>
    </section>` : ""}
    <div class="row"><button class="btn primary" id="done">Done</button></div>
  </div>`);
  ["enj", "fru"].forEach(id => {
    const g = page.querySelector("#" + id); if (!g) return;
    g.querySelectorAll("button").forEach((b, i) => b.onclick = () => {
      g.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on");
      if (id === "enj") enjoyment = i + 1; else frustration = i + 1;
    });
  });
  page.querySelector("#done").onclick = async () => {
    await api("/api/session/finish", { session_id: sid, enjoyment, frustration });
    session = null; location.hash = "#home"; home();
  };
  location.hash = "#finish";
  render(page);
  // save immediately too (ratings, if any, are patched in on Done)
  const f = await api("/api/session/finish", { session_id: sid });
  if (f.next_preview && done) {
    page.querySelector("#preview").innerHTML = `Next time: <b>${h(f.next_preview.title)}</b> (${h(f.next_preview.concept)}, ≈ ${f.next_preview.minutes} min).`;
  }
}

// ------------------------------------------------------------------ collection
async function collection() {
  const d = await api("/api/collection");
  const groups = {};
  d.items.forEach(i => (groups[i.kind] = groups[i.kind] || []).push(i));
  const order = ["built", "fixed", "understood"];
  const page = el(`<div>
    <h1>Things you can now do</h1>
    <p class="muted">Every line here is something you actually did. Entries marked “with a hint” or “tiny action” are kept honest on purpose.</p>
    ${!d.items.length ? `<div class="card soft"><p style="margin:0">Empty for now. The first Start small fills it.</p></div>` : ""}
    ${order.filter(k => groups[k]).map(k => `<section class="card"><div class="eyebrow">${k}</div>
      <ul class="collection-list">${groups[k].map(i => `<li><span class="small muted" style="min-width:84px">${new Date(i.at * 1000).toLocaleDateString()}</span><span>${h(i.title)}</span></li>`).join("")}</ul></section>`).join("")}
  </div>`);
  render(page);
}

// ------------------------------------------------------------------ tasks
let taskSession = null;
async function tasks() {
  const d = await api("/api/tasks");
  const page = el(`<div>
    <h1>Everyday tasks</h1>
    <p class="muted">“Work on the project” is not startable. “Open the folder and rename one file” is. Write the physical next action and where you'll stop; the app only holds the door open.</p>
    <section class="card">
      ${d.tasks.length ? d.tasks.map(t => `<div class="task" data-id="${t.id}">
        <div class="row between"><div><div class="small muted">${h(t.title)}</div><div class="next">${h(t.next_action)}</div>
          <div class="small muted">Stop when: ${h(t.stop_when)} · ≈ ${t.minutes} min${t.starts ? ` · started ${t.starts}×` : ""}</div></div>
          <div class="row"><button class="btn primary tiny" data-act="start">Start</button><button class="btn ghost tiny" data-act="delete" title="Remove">✕</button></div></div>
      </div>`).join("") : `<p class="muted" style="margin:0">No tasks yet.</p>`}
    </section>
    <section class="card quiet">
      <div class="eyebrow">Add one</div>
      <div class="field"><label>What is it, broadly</label><input type="text" id="t-title" placeholder="e.g. Tax paperwork"></div>
      <div class="field"><label>The physical next action (something your hands do)</label><input type="text" id="t-next" placeholder="e.g. Open the receipts folder and sort the top 5 by date"></div>
      <div class="field"><label>Stop when</label><input type="text" id="t-stop" placeholder="e.g. 5 receipts are named, or 5 minutes pass"></div>
      <div class="field" style="max-width:160px"><label>Minutes</label><input type="number" id="t-min" value="5" min="1" max="60"></div>
      <button class="btn" id="t-add">Add</button>
    </section>
  </div>`);
  page.querySelector("#t-add").onclick = async () => {
    const body = { title: $("#t-title", page).value, next_action: $("#t-next", page).value, stop_when: $("#t-stop", page).value, minutes: +$("#t-min", page).value || 5 };
    if (!body.title || !body.next_action || !body.stop_when) { toast("All three lines matter — the next action and the stop point are the whole trick."); return; }
    await api("/api/tasks", body); tasks();
  };
  page.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
    const id = +b.closest(".task").dataset.id;
    if (b.dataset.act === "delete") { await api(`/api/tasks/${id}/delete`, {}); tasks(); return; }
    const t = d.tasks.find(x => x.id === id);
    const r = await api(`/api/tasks/${id}/start`, {});
    taskSession = { id: r.session_id, task: t, startedAt: Date.now() };
    focusTask();
  });
  render(page);
}

function focusTask() {
  const t = taskSession.task;
  const page = el(`<div>
    <section class="card hero">
      <div class="eyebrow">Doing · ${h(t.title)}</div>
      <h1>${h(t.next_action)}</h1>
      <p class="muted">Stop when: <b>${h(t.stop_when)}</b> · about ${t.minutes} min · <span id="clock">0:00</span></p>
      <p class="small muted">Nothing here is graded. When you hit the stop point, come back and press Done.</p>
      <div class="row"><button class="btn primary big" id="tdone">Done — I reached the stop point</button><button class="btn ghost" id="tstop">Stop for now</button></div>
    </section>
  </div>`);
  const clock = page.querySelector("#clock");
  const tick = setInterval(() => { const s = Math.round((Date.now() - taskSession.startedAt) / 1000); clock.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }, 1000);
  page.querySelector("#tdone").onclick = async () => { clearInterval(tick); await api(`/api/tasks/${t.id}/done`, { session_id: taskSession.id }); taskSession = null; toast("Done. That was a real start."); tasks(); };
  page.querySelector("#tstop").onclick = async () => { clearInterval(tick); await api("/api/session/finish", { session_id: taskSession.id }); taskSession = null; tasks(); };
  render(page);
}

// ------------------------------------------------------------------ evaluation
async function evaluation() {
  const d = await api("/api/evaluation");
  const s = d.summary;
  const max = Math.max(1, ...d.days.map(x => x.attempts));
  const pct = v => v === null || v === undefined ? "—" : v + "%";
  const page = el(`<div>
    <h1>The last two weeks</h1>
    <p class="muted">Personal observations, not proof of anything. The question is simple: are you coming back, and is understanding growing?</p>
    <section class="card">
      <div class="eyebrow">Days with a start</div>
      <div class="days">${d.days.map(x => `<div class="day ${x.started ? "" : "none"}" title="${x.date}: ${x.started} start(s), ${x.attempts} attempt(s)${x.micro ? ", " + x.micro + " tiny" : ""}"><div class="bar" style="height:${Math.round(100 * x.attempts / max)}%"></div></div>`).join("")}</div>
      <div class="row between small muted"><span>${d.days[0].date}</span><span>today</span></div>
    </section>
    <section class="card">
      <div class="stats">
        <div class="stat"><b>${s.days_with_a_start}</b><span class="small muted">days with a start</span></div>
        <div class="stat"><b>${s.sessions}</b><span class="small muted">sessions (${s.micro_sessions} tiny)</span></div>
        <div class="stat"><b>${pct(s.independent_rate)}</b><span class="small muted">right with no help</span></div>
        <div class="stat"><b>${pct(s.novel_variation_rate)}</b><span class="small muted">right on fresh variations</span></div>
        <div class="stat"><b>${pct(s.independent_review_rate)}</b><span class="small muted">right on later reviews</span></div>
        <div class="stat"><b>${s.solution_views}</b><span class="small muted">worked solutions viewed</span></div>
        <div class="stat"><b>${s.enjoyment_avg ?? "—"}</b><span class="small muted">enjoyment (1–5)</span></div>
        <div class="stat"><b>${s.frustration_avg ?? "—"}</b><span class="small muted">frustration (1–5)</span></div>
      </div>
    </section>
    <section class="card soft"><div class="eyebrow">Reading it</div>${d.reading.map(r => `<p>${h(r)}</p>`).join("")}</section>
    <p class="small muted">Not tracked on purpose: screen time, streaks, notification clicks. “Too hard” pressed ${s.too_hard}×, “too easy” ${s.too_easy}×.</p>
  </div>`);
  render(page);
}

// ------------------------------------------------------------------ settings
async function settingsPage() {
  const s = await api("/api/settings");
  const ai = await api("/api/ai/status");
  const tr = await api("/api/tracks");
  const page = el(`<div>
    <h1>Settings</h1>
    <section class="card">
      <div class="eyebrow">Sessions</div>
      <div class="row">
        <div class="field" style="max-width:180px"><label>Entry activity, minutes</label><input type="number" id="entry" value="${s.entry_minutes}" min="1" max="10"></div>
        <div class="field" style="max-width:180px"><label>Full session, minutes</label><input type="number" id="sess" value="${s.session_minutes}" min="3" max="60"></div>
      </div>
      <p class="small muted">These are design defaults, not scientifically optimal numbers. Shorter is fine.</p>
    </section>
    <section class="card">
      <div class="eyebrow">Routine cue</div>
      <div class="field"><label>I open this…</label><input type="text" id="cue" value="${h(s.cue)}"></div>
      <p class="small muted">A stable cue (“after X, I do Y”) is the one habit mechanism with solid evidence. The app never nags; it just shows this line on the home screen.</p>
      <div class="field inline"><input type="checkbox" id="rem" ${s.reminders_enabled ? "checked" : ""}><label for="rem" style="margin:0">Enable the optional reminder script</label></div>
      <div class="row"><div class="field" style="max-width:160px"><label>Quiet from (hour)</label><input type="number" id="q1" value="${s.quiet_hours[0]}" min="0" max="23"></div>
        <div class="field" style="max-width:160px"><label>Quiet until (hour)</label><input type="number" id="q2" value="${s.quiet_hours[1]}" min="0" max="23"></div></div>
      <p class="small muted">The app installs nothing. If you want a reminder, run <code>python remind.py</code> yourself (or schedule it in Task Scheduler). It shows one dismissible message, at most once a day, never in quiet hours, and only if this box is ticked.</p>
    </section>
    <section class="card">
      <div class="eyebrow">Motivation features (all optional)</div>
      <div class="field inline"><input type="checkbox" id="anim" ${s.animations ? "checked" : ""}><label for="anim" style="margin:0">Small celebration animation on an unassisted success</label></div>
      <div class="field inline"><input type="checkbox" id="sparks" ${s.sparks_enabled ? "checked" : ""}><label for="sparks" style="margin:0">Show sparks ✦ (one per activity passed without help; repeats earn nothing)</label></div>
      <p class="small muted">Nothing is gated behind these. The collection of things you can do is always on, because it is just a record of what happened.</p>
    </section>
    <section class="card">
      <div class="eyebrow">AI help (optional)</div>
      <div class="field inline"><input type="checkbox" id="ai" ${s.ai_enabled ? "checked" : ""}><label for="ai" style="margin:0">Use Claude for a third explanation and reactions to my own-words answers</label></div>
      <div class="field" style="max-width:320px"><label>Model</label><input type="text" id="aimodel" value="${h(s.ai_model)}"></div>
      <p class="small muted">${ai.available ? "SDK found. Needs ANTHROPIC_API_KEY or `ant auth login`; requests cost money on your account." : h(ai.reason) + " Everything works without it — the curated explanations are the default, not a fallback."} Only the activity text and what you typed are sent; never your progress.</p>
    </section>
    <section class="card">
      <div class="eyebrow">Track</div>
      <div class="field" style="max-width:280px"><label>Subject</label><select id="track">${tr.tracks.map(t => `<option value="${t}" ${t === tr.current ? "selected" : ""}>${t}</option>`).join("")}</select></div>
      <p class="small muted">Concepts: ${tr.concepts.map(c => `${h(c.title)} <em>(${c.status})</em>`).join(" · ")}</p>
      <p class="small muted">To add a subject, drop a <code>startsmall/content/&lt;name&gt;_track.py</code> next to the Python one; the content test will refuse anything whose answers don't run.</p>
    </section>
    <div class="row"><button class="btn primary" id="save">Save</button><span class="small muted">Data lives in <code>data/startsmall.db</code>. Delete that file to start over.</span></div>
  </div>`);
  page.querySelector("#save").onclick = async () => {
    const g = id => page.querySelector("#" + id);
    await api("/api/settings", {
      entry_minutes: +g("entry").value || 2, session_minutes: +g("sess").value || 8, cue: g("cue").value,
      reminders_enabled: g("rem").checked, quiet_hours: [+g("q1").value, +g("q2").value],
      animations: g("anim").checked, sparks_enabled: g("sparks").checked,
      ai_enabled: g("ai").checked, ai_model: g("aimodel").value.trim() || "claude-opus-5", current_track: g("track").value,
    });
    toast("Saved."); settingsPage();
  };
  render(page);
}

route();
