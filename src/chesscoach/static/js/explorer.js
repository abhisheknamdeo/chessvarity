// Play your own moves from any position, see them listed, copy the position, or play the computer from it.
import { h, icon, toast } from "./dom.js";
import { api } from "./api.js";
import { arrowFrom, drawBoard } from "./board.js";
import { go } from "./router.js";
import { ORDINAL, KINDS, COLOURS, contextBlock, suggestionCard } from "./suggestions.js";

export async function copyText(text, message = "Position copied") {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const box = h("textarea", { style: "position:fixed;opacity:0" });
    box.value = text; document.body.append(box); box.select();
    try { document.execCommand("copy"); } catch (__) { /* nothing more to try */ }
    box.remove();
  }
  toast(message);
}

export const playHref = (fen) => `#/play?fen=${encodeURIComponent(fen)}&side=${fen.split(" ")[1] === "w" ? "white" : "black"}`;

/** Small buttons for any board: copy the position, or play the computer from it. */
export function boardTools(getFen, { onTry } = {}) {
  return h("div", { class: "row", style: "gap:6px;margin-top:8px" },
    onTry ? h("button", { class: "btn small", type: "button", onclick: onTry }, icon("play"), "Try moves here") : null,
    h("button", { class: "btn small", type: "button", onclick: () => copyText(getFen()) }, icon("copy"), "Copy position"),
    h("button", { class: "btn small", type: "button", onclick: () => go(playHref(getFen()).slice(1)) }, icon("swords"), "Play from here"));
}

/**
 * An interactive board. `fen` is where it starts; `onBack` (optional) shows a "Back" button.
 * Legal moves come from the server, so castling, en passant and promotion just work.
 */
