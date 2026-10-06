// Ties the roadmap to the pages where its topics are practised: a "done" checkbox for a topic, and a
// small "On your roadmap" card for the Openings and Attack academy pages that links back to the roadmap.
import { h, mount, toast } from "./dom.js";
import { api } from "./api.js";
import { currentPlayer } from "./state.js";

export async function setTopicDone(topic, done) {
  const player = currentPlayer();
  await api(`/api/players/${player.id}/roadmap/topics/${topic}`, { method: "PUT", body: { status: done ? "mastered" : "not_started" } });
}

// A checkbox for one roadmap topic. `after` runs once the change is saved.
export function topicCheck(t, after) {
  const box = h("input", { type: "checkbox", checked: t.status === "mastered", "aria-label": `Completed: ${t.title}`,
    onchange: async () => {
      try { await setTopicDone(t.key, box.checked); toast(box.checked ? `“${t.title}” completed.` : `“${t.title}” marked not done.`); if (after) await after(); }
      catch (err) { box.checked = !box.checked; toast(err.message); }
    } });
  return box;
}

// The roadmap topics at the player's level that are practised on this page (`prefix` such as "#/academy/attack").
export function roadmapStrip(prefix) {
  const card = h("div", { class: "card stack-s", style: "border-left:4px solid var(--brass)" });
  const player = currentPlayer();
  if (!player) return null;
  async function load() {
    let d;
    try { d = await api(`/api/players/${player.id}/roadmap`); } catch { card.remove(); return; }
    const topics = d.categories.flatMap((c) => [...c.now, ...c.review])
      .filter((t) => t.practice && t.practice.href.startsWith(prefix));
    if (!topics.length) { card.remove(); return; }
    topics.sort((a, b) => (a.status === "mastered") - (b.status === "mastered") || b.start - a.start);
    const done = topics.filter((t) => t.status === "mastered").length;
    mount(card,
      h("div", { class: "row", style: "justify-content:space-between;gap:8px" },
        h("b", {}, `On your roadmap · ${d.bands[d.band].label}`),
        h("span", { class: "small muted" }, `${done} of ${topics.length} done · `, h("a", { href: "#/roadmap" }, "Open my roadmap →"))),
      h("div", { class: "small muted" }, "Tick a milestone when you've got it. It's saved to your roadmap too."),
      h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:4px 16px" },
        topics.map((t) => h("label", { class: "row small", style: "gap:8px;flex-wrap:nowrap;cursor:pointer", title: t.goal },
          topicCheck(t, load), h("span", { style: t.status === "mastered" ? "text-decoration:line-through;color:var(--muted)" : "" }, t.title)))));
  }
  load();
  return card;
}
