// My chess plan: what's coming up, what needs doing, and what to prepare for. A month grid or an agenda of
// tournaments, training, registration deadlines, hotel stays and goal dates, with a details drawer for each.
import { h, icon, mount, toast } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { askChoice } from "../dialogs.js";
import { go } from "../router.js";
import { askTournament } from "./planner.js";
import { askTraining, clock, timeRange } from "./training.js";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const nice = (s) => parse(s).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
const short = (s) => parse(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const dayHead = (s) => parse(s).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }).toUpperCase();
const span = (i) => (i.end !== i.start ? (i.start.slice(0, 7) === i.end.slice(0, 7) ? `${short(i.start)}–${parse(i.end).getDate()}` : `${short(i.start)} – ${short(i.end)}`) : short(i.start));
const daysBetween = (a, b) => Math.round((parse(b) - parse(a)) / 86400000);

const KINDS = {
  upcoming: { label: "Tournament", cls: "ev-up", ic: "🏆" },
  past: { label: "Past tournament", cls: "ev-past", ic: "🏁" },
  training: { label: "Training", cls: "ev-train", ic: "♟" },
  deadline: { label: "Registration deadline", cls: "ev-dead", ic: "📝" },
  hotel: { label: "Hotel", cls: "ev-hotel", ic: "🏨" },
  goal: { label: "Goal", cls: "ev-goal", ic: "🎯" },
};
// The filter chips; each covers one or more kinds.
const FILTERS = [["tournaments", "Tournaments", ["upcoming", "past"]], ["training", "Training", ["training"]], ["deadlines", "Deadlines", ["deadline"]],
  ["travel", "Travel", ["hotel"]], ["goals", "Goals", ["goal"]]];
const kindOf = (i) => (i.type === "tournament" ? (i.kind === "upcoming" ? "upcoming" : "past") : i.type);
const RANK = { upcoming: 0, past: 1, hotel: 2, training: 3, deadline: 4, goal: 5 };
const TRAINING_KIND = { class: "Class", lesson: "Private lesson", club: "Club night", practice: "Practice", study: "Home study", other: "Training" };
const STATUS = { done: "✓", todo: "⚑", na: "—" };
const titleOf = (i) => (i.type === "deadline" ? i.event_name || i.title.replace(/^Register by: /, "") : i.type === "goal" ? i.title.replace(/^Goal: /, "") : i.type === "hotel" ? (i.hotel_name || i.title.replace(/^Hotel: /, "")) : i.title);

