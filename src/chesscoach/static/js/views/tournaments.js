// Tournaments and their rounds: import from USCF or add by hand, then add the moves of each game.
import { openShareDialog } from "../share.js";
import { openScoresheets, photoCount } from "../scoresheets.js";
import { h, icon, mount, toast, fmtDate, uscfUrl } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer, state, loadSections } from "../state.js";
import { askForm, askChoice } from "../dialogs.js";
import { go } from "../router.js";
import { empty } from "../components.js";
import { uscfCard } from "./uscf.js";
import { ratingChart } from "../charts.js";

const SYSTEMS = { R: "Regular", Q: "Quick", B: "Blitz", OR: "Online regular", OQ: "Online quick", OB: "Online blitz" };
const SYSTEM_COLORS = { R: "var(--brand)", Q: "#0d9488", B: "#d97706", OR: "#7c3aed", OQ: "#e0533d", OB: "#16a34a" };
const signed = (n) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "±0");

// "Regular 1443 → 1405 (−38) · Quick 1278 → 1240 (−38)"
function ratingLine(e) {
  if (!e.ratings || !e.ratings.length) return null;
  return h("div", { class: "rating-line" }, e.ratings.map((c) => h("span", {},
    h("span", { class: "muted" }, `${SYSTEMS[c.system] || c.system || "Rating"} `), `${c.before} → ${c.after} `,
    h("span", { class: c.change > 0 ? "up" : c.change < 0 ? "down" : "same" }, `(${signed(c.change)})`))));
}

// A line per rating system across the played tournaments, oldest to newest.
function ratingHistory(past) {
  const played = past.filter((e) => e.ratings && e.ratings.length).slice().reverse();
  const series = Object.keys(SYSTEMS).map((sys) => ({
    sys, name: SYSTEMS[sys], color: SYSTEM_COLORS[sys],
    points: played.flatMap((e, i) => e.ratings.filter((c) => c.system === sys).map((c) => ({
      x: i, value: c.after, title: `${e.name}${e.start_date ? ` · ${fmtDate(e.start_date)}` : ""}: ${c.before} → ${c.after} (${signed(c.change)})` }))),
  })).filter((s) => s.points.length);
  if (!series.length || played.length < 2) return null;
  const latest = series.map((s) => { const last = s.points[s.points.length - 1]; return h("span", {}, h("i", { style: `background:${s.color}` }), `${s.name} `, h("b", {}, last.value)); });
  return h("div", { class: "card stack-s" },
    h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, icon("chart"), " Rating after each tournament"), h("span", { class: "small muted" }, "Hover a dot for the tournament")),
    ratingChart(series, played.length), h("div", { class: "legend" }, latest));
}

const RESULTS = [["", "Result…"], ["win", "Won"], ["draw", "Drew"], ["loss", "Lost"]];
const COLORS = [["", "Color…"], ["white", "White"], ["black", "Black"]];
const opt = (v, t, current) => h("option", { value: v, selected: v === current }, t);
const dateBox = (d) => (d ? d.replaceAll(".", "-") : "");

