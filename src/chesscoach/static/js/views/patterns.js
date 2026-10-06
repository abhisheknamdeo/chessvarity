// Mistake patterns: every habit at a glance, the ones to work on first in full, and the rest one click away.
import { h, icon, ring, level } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { trainHref, emptyState } from "../components.js";

const LEVEL = { work: "Work on this", ok: "Getting there", strong: "Strength" };

/** The examples from your own games, each saying what happened. The same thing in several games is shown once. */
function examples(habit) {
  if (!habit.evidence.length) return null;
  const groups = new Map();
  for (const e of habit.evidence) {
    const key = e.headline || `Move ${e.move_number}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  const href = (e) => `#/game/${e.game_id}${e.ply ? "/" + e.ply : ""}`;
  const who = (e) => [e.opponent && e.opponent !== "Opponent" ? `vs ${e.opponent}` : "", `move ${e.move_number}`, e.played ? `you played ${e.played}` : ""].filter(Boolean).join(" · ");
  return h("div", { class: "stack-s" }, h("div", { class: "pt-sub" }, "In your games"),
    h("div", { class: "pt-examples" }, [...groups].map(([title, list]) => list.length === 1
      ? h("a", { class: "pt-example", href: href(list[0]) }, h("b", {}, title), h("span", { class: "small muted" }, who(list[0])))
      : h("div", { class: "pt-example" }, h("b", {}, title),
        h("span", { class: "small muted" }, `In ${list.length} games: `,
          ...list.flatMap((e, i) => [i ? " · " : "", h("a", { href: href(e), title: who(e) }, `game ${i + 1}`)]))))));
}

const advice = (habit, n) => h("div", { class: "stack-s" }, h("div", { class: "pt-sub" }, "What to do"),
  h("ul", { class: "dots", style: "margin:0" }, habit.advice.slice(0, n).map((a) => h("li", {}, a))));
const training = (habit) => (habit.train.length ? h("div", { class: "row", style: "gap:8px" },
  habit.train.map((t, i) => h("a", { class: `btn small${i === 0 ? " primary" : ""}`, href: trainHref(t) }, icon("arrow"), t.label))) : null);

/** A habit to work on now: everything shown. */
function focusCard(habit, n) {
  return h("article", { class: "card pt-focus", id: `habit-${habit.id}` },
    h("div", { class: "row spread", style: "align-items:flex-start;flex-wrap:nowrap;gap:14px" },
      h("div", { style: "min-width:0" },
        h("div", { class: "pt-kicker" }, `Priority ${n} · ${habit.title}`),
        h("h3", { style: "margin:4px 0 6px" }, habit.headline),
        h("p", { class: "muted", style: "margin:0" }, habit.detail)),
      ring(habit.score)),
    h("div", { class: "pt-focus-body" }, advice(habit, 3), examples(habit)),
    training(habit));
}

/** Any other habit: one line, opens for the details. */
function habitRow(habit) {
  return h("details", { class: "card pt-row", id: `habit-${habit.id}` },
    h("summary", {},
      h("span", { class: `pill ${level(habit.score)}` }, LEVEL[habit.level]),
      h("span", { class: "pt-row-title" }, h("b", {}, habit.title), h("span", { class: "small muted" }, habit.headline)),
      h("span", { class: "pt-row-score" }, habit.score), h("span", { class: "pt-chev", "aria-hidden": "true" }, "›")),
    h("div", { class: "stack-s", style: "margin-top:12px" },
      h("p", { class: "muted", style: "margin:0" }, habit.detail), advice(habit, 4), examples(habit), training(habit)));
}

/** Every habit as a bar, worst first. Click one to jump to it. */
function glance(habits) {
  return h("section", { class: "card stack-s", "aria-labelledby": "pt-glance" },
    h("div", { class: "row spread" }, h("h2", { id: "pt-glance", style: "margin:0" }, "Your habits at a glance"),
      h("span", { class: "small muted" }, "0 = needs work, 100 = a strength")),
    h("div", { class: "pt-bars" }, habits.map((x) => h("button", { class: "pt-bar", type: "button", onclick: () => {
      const el = document.getElementById(`habit-${x.id}`);
      if (el && el.tagName === "DETAILS") el.open = true;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } },
      h("span", { class: "pt-bar-label" }, x.title),
      h("span", { class: "pt-bar-track" }, h("i", { class: level(x.score), style: `width:${Math.max(4, x.score)}%` })),
      h("span", { class: "pt-bar-num" }, x.score)))));
}

export async function patternsView() {
  const player = currentPlayer();
  const r = await api(`/api/players/${player.id}/habits`);
  document.title = "Mistake patterns · Chess Varsity";
  const head = h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Mistake patterns"),
    h("p", {}, `The habits behind your mistakes, found across ${r.games ? `your last ${r.games} game${r.games === 1 ? "" : "s"}` : "your games"}. Fix one habit and many mistakes disappear at once.`)));
  if (!r.ready) {
    return h("div", { class: "stack" }, head, h("div", { class: "card stack-s" },
      emptyState({ icon: "🔍", title: "Your habits appear after a few games", text: r.message || "Add and analyze a few games. Habits show once there are about 20 analyzed moves.",
        progress: `${r.games || 0} game${r.games === 1 ? "" : "s"} analyzed so far`,
        action: h("a", { class: "btn primary small", href: "#/add" }, icon("plus"), "Add a game") }),
      h("p", { class: "small muted", style: "margin:4px 0 0" }, "Meanwhile, ", h("a", { href: "#/academy" }, "sharpen your tactics in the Attack academy"), " or ", h("a", { href: "#/roadmap" }, "see your roadmap"), ".")));
  }
  const sorted = [...r.habits].sort((a, b) => a.score - b.score);
  const focus = sorted.filter((x) => x.level === "work").slice(0, 3);
  const rest = sorted.filter((x) => !focus.includes(x));
  // Recommendations that aren't one of the habits (for example, openings that suit you) are shown once, as extras.
  const headlines = new Set(r.habits.map((x) => x.headline));
  const extras = (r.recommendations || []).filter((rec) => !headlines.has(rec.title));
  return h("div", { class: "stack pt" }, head,
    glance(sorted),
    focus.length ? h("section", { class: "stack-s", "aria-labelledby": "pt-first" },
      h("h2", { id: "pt-first", style: "margin:8px 0 0" }, focus.length === 1 ? "Work on this first" : `Work on these ${focus.length} first`),
      focus.map((x, i) => focusCard(x, i + 1)))
      : h("div", { class: "alert good" }, h("b", {}, "No weak habits in these games. "), "Keep playing tougher opponents and keep practicing."),
    extras.length ? h("div", { class: "stack-s" }, extras.map((rec) => h("div", { class: "callout" },
      h("b", {}, rec.title), h("p", { class: "muted small", style: "margin:4px 0" }, rec.why),
      rec.actions && rec.actions.length ? h("ul", { class: "dots small", style: "margin:0" }, rec.actions.map((x) => h("li", {}, x))) : null,
      h("div", { class: "row", style: "gap:8px;margin-top:6px" },
        rec.suggested ? h("a", { class: "btn small", href: "#/openings/repertoire" }, "See attacking openings") : null,
        ...(rec.train || []).map((t) => h("a", { class: "btn small", href: trainHref(t) }, t.label)))))) : null,
    rest.length ? h("section", { class: "stack-s", "aria-labelledby": "pt-rest" },
      h("h2", { id: "pt-rest", style: "margin:8px 0 0" }, focus.length ? "Your other habits" : "Your habits"),
      h("p", { class: "small muted", style: "margin:0" }, "Open any of them for the details, examples from your games and what to do."),
      rest.map(habitRow)) : null);
}
