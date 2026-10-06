// Getting ready for a tournament: the openings to bring, the attacking position to aim for, and a countdown.
import { h, icon, fmtDate } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { drawBoard } from "../board.js";
import { explorer, boardTools } from "../explorer.js";
import { lineViewer } from "../components.js";
import { go } from "../router.js";

const movetext = (sans) => sans.map((s, i) => (i % 2 === 0 ? `${i / 2 + 1}. ${s}` : s)).join(" ");
const countdown = (days) => (days === null || days === undefined ? "" : days < 0 ? "already started" : days === 0 ? "today!" : days === 1 ? "tomorrow" : `in ${days} days`);

function openingDetail(o) {
  const t = o.target;
  const boardEl = h("div", { class: "board", style: "max-width:400px" });
  const slot = h("div", { class: "stack-s", style: "min-width:280px;flex:1;max-width:420px" });
  const showTarget = () => {
    drawBoard(boardEl, t.fen, { orient: o.side, arrows: t.arrows });
    slot.replaceChildren(boardEl,
      h("div", { class: "legend" },
        h("span", {}, h("i", { style: "background:var(--arrow-best)" }), "where the pieces go"),
        h("span", {}, h("i", { style: "background:var(--arrow-threat)" }), "what they aim at")),
      h("div", { class: "row", style: "gap:6px" },
        h("button", { class: "btn small", onclick: showLine }, icon("play"), "Show me how to get there"),
        h("button", { class: "btn small", onclick: showTry }, icon("edit"), "Try moves here")),
      boardTools(() => t.fen));
  };
  const back = () => showTarget();
  function showLine() {
    slot.replaceChildren(h("div", { class: "row spread" }, h("b", {}, "The way there"), h("button", { class: "btn small", onclick: back }, icon("x"), "Back to the target position")),
      lineViewer({ startFen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", steps: t.steps, orient: o.side }));
  }
  function showTry() {
    slot.replaceChildren(explorer({ fen: t.fen, orient: o.side, title: "Try moves from the target position", onBack: back, backLabel: "Back to the target position" }));
  }
  showTarget();

  const list = (items) => h("ul", { class: "dots" }, items.map((x) => h("li", {}, x)));
  return h("div", { class: "row", style: "align-items:flex-start;gap:20px", "data-opening": o.id },
    slot,
    h("div", { class: "stack-s", style: "flex:1;min-width:260px" },
      h("div", {}, h("h3", { style: "margin:0" }, o.name), h("span", { class: `pill ${o.style === "attacking" ? "warn" : "brand"}` }, o.style === "attacking" ? "Attacking" : "Solid")),
      h("p", { style: "margin:0" }, o.idea),
      h("div", { class: "callout" }, h("b", {}, "Why this one for me"), list(o.why)),
      h("div", {}, h("div", { class: "small muted" }, "The moves to reach it"), h("div", { class: "mono small" }, movetext(t.moves))),
      h("div", {}, h("b", {}, "What I am aiming for"), list(t.aims)),
      h("div", { class: "callout warn" }, h("b", {}, "Watch out for"), list(t.watch)),
      o.traps.length ? h("div", {}, h("b", {}, "A trap to know"), o.traps.map((x) => h("div", { class: "small" }, h("b", {}, x.name), ` (${movetext(x.moves)}). ${x.note}`))) : null));
}

function sidePicker(title, side, options) {
  const holder = h("div", {});
  const chips = h("div", { class: "row", style: "gap:6px" });
  let chosen = 0;
  const paint = () => {
    chips.replaceChildren(...options.map((o, i) => h("button", { class: "chip", "aria-pressed": i === chosen ? "true" : "false", "data-pick": o.id, onclick: () => { chosen = i; paint(); } },
      i === 0 ? icon("star") : null, o.name)));
    holder.replaceChildren(openingDetail(options[chosen]));
  };
  paint();
  return h("div", { class: "card stack-s", "data-side": side },
    h("div", { class: "row spread" }, h("h2", { style: "margin:0" }, title), h("span", { class: "muted small" }, "Best fit first")), chips, holder);
}

export async function prepView(_params, query) {
  document.title = "Tournament plan · Chess Varsity";
  const player = currentPlayer();
  const data = await api(`/api/players/${player.id}/prep${query && query.event ? `?event_id=${encodeURIComponent(query.event)}` : ""}`);
  const e = data.event;

  const picker = data.upcoming.length > 1 ? h("select", { class: "select", style: "max-width:260px", "aria-label": "Which tournament", onchange: (ev) => go(`/prep?event=${ev.target.value}`) },
    data.upcoming.map((u) => h("option", { value: u.id, selected: e && u.id === e.id }, `${u.name}${u.start_date ? ` · ${fmtDate(u.start_date)}` : ""}`))) : null;

  const head = e
    ? h("div", { class: "page-h" },
      h("div", {}, h("h1", {}, e.name),
        h("p", {}, ["Your plan for the next tournament", e.start_date ? fmtDate(e.start_date) : "date not set yet", e.location, e.time_control].filter(Boolean).join(" · "))),
      h("div", { class: "ph-side" }, data.days_until !== null ? h("div", { class: "ph-count" }, countdown(data.days_until)) : null, picker))
    : h("div", { class: "stack" }, h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Tournament plan"),
      h("p", {}, "The openings to bring, the position to aim for, and a countdown to your next tournament."))),
      h("div", { class: "card stack-s" }, h("h2", { style: "margin:0" }, "No tournament planned yet"),
      h("p", { class: "muted", style: "margin:0" }, "Add your next tournament and this page counts down to it. Meanwhile, here are openings that suit me."),
      h("div", {}, h("a", { class: "btn primary", href: "#/tournaments" }, icon("calendar"), "Add a tournament"))));

  const focus = data.focus.length
    ? h("div", { class: "card stack-s" }, h("h2", { style: "margin:0" }, "What to work on first"),
      h("p", { class: "muted small", style: "margin:0" }, "From my recent games. Pick one of these as my rule for the tournament."),
      h("div", { class: "grid g2" }, data.focus.map((f) => h("div", { class: "callout warn", style: "margin:0" }, h("b", {}, f.headline), h("ul", { class: "dots" }, f.advice.map((a) => h("li", {}, a)))))))
    : !data.ready ? h("div", { class: "alert info" }, "Add and analyze a few more games and this page will tailor its advice to how I really play.") : null;

  const schedule = h("div", { class: "card stack-s" }, h("h2", { style: "margin:0" }, "Countdown"),
    h("div", { class: "stack-s" }, data.schedule.map((s) => h("div", { class: "row", style: `gap:10px;flex-wrap:nowrap;${s.past ? "opacity:.5" : ""}` },
      h("span", { class: `pill ${s.past ? "gray" : "brand"}`, style: "min-width:120px;justify-content:center" }, s.when), h("span", {}, s.task)))));

  const checklist = h("div", { class: "grid g3" }, [["Before the tournament", data.checklist.before], ["During each game", data.checklist.during], ["After each game", data.checklist.after]].map(([t, items]) =>
    h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, t), h("ul", { class: "dots", style: "margin:0" }, items.map((x) => h("li", {}, x))))));

  return h("div", { class: "stack", style: "max-width:1100px" },
    head,
    data.time_tip ? h("div", { class: "alert info" }, icon("bulb"), " ", data.time_tip) : null,
    focus,
    sidePicker("With White I will play…", "white", data.white),
    sidePicker("With Black I will play…", "black", data.black),
    h("p", { class: "muted small", style: "margin:0" }, "Learn the ideas, not the moves. If the opponent plays something else, ask the same questions: what does each piece want to do, and where is the king safe?"),
    schedule, checklist,
    h("div", { class: "card row spread" }, h("div", {}, h("b", {}, "Before every move, run the seven questions."), h("div", { class: "muted small" }, "It is the best protection against blunders and traps.")),
      h("a", { class: "btn primary", href: "#/think" }, icon("bulb"), "Think like a Grandmaster")));
}
