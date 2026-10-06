// The Chess Development Roadmap: where am I, what to learn now and why, what to practise, and what comes next.
import { h, icon, mount, meter, level } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { topicCheck } from "../roadmaplinks.js";

const STATUS_LABEL = { not_started: "Not started", learning: "Learning", practicing: "Practising", developing: "Developing", mastered: "Mastered" };
const PRIORITY_TONE = { High: "bad", Medium: "warn", Low: "good", Focus: "brand" };
const ENDGAME_TIERS = { review: "Must know", now: "Should know", preview: "Advanced (next level)" };
const TIERS = { review: "Review (earlier levels)", now: "Learn now", preview: "Coming next level" };
const open = new Set(); // which area cards are expanded, kept across re-renders

function pctText(n) { return n === null || n === undefined ? "—" : `${n}%`; }

function milestoneBar(d) {
  const band = d.bands[d.band];
  if (d.rating === null || d.rating === undefined) return null;
  const hi = d.next_milestone || band.lo + 400;
  const within = Math.max(0, Math.min(1, (d.rating - band.lo) / (hi - band.lo)));
  return h("div", { class: "stack-s" },
    h("div", { class: "row small", style: "justify-content:space-between" },
      h("b", {}, `${d.rating}`), d.next_milestone ? h("span", {}, `→ ${d.next_milestone}`) : null, d.future_milestone ? h("span", { class: "muted" }, `→ ${d.future_milestone}`) : null),
    h("div", { role: "progressbar", "aria-label": "Progress through this level", "aria-valuenow": Math.round(within * 100), "aria-valuemin": 0, "aria-valuemax": 100,
      style: "height:10px;border-radius:99px;background:var(--line-2);overflow:hidden" },
      h("div", { style: `height:100%;width:${Math.round(within * 100)}%;background:var(--brass);border-radius:99px` })),
    h("div", { class: "small muted" }, d.next_milestone ? `${d.next_milestone - d.rating} rating points to the next milestone. The roadmap shows the skills that usually matter on the way; it can't promise a rating.` : "The top level: keep refining everything."));
}

function summary(d, go) {
  const band = d.bands[d.band];
  const cur = d.current_band;
  const ratingBox = d.rating !== null && d.rating !== undefined
    ? h("div", {}, h("div", { class: "small muted" }, `${d.rating_system || "USCF"} rating`), h("div", { style: "font-size:1.8rem;font-weight:800" }, d.rating.toLocaleString()))
    : h("div", {}, h("div", { class: "small muted" }, "Rating"), h("div", {}, h("a", { href: "#/tournaments" }, "Connect your USCF ID"), h("span", { class: "muted small" }, " or "), h("a", { href: "#/profile" }, "add your rating"), h("span", { class: "muted small" }, " to place you automatically")));
  const pick = h("select", { class: "select", "aria-label": "Explore levels", style: "max-width:220px", onchange: (e) => go(+e.target.value) },
    d.bands.map((b) => h("option", { value: b.index, selected: b.index === d.band }, `${b.label}${b.index === cur ? " (your level)" : cur !== null && b.index > cur ? " (future)" : ""}`)));
  return h("div", { class: "card stack" },
    h("div", { class: "grid g4", style: "align-items:end" },
      ratingBox,
      h("div", {}, h("div", { class: "small muted" }, d.is_current ? "Your current level" : "Viewing level"), h("div", { style: "font-size:1.35rem;font-weight:800" }, band.label)),
      h("div", {}, h("div", { class: "small muted" }, "Next milestone"), h("div", { style: "font-size:1.35rem;font-weight:800" }, d.next_milestone ? `${d.next_milestone}` : "—")),
      h("div", { class: "stack-s" }, h("label", { class: "small muted" }, "Explore levels"), pick)),
    milestoneBar(d),
    d.is_future ? h("div", { class: "alert warn" }, h("b", {}, "Future level — not yet your primary focus. "), "It's here so you can see what's coming; your own level is where to spend your time.")
      : !d.is_current && cur !== null ? h("div", { class: "alert info" }, "An earlier level: useful for review.")
        : cur === null ? h("div", { class: "alert info" }, "No rating yet, so this shows the 800–999 level. Connect your USCF ID on Tournaments & USCF (your rating comes from there), add a rating on your profile, or pick a level above.") : null,
    h("div", { class: "row", style: "justify-content:space-between" },
      h("button", { class: "btn small", disabled: d.band === 0, onclick: () => go(d.band - 1) }, "← Previous level"),
      cur !== null && !d.is_current ? h("button", { class: "btn small primary", onclick: () => go(null) }, "My current level") : h("span"),
      h("button", { class: "btn small", disabled: d.band === d.bands.length - 1, onclick: () => go(d.band + 1) }, "Next level →")));
}

function showWhy(p) {
  if (p.workbook) return `#/workbook/${p.workbook}`;
  if (p.category === "endgame" || p.category === "middlegame") return "#/patterns";
  return "#/patterns";
}