function countdown(start, today) {
  const n = daysBetween(today, start);
  return n < 0 ? "under way" : n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`;
}

export async function calendarView(_params, query) {
  document.title = "Calendar · Chess Varsity";
  const player = currentPlayer();
  const today = iso(new Date());
  const first = query && /^\d{4}-\d{2}$/.test(query.month || "") ? parse(`${query.month}-01`) : new Date();
  const st = { year: first.getFullYear(), month: first.getMonth(), view: "month", on: new Set(FILTERS.map(([k]) => k)), agendaPast: false };
  let data = { items: [], undated: 0 }, loaded = "";
  let ahead = { items: [] };         // the next four months, for "Next up" whatever month is on screen

  const grid = h("div", { class: "cal-grid", role: "grid", "aria-label": "Month" });
  const title = h("h2", { class: "cal-title" });
  const agenda = h("div", { class: "stack" });
  const body = h("div", { class: "stack-s" });
  const nextUp = h("section", { class: "next-up", "aria-label": "Next up" });
  const chips = h("div", { class: "filter-chips", role: "group", "aria-label": "Show" });
  const notes = h("div", {});
  const shownKinds = () => new Set(FILTERS.filter(([k]) => st.on.has(k)).flatMap(([, , kinds]) => kinds));
  const visible = () => { const k = shownKinds(); return data.items.filter((i) => k.has(kindOf(i))); };
  const on = (items, day) => items.filter((i) => i.start <= day && day <= i.end).sort((a, b) => RANK[kindOf(a)] - RANK[kindOf(b)] || (a.time || "").localeCompare(b.time || ""));

  const gridStart = () => { const d = new Date(st.year, st.month, 1); d.setDate(1 - d.getDay()); return d; };
  function wanted() {
    if (st.view === "agenda") {
      const a = new Date(); if (st.agendaPast) a.setDate(a.getDate() - 30);
      const b = new Date(); b.setDate(b.getDate() + 180);
      return [iso(a), iso(b)];
    }
    const a = gridStart(), b = new Date(a); b.setDate(b.getDate() + 41);
    return [iso(a), iso(b)];
  }
  async function refresh(force = false) {
    const [a, b] = wanted();
    const end = new Date(); end.setDate(end.getDate() + 120);
    const jobs = [];
    if (force || loaded !== `${a}|${b}`) jobs.push(api(`/api/players/${player.id}/calendar?start=${a}&end=${b}`).then((d) => { data = d; loaded = `${a}|${b}`; }));
    if (force || !ahead.loaded) jobs.push(api(`/api/players/${player.id}/calendar?start=${today}&end=${iso(end)}`).then((d) => { ahead = { ...d, loaded: true }; }));
    await Promise.all(jobs);
    paint();
  }
  const reload = () => refresh(true);
  const shift = (n) => { const d = new Date(st.year, st.month + n, 1); st.year = d.getFullYear(); st.month = d.getMonth(); refresh(); };

  // ---- the details drawer (right side on a computer, a sheet from the bottom on a phone) ----
  const drawerBody = h("div", { class: "drawer-body" });
  const drawer = h("aside", { class: "cal-drawer", role: "dialog", "aria-modal": "true", "aria-labelledby": "drawer-title", hidden: true },
    h("button", { class: "icon-btn drawer-close", type: "button", "aria-label": "Close", onclick: () => closeDrawer() }, icon("x")), drawerBody);
  const scrim = h("div", { class: "cal-scrim", hidden: true, onclick: () => closeDrawer() });
  let lastFocus = null, drawerFor = null;
  function openDrawer(content, key) {
    drawerFor = key;
    mount(drawerBody, content);
    if (drawer.hidden) lastFocus = document.activeElement;
    drawer.hidden = false; scrim.hidden = false;
    const heading = drawer.querySelector("#drawer-title"); if (heading) { heading.tabIndex = -1; heading.focus(); }
  }
  function closeDrawer() {
    if (drawer.hidden) return;
    drawer.hidden = true; scrim.hidden = true; drawerFor = null;
    if (lastFocus && lastFocus.isConnected) lastFocus.focus();
  }
  const onKey = (e) => { if (e.key === "Escape") closeDrawer(); };
  document.addEventListener("keydown", onKey);

  const fact = (label, value) => (value ? h("div", { class: "fact" }, h("span", { class: "muted small" }, label), h("span", {}, value)) : null);
  const head = (i, sub) => h("div", { class: "stack-s" },
    h("span", { class: `kind-tag ${KINDS[kindOf(i)].cls}` }, KINDS[kindOf(i)].ic, " ", KINDS[kindOf(i)].label),
    h("h2", { id: "drawer-title", style: "margin:0" }, titleOf(i)), sub ? h("div", { class: "muted" }, sub) : null);

  async function markSession(i, action) {
    try { await api(`/api/training/${i.id}/occurrence`, { method: "POST", body: { date: i.start, action } }); await reload(); closeDrawer(); toast("Updated"); }
    catch (e) { toast(e.message); }
  }
  async function tickPrep(i, step, done) {
    try {
      i.prep = await api(`/api/events/${i.id}/prep`, { method: "PATCH", body: { step, done } });
      for (const list of [data.items, ahead.items]) for (const x of list) if (x.type === "tournament" && x.id === i.id) x.prep = i.prep;
      openDrawer(details(i), drawerFor); paintNextUp();
    } catch (e) { toast(e.message); }
  }

  function prepBlock(i) {
    const p = i.prep;
    return h("div", { class: "prep-box stack-s" },
      h("div", { class: "row spread" }, h("b", {}, `Prepare for ${i.title}`), h("span", { class: "pill brass" }, `${p.percent}% ready`)),
      h("div", { class: "prep-bar", role: "progressbar", "aria-label": "Preparation", "aria-valuenow": p.percent, "aria-valuemin": 0, "aria-valuemax": 100 }, h("i", { style: `width:${p.percent}%` })),
      h("ul", { class: "prep-list" }, p.steps.map((s) => h("li", {},
        h("label", { class: "row", style: "gap:8px;flex-wrap:nowrap;cursor:pointer;flex:1" },
          h("input", { type: "checkbox", checked: s.done, disabled: s.done && s.auto && !s.by_hand, "aria-label": s.label, onchange: (e) => tickPrep(i, s.key, e.target.checked) }),
          h("span", { style: s.done ? "color:var(--muted);text-decoration:line-through" : "" }, s.label),
          s.done && s.auto && !s.by_hand ? h("span", { class: "small muted" }, "· done this week") : null),
        h("a", { class: "small", href: s.href }, "Open →")))),
      h("a", { class: "btn primary", href: `#/prep?event=${i.id}` }, "Start preparation →"));
  }

  function details(i) {
    const k = kindOf(i);
    if (i.type === "tournament") {
      const s = i.statuses || {};
      const results = i.wins + i.draws + i.losses;
      return h("div", { class: "stack" },
        head(i, `${span(i)}, ${i.start.slice(0, 4)}${k === "upcoming" ? ` · ${countdown(i.start, today)}` : ""}`),
        h("div", { class: "facts" },
          fact("Where", i.location), fact("Section", /^\d+$/.test(i.section || "") ? `Section ${i.section}` : i.section), fact("Time control", i.time_control),
          k === "upcoming" && i.attending !== "skip" ? [fact("Registration", `${STATUS[s.reg_status] || ""} ${s.reg_status === "done" ? "Registered" : s.reg_status === "na" ? "Not needed" : "Not yet"}`),
            fact("Entry fee", `${STATUS[s.paid_status] || ""} ${s.paid_status === "done" ? "Paid" : s.paid_status === "na" ? "Not needed" : "Not yet"}`),
            fact("Hotel", `${STATUS[s.hotel_status] || ""} ${s.hotel_status === "done" ? `Booked${i.hotel_name ? ` · ${i.hotel_name}` : ""}` : s.hotel_status === "na" ? "Not needed" : "Not booked yet"}`),
            fact("Travel", `${STATUS[s.travel_status] || ""} ${s.travel_status === "done" ? "Sorted" : s.travel_status === "na" ? "Not needed" : "Not yet"}`),
            i.reg_deadline ? fact("Register by", nice(i.reg_deadline)) : null] : null,
          k === "upcoming" && i.attending === "skip" ? fact("Plan", "Not going") : null,
          fact("Games", i.rounds ? `${i.games_with_moves} / ${i.rounds} with moves` : ""),
          results ? fact("Result", `${i.wins}-${i.draws}-${i.losses} (won-drawn-lost)`) : null,
          (i.ratings || []).length ? fact("Rating", i.ratings.map((c) => `${c.before} → ${c.after} (${c.change > 0 ? "+" : ""}${c.change})`).join(" · ")) : null),
        k === "upcoming" && i.prep && i.attending !== "skip" ? prepBlock(i) : null,
        h("div", { class: "row", style: "gap:8px" },
          h("a", { class: "btn", href: `#/tournaments?event=${i.id}` }, "View tournament"),
          k === "upcoming" ? h("a", { class: "btn", href: `#/planner?event=${i.id}` }, icon("flag"), "Registration, hotel & travel") : null));
    }
    if (i.type === "training") {
      return h("div", { class: "stack" },
        head(i, `${nice(i.start)} · ${timeRange(i.time, i.end_time)}`),
        h("div", { class: "facts" }, fact("Kind", TRAINING_KIND[i.kind]), fact("Coach", i.coach), fact("Topic", i.topic), fact("Where", i.location),
          fact("Repeats", i.recurrence && i.recurrence !== "none" ? i.recurrence : ""), fact("Status", i.skipped ? "Cancelled" : i.done ? "✓ Attended" : "")),
        i.notes ? h("p", { class: "small", style: "margin:0" }, i.notes) : null,
        h("div", { class: "row", style: "gap:8px" },
          i.skipped ? null : h("button", { class: "btn", type: "button", "data-mark": i.done ? "undone" : "done", onclick: () => markSession(i, i.done ? "undone" : "done") }, i.done ? "Not attended after all" : "✓ Mark as attended"),
          h("button", { class: "btn", type: "button", "data-mark": i.skipped ? "unskip" : "skip", onclick: () => markSession(i, i.skipped ? "unskip" : "skip") }, i.skipped ? "Bring it back" : "Cancel this one"),
          h("a", { class: "btn", href: "#/training" }, "Open training")));
    }
    if (i.type === "deadline") {
      return h("div", { class: "stack" },
        head(i, `Register by ${nice(i.start)} · ${countdown(i.start, today)}`),
        h("div", { class: "facts" }, fact("Tournament", i.event_name), fact("Starts", i.event_start ? nice(i.event_start) : ""), fact("Status", i.done ? "✓ Registered" : "⚑ Not registered yet")),
        h("div", { class: "row", style: "gap:8px" },
          h("a", { class: i.done ? "btn" : "btn primary", href: `#/planner?event=${i.id}` }, i.done ? "View in the planner" : "Register / open the planner"),
          h("a", { class: "btn", href: `#/tournaments?event=${i.id}` }, "View tournament")));
    }
    if (i.type === "hotel") {
      return h("div", { class: "stack" },
        head(i, `${span(i)} · for ${i.event_name}`),
        h("div", { class: "facts" }, fact("Status", i.done ? "✓ Booked" : "⚑ Not booked yet"), fact("Confirmation", i.confirmation)),
        h("div", {}, h("a", { class: "btn", href: `#/planner?event=${i.id}` }, "Open in the planner")));
    }
    const pct = i.steps ? Math.round((100 * i.steps_done) / i.steps) : null;
    return h("div", { class: "stack" },
      head(i, `Due ${nice(i.start)} · ${countdown(i.start, today).replace("under way", "overdue")}`),
      i.notes ? h("p", { style: "margin:0" }, i.notes) : null,
      pct !== null ? h("div", { class: "stack-s" }, h("div", { class: "small muted" }, `${i.steps_done} of ${i.steps} steps done`),
        h("div", { class: "prep-bar" }, h("i", { style: `width:${pct}%;background:var(--ev-goal)` }))) : null,
      h("div", {}, h("a", { class: "btn", href: "#/goals" }, "View goal")));
  }
  const show = (i) => openDrawer(details(i), `${i.type}:${i.id}:${i.start}`);

  function dayDrawer(day) {
    const items = on(visible(), day);
    openDrawer(h("div", { class: "stack" },
      h("h2", { id: "drawer-title", style: "margin:0" }, nice(day)),
      items.length ? h("div", { class: "stack-s" }, items.map((i) => agendaRow(i, false))) : h("div", { class: "muted" }, "Nothing on this day."),
      h("div", { class: "row", style: "gap:8px" },
        h("button", { class: "btn small", id: "add-training-day", onclick: () => addTraining(day) }, icon("plus"), "Add training here"),
        h("button", { class: "btn small", id: "add-on-day", onclick: () => addTournament(day) }, icon("plus"), "Add a tournament here"))), `day:${day}`);
  }

  // ---- adding things ----
  async function addTraining(day = "") {
    const b = await askTraining({ date: day });
    if (!b) return;
    try { await api("/api/training", { method: "POST", body: b }); closeDrawer(); await reload(); toast("Training added"); } catch (e) { toast(e.message); }
  }
  async function addTournament(day = "") {
    const b = await askTournament({ startDate: day });
    if (!b) return;
    if (b.start_date) b.kind = b.start_date < today ? "past" : "upcoming";          // a day that has gone by is a tournament already played
    else b.kind = "upcoming";
    try { await api("/api/events", { method: "POST", body: b }); closeDrawer(); await reload(); toast("Tournament added"); } catch (e) { toast(e.message); }
  }
  // Deadlines and hotel stays belong to a tournament: pick it, then fill them in on the planner.
  async function forTournament(what) {
    const upcoming = [...new Map(ahead.items.filter((i) => i.type === "tournament" && i.kind === "upcoming").map((i) => [i.id, i])).values()];
    if (!upcoming.length) { toast("Add the tournament first, then its registration deadline and hotel."); return addTournament(); }
    const id = await askChoice({ title: `Add a ${what}`, message: "Which tournament is it for? You'll fill it in on the planner.",
      options: upcoming.map((i) => ({ value: i.id, label: `${i.title} · ${span(i)}` })) });
    if (id) go(`/planner?event=${id}`);
  }
  const addMenu = h("details", { class: "add-menu" },
    h("summary", { class: "btn primary small", "aria-label": "Add to the calendar" }, icon("plus"), "Add"),
    h("div", { class: "menu", role: "menu" },
      [["🏆", "Tournament", () => addTournament()], ["♟", "Training", () => addTraining()], ["📝", "Registration deadline", () => forTournament("registration deadline")],
        ["🏨", "Hotel", () => forTournament("hotel stay")], ["🎯", "Goal", () => go("/goals")], ["📅", "Other", () => addTraining()]]
        .map(([ic, t, fn]) => h("button", { type: "button", role: "menuitem", onclick: () => { addMenu.open = false; fn(); } }, h("span", { "aria-hidden": "true" }, ic), t))));
  const onClickAway = (e) => { if (addMenu.open && !addMenu.contains(e.target)) addMenu.open = false; };
  document.addEventListener("click", onClickAway);

  // ---- next up ----
  function paintNextUp() {
    const soon = ahead.items.filter((i) => i.end >= today && (
      (i.type === "tournament" && i.kind === "upcoming" && i.attending !== "skip") || (i.type === "training" && !i.skipped && !i.done)
      || (i.type === "deadline" && !i.done) || (i.type === "hotel" && !i.done && i.start >= today) || i.type === "goal"))
      .sort((a, b) => a.start.localeCompare(b.start) || (a.time || "").localeCompare(b.time || "") || RANK[kindOf(a)] - RANK[kindOf(b)]).slice(0, 4);
    mount(nextUp,
      h("div", { class: "next-h" }, "Next up"),
      soon.length ? h("div", { class: "next-row" }, soon.map((i) => {
        const k = kindOf(i);
        const extra = i.type === "tournament" ? [i.needs.length ? `⚑ ${i.needs.join(", ")} to do` : "", i.prep ? `${i.prep.percent}% prepared` : ""].filter(Boolean).join(" · ")
          : i.type === "deadline" ? "⚑ Not registered yet" : i.type === "training" && i.time ? clock(i.time) : "";
        return h("button", { class: `next-card ${KINDS[k].cls}`, type: "button", onclick: () => show(i) },
          h("span", { class: "next-ic", "aria-hidden": "true" }, KINDS[k].ic),
          h("span", { class: "next-text" },
            h("span", { class: "next-kind" }, i.type === "deadline" ? "Registration deadline" : i.type === "hotel" ? "Hotel check-in" : KINDS[k].label),
            h("b", { class: "next-title" }, titleOf(i)),
            h("span", { class: "small" }, span(i), " · ", h("span", { class: "muted" }, countdown(i.start, today))),
            extra ? h("span", { class: "small next-extra" }, extra) : null));
      })) : h("div", { class: "muted small" }, "Nothing planned yet. Add a tournament or a training session to see it here."));
  }

  // ---- filters ----
  function paintChips() {
    const all = st.on.size === FILTERS.length;
    mount(chips,
      h("button", { type: "button", class: "fchip", "aria-pressed": all ? "true" : "false", onclick: () => { st.on = new Set(FILTERS.map(([k]) => k)); paint(); } }, "All"),
      FILTERS.map(([k, t, kinds]) => h("button", { type: "button", class: `fchip ${KINDS[kinds[0]].cls}`, "data-filter": k, "aria-pressed": !all && st.on.has(k) ? "true" : "false",
        onclick: () => {
          // From "All", a chip shows just that kind; after that chips add and remove kinds; none left means all again.
          if (all) st.on = new Set([k]); else if (st.on.has(k)) st.on.delete(k); else st.on.add(k);
          if (!st.on.size) st.on = new Set(FILTERS.map(([x]) => x));
          paint();
        } }, h("span", { class: "fdot", "aria-hidden": "true" }), t)));
  }

  // ---- month grid ----
  const LANES = 3;
  function assignLanes(items) {
    const lanes = new Map(), ends = [];
    const order = [...items].sort((a, b) => a.start.localeCompare(b.start) || b.end.localeCompare(a.end) || RANK[kindOf(a)] - RANK[kindOf(b)] || (a.time || "").localeCompare(b.time || ""));
    for (const i of order) {
      let n = ends.findIndex((end) => end < i.start);
      if (n < 0) { n = ends.length; ends.push(i.end); } else ends[n] = i.end;
      lanes.set(i, n);
    }
    return lanes;
  }
  const chipLabel = (i) => (i.type === "training" && i.time ? `${clock(i.time).replace(" ", "")} ${i.title}` : `${KINDS[kindOf(i)].ic} ${titleOf(i)}`);
  function chip(i, day, col) {
    const k = kindOf(i);
    const isStart = i.start === day, isEnd = i.end === day, showLabel = isStart || col === 0;
    const needs = i.type === "tournament" && i.kind === "upcoming" && i.needs.length && i.attending !== "skip";
    const cls = `ev ${KINDS[k].cls}${isStart ? " s" : ""}${isEnd ? " e" : ""}${needs ? " needs" : ""}${i.skipped ? " skipped" : ""}${i.done ? " attended" : ""}`;
    return h("button", { class: cls, type: "button", title: `${titleOf(i)} · ${KINDS[k].label} · ${span(i)}`, "aria-label": `${KINDS[k].label}: ${titleOf(i)}, ${span(i)}`, "data-type": k, "data-event": i.id,
      onclick: (ev) => { ev.stopPropagation(); show(i); } },
      h("span", { class: "ev-t" }, showLabel ? chipLabel(i) : " "));
  }
  function paintGrid() {
    const items = visible(), lanes = assignLanes(items);
    const start = gridStart();
    const cells = [];
    for (let n = 0; n < 42; n++) {
      const d = new Date(start); d.setDate(start.getDate() + n);
      const day = iso(d), col = n % 7, here = on(items, day), inMonth = d.getMonth() === st.month;
      if (n >= 35 && !inMonth && col === 0) break;
      const slots = Array(LANES).fill(null);
      let more = 0;
      for (const i of here) { const lane = lanes.get(i); if (lane < LANES) slots[lane] = i; else more++; }
      while (slots.length && slots[slots.length - 1] === null) slots.pop();
      cells.push(h("div", { class: `cal-cell${inMonth ? "" : " out"}${day === today ? " today" : ""}${col === 0 || col === 6 ? " wknd" : ""}`, role: "gridcell", "data-day": day,
        tabindex: "0", "aria-label": `${nice(day)}${here.length ? `, ${here.length} item${here.length === 1 ? "" : "s"}` : ""}`,
        onclick: () => dayDrawer(day), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); dayDrawer(day); } } },
        h("div", { class: "cal-n" }, d.getDate() === 1 ? `${MONTHS[d.getMonth()].slice(0, 3)} 1` : d.getDate()),
        h("div", { class: "cal-evs" }, slots.map((i) => (i ? chip(i, day, col) : h("span", { class: "ev-gap" }))), more ? h("span", { class: "cal-more" }, `+${more} more`) : null)));
    }
    mount(grid, DAYS.map((d) => h("div", { class: "cal-h", role: "columnheader" }, d)), cells);
    title.textContent = `${MONTHS[st.month]} ${st.year}`;
  }

  // ---- agenda ----
  function agendaRow(i, withDate) {
    const k = kindOf(i);
    const training = i.type === "training";
    const sub = [withDate ? span(i) : "", training ? timeRange(i.time, i.end_time) : "", training ? i.topic : "", i.location,
      i.type === "deadline" ? (i.done ? "✓ Registered" : "⚑ Not registered yet") : "", i.type === "hotel" ? (i.done ? "✓ Booked" : "⚑ Not booked yet") : "",
      i.type === "tournament" && i.kind === "upcoming" && i.needs.length && i.attending !== "skip" ? `⚑ ${i.needs.join(", ")} to do` : "",
      training && i.skipped ? "Cancelled" : training && i.done ? "✓ Attended" : ""].filter(Boolean).join(" · ");
    return h("button", { type: "button", class: `agenda-item ${KINDS[k].cls}${i.skipped ? " skipped" : ""}`, "data-type": k, onclick: () => show(i) },
      h("span", { class: "ag-ic", "aria-hidden": "true" }, KINDS[k].ic),
      h("span", { style: "flex:1;min-width:0;text-align:left" }, h("b", {}, titleOf(i)), h("span", { class: "small muted", style: "display:block" }, `${KINDS[k].label}${sub ? ` · ${sub}` : ""}`)),
      icon("chevron"));
  }
  function paintAgenda() {
    const [a] = wanted();
    const items = visible().filter((i) => i.end >= (st.agendaPast ? a : today)).sort((x, y) => x.start.localeCompare(y.start) || (x.time || "").localeCompare(y.time || ""));
    // This week / Next week / each later month; inside, one heading per day.
    const now = parse(today), weekEnd = new Date(now); weekEnd.setDate(now.getDate() + (6 - now.getDay()));
    const nextEnd = new Date(weekEnd); nextEnd.setDate(weekEnd.getDate() + 7);
    const bucket = (d) => (d < today ? "Earlier" : d <= iso(weekEnd) ? "This week" : d <= iso(nextEnd) ? "Next week" : `${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`);
    const groups = new Map();
    for (const i of items) {
      const day = i.start < today && i.end >= today ? today : i.start;
      const g = bucket(day);
      if (!groups.has(g)) groups.set(g, new Map());
      const days = groups.get(g); days.set(day, [...(days.get(day) || []), i]);
    }
    mount(agenda,
      h("label", { class: "row small", style: "gap:8px;cursor:pointer" }, h("input", { type: "checkbox", checked: st.agendaPast, onchange: async (e) => { st.agendaPast = e.target.checked; await refresh(); } }), "Include the last month"),
      groups.size ? [...groups].map(([g, days]) => h("section", { class: "card stack-s ag-group" }, h("h3", { class: "ag-h" }, g),
        [...days].map(([day, list]) => h("div", { class: "ag-day" }, h("div", { class: "ag-date" }, day === today ? `TODAY · ${dayHead(day)}` : dayHead(day)),
          h("div", { class: "stack-s" }, list.map((i) => agendaRow(i, i.end !== i.start)))))))
        : h("div", { class: "card muted" }, "Nothing coming up. Add a tournament or a training session with + Add."));
  }

  // ---- controls ----
  const viewSwitch = h("div", { class: "seg", role: "tablist", "aria-label": "View" });
  const controls = h("div", { class: "cal-controls" },
    h("div", { class: "row", style: "gap:6px;flex-wrap:nowrap" },
      h("button", { class: "btn small", id: "cal-prev", "aria-label": "Previous month", onclick: () => shift(-1) }, "‹"), title,
      h("button", { class: "btn small", id: "cal-next", "aria-label": "Next month", onclick: () => shift(1) }, "›"),
      h("button", { class: "btn small", id: "cal-today", onclick: () => { const n = new Date(); st.year = n.getFullYear(); st.month = n.getMonth(); refresh(); } }, "Today")),
    h("div", { class: "row", style: "gap:8px" }, viewSwitch, addMenu));

  function paint() {
    mount(viewSwitch, [["month", "Month"], ["agenda", "Agenda"]].map(([k, t]) => h("button", { type: "button", role: "tab", "data-view": k, "aria-selected": st.view === k ? "true" : "false",
      onclick: () => { st.view = k; refresh(); } }, t)));
    title.classList.toggle("hidden", st.view !== "month");
    controls.querySelectorAll("#cal-prev, #cal-next").forEach((b) => b.classList.toggle("hidden", st.view !== "month"));
    paintChips(); paintNextUp();
    if (st.view === "month") { paintGrid(); mount(body, h("div", { class: "cal-wrap" }, grid)); }
    else { paintAgenda(); mount(body, agenda); }
    mount(notes, data.undated ? h("p", { class: "muted small", style: "margin:0" }, `${data.undated} tournament${data.undated === 1 ? " has" : "s have"} no date yet, so ${data.undated === 1 ? "it is" : "they are"} not on the calendar. Add a start date in the `, h("a", { href: "#/planner" }, "planner"), ".") : null);
  }
  await refresh();

  const page = h("div", { class: "stack cal2", style: "max-width:1100px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Calendar"),
      h("p", {}, "Everything coming up in your chess journey — tournaments, training, deadlines and goals."))),
    nextUp, controls, chips, body, notes, scrim, drawer);
  page.cleanup = () => { document.removeEventListener("keydown", onKey); document.removeEventListener("click", onClickAway); };
  return page;
}
