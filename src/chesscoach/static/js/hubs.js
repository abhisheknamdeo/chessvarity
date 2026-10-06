// The sidebar has a handful of sections; each groups related pages as tabs along the top of the page.
import { h } from "./dom.js";

export const HUBS = {
  tournaments: {
    label: "Tournaments", home: "/tournaments",
    tabs: [["/tournaments", "Tournaments & USCF"], ["/stats", "My results"], ["/prep", "Tournament plan"]],
  },
  schedule: {
    label: "Schedule", home: "/calendar",
    tabs: [["/calendar", "Calendar"], ["/training", "Training"], ["/planner", "Planner"]],
  },
  improve: {
    label: "Improve", home: "/roadmap",
    tabs: [["/roadmap", "My roadmap"], ["/patterns", "Mistake patterns"], ["/wins", "Wins I missed"], ["/workbook", "My workbook"], ["/goals", "My goals"]],
  },
  study: {
    label: "Study", home: "/openings",
    tabs: [["/openings", "Openings"], ["/models", "Model games"], ["/academy", "Attack academy"], ["/think", "Think like a Grandmaster"], ["/play", "Play the computer"]],
  },
};

const inside = (path, base) => path === base || path.startsWith(`${base}/`);

/** The section a path belongs to, or null (the dashboard, a game review, and so on). */
export function hubFor(path) {
  const found = Object.entries(HUBS).find(([, hub]) => hub.tabs.some(([base]) => inside(path, base)));
  return found ? found[0] : null;
}

/** The tab bar shown above every page of a section. */
export function hubTabs(key, path) {
  const hub = HUBS[key];
  return h("nav", { class: "hub-tabs", "aria-label": hub.label },
    hub.tabs.map(([base, text]) => h("a", { href: `#${base}`, "aria-current": inside(path, base) ? "page" : "false" }, text)));
}
