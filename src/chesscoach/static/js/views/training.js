// The training schedule: classes, lessons, club nights and practice, by week, with the regular timetable underneath.
import { h, icon, mount, toast } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { askForm } from "../dialogs.js";
import { empty } from "../components.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FULL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const KINDS = [["class", "Class"], ["lesson", "Private lesson"], ["club", "Club night"], ["practice", "Practice"], ["study", "Home study"], ["other", "Other"]];
const REPEATS = [["none", "Does not repeat"], ["weekly", "Every week"], ["biweekly", "Every other week"], ["monthly", "Every month"]];
const pad = (n) => String(n).padStart(2, "0");
export const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parseIso = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

/** "16:30" -> "4:30 pm". */
export function clock(t) {
  if (!t) return "";
  const [hh, mm] = t.split(":").map(Number);
  return `${hh % 12 || 12}:${pad(mm)} ${hh < 12 ? "am" : "pm"}`;
}
export const timeRange = (a, b) => (a && b ? `${clock(a)} to ${clock(b)}` : a ? clock(a) : "All day");
/** A compact range for narrow places: "4:30-5:30 pm". */
export function shortRange(a, b) {
  if (!a) return "All day";
  if (!b) return clock(a);
  const [x, y] = [clock(a), clock(b)];
  return x.slice(-2) === y.slice(-2) ? `${x.slice(0, -3)}-${y}` : `${x}-${y}`;
}

/** Ask for a training session or series. Resolves to the request body, or null if cancelled. */
export async function askTraining({ series = null, date = "" } = {}) {
  const s = series || {};
  const v = await askForm({
    title: series ? "Edit training" : "Add training", confirmLabel: series ? "Save" : "Add to the schedule",
    fields: [
      { name: "title", label: "What is it?", required: true, value: s.title || "", placeholder: "e.g. Tactics class with Coach Lee", maxlength: 100 },
      { name: "kind", label: "Kind", value: s.kind || "class", options: KINDS },
      { name: "start_date", label: "Date (or the first date if it repeats)", type: "date", value: s.start_date || date || isoDate(new Date()), required: true },
      { name: "start_time", label: "Starts", type: "time", value: s.start_time || "" },
      { name: "end_time", label: "Ends", type: "time", value: s.end_time || "" },
      { name: "recurrence", label: "Does it repeat?", value: s.recurrence || "none", options: REPEATS },
      { name: "weekdays", label: "On which days (for a weekly repeat; none ticked means the day of the first date)", checks: DAYS.map((d, i) => [i, d]), value: s.weekdays || [] },
      { name: "until", label: "Repeat until (optional)", type: "date", value: s.until || "" },
      { name: "location", label: "Where (or an online link)", value: s.location || "", maxlength: 120 },
      { name: "coach", label: "Coach or teacher", value: s.coach || "", maxlength: 60 },
      { name: "topic", label: "Topic (optional)", value: s.topic || "", maxlength: 60, placeholder: "e.g. Rook endgames" },
      { name: "notes", label: "Notes (optional)", value: s.notes || "", maxlength: 500 },
    ],
  });
  return v || null;
}

