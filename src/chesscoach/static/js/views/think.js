// Think like a Grandmaster: the questions strong players ask on every move, how traps work, and a trainer to practise on.
import { h, icon, fmtDate } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { explorer } from "../explorer.js";
import { empty } from "../components.js";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function trainer(mine, samples) {
  const stage = h("div", {});
  const status = h("div", { class: "alert info hidden", role: "status" });

  function begin({ fen, orient, title, lastUci }) {
    stage.replaceChildren(explorer({ fen, orient, title, think: true, hints: false, lastUci, onBack: () => stage.replaceChildren(), backLabel: "Close" }));
    stage.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const own = mine.length
    ? h("div", { class: "stack-s" }, h("h3", { style: "margin:0" }, "Positions from my own games"),
      h("p", { class: "muted small", style: "margin:0" }, "These are moments where things went wrong. Think it through as if it were your move, before you look at the review."),
      h("div", { class: "row", style: "gap:6px" }, mine.map((p, i) => h("button", { class: "chip", "data-position": p.id, onclick: () => begin({ fen: p.fen, orient: p.side, lastUci: p.last_uci, title: `Move ${p.move_number}${p.opponent ? ` vs ${p.opponent}` : ""}` }) },
        `Move ${p.move_number}${p.opponent ? ` vs ${p.opponent}` : ""}${p.date ? ` · ${fmtDate(p.date)}` : ""}`))))
    : h("div", { class: "muted small" }, "Once I have added and analyzed games, positions from my own games appear here.");

  const fenBox = h("input", { class: "input", placeholder: "Paste a position (FEN) to think about…", "aria-label": "Position in FEN", style: "flex:1;min-width:220px" });
  const custom = h("div", { class: "row", style: "gap:6px" }, fenBox, h("button", { class: "btn", onclick: async () => {
    status.classList.add("hidden");
    try {
      const fen = fenBox.value.trim();
      await api("/api/think", { method: "POST", body: { fen } });
      begin({ fen, orient: fen.split(" ")[1] === "b" ? "black" : "white", title: "My position" });
    } catch (e) { status.className = "alert bad"; status.textContent = e.message; }
  } }, "Think about it"));

  const sample = h("div", { class: "stack-s" }, h("h3", { style: "margin:0" }, "Sample positions"),
    h("div", { class: "row", style: "gap:6px" }, samples.map((s) => h("button", { class: "chip", "data-sample": s.id, onclick: () => begin({ fen: s.fen, orient: s.fen.split(" ")[1] === "b" ? "black" : "white", title: s.title }) }, s.title))));

  return h("div", { class: "card stack", id: "trainer" },
    h("div", {}, h("h2", { style: "margin:0" }, "Practice the routine"),
      h("p", { class: "muted", style: "margin:4px 0 0" }, "Pick a position. The board opens with the coach ready to ask the questions. You can also move the pieces to see how the answers change.")),
    own, sample, h("div", { class: "stack-s" }, h("h3", { style: "margin:0" }, "Any position"), custom, status), stage);
}

export async function thinkView() {
  document.title = "Think like a Grandmaster · Chess Varsity";
  const player = currentPlayer();
  const [guide, mine, puzzles] = await Promise.all([
    api("/api/think/guide"), api(`/api/players/${player.id}/think/positions`).catch(() => []), api("/api/library/academy/puzzles?theme=tactics").catch(() => [])]);
  const samples = [
    { id: "start", title: "The starting position", fen: START },
    { id: "scholar", title: "After 1.e4 e5 2.Bc4 Nc6 3.Qh5", fen: "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3" },
    // Not the puzzle's own title: it often names the trick.
    ...puzzles.slice(0, 4).map((p, i) => ({ id: p.id, title: `Academy position ${i + 1}`, fen: p.fen })),
  ];

  const loop = h("div", { class: "card stack-s", id: "the-loop" },
    h("h2", { style: "margin:0" }, guide.loop.title), h("p", { style: "margin:0" }, guide.loop.intro),
    h("ol", { class: "loop" }, guide.loop.steps.map((s) => h("li", {}, h("b", {}, s.title.replace(/^\d+\.\s*/, "")), h("div", { class: "muted" }, s.question)))));

  const traps = h("div", { class: "stack-s" }, h("div", {}, h("h2", { style: "margin:0" }, "How not to get trapped"),
    h("p", { class: "muted", style: "margin:4px 0 0" }, "Almost every trap has a warning sign. Learn the signs and the habit that beats each one.")),
    h("div", { class: "grid g2" }, guide.traps.map((t) => h("div", { class: "card tight stack-s" }, h("h3", { style: "margin:0" }, t.name),
      h("div", { class: "small" }, h("b", {}, "Warning sign: "), t.sign), h("div", { class: "small callout lesson", style: "margin:0" }, h("b", {}, "The habit: "), t.habit)))));

  const principles = h("div", { class: "card stack-s" }, h("h2", { style: "margin:0" }, "Habits of strong players"),
    h("div", { class: "grid g2" }, guide.principles.map((p) => h("div", {}, h("b", {}, p.title), h("div", { class: "muted" }, p.text)))));

  const phases = h("div", { class: "grid g3" }, guide.phases.map((p) => h("div", { class: "card stack-s" }, h("span", { class: "pill brand" }, p.goal), h("h3", { style: "margin:0" }, p.title), h("p", { class: "muted", style: "margin:0" }, p.text))));

  const after = h("div", { class: "card stack-s" }, h("h2", { style: "margin:0" }, "After every game"), h("ol", { class: "dots", style: "margin:0" }, guide.after_game.map((x) => h("li", {}, x))));

  return h("div", { class: "stack", style: "max-width:1000px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Think like a Grandmaster"),
      h("p", {}, "A grandmaster does not see more moves than you. They ask better questions. This page teaches the questions, shows how traps work, and lets you practice on real positions. It never just hands you a move."))),
    loop, trainer(mine, samples), traps, principles, phases, after,
    h("div", { class: "card row spread" }, h("div", {}, h("b", {}, "Ready for the next tournament?"), h("div", { class: "muted small" }, "Turn this into a plan with an opening for each color.")),
      h("a", { class: "btn primary", href: "#/prep" }, icon("star"), "Tournament plan")));
}
