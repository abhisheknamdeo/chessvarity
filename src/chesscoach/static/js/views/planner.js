// The tournament planner: every upcoming tournament with flags for registration, payment, hotel and travel.
import { h, icon, mount, toast, fmtDate, meter } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { askForm } from "../dialogs.js";
import { empty } from "../components.js";

const dateBox = (d) => (d ? d.replaceAll(".", "-") : "");
const FLAGS = [
  ["reg_status", "Registered", "Signed up and entry accepted"],
  ["paid_status", "Entry fee paid", "The entry fee has been paid"],
  ["hotel_status", "Hotel booked", "A room is reserved (choose N/A for a local event)"],
  ["travel_status", "Travel arranged", "Flights, car or a ride are sorted (N/A if it is local)"],
];
const STATES = [["todo", "To do"], ["done", "Done"], ["na", "N/A"]];
const ATTENDING = [["maybe", "Thinking about it"], ["going", "Going"], ["skip", "Not going"]];

/** Ask for a tournament's details and its planning details. Resolves to the request body, or null if cancelled. */
export async function askTournament({ event = null, startDate = "" } = {}) {
  const p = event ? event.plan : {};
  const v = await askForm({
    title: event ? "Edit tournament" : "New tournament", confirmLabel: event ? "Save" : "Add tournament",
    fields: [
      { name: "name", label: "Name", required: true, value: event ? event.name : "", placeholder: "e.g. National Open", maxlength: 100 },
      { name: "start_date", label: "Starts", type: "date", value: event ? dateBox(event.start_date) : startDate },
      { name: "end_date", label: "Ends (optional)", type: "date", value: event ? dateBox(event.end_date) : "" },
      { name: "location", label: "City and state", value: event ? event.location : "", maxlength: 60, placeholder: "e.g. Orlando, FL" },
      { name: "address", label: "Venue address (optional)", value: p.address || "", maxlength: 160 },
      { name: "website", label: "Website (optional)", value: p.website || "", maxlength: 200, placeholder: "https://…" },
      { name: "entry_fee", label: "Entry fee (optional)", value: p.entry_fee || "", maxlength: 30, placeholder: "e.g. $45" },
      { name: "time_control", label: "Time control (optional)", value: event ? event.time_control : "", maxlength: 30, placeholder: "e.g. G/90 d5" },
      { name: "reg_deadline", label: "Register by (optional)", type: "date", value: dateBox(p.reg_deadline) },
      { name: "reg_confirmation", label: "Registration confirmation # (optional)", value: p.reg_confirmation || "", maxlength: 60 },
      { name: "hotel_name", label: "Hotel (optional)", value: p.hotel_name || "", maxlength: 100 },
      { name: "hotel_checkin", label: "Hotel check-in", type: "date", value: dateBox(p.hotel_checkin) },
      { name: "hotel_checkout", label: "Hotel check-out", type: "date", value: dateBox(p.hotel_checkout) },
      { name: "hotel_confirmation", label: "Hotel confirmation # (optional)", value: p.hotel_confirmation || "", maxlength: 60 },
    ],
  });
  if (!v) return null;
  return { ...v, kind: event ? event.kind : "upcoming", notes: event ? event.notes || "" : "" };
}

