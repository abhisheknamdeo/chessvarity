import { h, icon, mount } from "../dom.js";
import { api } from "../api.js";
import { roadmapStrip } from "../roadmaplinks.js";
import { state, currentPlayer } from "../state.js";
import { puzzleRunner } from "../puzzle.js";
import { go } from "../router.js";
import { boardTools } from "../explorer.js";

const ICON = { mates: "wK", attack: "wQ", traps: "bN", tactics: "wR" };

export async function academyView({ theme } = {}) {
  const player = currentPlayer();
  const [themes, progress] = await Promise.all([
    api("/api/library/academy/themes"),
    player ? api(`/api/players/${player.id}/progress`) : { solved: [] },
  ]);
  const solved = new Set(progress.solved);
  document.title = "Attack academy · Chess Varsity";
  if (!theme) {
    return h("div", { class: "stack" },
      h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Attack academy"), h("p", {}, "Puzzles that teach attacking chess. Every position was checked by a chess engine."))),
      roadmapStrip("#/academy"),
      h("div", { class: "grid g2" }, themes.map((t) =>
        h("a", { class: "card theme-card", href: `#/academy/${t.id}`, style: "text-decoration:none;color:inherit" },
          h("div", { class: "ic" }, h("img", { src: `/static/pieces/${ICON[t.id] || "wP"}.svg`, alt: "" })), h("h3", {}, t.title), h("p", { class: "muted" }, t.blurb),
          h("span", { class: "pill brand" }, `${t.count} puzzles`)))));
  }
  const info = themes.find((t) => t.id === theme);
  if (!info) return h("div", { class: "card" }, "That theme does not exist.", h("a", { href: "#/academy" }, " Back to the academy"));
  const puzzles = await api(`/api/library/academy/puzzles?theme=${encodeURIComponent(theme)}`);
  let index = Math.max(0, puzzles.findIndex((p) => !solved.has(p.id)));
  const body = h("div", {});
  const listCard = h("div", { class: "card" });

  function render() {
    const p = puzzles[index];
    const sideText = p.side === "white" ? "White" : "Black";
    const runner = puzzleRunner({ ...p, prompt: `${sideText} to move` }, {
      orient: p.side,
      onSolved: async () => { solved.add(p.id); if (player) { try { await api(`/api/players/${player.id}/puzzles/${p.id}/solved`, { method: "POST" }); } catch (_) { /* offline */ } } renderList(); },
      onNext: () => { index = (index + 1) % puzzles.length; render(); },
    });
    mount(body, h("div", { class: "split-narrow" },
      h("div", { class: "card stack-s" },
        h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, p.title), h("span", { class: "pill brand" }, `${sideText} to move`)),
        h("p", { class: "muted" }, p.idea),
        runner, boardTools(() => p.fen)),
      listCard));
    renderList();
  }
  function renderList() {
    mount(listCard, h("h3", {}, `${info.title} · ${puzzles.filter((p) => solved.has(p.id)).length}/${puzzles.length} solved`),
      h("div", { class: "puz-list" }, puzzles.map((p, i) => h("button", { class: "puz", "aria-current": i === index ? "true" : "false", onclick: () => { index = i; render(); } },
        h("span", {}, h("b", {}, p.title), h("div", { class: "small muted" }, `${p.side === "white" ? "White" : "Black"} to move · ${Math.ceil(p.line.length / 2)}-move solution`)),
        solved.has(p.id) ? h("span", { class: "ok" }, icon("check")) : null))));
  }
  render();
  return h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("a", { href: "#/academy", class: "small" }, "← All themes"), h("h1", {}, info.title), h("p", {}, info.blurb))), roadmapStrip(`#/academy/${theme}`), body);
}