export async function tournamentsView(_params, query) {
  document.title = "Tournaments · Chess Varsity";
  const player = currentPlayer();
  let events = await api(`/api/players/${player.id}/events`);
  const open = new Set(events.filter((e) => e.kind === "upcoming").map((e) => e.id));
  // The most recent tournament starts open (again whenever a newer one arrives, e.g. after an import).
  let latestPlayed = null;
  const findLatest = () => {
    const next = events.find((e) => e.kind !== "upcoming") || null;
    if (next && (!latestPlayed || next.id !== latestPlayed.id)) open.add(next.id);
    latestPlayed = next;
  };
  findLatest();
  if (query && query.event) open.add(+query.event);
  const list = h("div", { class: "stack" });

  const reload = async () => { events = await api(`/api/players/${player.id}/events`); findLatest(); paint(); };
  const replace = (next) => { events = events.map((e) => (e.id === next.id ? next : e)); paint(); };
  const linkedIds = () => new Set(events.flatMap((e) => e.rounds.map((r) => r.game_id).filter(Boolean)));

  async function newTournament() {
    const v = await askForm({
      title: "New tournament", confirmLabel: "Create",
      fields: [
        { name: "name", label: "Name", required: true, placeholder: "e.g. State Championship" },
        { name: "start_date", label: "Start date", type: "date" },
        { name: "location", label: "Where (optional)", maxlength: 60 },
        { name: "kind", label: "Is it…", value: "upcoming", options: [["upcoming", "Coming up"], ["past", "Already played"]] },
        { name: "time_control", label: "Time control (optional)", placeholder: "e.g. G/60 d5", maxlength: 30 },
        { name: "rounds", label: "How many rounds? (you can change this later)", type: "number", value: 5 },
      ],
    });
    if (!v) return;
    try {
      const made = await api("/api/events", { method: "POST", body: { ...v, rounds: Math.max(0, Math.min(12, v.rounds || 0)) } });
      open.add(made.id); await reload(); toast("Tournament added");
    } catch (e) { toast(e.message); }
  }

  async function editTournament(e) {
    const v = await askForm({
      title: "Edit tournament", confirmLabel: "Save",
      fields: [
        { name: "name", label: "Name", required: true, value: e.name },
        { name: "start_date", label: "Start date", type: "date", value: dateBox(e.start_date) },
        { name: "end_date", label: "End date (optional)", type: "date", value: dateBox(e.end_date) },
        { name: "location", label: "Where", value: e.location, maxlength: 60 },
        { name: "kind", label: "Is it…", value: e.kind, options: [["upcoming", "Coming up"], ["past", "Already played"]] },
        { name: "time_control", label: "Time control", value: e.time_control, maxlength: 30 },
      ],
    });
    if (!v) return;
    try { replace(await api(`/api/events/${e.id}`, { method: "PATCH", body: { ...v, notes: e.notes || "" } })); } catch (err) { toast(err.message); }
  }

  async function deleteTournament(e) {
    const moves = e.games_with_moves;
    const note = moves ? ` Your ${moves} game${moves === 1 ? "" : "s"} with moves will be kept.` : "";
    if (!confirm(`Delete “${e.name}” and its round records?${note}`)) return;
    await api(`/api/events/${e.id}`, { method: "DELETE" });
    await reload(); await loadSections(); toast("Tournament deleted");
  }

  async function linkExisting(e, r) {
    const taken = linkedIds();
    const games = state.sections.flatMap((s) => s.games).filter((g) => !taken.has(g.id)).slice(0, 40);
    if (!games.length) { toast("All of your games are already attached to a round."); return; }
    const label = (g) => `${g.opponent ? `vs ${g.opponent}` : `${g.white} – ${g.black}`}${g.date ? ` · ${fmtDate(g.date)}` : ""}${g.event ? ` · ${g.event}` : ""}`;
    const id = await askChoice({ title: `Attach a game to round ${r.round}`, message: "Pick a game you have already added.", options: games.map((g) => ({ value: g.id, label: label(g) })) });
    if (!id) return;
    try { replace(await api(`/api/rounds/${r.id}/link/${id}`, { method: "POST" })); toast("Game attached"); } catch (err) { toast(err.message); }
  }

  function roundRow(e, r) {
    const patch = async (body) => { try { replace(await api(`/api/rounds/${r.id}`, { method: "PATCH", body })); } catch (err) { toast(err.message); } };
    const oppInput = h("input", { class: "input", value: r.opponent, maxlength: 60, placeholder: "Opponent", "aria-label": `Round ${r.round} opponent`, style: "min-width:140px", onchange: (ev) => patch({ opponent: ev.target.value }) });
    const opponent = r.opponent_uscf_id
      ? h("div", { class: "row", style: "gap:4px;flex-wrap:nowrap" }, oppInput,
        h("a", { class: "icon-btn", href: uscfUrl(r.opponent_uscf_id), target: "_blank", rel: "noopener", title: `${r.opponent || "Opponent"} on US Chess (ID ${r.opponent_uscf_id})`,
          "aria-label": `${r.opponent || "Opponent"} on US Chess` }, icon("link")))
      : oppInput;
    const colour = h("select", { class: "select", "aria-label": `Round ${r.round} color`, onchange: (ev) => patch({ color: ev.target.value }) }, COLORS.map(([v, t]) => opt(v, t, r.color)));
    const result = h("select", { class: `select res-${r.result || "none"}`, "aria-label": `Round ${r.round} result`, onchange: (ev) => patch({ result: ev.target.value }) }, RESULTS.map(([v, t]) => opt(v, t, r.result)));
    const game = r.game_id
      ? h("div", { class: "row", style: "gap:6px" },
        h("a", { class: "btn small", href: `#/game/${r.game_id}` }, icon("play"), "Open game"),
        r.game && r.game.accuracy !== null && r.game.accuracy !== undefined ? h("span", { class: "pill good", title: "Accuracy" }, `${Math.round(r.game.accuracy)}%`) : r.game && r.game.status !== "done" ? h("span", { class: "pill gray" }, "analyzing…") : null,
        r.game && r.game.status === "done" ? h("button", { class: "btn small", title: "Share this game with the community", onclick: () => openShareDialog(r.game_id) }, icon("users"), "Share") : null,
        h("button", { class: "btn small", title: "Detach this game from the round (the game is kept)", onclick: async () => { replace(await api(`/api/rounds/${r.id}/unlink`, { method: "POST" })); } }, "Detach"))
      : h("div", { class: "row", style: "gap:6px" },
        h("a", { class: "btn small primary", href: `#/add?round=${r.id}`, "data-add-moves": r.id }, icon("plus"), "Add moves"),
        h("button", { class: "btn small", title: "Attach a game you already added", onclick: () => linkExisting(e, r) }, icon("link"), "Attach"));
    const remove = h("button", { class: "row-del", style: "opacity:.6", title: "Remove this round", "aria-label": `Remove round ${r.round}`, onclick: async () => {
      if (r.game_id && !confirm("Remove this round? The game with its moves is kept.")) return;
      await api(`/api/rounds/${r.id}`, { method: "DELETE" }); await reload();
    } }, icon("trash"));
    const sheets = r.scoresheets || [];
    const photos = h("button", { class: "btn small", style: "white-space:nowrap", title: "Photos of the paper scoresheet", onclick: () => openScoresheets(r, (list) => { r.scoresheets = list; photoCount(photos, list); }) });
    photoCount(photos, sheets);
    return h("tr", {}, h("td", { style: "width:44px" }, h("b", {}, r.round)), h("td", {}, opponent), h("td", {}, colour), h("td", {}, result), h("td", {}, game), h("td", {}, photos), h("td", { style: "width:34px" }, remove));
  }

  function eventCard(e) {
    const played = e.wins + e.draws + e.losses;
    const latest = latestPlayed && e.id === latestPlayed.id;
    const details = h("details", { class: `card event${latest ? " latest" : ""}`, "data-event": e.id, open: open.has(e.id) });
    details.addEventListener("toggle", () => { if (details.open) open.add(e.id); else open.delete(e.id); });
    const total = e.rounds.length;
    details.append(
      h("summary", { class: "row spread", style: "cursor:pointer;list-style:none" },
        h("div", {}, h("h3", { style: "margin:0" }, e.name),
          h("div", { class: "muted small" }, [e.start_date ? fmtDate(e.start_date) : "Date not set", e.location, e.time_control, /^\d+$/.test(e.section || "") ? `Section ${e.section}` : e.section].filter(Boolean).join(" · ")),
          ratingLine(e)),
        h("div", { class: "row", style: "gap:6px" },
          e.kind === "upcoming" ? h("span", { class: "pill warn" }, e.start_date ? "Coming up" : "Coming up · no date") : null,
          latest ? h("span", { class: "pill brass" }, "Latest") : null,
          played ? h("span", { class: "pill gray", title: "Won-Drawn-Lost" }, `${e.wins}-${e.draws}-${e.losses}`) : null,
          total ? h("span", { class: "pill brand", title: "Rounds with the moves entered" }, `${e.games_with_moves}/${total} games with moves`) : null,
          e.source === "uscf" ? h("span", { class: "pill gray" }, "USCF") : null)),
      h("div", { class: "stack-s", style: "margin-top:12px" },
        total ? h("div", { style: "overflow:auto" }, h("table", { class: "rounds" },
          h("thead", {}, h("tr", {}, ["Rd", "Opponent", "Colour", "Result", "Game", "Scoresheet", ""].map((t) => h("th", {}, t)))),
          h("tbody", {}, e.rounds.map((r) => roundRow(e, r)))))
          : h("p", { class: "muted", style: "margin:0" }, "No rounds yet. Add each round as you play it."),
        h("div", { class: "row" },
          h("button", { class: "btn small", onclick: async () => { try { replace(await api(`/api/events/${e.id}/rounds`, { method: "POST", body: {} })); } catch (err) { toast(err.message); } } }, icon("plus"), "Add a round"),
          e.kind === "upcoming" ? h("a", { class: "btn small primary", href: `#/planner?event=${e.id}` }, icon("flag"), "Registration, hotel and travel") : null,
          e.kind === "upcoming" ? h("a", { class: "btn small", href: `#/prep?event=${e.id}` }, icon("star"), "Plan the openings") : null,
          e.kind === "upcoming" ? h("button", { class: "btn small", onclick: async () => { replace(await api(`/api/events/${e.id}`, { method: "PATCH", body: { name: e.name, start_date: dateBox(e.start_date), end_date: dateBox(e.end_date), location: e.location, kind: "past", time_control: e.time_control, notes: e.notes || "" } })); } }, "Mark as played") : null,
          h("button", { class: "btn small", onclick: () => editTournament(e) }, icon("edit"), "Edit"),
          h("button", { class: "btn small danger", onclick: () => deleteTournament(e) }, icon("trash"), "Delete"))));
    return details;
  }

  function paint() {
    const upcoming = events.filter((e) => e.kind === "upcoming"), past = events.filter((e) => e.kind !== "upcoming");
    mount(list,
      events.length ? null : empty("wQ", "No tournaments yet", "Connect USCF above to import them, or add one yourself. Each tournament holds its rounds, and each round holds one game.",
        h("button", { class: "btn primary", onclick: newTournament }, icon("plus"), "Add a tournament")),
      upcoming.length ? h("div", { class: "stack-s" }, h("h2", { style: "margin:0" }, "Coming up"), upcoming.map(eventCard)) : null,
      past.length ? h("div", { class: "stack-s" }, h("h2", { style: "margin:0" }, "Recently played tournaments and game history"), ratingHistory(past), past.map(eventCard)) : null);
  }
  paint();

  const card = await uscfCard({ onImported: async () => { await reload(); await loadSections(); } });
  return h("div", { class: "stack", style: "max-width:1000px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Tournaments"), h("p", {}, "Every tournament you play, round by round. Add the moves of each game to its round.")),
      h("button", { class: "btn primary", id: "new-tournament", onclick: newTournament }, icon("plus"), "New tournament")),
    card, list);
}
