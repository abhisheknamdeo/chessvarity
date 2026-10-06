// Wins you missed: every chance in a list beside one large board, with the lesson they share said once.
import { h, icon, mount, fmtDate } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { lineViewer, emptyState } from "../components.js";
import { arrowFrom } from "../board.js";

const KIND = { threw_away_win: ["A win slipped away", "bad"], turning_point: ["Turning point", "warn"], better_position: ["Better position", "warn"] };
const kindOf = (m) => KIND[m.kind] || KIND.better_position;
const SEEN_KEY = "cc-wins-seen";
const readSeen = () => { try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); } catch (_) { return new Set(); } };
const saveSeen = (s) => { try { localStorage.setItem(SEEN_KEY, JSON.stringify([...s].slice(-300))); } catch (_) { /* not remembered */ } };
const idOf = (m) => `${m.game_id}-${m.ply}`;

export async function winsView() {
  const player = currentPlayer();
  const items = await api(`/api/players/${player.id}/wins`);
  document.title = "Wins you missed · Chess Varsity";
  const head = h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Wins you missed"),
    h("p", {}, "Moments in games you didn't win where a stronger move was there. Step through the better line, then spot it next time.")));
  if (!items.length) {
    return h("div", { class: "stack" }, head, h("div", { class: "card stack-s" },
      emptyState({ icon: "👑", title: "Nothing missed yet", text: "When a game is lost or drawn from a good position, the coach shows here how it could have been won.",
        action: h("a", { class: "btn primary small", href: "#/add" }, icon("plus"), "Add a game") }),
      h("p", { class: "small muted", style: "margin:4px 0 0" }, "Meanwhile, practice finishing off attacks in the ", h("a", { href: "#/academy/attack" }, "Attack academy"), ".")));
  }

  const seen = readSeen();
  let index = Math.max(0, items.findIndex((m) => !seen.has(idOf(m))));
  // The lesson most chances share is said once at the top, not repeated on every card.
  const counts = new Map();
  for (const m of items) counts.set(m.lesson, (counts.get(m.lesson) || 0) + 1);
  const common = [...counts].sort((a, b) => b[1] - a[1])[0][0];
  const PLURAL = { "A win slipped away": ["win slipped away", "wins slipped away"], "Turning point": ["turning point", "turning points"], "Better position": ["better position", "better positions"] };
  const byKind = new Map();
  for (const m of items) byKind.set(kindOf(m)[0], (byKind.get(kindOf(m)[0]) || 0) + 1);
  const tally = [...byKind].map(([k, n]) => `${n} ${PLURAL[k][n === 1 ? 0 : 1]}`).join(" · ");

  const viewer = h("div", {});
  const list = h("div", { class: "card stack-s" });
  const progress = h("div", {});

  function paint() {
    const m = items[index];
    seen.add(idOf(m)); saveSeen(seen);
    const [label, tone] = kindOf(m);
    mount(viewer, h("article", { class: "card stack-s wn-main" },
      h("div", { class: "row spread", style: "gap:8px" }, h("span", { class: `pill ${tone}` }, label),
        h("span", { class: "small muted" }, `${index + 1} of ${items.length}`)),
      h("h2", { style: "margin:0" }, m.headline),
      h("div", { class: "small muted" }, [m.event, m.opponent && m.opponent !== "Opponent" ? `vs ${m.opponent}` : "", fmtDate(m.date)].filter(Boolean).join(" · ")),
      h("ul", { class: "dots", style: "margin:0" }, m.story.map((s) => h("li", {}, s))),
      h("div", { class: "wn-board" }, lineViewer({ startFen: m.fen, steps: m.variation, orient: m.side,
        arrows: [arrowFrom(m.played.uci, "played"), arrowFrom(m.best.uci, "best")], label: "Your move in blue, the better idea in green. Step through:" })),
      m.lesson !== common ? h("div", { class: "callout lesson" }, m.lesson) : null,
      h("div", { class: "row spread", style: "gap:8px" },
        h("a", { class: "btn small", href: `#/game/${m.game_id}/${m.ply}` }, icon("arrow"), "Open the game at this move"),
        h("div", { class: "row", style: "gap:6px" },
          h("button", { class: "btn small", type: "button", disabled: index === 0, onclick: () => { index -= 1; paint(); } }, "← Previous"),
          h("button", { class: "btn small primary", type: "button", disabled: index === items.length - 1, onclick: () => { index += 1; paint(); } }, "Next →")))));
    mount(list, h("h3", { style: "margin:0" }, "Your chances"),
      h("div", { class: "puz-list" }, items.map((x, i) => h("button", { class: "puz", type: "button", "aria-current": i === index ? "true" : "false", onclick: () => { index = i; paint(); } },
        h("span", {}, h("b", {}, x.headline), h("div", { class: "small muted" }, [fmtDate(x.date), x.opponent && x.opponent !== "Opponent" ? `vs ${x.opponent}` : x.event].filter(Boolean).join(" · "))),
        seen.has(idOf(x)) && i !== index ? h("span", { class: "ok", title: "Reviewed" }, icon("check")) : null))));
    const done = items.filter((x) => seen.has(idOf(x))).length;
    mount(progress, h("div", { class: "row", style: "gap:10px;flex-wrap:nowrap" },
      h("div", { class: "meter", style: "flex:1;height:8px" }, h("i", { style: `width:${Math.round((100 * done) / items.length)}%` })),
      h("span", { class: "small muted", style: "white-space:nowrap" }, `${done} of ${items.length} reviewed`)));
  }
  paint();
  return h("div", { class: "stack" }, head,
    h("div", { class: "card stack-s wn-summary" },
      h("div", { class: "row spread", style: "gap:8px" }, h("b", {}, `${items.length} chance${items.length === 1 ? "" : "s"} in your games`), h("span", { class: "small muted" }, tally)),
      h("div", { class: "callout lesson", style: "margin:0" }, h("b", {}, "The common thread: "), common),
      progress),
    h("div", { class: "split wn-split" }, viewer, list));
}