function priorities(d) {
  return h("div", { class: "stack-s" },
    h("div", { class: "row", style: "justify-content:space-between;gap:8px" },
      h("h2", { style: "margin:0" }, "Focus now: your next 3 priorities"),
      h("div", { class: "row", style: "gap:10px" },
        d.personal ? h("span", { class: "small muted" }, `From your last ${Math.min(d.games, 10)} analyzed games`) : null,
        h("span", { class: "pill brass", title: "Plain-words AI explanations of each priority are on the way" }, "✨ AI explanations coming soon"))),
    d.personal ? null : h("div", { class: "alert info row", style: "justify-content:space-between;gap:12px" },
      h("span", {}, h("b", {}, "These are general priorities for your level. "), "Add and analyze a few of your games and they'll be based on your own play."),
      h("a", { class: "btn small primary", href: "#/add" }, icon("plus"), "Add a game")),
    h("div", { class: "grid g3" }, d.priorities.map((p, i) => h("div", { class: "card stack-s" },
      h("div", { class: "row", style: "justify-content:space-between;gap:6px" },
        h("h3", { style: "margin:0" }, `${i + 1}. ${p.title}`), h("span", { class: `pill ${PRIORITY_TONE[p.priority] || "gray"}` }, p.priority === "Focus" ? "Focus" : `${p.priority} priority`)),
      h("p", { class: "small", style: "margin:0" }, p.why),
      p.focus_on.length ? h("div", { class: "small" }, h("b", {}, "Focus on: "), p.focus_on.join(", ")) : null,
      h("ul", { class: "dots small", style: "margin:0" }, p.do.map((x) => h("li", {}, x))),
      h("div", { class: "small" }, h("b", {}, "Success target: "), p.target),
      h("div", { class: "row", style: "gap:6px;margin-top:auto" },
        p.examples && p.examples.length ? h("a", { class: "btn small primary", href: showWhy(p) }, "Show me why") : null,
        p.examples && p.examples[0] ? h("a", { class: "btn small", href: `#/game/${p.examples[0].game_id}/${p.examples[0].ply}` }, "See an example") : null)))));
}

// One topic: a "done" checkbox, and a link to where it's practised when that differs from its area's.
function topicRow(t, c, reload) {
  const elsewhere = t.practice && (!c.practice || t.practice.href !== c.practice.href);
  const inProgress = t.status !== "mastered" && t.status !== "not_started";
  return h("label", { class: "row", style: "gap:10px;flex-wrap:nowrap;align-items:flex-start;border-top:1px solid var(--line);padding:8px 0;cursor:pointer" },
    h("span", { style: "padding-top:2px" }, topicCheck(t, reload)),
    h("div", { style: "min-width:0" },
      h("b", { class: "small", style: t.status === "mastered" ? "text-decoration:line-through;color:var(--muted)" : "" }, t.title),
      inProgress ? h("span", { class: "pill gray", style: "margin-left:6px" }, STATUS_LABEL[t.status]) : null,
      h("div", { class: "small muted" }, t.goal,
        elsewhere ? [" · ", h("a", { href: t.practice.href }, `Practice: ${t.practice.label} →`)] : null)));
}

function areaCard(c, reload, focus) {
  const tiers = c.key === "endgame" ? ENDGAME_TIERS : TIERS;
  const body = h("div", { class: "stack-s" },
    ["now", "review", "preview"].filter((k) => c[k].length).map((k) => h("div", {},
      h("div", { class: "small", style: "font-weight:700;margin-top:6px" }, tiers[k], k === "preview" ? h("span", { class: "muted", style: "font-weight:500" }, " · not yet your focus") : null),
      c[k].map((t) => topicRow(t, c, reload)))));
  const started = c.completed > 0 || (c.progress || 0) > 0;
  const label = () => (details.open ? "Hide topics" : started ? "Continue learning" : "Start");
  const details = h("details", { class: "area-topics", open: open.has(c.key) },
    h("summary", { class: `btn small${started ? "" : " primary"}`, style: "list-style:none;display:inline-flex" }), body);
  details.querySelector("summary").textContent = label();
  details.addEventListener("toggle", () => { if (details.open) open.add(c.key); else open.delete(c.key); details.querySelector("summary").textContent = label(); });
  return h("div", { class: `card area-card${focus ? " focus" : ""}` },
    h("div", { class: "row", style: "justify-content:space-between;gap:6px" },
      h("h3", { style: "margin:0" }, c.title),
      h("div", { class: "row", style: "gap:6px" }, focus ? h("span", { class: "pill brass" }, "Focus") : null,
        c.priority ? h("span", { class: `pill ${PRIORITY_TONE[c.priority]}` }, `${c.priority}`) : null)),
    h("div", { class: "row", style: "gap:10px;flex-wrap:nowrap" },
      h("div", { style: "flex:1" }, meter(c.mastery ?? 0, level(c.mastery ?? 0))), h("b", {}, pctText(c.mastery))),
    c.performance ? h("div", { class: "small muted" }, `From your games: ${c.performance.score}%`) : null,
    h("div", { class: "small" }, `${c.completed} of ${c.total} topics done`, c.now.length ? ` · ${c.now.length} new at this level` : ""),
    c.practice ? h("div", { class: "small" }, "Practice in ", h("a", { href: c.practice.href }, `${c.practice.label} →`)) : null,
    details);
}

