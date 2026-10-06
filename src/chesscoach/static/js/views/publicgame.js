// A game someone shared by link: replay it with the coach's analysis. Works without an account.
import { h, icon, mount, pct } from "../dom.js";
import { drawBoard } from "../board.js";
import { timelineChart } from "../charts.js";
import { state } from "../state.js";

const RESULT = { "1-0": "1–0", "0-1": "0–1", "1/2-1/2": "½–½", "*": "*" };

export async function renderPublicGame(token) {
  const root = document.getElementById("root");
  document.title = "A shared game · Chess Varsity";
  let d;
  try {
    const res = await fetch(`/api/public/games/${encodeURIComponent(token)}`);
    d = await res.json();
    if (!res.ok) throw new Error(d.detail || "This link isn't available.");
  } catch (err) {
    mount(root, h("div", { class: "auth" }, h("div", { class: "form", style: "margin:auto" },
      h("div", { class: "card stack" }, h("h2", {}, "This game isn't available"), h("p", { class: "muted" }, err.message),
        h("a", { class: "btn primary", href: "#/" }, "Go to Chess Varsity")))));
    return;
  }
  document.title = `${d.white} vs ${d.black} · Chess Varsity`;
  let ply = 0;
  const boardEl = h("div", { class: "board", style: "max-width:520px" });
  const chartBox = h("div", {});
  const note = h("div", { class: "small", style: "min-height:2.6em" });
  const moveList = h("div", { class: "steps", style: "max-height:170px;overflow:auto" });
  const label = (p) => `${Math.ceil(p / 2)}${p % 2 ? "." : "…"} ${d.moves[p - 1].san}`;

  function setPly(p) {
    ply = Math.max(0, Math.min(d.moves.length, p));
    drawBoard(boardEl, ply ? d.moves[ply - 1].fen : d.start_fen, { orient: d.color, lastMove: ply ? d.moves[ply - 1].uci : null });
    if (d.timeline && d.timeline.length) mount(chartBox, timelineChart(d.timeline, { playerWhite: d.color === "white", ply, onSelect: setPly }));
    const c = ply ? (d.commentary || []).find((x) => x.ply === ply) : null;
    mount(note, c ? [h("b", {}, `${label(ply)}  `), c.text] : h("span", { class: "muted" }, ply ? "" : "Step through the game with ◀ ▶, the arrow keys, or by clicking a move."));
    [...moveList.children].forEach((b, i) => b.setAttribute("aria-current", i === ply - 1 ? "true" : "false"));
  }
  moveList.append(...d.moves.map((m, i) => h("button", { class: "step", onclick: () => setPly(i + 1) }, i % 2 === 0 ? `${i / 2 + 1}. ${m.san}` : m.san)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") setPly(ply - 1);
    if (e.key === "ArrowRight") setPly(ply + 1);
  });

  const signedIn = !!state.user;
  mount(root, h("div", { class: "stack", style: "max-width:1100px;margin:0 auto;padding:20px 16px" },
    h("div", { class: "row", style: "justify-content:space-between;gap:10px;flex-wrap:wrap" },
      h("a", { class: "row", href: "#/", style: "gap:10px;font-weight:800;font-size:1.1rem;color:var(--ink);text-decoration:none" },
        h("img", { src: "/static/logo.svg", alt: "", style: "width:32px;height:32px" }), "Chess Varsity", h("span", { class: "beta" }, "BETA")),
      h("a", { class: "btn primary small", href: signedIn ? "#/" : "#/register" }, signedIn ? "Back to my games" : "Analyze your own games, free")),
    h("div", { class: "split-lib" },
      h("div", { class: "stack-s" }, boardEl,
        h("div", { class: "row", style: "gap:6px" },
          h("button", { class: "btn small", "aria-label": "First move", onclick: () => setPly(0) }, "⏮"),
          h("button", { class: "btn small", "aria-label": "Previous move", onclick: () => setPly(ply - 1) }, "◀"),
          h("button", { class: "btn small", "aria-label": "Next move", onclick: () => setPly(ply + 1) }, "▶"),
          h("button", { class: "btn small", "aria-label": "Last move", onclick: () => setPly(d.moves.length) }, "⏭")),
        chartBox, moveList),
      h("div", { class: "stack" },
        h("div", { class: "card stack-s" },
          h("div", { class: "small muted" }, `Shared by ${d.author}`),
          h("h2", { style: "margin:0" }, `${d.white} vs ${d.black}`, h("span", { class: "muted", style: "font-weight:600" }, `  ${RESULT[d.result] || d.result}`)),
          h("div", { class: "small muted" }, [d.eco && d.opening ? `${d.eco} ${d.opening}` : d.opening, d.event,
            d.accuracy !== null && d.accuracy !== undefined ? `${pct(d.accuracy)} accuracy for ${d.author}` : null].filter(Boolean).join(" · ")),
          d.headline ? h("div", { class: "callout small" }, icon("bulb"), " ", d.headline) : null),
        h("div", { class: "card" }, h("div", { class: "small muted", style: "margin-bottom:4px" }, "Coach's note"), note),
        h("p", { class: "small muted", style: "margin:0" }, "Analyzed by Chess Varsity with Stockfish. This page was shared by its owner and isn't listed publicly.")))));
  setPly(0);
}