export function explorer({ fen, orient = "white", title = "Try your own moves", onBack, backLabel = "Back to the game", think = false, hints, lastUci = null }) {
  const st = { fens: [fen], sans: [], ucis: [], selected: null, flip: false, computer: false, level: 4, thinking: false };
  const cache = new Map();
  const boardEl = h("div", { class: "board big" });
  const status = h("div", { class: "muted small", "aria-live": "polite", style: "min-height:1.4em" });
  const list = h("div", { class: "steps" });
  const startTurnWhite = fen.split(" ")[1] === "w";
  const startNumber = +fen.split(" ")[5] || 1;

  const legal = async (f) => { if (!cache.has(f)) cache.set(f, await api(`/api/legal?fen=${encodeURIComponent(f)}`)); return cache.get(f); };
  const current = () => st.fens[st.fens.length - 1];
  const label = (i) => {
    const white = startTurnWhite ? i % 2 === 0 : i % 2 === 1;
    const no = startNumber + (startTurnWhite ? Math.floor(i / 2) : Math.floor((i + 1) / 2));
    return white ? `${no}. ${st.sans[i]}` : i === 0 ? `${no}… ${st.sans[i]}` : st.sans[i];
  };

  const suggestEl = h("div", { class: "suggest", "aria-live": "polite" });
  const suggestions = new Map();     // fen -> the engine's best moves there
  const pending = new Set();
  const showHints = () => { try { return localStorage.getItem("dk-hints") !== "off"; } catch (_) { return true; } };
  st.hints = hints === undefined ? showHints() : hints;        // a trainer can start with the hints hidden so the student thinks first
  const savedCount = () => { try { const n = +localStorage.getItem("dk-hints-n"); return n >= 1 && n <= 3 ? n : 2; } catch (_) { return 2; } };
  st.count = savedCount();                                    // how many suggested moves to show: 1, 2 or 3

  // "Coach me": the seven-question routine for the current position. It describes the position and never names a move.
  const thinkEl = h("div", { class: "coach stack-s", "aria-live": "polite" });
  const thoughts = new Map();       // "fen|last move" -> the routine, or null if it could not be loaded
  const revealed = new Set();
  st.think = think;
  let thinkPainted = "";

  async function paintThink() {
    thinkEl.classList.toggle("hidden", !st.think);
    if (!st.think) return;
    const last = st.ucis.length ? st.ucis[st.ucis.length - 1] : lastUci;
    const key = `${current()}|${last || ""}`;
    if (thinkPainted === key && thinkEl.childNodes.length) return;
    if (!thoughts.has(key)) {
      thinkEl.replaceChildren(h("span", { class: "muted small" }, "Getting the questions ready…"));
      try { thoughts.set(key, await api("/api/think", { method: "POST", body: { fen: current(), last_uci: last, color: orient } })); }
      catch (_) { thoughts.set(key, null); }
      if (`${current()}|${st.ucis.length ? st.ucis[st.ucis.length - 1] : lastUci || ""}` !== key) return;
    }
    thinkPainted = key;
    const routine = thoughts.get(key);
    if (!routine) { thinkEl.replaceChildren(h("span", { class: "muted small" }, "The thinking coach is not available right now.")); return; }
    thinkEl.replaceChildren(
      h("div", { class: "small muted" }, "Answer each question yourself first, out loud if you can. Then press “Check my thinking”. The coach describes the position; it never picks your move."),
      ...routine.steps.map((s) => {
        const id = `${key}#${s.id}`;
        const facts = h("ul", { class: "dots coach-facts" }, s.facts.map((f) => h("li", {}, f)));
        facts.classList.toggle("hidden", !revealed.has(id));
        const button = h("button", { class: "btn small", type: "button", "data-reveal": s.id, onclick: () => {
          if (revealed.has(id)) revealed.delete(id); else revealed.add(id);
          facts.classList.toggle("hidden", !revealed.has(id));
          button.textContent = revealed.has(id) ? "Hide" : "Check my thinking";
        } }, revealed.has(id) ? "Hide" : "Check my thinking");
        return h("div", { class: "coach-step" }, h("b", {}, s.title), h("div", { class: "small" }, s.question), button, facts);
      }));
  }

  async function loadSuggestions(f) {
    if (suggestions.has(f) || pending.has(f)) return;
    pending.add(f);
    try {
      suggestions.set(f, await api("/api/play/suggest", { method: "POST", body: { fen: f, n: 3 } }));      // always three, so switching the count is instant
    } catch (_) { suggestions.set(f, null); }
    pending.delete(f);
    if (f === current()) render();
  }

  let suggestPainted = "";
  function paintSuggestions(info) {
    const f = current();
    const wanted = st.hints && !info.over && !st.thinking;
    suggestEl.classList.toggle("hidden", !wanted);
    if (!wanted) { suggestPainted = ""; return []; }
    const data = suggestions.get(f);
    if (data === undefined) {
      loadSuggestions(f);
      suggestPainted = "";
      suggestEl.replaceChildren(h("span", { class: "muted small" }, "Studying the position for the best moves (about a second)…"));
      return [];
    }
    if (!data) { suggestEl.replaceChildren(h("span", { class: "muted small" }, "The engine is not available right now, so there are no suggestions.")); return []; }
    const shown = data.moves.slice(0, st.count);
    const key = `${f}|${st.count}`;
    if (suggestPainted !== key) {
      suggestPainted = key;
      suggestEl.replaceChildren(
        contextBlock(data.context, info.turn),
        h("div", { class: "small muted" }, `Best moves, in order: ${shown.map((_, i) => `${COLOURS[i]} arrow = ${ORDINAL[i]}`).join(", ")}.`),
        ...shown.map((m, i) => {
          const pick = info.moves.find((x) => x.uci === m.uci);
          return suggestionCard(m, i, { onPlay: pick ? async () => { await play(pick); computerReply(); } : null });
        }));
    }
    return shown.map((m, i) => arrowFrom(m.uci, KINDS[i]));
  }

  async function render() {
    const info = await legal(current());
    const targets = st.selected ? info.moves.filter((m) => m.uci.startsWith(st.selected)).map((m) => m.uci.slice(2, 4)) : [];
    const shownOrient = st.flip ? (orient === "white" ? "black" : "white") : orient;
    const arrows = paintSuggestions(info);
    paintThink();
    drawBoard(boardEl, current(), { orient: shownOrient, arrows, selected: st.selected, targets, lastMove: st.ucis[st.ucis.length - 1], onSquare: click });
    status.textContent = st.thinking ? "The computer is thinking…" : info.over ? `Game over (${info.result}).` : `${info.turn === "white" ? "White" : "Black"} to move. Click a piece, then its square.`;
    list.replaceChildren(...(st.sans.length ? st.sans.map((s, i) => h("button", { class: "step", onclick: () => { st.fens.length = i + 2; st.sans.length = i + 1; st.ucis.length = i + 1; st.selected = null; render(); } }, label(i))) : [h("span", { class: "muted small" }, "Your moves will appear here.")]));
  }

  async function play(m) {
    st.fens.push(m.fen); st.sans.push(m.san); st.ucis.push(m.uci); st.selected = null;
    await render();
  }

  async function computerReply() {
    const info = await legal(current());
    if (!st.computer || info.over) return;
    st.thinking = true; await render();
    try {
      const r = await api("/api/play/reply", { method: "POST", body: { fen: current(), level: st.level } });
      st.thinking = false;
      await play({ fen: r.fen, san: r.move.san, uci: r.move.uci });
    } catch (e) { st.thinking = false; toast(e.message); render(); }
  }

  async function click(sq) {
    if (st.thinking) return;
    const info = await legal(current());
    if (info.over) return;
    if (st.selected) {
      const options = info.moves.filter((m) => m.uci.slice(0, 2) === st.selected && m.uci.slice(2, 4) === sq);
      if (options.length) {
        const m = options.find((x) => x.uci.length === 5 && x.uci[4] === "q") || options[0];
        await play(m);
        return computerReply();
      }
    }
    st.selected = info.moves.some((m) => m.uci.slice(0, 2) === sq) && st.selected !== sq ? sq : null;
    render();
  }

  const computerToggle = h("input", { type: "checkbox", id: "ex-cpu", onchange: (e) => { st.computer = e.target.checked; if (st.computer) computerReply(); } });
  const levelSel = h("select", { class: "select", style: "max-width:190px", "aria-label": "Computer level", onchange: (e) => { st.level = +e.target.value; } });
  api("/api/play/levels").then((levels) => levelSel.replaceChildren(...levels.map((l) => h("option", { value: l.id, selected: l.id === st.level }, `${l.label} (~${l.elo})`)))).catch(() => {});

  const hintToggle = h("input", { type: "checkbox", id: "ex-hints", checked: st.hints, onchange: (e) => {
    st.hints = e.target.checked;
    try { localStorage.setItem("dk-hints", st.hints ? "on" : "off"); } catch (_) { /* not saved */ }
    render();
  } });

  const countSel = h("select", { class: "select", id: "ex-count", "aria-label": "How many suggested moves to show", style: "width:auto;padding:4px 8px" },
    [[1, "1 move"], [2, "2 moves"], [3, "3 moves"]].map(([n, t]) => h("option", { value: n, selected: n === st.count }, t)));
  countSel.addEventListener("change", () => {
    st.count = +countSel.value;
    try { localStorage.setItem("dk-hints-n", String(st.count)); } catch (_) { /* not saved */ }
    render();
  });
  const thinkToggle = h("input", { type: "checkbox", id: "ex-think", checked: st.think, onchange: (e) => { st.think = e.target.checked; thinkPainted = ""; render(); } });

  render();
  return h("div", { class: "stack-s" },
    h("div", { class: "row spread" }, h("b", {}, title), onBack ? h("button", { class: "btn small", onclick: onBack }, icon("x"), backLabel) : null),
    boardEl, status,
    h("div", { class: "row small", style: "gap:8px" },
      h("label", { class: "row", style: "gap:8px;cursor:pointer" }, hintToggle, "Show the best moves on the board"),
      countSel),
    suggestEl,
    h("label", { class: "row small", style: "gap:8px;cursor:pointer" }, thinkToggle, "Coach me: help me think it through (no answers given)"),
    thinkEl,
    h("div", { class: "row", style: "gap:6px" },
      h("button", { class: "btn small", onclick: () => { if (st.sans.length) { st.fens.pop(); st.sans.pop(); st.ucis.pop(); st.selected = null; render(); } } }, "Undo"),
      h("button", { class: "btn small", onclick: () => { Object.assign(st, { fens: [fen], sans: [], ucis: [], selected: null }); render(); } }, "Start again"),
      h("button", { class: "btn small", onclick: () => { st.flip = !st.flip; render(); } }, "Flip"),
      h("button", { class: "btn small", onclick: () => copyText(current()) }, icon("copy"), "Copy position"),
      h("button", { class: "btn small primary", onclick: () => go(playHref(current()).slice(1)) }, icon("swords"), "Play from here")),
    h("label", { class: "row small", style: "gap:8px;cursor:pointer" }, computerToggle, "Let the computer answer my moves", levelSel),
    h("div", {}, h("div", { class: "small muted", style: "margin-bottom:4px" }, "Moves played here"), list));
}
