import { h, mount } from "./dom.js";
import { setUnauthorizedHandler } from "./api.js";
import { state, loadMe, loadSections, emit, clearSession, store } from "./state.js";
import { route, setNotFound, setOnChange, start, parse } from "./router.js";
import { buildShell, applyTheme } from "./shell.js";
import { renderAuth } from "./views/auth.js";
import { renderPublicGame } from "./views/publicgame.js";
import { dashboardView } from "./views/dashboard.js";
import { addView } from "./views/add.js";
import { gameView } from "./views/game.js";
import { patternsView } from "./views/patterns.js";
import { winsView } from "./views/wins.js";
import { workbookView } from "./views/workbook.js";
import { openingsView } from "./views/openings.js";
import { academyView } from "./views/academy.js";
import { modelsView } from "./views/models.js";
import { profileView } from "./views/profile.js";
import { playView } from "./views/play.js";
import { tournamentsView } from "./views/tournaments.js";
import { statsView } from "./views/stats.js";
import { goalsView } from "./views/goals.js";
import { prepView } from "./views/prep.js";
import { thinkView } from "./views/think.js";
import { plannerView } from "./views/planner.js";
import { calendarView } from "./views/calendar.js";
import { trainingView } from "./views/training.js";
import { adminView } from "./views/admin.js";
import { contactView } from "./views/contact.js";
import { parentsView } from "./views/parents.js";
import { communityView } from "./views/community.js";
import { roadmapView } from "./views/roadmap.js";
import { applyPrefs } from "./prefs.js";
import { hubFor, hubTabs } from "./hubs.js";

applyTheme(store.get("cc-theme") || "auto");
applyPrefs();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!store.get("cc-theme")) applyTheme("auto"); });

setUnauthorizedHandler(() => {
  if (state.user) { clearSession(); location.hash = "#/login"; location.reload(); }
});

const root = document.getElementById("root");

async function boot() {
  window.addEventListener("error", (e) => console.error(e.message));
  // A game shared by link (#/g/<token>) opens for anyone, signed in or not, without the app around it.
  if (parse().path.startsWith("/g/")) {
    await loadMe();
    await renderPublicGame(parse().segments[1] || "");
    window.addEventListener("hashchange", () => location.reload());
    return;
  }
  // Links from emails open these pages whether or not someone is signed in on this browser.
  const fromEmail = ["/verify", "/reset"];
  if (fromEmail.includes(parse().path)) {
    const { path, query } = parse();
    renderAuth(path.slice(1), query);
    window.addEventListener("hashchange", () => location.reload());
    return;
  }
  const user = await loadMe();
  if (!user) {
    const pages = ["/login", "/register", "/forgot", "/contact"];
    const showAuth = () => {
      const { path, query } = parse();
      if (fromEmail.includes(path)) { location.reload(); return; }
      renderAuth(pages.includes(path) ? path.slice(1) : "login", query);
    };
    if (!pages.includes(parse().path)) location.hash = "#/login";
    showAuth();
    window.addEventListener("hashchange", showAuth);
    return;
  }
  await loadSections();
  // An email link opened in this tab while signed in: load its page afresh.
  window.addEventListener("hashchange", () => { if (fromEmail.includes(parse().path)) location.reload(); });

  const { el, main } = buildShell();
  mount(root, el);

  let cleanup = null;
  let token = 0;
  // The page banner: a gold section label above the title, and the section's chess piece on the right.
  const SECTIONS = {
    tournaments: ["Tournaments", "♜"], schedule: ["Schedule", "♝"], improve: ["Improve", "♞"], study: ["Study", "♛"],
    "/community": ["Community", "♟"], "/profile": ["My account", "♚"], "/admin": ["Admin", "♚"], "/contact": ["Contact us", "♟"], "/add": ["Add a game", "♙"],
  };
  function decorateHeaders() {
    const path = parse().path, hub = hubFor(path);
    for (const head of main.querySelectorAll(".page-h:not([data-decorated])")) decorate(head, hub, path);
  }
  // Pages that redraw themselves (goals, the roadmap…) get the same banner each time.
  new MutationObserver(decorateHeaders).observe(main, { childList: true, subtree: true });
  function decorate(head, hub, path) {
    const [label, piece] = SECTIONS[hub] || SECTIONS["/" + path.split("/")[1]] || ["Chess Varsity", "♞"];
    head.dataset.decorated = "1";
    const text = head.firstElementChild;
    if (text && !text.querySelector(".ph-kicker")) text.prepend(h("div", { class: "ph-kicker" }, label));
    head.classList.toggle("has-actions", head.children.length > 1);
    head.append(h("span", { class: "ph-art", "aria-hidden": "true" }, piece));
  }

  const wrap = (view) => async (params, query) => {
    const mine = ++token;
    if (cleanup) { cleanup(); cleanup = null; }
    mount(main, h("div", { class: "muted", style: "padding:40px;text-align:center" }, "Loading…"));
    try {
      const node = await view(params, query);
      if (mine !== token) { if (node && node.cleanup) node.cleanup(); return; }
      cleanup = node && node.cleanup ? node.cleanup : null;
      const path = parse().path, hub = hubFor(path);
      mount(main, hub ? hubTabs(hub, path) : null, node);
      main.focus({ preventScroll: true });
      if (!location.hash.match(/^#\/game\//)) window.scrollTo({ top: 0 });
    } catch (err) {
      if (mine !== token) return;
      mount(main, h("div", { class: "card", style: "max-width:560px;margin:40px auto" }, h("h2", {}, "Something went wrong"), h("p", { class: "muted" }, err.message), h("a", { class: "btn", href: "#/" }, "Back to my dashboard")));
    }
  };

  route("/", wrap(dashboardView));
  route("/add", wrap(addView));
  route("/game/:id/:ply?", wrap(gameView));
  route("/patterns", wrap(patternsView));
  route("/wins", wrap(winsView));
  route("/workbook/:skill?", wrap(workbookView));
  route("/openings/:tab?", wrap(openingsView));
  route("/academy/:theme?", wrap(academyView));
  route("/models/:id?", wrap(modelsView));
  route("/profile", wrap(profileView));
  route("/play", wrap(playView));
  route("/tournaments", wrap(tournamentsView));
  route("/planner", wrap(plannerView));
  route("/calendar", wrap(calendarView));
  route("/training", wrap(trainingView));
  route("/stats", wrap(statsView));
  route("/goals", wrap(goalsView));
  route("/prep", wrap(prepView));
  route("/think", wrap(thinkView));
  route("/contact", wrap(contactView));
  route("/community/:id?", wrap(communityView));
  route("/parents/:tab?", wrap(parentsView));
  route("/roadmap", wrap(roadmapView));
  if (user.is_admin) route("/admin", wrap(adminView));
  setNotFound(wrap(() => h("div", { class: "card empty" }, h("h3", {}, "Page not found"), h("a", { class: "btn", href: "#/" }, "Go home"))));
  setOnChange(() => emit("route"));
  start();
}

boot();