const when = (days) => (days === null || days === undefined ? "" : days < 0 ? "already started" : days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`);

function deadlineNote(e) {
  const d = e.deadline_in, p = e.plan;
  if (!p.reg_deadline) return null;
  const closed = p.reg_status === "done";
  const text = `Register by ${fmtDate(p.reg_deadline)}`;
  if (closed) return h("span", { class: "muted small" }, `${text} · done`);
  if (d !== null && d < 0) return h("span", { class: "sugg-warn" }, `⚠ ${text} · the deadline has passed`);
  if (d !== null && d <= 7) return h("span", { class: "sugg-warn" }, `⚠ ${text} · ${when(d)}`);
  return h("span", { class: "small" }, `${text}${d !== null ? ` · ${when(d)}` : ""}`);
}

export async function plannerView(_params, query) {
  document.title = "Tournament planner · Chess Varsity";
  const player = currentPlayer();
  let events = await api(`/api/players/${player.id}/events`);
  const st = { filter: "all" };
  const summary = h("div", { class: "grid g4" });
  const filters = h("div", { class: "filters" });
  const list = h("div", { class: "stack" });
  const focus = query && query.event ? +query.event : null;

  const upcoming = () => events.filter((e) => e.kind === "upcoming");
  const relevant = (e) => e.plan.attending !== "skip";
  const replace = (next) => { events = events.map((e) => (e.id === next.id ? next : e)); paint(); };
  const patchPlan = async (e, body) => { try { replace(await api(`/api/events/${e.id}/plan`, { method: "PATCH", body })); } catch (err) { toast(err.message); } };

  async function add() {
    const body = await askTournament();
    if (!body) return;
    try { const made = await api("/api/events", { method: "POST", body }); events = await api(`/api/players/${player.id}/events`); paint(); toast(`“${made.name}” added to the planner`); }
    catch (err) { toast(err.message); }
  }
  async function edit(e) {
    const body = await askTournament({ event: e });
    if (!body) return;
    try { replace(await api(`/api/events/${e.id}`, { method: "PATCH", body })); toast("Saved"); } catch (err) { toast(err.message); }
  }
  async function remove(e) {
    if (!confirm(`Delete “${e.name}” and everything planned for it?`)) return;
    await api(`/api/events/${e.id}`, { method: "DELETE" });
    events = events.filter((x) => x.id !== e.id); paint(); toast("Tournament deleted");
  }

  function flagTile(e, [key, label, hint]) {
    const value = e.plan[key];
    return h("div", { class: `flag ${value}`, "data-flag": key, "data-state": value, title: hint },
      h("div", { class: "flag-title" }, icon("flag"), h("b", {}, label)),
      h("div", { class: "seg", role: "group", "aria-label": label },
        STATES.map(([s, t]) => h("button", { type: "button", "data-set": s, "aria-pressed": value === s ? "true" : "false", onclick: () => value !== s && patchPlan(e, { [key]: s }) }, t))));
  }

  function card(e) {
    const p = e.plan, tracked = FLAGS.filter(([k]) => p[k] !== "na"), done = tracked.filter(([k]) => p[k] === "done").length;
    const countdown = e.days_until !== null ? when(e.days_until) : "";
    const details = [
      p.address || e.location ? h("div", { class: "small" }, icon("flag"), " ", [e.location, p.address].filter(Boolean).join(" · ")) : null,
      p.website ? h("div", { class: "small" }, icon("link"), " ", h("a", { href: p.website, target: "_blank", rel: "noopener noreferrer" }, p.website.replace(/^https?:\/\//i, ""))) : null,
      p.entry_fee || e.time_control ? h("div", { class: "small muted" }, [p.entry_fee && `Entry ${p.entry_fee}`, e.time_control].filter(Boolean).join(" · ")) : null,
      deadlineNote(e),
      p.hotel_name || p.hotel_checkin ? h("div", { class: "small" }, `Hotel: ${[p.hotel_name, p.hotel_checkin && `${fmtDate(p.hotel_checkin)} to ${p.hotel_checkout ? fmtDate(p.hotel_checkout) : "?"}`, p.hotel_confirmation && `conf. ${p.hotel_confirmation}`].filter(Boolean).join(" · ")}`) : null,
      p.reg_confirmation ? h("div", { class: "small muted" }, `Registration confirmation: ${p.reg_confirmation}`) : null,
    ];
    const attending = h("select", { class: "select", style: "width:auto", "aria-label": `Am I going to ${e.name}?`, onchange: (ev) => patchPlan(e, { attending: ev.target.value }) },
      ATTENDING.map(([v, t]) => h("option", { value: v, selected: v === p.attending }, t)));
    return h("div", { class: `card trip ${p.attending}${focus === e.id ? " focus" : ""}`, id: `trip-${e.id}`, "data-event": e.id },
      h("div", { class: "row spread", style: "align-items:flex-start" },
        h("div", {}, h("h3", { style: "margin:0" }, e.name),
          h("div", { class: "muted small" }, [e.start_date ? `${fmtDate(e.start_date)}${e.end_date && e.end_date !== e.start_date ? ` to ${fmtDate(e.end_date)}` : ""}` : "Date not set yet", countdown].filter(Boolean).join(" · "))),
        h("div", { class: "row", style: "gap:8px" },
          e.needs.length ? h("span", { class: "pill warn", title: e.needs.join(", ") }, `⚑ ${e.needs.length} to do`) : p.attending === "skip" ? h("span", { class: "pill gray" }, "Not going") : h("span", { class: "pill good" }, "All set"),
          attending)),
      relevant(e) ? h("div", { class: "flags" }, FLAGS.map((f) => flagTile(e, f))) : h("div", { class: "muted small" }, "Marked as not going, so there is nothing to book."),
      relevant(e) && tracked.length ? h("div", { class: "row small", style: "gap:10px;flex-wrap:nowrap" }, h("div", { style: "flex:1" }, meter(Math.round(100 * done / tracked.length), done === tracked.length ? "good" : "warn")), h("span", { class: "muted" }, `${done} of ${tracked.length} done`)) : null,
      h("div", { class: "stack-s" }, details),
      h("div", { class: "row", style: "gap:6px" },
        h("button", { class: "btn small", onclick: () => edit(e) }, icon("edit"), "Edit details"),
        h("a", { class: "btn small", href: `#/prep?event=${e.id}` }, icon("star"), "Plan the openings"),
        h("a", { class: "btn small", href: "#/calendar" }, icon("calendar"), "See in the calendar"),
        h("button", { class: "btn small danger", onclick: () => remove(e) }, icon("trash"), "Delete")));
  }

  function paintSummary() {
    const up = upcoming().filter(relevant), going = up.filter((e) => e.plan.attending === "going");
    const count = (key, of) => of.filter((e) => e.plan[key] === "done").length;
    const soon = up.filter((e) => e.plan.reg_deadline && e.plan.reg_status !== "done" && e.deadline_in !== null && e.deadline_in >= 0).sort((a, b) => a.deadline_in - b.deadline_in)[0];
    const kpi = (label, value, note) => h("div", { class: "card tight kpi" }, h("div", { class: "l" }, label), h("div", { class: "v" }, value), note ? h("div", { class: "d muted" }, note) : null);
    mount(summary,
      kpi("Coming up", up.length, `${going.length} going`),
      kpi("Registered", `${count("reg_status", up)} of ${up.length}`, up.length - count("reg_status", up) ? `${up.length - count("reg_status", up)} still to register` : "all done"),
      kpi("Hotels booked", `${count("hotel_status", up)} of ${up.filter((e) => e.plan.hotel_status !== "na").length}`, "not counting local events"),
      kpi("Next deadline", soon ? when(soon.deadline_in) : "none", soon ? `${soon.name}: ${fmtDate(soon.plan.reg_deadline)}` : "no open registration deadlines"));
  }

  const FILTERS = [["all", "All"], ["going", "Going"], ["maybe", "Thinking about it"], ["skip", "Not going"], ["attention", "Needs attention"]];
  function paint() {
    paintSummary();
    const up = upcoming();
    const shown = up.filter((e) => st.filter === "all" || (st.filter === "attention" ? e.needs.length > 0 : e.plan.attending === st.filter));
    mount(filters, h("span", { class: "muted small" }, "Show:"), FILTERS.map(([k, t]) => h("button", { class: "chip", "data-filter": k, "aria-pressed": st.filter === k ? "true" : "false", onclick: () => { st.filter = k; paint(); } },
      k === "attention" ? `${t} · ${up.filter((e) => e.needs.length).length}` : t)));
    const past = events.filter((e) => e.kind !== "upcoming");
    mount(list,
      up.length ? null : empty("wR", "Nothing planned yet", "Add the tournaments you are thinking about. For each one you can flag whether you have registered, paid, booked a hotel and arranged travel.",
        h("button", { class: "btn primary", onclick: add }, icon("plus"), "Add a tournament")),
      shown.length ? shown.map(card) : up.length ? h("div", { class: "card muted" }, "No tournaments match that filter.") : null,
      past.length ? h("p", { class: "muted small" }, `${past.length} tournament${past.length === 1 ? "" : "s"} already played are on the `, h("a", { href: "#/tournaments" }, "Tournaments page"), ".") : null);
    if (focus && !st.scrolled) {          // the page is not on screen yet on the first paint, so wait a moment
      st.scrolled = true;
      setTimeout(() => { const el = document.getElementById(`trip-${focus}`); if (el) el.scrollIntoView({ block: "center" }); }, 80);
    }
  }
  paint();

  return h("div", { class: "stack", style: "max-width:1000px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Tournament planner"), h("p", {}, "Every tournament you might play, with a flag for each thing to sort out.")),
      h("div", { class: "row", style: "gap:8px" }, h("button", { class: "btn primary", id: "add-trip", onclick: add }, icon("plus"), "Add a tournament"), h("button", { class: "btn small", onclick: () => window.print() }, "Print"))),
    summary, filters, list);
}
