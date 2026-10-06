// The goal sheet: short-term and long-term goals, with progress measured from the student's own games where possible.
import { h, icon, mount, toast, meter, fmtDate } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { askForm } from "../dialogs.js";

const fmt = (v, unit) => (v === null || v === undefined ? "–" : `${Number.isInteger(v) ? v : Math.round(v * 10) / 10}${unit === "%" ? "%" : ""}`);

export async function goalsView() {
  document.title = "My goals · Chess Varsity";
  const player = currentPlayer();
  let sheet = await api(`/api/players/${player.id}/goals`);
  const root = h("div", { class: "stack", style: "max-width:1100px" });
  const finishedOpen = { value: false };
  let allSuggestions = false;

  const call = async (path, options) => {
    try { sheet = await api(path, options); paint(); } catch (e) { toast(e.message); }
  };

  async function addGoal(preset = {}) {
    const measures = [["", "No number, I will tick it off myself"], ...sheet.metrics.map((m) => [m.id, m.label])];
    const v = await askForm({
      title: preset.title ? "Add this goal" : "New goal", confirmLabel: "Add goal",
      intro: "A goal is easier when it is small and has a date. Pick a measure and the app tracks it from your games.",
      fields: [
        { name: "title", label: "What do I want to achieve?", required: true, value: preset.title || "", maxlength: 120 },
        { name: "horizon", label: "How long will it take?", value: preset.horizon || "short", options: [["short", "Short-term (the next few weeks)"], ["long", "Long-term (a season or a year)"]] },
        { name: "metric", label: "How will I measure it?", value: preset.metric || "", options: measures },
        { name: "target", label: "Target number (if measured)", type: "number", value: preset.target === undefined || preset.target === null ? "" : preset.target },
        { name: "due_date", label: "Finish by (optional)", type: "date" },
      ],
    });
    if (!v) return;
    if (v.metric && v.target === null) { toast("Give the goal a target number, or choose “No number”."); return addGoal({ ...preset, ...v }); }
    await call("/api/goals", { method: "POST", body: { ...v, metric: v.metric || "", target: v.metric ? v.target : null, notes: preset.notes || "", steps: preset.steps || [] } });
    toast("Goal added");
  }

  function progressBlock(g) {
    if (!g.metric) return null;
    const tone = g.reached ? "good" : g.percent >= 50 ? "" : "warn";
    return h("div", { class: "stack-s" },
      meter(g.percent === null ? 0 : g.percent, tone || "warn"),
      h("div", { class: "row spread small" },
        h("span", { class: "muted" }, g.metric_label),
        h("span", {}, g.current === null ? "Not enough games yet" : `${fmt(g.baseline, g.unit)} → `, g.current === null ? null : h("b", {}, fmt(g.current, g.unit)), ` → target ${fmt(g.target, g.unit)}`)),
      g.reached && g.status === "active" ? h("div", { class: "alert good" }, "You reached the target! Mark the goal as done.") : null);
  }

  function stepsBlock(g) {
    const input = h("input", { class: "input", placeholder: "Add a small step…", maxlength: 160, "aria-label": `New step for ${g.title}`, style: "flex:1;min-width:160px" });
    const add = async () => { if (input.value.trim()) await call(`/api/goals/${g.id}/steps`, { method: "POST", body: { text: input.value } }); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
    return h("div", { class: "stack-s" },
      g.steps.map((s) => h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" },
        h("input", { type: "checkbox", checked: s.done, "aria-label": s.text, onchange: (e) => call(`/api/steps/${s.id}`, { method: "PATCH", body: { done: e.target.checked } }) }),
        h("span", { style: `flex:1;${s.done ? "text-decoration:line-through;color:var(--muted)" : ""}` }, s.text),
        h("button", { class: "row-del", style: "opacity:.5", "aria-label": `Remove step ${s.text}`, onclick: () => call(`/api/steps/${s.id}`, { method: "DELETE" }) }, icon("x")))),
      g.status === "active" ? h("div", { class: "row", style: "gap:6px" }, input, h("button", { class: "btn small", onclick: add }, "Add step")) : null);
  }

  function goalCard(g) {
    const active = g.status === "active";
    return h("div", { class: `card stack-s goal ${g.status}`, "data-goal": g.id },
      h("div", { class: "row spread", style: "align-items:flex-start;flex-wrap:nowrap" },
        h("div", {}, h("h3", { style: "margin:0" }, g.title),
          h("div", { class: "muted small" }, [g.due_date ? `Finish by ${fmtDate(g.due_date)}` : "", g.steps.length ? `${g.steps_done} of ${g.steps.length} steps done` : ""].filter(Boolean).join(" · "))),
        g.status === "done" ? h("span", { class: "pill good" }, "Done") : g.status === "dropped" ? h("span", { class: "pill gray" }, "Set aside") : null),
      g.notes ? h("p", { class: "muted small", style: "margin:0" }, g.notes) : null,
      progressBlock(g), stepsBlock(g),
      h("div", { class: "row", style: "gap:6px" },
        active ? h("button", { class: "btn small primary", onclick: () => call(`/api/goals/${g.id}`, { method: "PATCH", body: { status: "done" } }) }, icon("check"), "Mark as done") : h("button", { class: "btn small", onclick: () => call(`/api/goals/${g.id}`, { method: "PATCH", body: { status: "active" } }) }, "Work on it again"),
        active ? h("button", { class: "btn small", onclick: () => call(`/api/goals/${g.id}`, { method: "PATCH", body: { status: "dropped" } }) }, "Set aside") : null,
        h("button", { class: "btn small danger", "aria-label": `Delete goal ${g.title}`, onclick: () => { if (confirm(`Delete the goal “${g.title}”?`)) call(`/api/goals/${g.id}`, { method: "DELETE" }); } }, icon("trash"), "Delete")));
  }

  function column(title, blurb, horizon) {
    const goals = sheet.goals.filter((g) => g.horizon === horizon && g.status === "active");
    return h("div", { class: "stack", "data-horizon": horizon },
      h("div", {}, h("h2", { style: "margin:0" }, title), h("div", { class: "muted small" }, blurb)),
      goals.length ? goals.map(goalCard) : h("div", { class: "card flat muted small", style: "border-style:dashed" }, horizon === "short" ? "No short-term goal yet. One for the next few weeks keeps practice focused." : "No long-term goal yet. Add one for the season, like a rating to reach."));
  }

  // A suggestion, ready to add in one click.
  const suggestionCard = (sg) => h("div", { class: "card flat stack-s tight gl-sug" },
    h("div", { class: "row spread", style: "flex-wrap:nowrap;align-items:flex-start;gap:8px" }, h("b", {}, sg.title),
      h("span", { class: `pill nowrap ${sg.horizon === "short" ? "warn" : "brand"}` }, sg.horizon === "short" ? "Short-term" : "Long-term")),
    sg.notes ? h("div", { class: "muted small" }, sg.notes) : null,
    h("div", { style: "margin-top:auto" }, h("button", { class: "btn small", "data-suggestion": sg.title, onclick: () => addGoal(sg) }, icon("plus"), "Add this goal")));

  function paint() {
    const finished = sheet.goals.filter((g) => g.status !== "active");
    const active = sheet.goals.filter((g) => g.status === "active");
    // No goals yet: one clear way to start, with the suggestions right there.
    if (!active.length) {
      mount(root,
        h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My goals"), h("p", {}, "What I am working on, in the short term and the long term."))),
        h("section", { class: "card gl-start" },
          h("div", { class: "gl-start-ic", "aria-hidden": "true" }, "🎯"),
          h("div", { class: "stack-s", style: "flex:1;min-width:0" },
            h("h2", { style: "margin:0" }, "Set your first goal"),
            h("p", { class: "muted", style: "margin:0" }, "Small goals with a date work best: a short-term one for the next few weeks, and a long-term one for the season. Measured goals update themselves from your games."),
            h("div", { class: "row", style: "gap:8px" }, h("button", { class: "btn primary", id: "add-goal", onclick: () => addGoal() }, icon("plus"), "Write my own goal")))),
        sheet.suggested.length ? h("section", { class: "stack-s", id: "suggested" },
          h("h2", { style: "margin:8px 0 0" }, "Or pick one that fits you"),
          h("p", { class: "muted small", style: "margin:0" }, "Suggested from your games and habits."),
          h("div", { class: "grid g3" }, sheet.suggested.map(suggestionCard))) : null,
        finished.length ? h("details", { class: "card", open: finishedOpen.value, ontoggle: (e) => { finishedOpen.value = e.target.open; } },
          h("summary", { style: "cursor:pointer;font-weight:700" }, `Finished and set-aside goals (${finished.length})`),
          h("div", { class: "grid g2", style: "margin-top:12px" }, finished.map(goalCard))) : null);
      return;
    }
    const shown = allSuggestions ? sheet.suggested : sheet.suggested.slice(0, 3);
    mount(root,
      h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My goals"), h("p", {}, "What I am working on, in the short term and the long term.")),
        h("div", { class: "row", style: "gap:8px" },
          h("button", { class: "btn primary", id: "add-goal", onclick: () => addGoal() }, icon("plus"), "New goal"),
          h("button", { class: "btn small", onclick: () => window.print() }, "Print my goal sheet"))),
      h("div", { class: "grid g2" },
        column("Short-term goals", "The next few weeks. Small, and finished soon.", "short"),
        column("Long-term goals", "A season or a year. The big picture.", "long")),
      sheet.suggested.length ? h("div", { class: "card stack-s", id: "suggested" },
        h("div", { class: "row spread" }, h("h2", { style: "margin:0" }, "Suggested for me"),
          sheet.suggested.length > 3 ? h("button", { class: "linkish small", type: "button", onclick: () => { allSuggestions = !allSuggestions; paint(); } },
            allSuggestions ? "Show fewer" : `Show all ${sheet.suggested.length}`) : null),
        h("p", { class: "muted small", style: "margin:0" }, "Based on my games and habits. Add the ones that feel right."),
        h("div", { class: "grid g3" }, shown.map(suggestionCard))) : null,
      finished.length ? h("details", { class: "card", open: finishedOpen.value, ontoggle: (e) => { finishedOpen.value = e.target.open; } },
        h("summary", { style: "cursor:pointer;font-weight:700" }, `Finished and set-aside goals (${finished.length})`),
        h("div", { class: "grid g2", style: "margin-top:12px" }, finished.map(goalCard))) : null);
  }
  paint();
  return root;
}