export async function trainingView() {
  document.title = "Training · Chess Varsity";
  const player = currentPlayer();
  const monday = (d) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
  const st = { week: monday(new Date()), series: [], items: [], summary: { sessions: 0, attended: 0, minutes: 0 } };
  const today = isoDate(new Date());
  const weekEl = h("div", { class: "week" });
  const kpis = h("div", { class: "grid g4" });
  const title = h("h2", { style: "margin:0;min-width:13em;text-align:center" });
  const regular = h("div", { class: "stack" });

  const load = async () => {
    const end = new Date(st.week); end.setDate(end.getDate() + 6);
    const [list, occ] = await Promise.all([
      api(`/api/players/${player.id}/training`),
      api(`/api/players/${player.id}/training/occurrences?start=${isoDate(st.week)}&end=${isoDate(end)}`),
    ]);
    st.series = list.series; st.items = occ.items; st.summary = occ.summary;
    paint();
  };
  const mark = async (item, action) => {
    try { await api(`/api/training/${item.series_id}/occurrence`, { method: "POST", body: { date: item.date, action } }); await load(); } catch (e) { toast(e.message); }
  };
  async function add(date) {
    const body = await askTraining({ date });
    if (!body) return;
    try { await api("/api/training", { method: "POST", body }); await load(); toast("Added to the schedule"); } catch (e) { toast(e.message); }
  }
  async function edit(series) {
    const body = await askTraining({ series });
    if (!body) return;
    try { await api(`/api/training/${series.id}`, { method: "PATCH", body }); await load(); toast("Saved"); } catch (e) { toast(e.message); }
  }
  async function remove(series) {
    if (!confirm(`Remove “${series.title}” from the schedule${series.recurrence !== "none" ? ", including every repeat" : ""}?`)) return;
    await api(`/api/training/${series.id}`, { method: "DELETE" });
    await load(); toast("Removed");
  }

  function session(item) {
    const cls = `session k-${item.kind}${item.skipped ? " skipped" : ""}${item.done ? " done" : ""}`;
    return h("div", { class: cls, "data-series": item.series_id, "data-date": item.date },
      h("div", { class: "session-t" }, shortRange(item.start_time, item.end_time)),
      h("b", { class: "session-n" }, item.title),
      h("div", { class: "small muted" }, [item.topic, item.location, item.coach && `with ${item.coach}`].filter(Boolean).join(" · ")),
      item.notes ? h("div", { class: "small" }, item.notes) : null,
      h("div", { class: "row", style: "gap:6px" },
        item.skipped ? h("span", { class: "pill gray" }, "Cancelled") : h("label", { class: "check small" }, h("input", { type: "checkbox", checked: item.done, "aria-label": `Attended ${item.title}`, onchange: (e) => mark(item, e.target.checked ? "done" : "undone") }), "Attended"),
        h("button", { class: "btn small", type: "button", "data-skip": item.date, title: item.skipped ? "Bring this session back" : "Cancel just this one session", onclick: () => mark(item, item.skipped ? "unskip" : "skip") }, item.skipped ? "Restore" : "Cancel")));
  }

  function paint() {
    const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(st.week); d.setDate(d.getDate() + i); return d; });
    title.textContent = `${days[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} to ${days[6].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
    const hours = Math.round((st.summary.minutes / 60) * 10) / 10;
    const kpi = (label, value, note) => h("div", { class: "card tight kpi" }, h("div", { class: "l" }, label), h("div", { class: "v" }, value), note ? h("div", { class: "d muted" }, note) : null);
    mount(kpis, kpi("Sessions this week", st.summary.sessions, "not counting cancelled ones"), kpi("Attended", `${st.summary.attended} of ${st.summary.sessions}`), kpi("Time planned", hours ? `${hours} h` : "–", "from the start and end times"));
    mount(weekEl, days.map((d) => {
      const day = isoDate(d), here = st.items.filter((o) => o.date === day);
      return h("div", { class: `week-day${day === today ? " today" : ""}`, "data-day": day },
        h("div", { class: "week-h" }, h("span", {}, DAYS[(d.getDay() + 6) % 7]), h("b", {}, d.getDate())),
        here.length ? here.map(session) : h("div", { class: "faint small week-empty" }, "Nothing planned"),
        h("button", { class: "week-add", type: "button", "aria-label": `Add training on ${FULL_DAYS[(d.getDay() + 6) % 7]}`, onclick: () => add(day) }, icon("plus"), "Add"));
    }));
    mount(regular, st.series.length
      ? st.series.map((s) => h("div", { class: `card tight row spread series k-${s.kind}`, "data-series": s.id },
        h("div", { style: "min-width:0" }, h("h3", { style: "margin:0" }, s.title), h("div", { class: "small" }, `${s.kind_label} · ${s.pattern}`),
          h("div", { class: "small muted" }, [s.topic, s.location, s.coach && `with ${s.coach}`, s.next ? `next: ${parseIso(s.next).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}` : "no more sessions"].filter(Boolean).join(" · "))),
        h("div", { class: "row", style: "gap:6px" }, h("button", { class: "btn small", onclick: () => edit(s) }, icon("edit"), "Edit"), h("button", { class: "btn small danger", onclick: () => remove(s) }, icon("trash"), "Remove"))))
      : empty("wR", "No training planned yet", "Add the classes, lessons and club nights you go to. Repeating ones appear every week without any extra work, and they show on the calendar too.",
        h("button", { class: "btn primary", onclick: () => add("") }, icon("plus"), "Add training")));
  }

  const shift = (n) => { st.week.setDate(st.week.getDate() + 7 * n); load(); };
  await load();
  return h("div", { class: "stack", style: "max-width:1200px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Training schedule"), h("p", {}, "Classes, lessons, club nights and practice, week by week.")),
      h("div", { class: "row", style: "gap:8px" }, h("button", { class: "btn primary", id: "add-training", onclick: () => add("") }, icon("plus"), "Add training"))),
    kpis,
    h("div", { class: "row", style: "gap:8px;justify-content:center" },
      h("button", { class: "btn small", id: "wk-prev", "aria-label": "Previous week", onclick: () => shift(-1) }, "◀"), title,
      h("button", { class: "btn small", id: "wk-next", "aria-label": "Next week", onclick: () => shift(1) }, "▶"),
      h("button", { class: "btn small", id: "wk-today", onclick: () => { st.week = monday(new Date()); load(); } }, "This week")),
    weekEl,
    h("div", { class: "stack-s" }, h("h2", { style: "margin:0" }, "Regular schedule"), regular));
}
