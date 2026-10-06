// Pieces of UI shared by several pages.
import { h, icon, ring, meter, level } from "./dom.js";
import { drawBoard, arrowFrom, flipTurn } from "./board.js";
import { boardTools } from "./explorer.js";

const TITLE_TONE = { missed_threat: "bad", hung_piece: "bad", missed_tactic: "warn", missed_attack: "warn", defensive_spiral: "warn", mistake: "gray" };
const ROLE_TEXT = { defends: "stops the threat", counterattacks: "answers with a counter-attack", attacks: "keeps the initiative", improves: "a calm, useful move" };

/** The three coloured arrows for a moment. */
export function momentArrows(m) {
  return [
    ...(m.threat ? [arrowFrom(m.threat.uci, "threat")] : []),
    arrowFrom(m.played.uci, "played"),
    arrowFrom(m.best.uci, "best"),
  ];
}

export function legend(m) {
  return h("div", { class: "legend" },
    m && m.threat ? h("span", {}, h("i", { style: "background:var(--arrow-threat)" }), "opponent's threat") : null,
    h("span", {}, h("i", { style: "background:var(--arrow-played)" }), "what you played"),
    h("span", {}, h("i", { style: "background:var(--arrow-best)" }), "better idea"));
}

/** A board with a stepper for a line of moves: [{san, uci, fen}] starting from startFen. */
export function lineViewer({ startFen, steps, orient, arrows = [], label }) {
  const board = h("div", { class: "board", style: "max-width:460px" });
  const list = h("div", { class: "steps" });
  let idx = 0;
  const turnWhite = startFen.split(" ")[1] === "w";
  const number0 = +startFen.split(" ")[5] || 1;
  function labelFor(i) {
    const white = turnWhite ? i % 2 === 0 : i % 2 === 1;
    const no = number0 + (turnWhite ? Math.floor(i / 2) : Math.floor((i + 1) / 2));
    return white ? `${no}. ${steps[i].san}` : i === 0 ? `${no}… ${steps[i].san}` : steps[i].san;
  }
  function render() {
    const fen = idx === 0 ? startFen : steps[idx - 1].fen;
    const shown = idx === 0 ? arrows : [arrowFrom(steps[idx - 1].uci, "best")];
    drawBoard(board, fen, { orient, arrows: shown, lastMove: idx ? steps[idx - 1].uci : null });
    list.replaceChildren(
      h("button", { class: "btn small", "aria-label": "Back", onclick: () => { idx = Math.max(0, idx - 1); render(); } }, "◀"),
      ...steps.map((s, i) => h("button", { class: "step", "aria-current": idx === i + 1 ? "true" : "false", onclick: () => { idx = i + 1; render(); } }, labelFor(i))),
      h("button", { class: "btn small", "aria-label": "Forward", onclick: () => { idx = Math.min(steps.length, idx + 1); render(); } }, "▶"),
    );
  }
  render();
  const currentFen = () => (idx === 0 ? startFen : steps[idx - 1].fen);
  return h("div", {}, label ? h("div", { class: "small muted", style: "margin-bottom:6px" }, label) : null, board, list, boardTools(currentFen));
}

export function dimensionBars(scores, labels) {
  return Object.keys(labels).map((key) => {
    const v = scores[key];
    const fill = h("div", { class: `fill ${v >= 0 ? "pos" : "neg"}` });
    fill.style.width = `${Math.abs(v) / 2}%`;
    return h("div", { class: "dual" },
      h("span", {}, labels[key]),
      h("div", { class: "track", role: "img", "aria-label": `${labels[key]}: ${v > 0 ? "+" : ""}${v}` }, fill),
      h("span", { class: `small ${v > 15 ? "up" : v < -15 ? "down" : "muted"}` }, `${v > 0 ? "+" : ""}${v}`));
  });
}

