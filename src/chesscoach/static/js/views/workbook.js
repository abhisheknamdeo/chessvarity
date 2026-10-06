import { h, icon, mount } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { puzzleRunner } from "../puzzle.js";
import { emptyState } from "../components.js";
import { fmtDate } from "../dom.js";
import { boardTools } from "../explorer.js";

const SKILLS = [["", "Everything"], ["threat_recognition", "Threats I missed"], ["blunder_check", "Pieces left in danger"], ["tactics", "Tactics I missed"], ["attacking", "Attack chances"], ["initiative", "Being too passive"]];

export async function workbookView({ skill } = {}) {
  const player = currentPlayer();
  document.title = "Workbook · Chess Varsity";
  let chosen = skill || "";
  const [items0, progress] = await Promise.all([api(`/api/players/${player.id}/workbook`), api(`/api/players/${player.id}/progress`)]);
  const solved = new Set(progress.solved);
  const body = h("div", {});
  const chips = h("div", { class: "filter-chips", role: "group", "aria-label": "Show" });
  function paintChips() {
    mount(chips, SKILLS.map(([v, t]) => {
      const n = v ? items0.filter((i) => i.skill === v).length : items0.length;
      if (v && !n) return null;
      return h("button", { type: "button", class: "fchip", "aria-pressed": v === chosen ? "true" : "false", onclick: () => { chosen = v; index = 0; render(); } },
        t, h("span", { class: "fchip-n" }, n));
    }));
  }
  let index = 0;

  function render() {
    paintChips();
    const items = chosen ? items0.filter((i) => i.skill === chosen) : items0;
    if (!items.length) {
      mount(body, h("div", { class: "card stack-s" },
        emptyState({ icon: "♟", title: "No positions here yet", text: "When the coach finds a mistake in one of your games, the position comes here so you can find the better move.",
          action: h("a", { class: "btn primary small", href: "#/add" }, icon("plus"), "Add a game") }),
        h("p", { class: "small muted", style: "margin:4px 0 0" }, "Meanwhile, try the ", h("a", { href: "#/academy" }, "Attack academy puzzles"), ".")));
      return;
    }
    index = Math.min(index, items.length - 1);
    const item = items[index];
    // A workbook position is a single move: any of the coach's good moves counts.
    const runner = puzzleRunner({
      fen: item.puzzle.fen, side: item.side, line: [item.puzzle.good_moves[0]], goodMoves: item.puzzle.good_moves,
      hint: "Check every check and capture first.", threat_uci: item.puzzle.threat_uci,
      answer: item.puzzle.answer, lesson: item.lesson, line_san: [item.candidates.filter((c) => c.good).map((c) => c.san).join(" or ")],
      revealText: `Good moves here: ${item.candidates.filter((c) => c.good).map((c) => c.san).join(", ")}. You played ${item.played} in the game.`,
    }, {
      orient: item.side,
      onSolved: async () => { solved.add(item.id); try { await api(`/api/players/${player.id}/puzzles/${item.id}/solved`, { method: "POST" }); } catch (_) { /* offline */ } },
      onNext: () => { index = (index + 1) % items.length; render(); },
    });
    mount(body, h("div", { class: "split-eq" },
      h("div", { class: "card stack-s" },
        h("div", { class: "muted small" }, `Position ${index + 1} of ${items.length}`),
        sourceCard(item),
        h("h3", {}, item.puzzle.prompt), runner, boardTools(() => item.puzzle.fen)),
      h("div", { class: "stack" },
        h("div", { class: "card stack-s" }, h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, "Your positions"),
            h("span", { class: "small muted" }, `${items.filter((it) => solved.has(it.id)).length} of ${items.length} solved`)),
          h("div", { class: "meter", style: "height:8px" }, h("i", { style: `width:${Math.round((100 * items.filter((it) => solved.has(it.id)).length) / items.length)}%` })),
          h("div", { class: "puz-list" }, items.map((it, i) => h("button", { class: "puz", "aria-current": i === index ? "true" : "false", onclick: () => { index = i; render(); } },
            h("span", {}, h("b", {}, it.title), h("div", { class: "small muted" }, `Move ${it.move_number} · you played ${it.played}`)),
            solved.has(it.id) ? h("span", { class: "ok", title: "Solved" }, icon("check")) : null)))))));
  }

  function sourceCard(item) {
    const g = item.game;
    const outcome = g.outcome === "win" ? "won" : g.outcome === "loss" ? "lost" : g.outcome === "draw" ? "drew" : "unfinished";
    const bits = [g.opponent ? `vs ${g.opponent}` : null, g.event || null, g.match ? `Match #${g.match}` : null, fmtDate(g.date) || null].filter(Boolean);
    return h("div", { class: "source" },
      h("div", { class: "source-h" }, icon("folder"), h("b", {}, "From this game")),
      h("div", { class: "small" }, bits.length ? bits.join(" · ") : "A game you added"),
      h("div", { class: "small muted" }, `You played ${g.color === "white" ? "White" : "Black"} and ${outcome}${g.opening ? ` · ${g.eco ? g.eco + " " : ""}${g.opening}` : ""}`),
      h("div", { class: "small muted" }, `Move ${item.move_number}: you played `, h("b", { class: "mono" }, g.played)),
      h("a", { class: "chip", style: "margin-top:6px", href: `#/game/${item.game_id}/${g.ply}` }, icon("arrow"), "Open this game at this move"));
  }

  const head = h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My workbook"), h("p", {}, "Positions from your own games. Find the better move, then compare it with what you played.")));
  render();
  return h("div", { class: "stack" }, head, items0.length ? chips : null, body);
}