// The areas, with this level's focus priorities first and marked.
function areas(d) {
  const focus = new Set(d.priorities.map((p) => p.category));
  const sorted = [...d.categories].sort((a, b) => focus.has(b.key) - focus.has(a.key));
  return h("div", { class: "grid g2 area-grid" }, sorted.map((c) => areaCard(c, load, focus.has(c.key))));
}

// 20. This week's plan, ticked off day by day (kept on this device, per week), with today highlighted.
function isoWeek(date = new Date()) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const start = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return `${d.getUTCFullYear()}-W${String(Math.ceil(((d - start) / 86400000 + 1) / 7)).padStart(2, "0")}`;
}
function weekPlan(d) {
  const key = `cc-plan-${isoWeek()}`;
  let done;
  try { done = new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch (_) { done = new Set(); }
  const today = new Date().toLocaleDateString("en-US", { weekday: "long" });
  return h("table", { class: "week-plan" }, h("tbody", {}, d.weekly_plan.map((w) => {
    const box = h("input", { type: "checkbox", checked: done.has(w.day), "aria-label": `Done: ${w.day}`, onchange: (e) => {
      if (e.target.checked) done.add(w.day); else done.delete(w.day);
      try { localStorage.setItem(key, JSON.stringify([...done])); } catch (_) { /* not remembered in a private window */ }
      row.classList.toggle("done", e.target.checked);
    } });
    const row = h("tr", { class: `${w.day === today ? "today" : ""}${done.has(w.day) ? " done" : ""}` },
      h("td", { style: "width:28px" }, box), h("td", { style: "white-space:nowrap;font-weight:600" }, w.day, w.day === today ? h("span", { class: "pill brand", style: "margin-left:6px" }, "Today") : null),
      h("td", {}, w.plan));
    return row;
  })));
}
let load = async () => {};

export async function roadmapView() {
  document.title = "My roadmap · Chess Varsity";
  const player = currentPlayer();
  const page = h("div", { class: "stack" });
  let viewing = null;

  async function go(band) { viewing = band; await load(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  load = async function () {
    const d = await api(`/api/players/${player.id}/roadmap${viewing === null ? "" : `?band=${viewing}`}`);
    const m = d.meta;
    mount(page,
      h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My chess roadmap"),
        h("p", {}, "Where you are, what to learn now and why, and what comes next: from your rating, your own games and the topics you mark."))),
      summary(d, go),
      priorities(d),
      h("h2", { style: "margin:8px 0 0" }, "Your areas"),
      areas(d),
      h("div", { class: "grid g2" },
        h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, icon("bulb"), " Thinking process: before every move"),
          h("ol", { style: "margin:0;padding-left:1.3em" }, d.thinking.map((s) => h("li", {}, s)))),
        h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, icon("swords"), " Attack & defense: ask yourself"),
          h("ul", { class: "dots", style: "margin:0" }, d.attack_questions.map((q) => h("li", {}, q))))),
      h("div", { class: "grid g2" },
        h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, icon("calendar"), " This week's training plan"),
          weekPlan(d),
          h("div", { class: "small muted" }, d.personal ? "Weighted towards your top priorities, and it changes as your games do." : "Add games to weight it towards your own weak spots.")),
        h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, icon("target"), ` Practice guidelines: ${d.bands[d.band].label}`),
          h("ul", { class: "dots small", style: "margin:0" },
            h("li", {}, h("b", {}, "Puzzles: "), `about ${m.puzzles} a day (${m.difficulty})`),
            h("li", {}, h("b", {}, "Calculation: "), `${m.depth} (a guideline, not a rule)`),
            h("li", {}, h("b", {}, "Engines: "), m.engine),
            h("li", {}, h("b", {}, "Openings: "), m.repertoire),
            h("li", {}, h("b", {}, "Main goal at this level: "), m.focus)),
          h("div", { class: "row", style: "gap:6px" }, h("a", { class: "btn small", href: "#/academy" }, "Attack academy"), h("a", { class: "btn small", href: "#/workbook" }, "My workbook"),
            h("a", { class: "btn small", href: "#/openings" }, "Openings")))),
      h("p", { class: "small muted", style: "margin:0" }, "Levels and guidelines are a general guide for learning, not a promise of a rating."));
  };
  await load();
  return page;
}