/** Everything the coach has to say about one moment (used in the game review and on other pages). */
export function momentBody(m, { compact = false } = {}) {
  const cands = m.category === "defensive_spiral" ? [] : m.candidates.filter((c) => c.good);
  const think = [
    ["threat", "T", "Threat", "What is my opponent threatening?"],
    ["checks", "H", "Checks", "Do I have any checks?"],
    ["captures", "I", "Important captures", "Can I win material?"],
    ["new_threats", "N", "New threats", "Can I create a threat?"],
    ["king_safety", "K", "King safety", "Is my king safe?"],
  ];
  const noteFor = (key, t) => {
    if (!t.available) return "Nothing special";
    return ["checks", "captures", "new_threats"].includes(key) ? t.moves.join(", ") : "There was something here";
  };
  return h("div", {},
    h("div", { class: "row", style: "gap:8px" },
      h("span", { class: `pill ${TITLE_TONE[m.category] || "gray"}` }, m.title),
      h("span", { class: "muted small" }, `Move ${m.move_number}${m.side === "white" ? "." : "…"} · you played `, h("b", { class: "mono" }, m.played.san))),
    h("h3", { style: "margin:8px 0 4px" }, m.headline),
    h("ul", { class: "dots" }, m.story.map((s) => h("li", {}, s))),
    m.spiral ? h("div", { class: "callout warn" }, h("b", {}, "Your answers in a row: "), m.spiral.moves.map((x) => `${x.number}. ${x.san}`).join("  →  ")) : null,
    cands.length ? h("div", {}, h("b", { class: "small" }, "Moves worth considering"),
      h("ul", { class: "clean stack-s", style: "margin-top:6px" }, cands.map((c) =>
        h("li", { class: "row", style: "gap:8px" }, h("b", { class: "mono" }, c.san),
          h("span", { class: "muted small" }, ROLE_TEXT[c.role] + (c.gives_check ? " · check" : "") + (c.captures ? ` · captures a ${c.captures}` : "") + (c.threat_san ? ` · threatens ${c.threat_san}` : "")))))) : null,
    compact || m.category === "defensive_spiral" || !think.some(([key]) => m.think[key].available) ? null : h("div", { class: "think" }, think.map(([key, letter, title, q]) =>
      h("div", { class: m.think.key === key ? "key" : "" }, h("b", {}, `${letter} · ${title}`), h("span", { class: "muted" }, q), h("br"), noteFor(key, m.think[key])))),
    m.think_message && !compact ? h("div", { class: "callout" }, m.think_message) : null,
    m.balance && m.balance.before ? h("div", { class: "callout" }, h("b", {}, "Position: "), m.balance.before.verdict.text) : null,
    h("div", { class: "callout" }, h("b", {}, "Ask yourself: "), m.question),
    h("div", { class: "callout lesson" }, h("b", {}, "Lesson: "), m.lesson));
}

export function habitCard(habit, { onEvidence, onTrain }) {
  return h("div", { class: "card" },
    h("div", { class: "row spread", style: "align-items:flex-start;flex-wrap:nowrap" },
      h("div", { style: "min-width:0" },
        h("span", { class: `pill ${level(habit.score)}` }, habit.level === "strong" ? "Strength" : habit.level === "ok" ? "Getting there" : "Work on this"),
        h("h3", { style: "margin-top:8px" }, habit.headline),
        h("p", { class: "muted" }, habit.detail)),
      ring(habit.score)),
    habit.evidence.length ? h("div", { style: "margin:8px 0" }, h("div", { class: "small muted", style: "margin-bottom:6px" }, "Examples from your games"),
      h("div", { class: "row", style: "gap:8px" }, habit.evidence.map((e) =>
        h("a", { class: "chip", href: `#/game/${e.game_id}${e.ply ? "/" + e.ply : ""}`, onclick: onEvidence }, `${e.opponent || "Game"} · move ${e.move_number}`)))) : null,
    h("div", { class: "small muted", style: "margin:10px 0 4px" }, "What to do"),
    h("ul", { class: "dots" }, habit.advice.map((a) => h("li", {}, a))),
    habit.train.length ? h("div", { class: "row", style: "margin-top:8px" }, habit.train.map((t) =>
      h("a", { class: "btn small", href: trainHref(t) }, icon("arrow"), t.label))) : null);
}

export function trainHref(t) {
  if (t.kind === "academy") return `#/academy/${t.theme}`;
  if (t.kind === "workbook") return `#/workbook/${t.skill || ""}`;
  if (t.kind === "openings") return "#/openings/library";
  if (t.kind === "model") return "#/models";
  if (t.kind === "wins") return "#/wins";
  return "#/";
}

/** A quiet "nothing here yet" note for inside a card: icon, title, one line, optional progress ("1 of 3 games") and action. */
export function emptyState({ icon: ic = "♟", title, text = "", progress = "", action = null }) {
  return h("div", { class: "empty-state" },
    h("span", { class: "es-ic", "aria-hidden": "true" }, ic),
    h("div", { class: "es-text" }, h("b", {}, title), text ? h("span", { class: "small muted" }, text) : null,
      progress ? h("span", { class: "es-progress" }, progress) : null),
    action);
}

export function empty(art, title, body, ...actions) {
  const isPiece = /^[wb][PNBRQK]$/.test(art);
  return h("div", { class: "card empty" }, h("div", { class: "art" }, isPiece ? h("img", { src: `/static/pieces/${art}.svg`, alt: "" }) : art), h("h3", {}, title), h("p", {}, body), h("div", { class: "row", style: "justify-content:center" }, actions));
}
