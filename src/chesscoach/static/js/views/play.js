import { h, icon, toast } from "../dom.js";
import { contextBlock, suggestionCard } from "../suggestions.js";
import { api } from "../api.js";
import { state, store } from "../state.js";
import { drawBoard, arrowFrom } from "../board.js";
import { copyText } from "../explorer.js";
import { loadSections } from "../state.js";
import { go } from "../router.js";
import { confetti } from "../fun.js";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const SAVED = "cc-play-settings";  // {level, side}, kept only when "Remember" is ticked
const DEFAULT_ELO = 1700;

function savedSettings() {
  try { return JSON.parse(store.get(SAVED) || "null"); } catch (_) { return null; }
}

export async function playView(_params, query) {
  document.title = "Play the computer · Chess Varsity";
  const levels = await api("/api/play/levels");
  const startFen = query.fen && query.fen.split(" ").length >= 4 ? query.fen : START;
  const startWhite = startFen.split(" ")[1] === "w";
  const startNumber = +startFen.split(" ")[5] || 1;
  const saved = savedSettings();
  const defaultLevel = (levels.find((l) => l.elo === DEFAULT_ELO) || levels[Math.min(4, levels.length - 1)]).id;
  const savedSide = saved && startFen === START && (saved.side === "white" || saved.side === "black") ? saved.side : null;
  const g = { side: query.side === "black" ? "black" : query.side === "white" ? "white" : savedSide || (startWhite ? "white" : "black"),
    level: saved && levels.some((l) => l.id === saved.level) ? saved.level : defaultLevel, fens: [startFen], sans: [], ucis: [], selected: null, arrows: [], over: null, thinking: false, resigned: false };
  const cache = new Map();

  const boardEl = h("div", { class: "board big" });
  const banner = h("div", { class: "hidden", role: "status" });
  const hintBox = h("div", { class: "hidden callout" });
  const moveBox = h("div", { class: "movelist" });
  const status = h("div", { class: "muted small", "aria-live": "polite", style: "min-height:1.4em" });
  const current = () => g.fens[g.fens.length - 1];
  const myTurn = () => (current().split(" ")[1] === "w") === (g.side === "white");
  const legal = async (f) => { if (!cache.has(f)) cache.set(f, await api(`/api/legal?fen=${encodeURIComponent(f)}`)); return cache.get(f); };

  function movesNumbered() {
    const rows = [];
    let no = startNumber, white = startWhite, i = 0;
    if (!white && g.sans.length) { rows.push([no, "…", g.sans[0]]); i = 1; no += 1; white = true; }
    for (; i < g.sans.length; i += 2) { rows.push([no, g.sans[i], g.sans[i + 1] || ""]); no += 1; }
    return rows;
  }

  async function render() {
    const info = await legal(current());
    const targets = g.selected ? info.moves.filter((m) => m.uci.startsWith(g.selected)).map((m) => m.uci.slice(2, 4)) : [];
    drawBoard(boardEl, current(), { orient: g.side, selected: g.selected, targets, arrows: g.arrows, lastMove: g.ucis[g.ucis.length - 1], onSquare: g.over || g.thinking ? null : click });
    moveBox.replaceChildren(...movesNumbered().flatMap(([no, a, b]) => [h("div", { class: "n" }, `${no}.`), h("span", { class: "mono" }, a), h("span", { class: "mono" }, b)]));
    status.textContent = g.over ? "" : g.thinking ? "The computer is thinking…" : myTurn() ? "Your move. Click a piece, then its square." : "";
    if (g.over) {
      const won = (g.over.result === "1-0") === (g.side === "white") && g.over.result !== "1/2-1/2";
      const draw = g.over.result === "1/2-1/2";
      banner.className = `alert ${draw ? "info" : won ? "good" : "bad"}`;
      banner.textContent = g.resigned ? "You resigned." : draw ? `Draw by ${g.over.reason || "agreement"}.` : won ? `You win${g.over.reason ? " by " + g.over.reason : ""}!` : `The computer wins${g.over.reason ? " by " + g.over.reason : ""}. Save the game and see where it turned.`;
      if (won && !g.resigned) confetti();
    } else banner.className = "hidden";
  }

  async function afterMove(info) {
    if (info.over) { g.over = { result: info.result, reason: info.reason || (info.result ? "" : "") }; return render(); }
    if (!myTurn()) return computerMove();
    return render();
  }

  async function computerMove() {
    g.thinking = true; g.arrows = []; hintBox.classList.add("hidden");
    await render();
    try {
      const r = await api("/api/play/reply", { method: "POST", body: { fen: current(), level: g.level } });
      g.fens.push(r.fen); g.sans.push(r.move.san); g.ucis.push(r.move.uci);
      g.thinking = false;
      if (r.over) { g.over = { result: r.result, reason: r.reason }; }
    } catch (e) { g.thinking = false; toast(e.message); }
    render();
  }

  async function click(sq) {
    if (!myTurn()) return;
    const info = await legal(current());
    if (g.selected) {
      const options = info.moves.filter((m) => m.uci.slice(0, 2) === g.selected && m.uci.slice(2, 4) === sq);
      if (options.length) {
        const m = options.find((x) => x.uci.length === 5 && x.uci[4] === "q") || options[0];
        g.fens.push(m.fen); g.sans.push(m.san); g.ucis.push(m.uci); g.selected = null; g.arrows = [];
        hintBox.classList.add("hidden");
        const next = await legal(m.fen);
        return afterMove(next);
      }
    }
    g.selected = info.moves.some((m) => m.uci.slice(0, 2) === sq) && g.selected !== sq ? sq : null;
    render();
  }

  async function newGame(fen = startFen) {
    Object.assign(g, { fens: [fen], sans: [], ucis: [], selected: null, arrows: [], over: null, thinking: false, resigned: false });
    hintBox.classList.add("hidden");
    await render();
    if (!myTurn()) computerMove();
  }

  function takeBack() {
    if (g.thinking || !g.sans.length) return;
    const undo = myTurn() ? 2 : 1;      // your move and the computer's reply
    for (let i = 0; i < undo && g.sans.length; i++) { g.fens.pop(); g.sans.pop(); g.ucis.pop(); }
    if (!myTurn() && g.sans.length) { g.fens.pop(); g.sans.pop(); g.ucis.pop(); }
    g.over = null; g.selected = null; g.arrows = []; g.resigned = false; hintBox.classList.add("hidden");
    render();
  }

  async function hint() {
    if (g.over || g.thinking || !myTurn()) return;
    try {
      const r = await api("/api/play/hint", { method: "POST", body: { fen: current() } });
      g.arrows = [arrowFrom(r.uci, "best")];
      hintBox.classList.remove("hidden");
      hintBox.replaceChildren(contextBlock(r.context, null), suggestionCard(r, 0));
      render();
    } catch (e) { toast(e.message); }
  }

  function pgn() {
    const result = g.over ? g.over.result || "*" : "*";
    const white = g.side === "white" ? state.player.name : `Computer (${levels.find((l) => l.id === g.level).label})`;
    const black = g.side === "black" ? state.player.name : `Computer (${levels.find((l) => l.id === g.level).label})`;
    const head = [["Event", "Practice vs computer"], ["White", white], ["Black", black], ["Result", result]];
    if (startFen !== START) head.push(["SetUp", "1"], ["FEN", startFen]);
    let text = "", no = startNumber, whiteMove = startWhite;
    g.sans.forEach((san, i) => {
      if (whiteMove) text += `${no}. ${san} `;
      else { text += `${i === 0 ? `${no}... ` : ""}${san} `; no += 1; }
      whiteMove = !whiteMove;
    });
    return `${head.map(([k, v]) => `[${k} "${v}"]`).join("\n")}\n\n${text}${result}\n`;
  }

  async function save() {
    if (!g.sans.length) { toast("Play a few moves first."); return; }
    try {
      const res = await api("/api/games", { method: "POST", body: { pgn: pgn(), color: g.side, event: "Practice vs computer" } });
      await loadSections();
      toast("Saved. Analyzing your game…");
      go(res.games.length ? `/game/${res.games[0].id}` : "/");
    } catch (e) { toast(e.message); }
  }

  const sideTabs = h("div", { class: "tabs" }, [["white", "White"], ["black", "Black"]].map(([k, t]) =>
    h("button", { "aria-selected": g.side === k ? "true" : "false", onclick: (e) => {
      g.side = k; [...e.currentTarget.parentNode.children].forEach((b) => b.setAttribute("aria-selected", b === e.currentTarget ? "true" : "false")); remember(); newGame();
    } }, t)));
  const rememberBox = h("input", { type: "checkbox", checked: !!saved, onchange: () => {
    if (rememberBox.checked) { remember(); toast("Your difficulty and side will be remembered on this device."); }
    else store.set(SAVED, "");
  } });
  function remember() { if (rememberBox.checked) store.set(SAVED, JSON.stringify({ level: g.level, side: g.side })); }
  const levelSel = h("select", { class: "select", "aria-label": "Difficulty", onchange: (e) => { g.level = +e.target.value; remember(); } }, levels.map((l) => h("option", { value: l.id, selected: l.id === g.level }, `${l.id}. ${l.label} (~${l.elo})`)));

  const panel = h("div", { class: "stack" },
    h("div", { class: "card stack-s" },
      h("h3", { style: "margin:0" }, "Play the computer"),
      startFen !== START ? h("div", { class: "callout" }, icon("copy"), " Starting from a position you copied.") : null,
      h("div", { class: "field" }, h("label", {}, "I play"), sideTabs),
      h("div", { class: "field" }, h("label", {}, "Difficulty"), levelSel,
        h("label", { class: "small muted", style: "display:flex;align-items:center;gap:6px;cursor:pointer;font-weight:500" }, rememberBox, "Remember my difficulty and side")),
      h("div", { class: "row" }, h("button", { class: "btn primary small", onclick: () => newGame() }, icon("refresh"), "New game"),
        h("button", { class: "btn small", onclick: () => newGame(START) }, "Standard start"))),
    h("div", { class: "card stack-s" },
      banner, hintBox,
      h("div", { class: "row" },
        h("button", { class: "btn small", onclick: takeBack }, "Take back"),
        h("button", { class: "btn small", onclick: hint }, icon("bulb"), "Hint"),
        h("button", { class: "btn small danger", onclick: () => { if (!g.over && g.sans.length && confirm("Resign this game?")) { g.over = { result: g.side === "white" ? "0-1" : "1-0", reason: "resignation" }; g.resigned = true; render(); } } }, "Resign"),
        h("button", { class: "btn small", onclick: () => copyText(current()) }, icon("copy"), "Copy position")),
      h("div", {}, h("div", { class: "small muted", style: "margin-bottom:4px" }, "Moves"), moveBox),
      h("div", { class: "row" },
        h("button", { class: "btn small primary", onclick: save }, icon("plus"), "Save and analyze this game"),
        h("button", { class: "btn small", onclick: () => copyText(pgn(), "Moves copied") }, "Copy PGN"))));

  await render();
  if (!myTurn()) computerMove();
  return h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Play the computer"), h("p", {}, "Practice against Stockfish at a level that suits you. Try a copied position, or a game from your own mistakes."))),
    h("div", { class: "review" }, h("div", { class: "left" }, boardEl, status), panel));
}
