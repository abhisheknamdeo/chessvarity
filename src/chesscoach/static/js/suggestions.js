// Suggested moves: what each one does and why, how much better or worse it is, and the line the engine expects.
import { h } from "./dom.js";

export const ORDINAL = ["1st", "2nd", "3rd"];
export const KINDS = ["best", "second", "third"];
export const COLOURS = ["green", "orange", "purple"];
const QUALITY_PILL = { best: "good", equal: "good", good: "good", ok: "warn", weak: "bad", bad: "bad" };

/** A short read on the position for the side to move: who is better, and any threat to deal with. */
export function contextBlock(ctx, turn) {
  if (!ctx) return null;
  return h("div", { class: "sugg-ctx" },
    h("div", {}, h("b", {}, `${ctx.side} to move: `), `${ctx.state} (${ctx.score}). `, h("span", { class: "muted" }, ctx.verdict)),
    ctx.in_check ? h("div", { class: "sugg-warn" }, "⚠ Your king is in check, so the move must answer it.") : null,
    ctx.threats.map((t) => h("div", { class: "sugg-warn" }, `⚠ ${t}`)));
}

/** One suggestion. `onPlay` (optional) adds a "Play it" button. */
export function suggestionCard(m, i, { onPlay } = {}) {
  return h("div", { class: `cand c${i + 1} q-${m.quality}`, "data-rank": m.rank },
    h("div", { class: "cand-head" },
      h("span", { class: "pill" }, ORDINAL[i]),
      h("b", { class: "san" }, m.san),
      h("span", { class: `pill ${QUALITY_PILL[m.quality] || "gray"}`, "data-quality": m.quality }, m.label),
      h("span", { class: "muted small", title: `${m.state} for the side to move` }, `${m.score} · ${m.state}`),
      onPlay ? h("button", { class: "btn small", type: "button", style: "margin-left:auto", onclick: onPlay }, "Play it") : null),
    h("div", { class: "cand-headline" }, m.headline),
    h("ul", { class: "dots cand-why" }, m.reasons.map((r) => h("li", {}, r))),
    m.warnings.map((w) => h("div", { class: "sugg-warn" }, `⚠ ${w}`)),
    m.reply ? h("div", { class: "small muted" }, h("b", {}, "Then: "), m.reply.text) : null,
    m.line ? h("div", { class: "cand-line mono small" }, h("span", { class: "muted" }, "Engine line: "), m.line) : null);
}
