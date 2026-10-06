// The signed-in layout: sidebar (navigation + my games by month or in folders) and the main area.
import { h, icon, mount, pct, fmtDate, toast } from "./dom.js";
import { api } from "./api.js";
import { state, on, clearSession, store, monthKey, MONTHS, loadSections } from "./state.js";
import { parse, go } from "./router.js";
import { askText, askChoice, askFeedback } from "./dialogs.js";
import { openBoardOptions } from "./prefs.js";
import { hubFor } from "./hubs.js";

// [where it goes, icon, label, section (see hubs.js), extra class]. The pages inside Tournaments, Improve and Study are tabs.
const NAV = [
  ["/", "home", "Dashboard"],
  ["/tournaments", "trophy", "Tournaments", "tournaments", "feature", "USCF"],
  ["/add", "plus", "Add games"],
  ["/roadmap", "flame", "Improve", "improve"],
  ["/openings", "book", "Study", "study"],
  ["/calendar", "calendar", "Schedule", "schedule"],
  ["/community", "users", "Community"],
];

export function applyTheme(mode) {
  const dark = mode === "dark" || (mode !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function buildShell() {
  const openGroups = new Set();
  let query = "";
  let mode = store.get("cc-tree") === "folders" ? "folders" : "months";
  const main = h("main", { class: "main", id: "main", tabindex: "-1" });
  const tree = h("div", { class: "tree", id: "tree" });
  const nav = h("nav", { class: "nav", "aria-label": "Main" });
  const shell = h("div", { class: "app" });
  const closeMenu = () => shell.removeAttribute("data-menu");
  const currentGameId = () => { const { segments } = parse(); return segments[0] === "game" ? segments[1] : null; };

  function renderNav() {
    const { path } = parse();
    const here = hubFor(path);
    // Parents comes after Community; Admin (for admins only) is the very last item.
    const items = [...NAV, ["/parents", "shield", "Parents"], ...(state.user && state.user.is_admin ? [["/admin", "chart", "Admin"]] : [])];
    mount(nav, items.map(([href, ic, label, hub, extra, tag]) => {
      const active = hub ? here === hub : href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
      return h("a", { href: `#${href}`, class: extra || "", "aria-current": active ? "page" : "false", onclick: closeMenu }, icon(ic), label, tag ? h("span", { class: "nav-tag" }, tag) : null);
    }));
  }

  const gameLabel = (g) => {
    const who = g.opponent ? `vs ${g.opponent}` : `${g.white} – ${g.black}`;
    return g.round ? `#${g.round} · ${who}` : who;
  };

  async function deleteGame(g) {
    if (!confirm(`Delete this game (${gameLabel(g)}) and its analysis? This cannot be undone.`)) return;
    await api(`/api/games/${g.id}`, { method: "DELETE" });
    toast("Game deleted");
    await loadSections();
    if (String(g.id) === currentGameId()) go("/");
  }

  function gameRow(g, activeId) {
    return h("div", { class: "g-item" },
      h("a", { class: "g-row", href: `#/game/${g.id}`, title: [g.opening_name, fmtDate(g.date)].filter(Boolean).join(" · "), "aria-current": String(g.id) === activeId ? "page" : "false", onclick: closeMenu },
        g.status === "done" || g.status === "error" ? h("span", { class: `dot ${g.outcome || ""}`, title: g.outcome || "unfinished" })
          : g.status === "saved" ? h("span", { class: "dot", title: "Saved, not analyzed yet", style: "background:transparent;border:1.5px solid currentColor;opacity:.6" })
            : h("span", { class: "spin", title: "Analyzing…" }),
        h("span", { class: "t" }, gameLabel(g)),
        g.accuracy !== null && g.accuracy !== undefined ? h("span", { class: "badge", title: "Accuracy" }, pct(g.accuracy)) : null),
      h("button", { class: "row-del", title: "Delete this game", "aria-label": `Delete game ${gameLabel(g)}`, onclick: () => deleteGame(g) }, icon("trash")));
  }

  function toggleGroup(group, key) {
    const open = group.dataset.open !== "true";
    group.dataset.open = open ? "true" : "false";
    if (open) { openGroups.add(key); openGroups.delete(`closed:${key}`); } else { openGroups.delete(key); openGroups.add(`closed:${key}`); }
  }

  const matches = (g, extra = "", q) => !q || [extra, g.opponent, g.opening_name, g.white, g.black].join(" ").toLowerCase().includes(q);

  function monthsTree(activeId, q) {
    let sections = state.sections.map((s) => ({
      ...s,
      loose: s.loose.filter((g) => matches(g, "", q)),
      tournaments: s.tournaments.map((t) => ({ ...t, games: t.games.filter((g) => matches(g, t.event, q)) })).filter((t) => t.games.length),
    })).filter((s) => !q || s.loose.length || s.tournaments.length);
    const now = monthKey();
    if (!q && !sections.some((s) => s.key === now)) {
      const d = new Date();
      sections = [{ key: now, label: `${MONTHS[d.getMonth()]} ${d.getFullYear()}`, loose: [], tournaments: [], games: [], wins: 0, draws: 0, losses: 0, placeholder: true }, ...sections];
    }
    return sections.map((s) => {
      const hasActive = s.games.some((g) => String(g.id) === activeId);
      const open = q ? true : hasActive || openGroups.has(s.key) || (s.key === now && !openGroups.has(`closed:${s.key}`) && !activeId);
      const group = h("div", { class: "tour", "data-open": open ? "true" : "false" });
      group.append(
        h("button", { "aria-expanded": open ? "true" : "false", onclick: () => toggleGroup(group, s.key) }, icon("chevron"),
          h("span", { class: "gname" }, s.label), h("span", { class: "count" }, s.games.length ? `${s.wins}-${s.draws}-${s.losses}` : "")),
        h("div", { class: "games" },
          s.placeholder ? h("a", { class: "g-row g-add", href: "#/add", onclick: closeMenu }, icon("plus"), h("span", { class: "t" }, "Add this month's first game")) : null,
          s.loose.map((g) => gameRow(g, activeId)),
          s.tournaments.map((t) => h("div", { class: "sub" },
            h("div", { class: "sub-h" }, icon("trophy"), h("span", { class: "t" }, t.event), h("span", { class: "count" }, `${t.wins}-${t.draws}-${t.losses}`)),
            t.games.map((g) => gameRow(g, activeId))))));
      return group;
    });
  }

  async function newFolder() {
    const name = await askText({ title: "New folder", label: "Folder name", confirmLabel: "Create folder" });
    if (!name) return;
    try { await api("/api/folders", { method: "POST", body: { name } }); await loadSections(); toast(`Folder “${name}” created`); }
    catch (e) { toast(e.message); }
  }
  async function renameFolder(f) {
    const name = await askText({ title: "Rename folder", label: "Folder name", value: f.name });
    if (!name || name === f.name) return;
    try { await api(`/api/folders/${f.id}`, { method: "PATCH", body: { name } }); await loadSections(); } catch (e) { toast(e.message); }
  }
  async function deleteFolder(f) {
    const n = f.games.length;
    const choice = await askChoice({
      title: `Delete “${f.name}”?`,
      message: n ? `This folder has ${n} game${n === 1 ? "" : "s"}. Keep them, or delete them too?` : "The folder is empty.",
      options: [{ value: "keep", label: n ? "Delete the folder, keep the games" : "Delete the folder" },
        ...(n ? [{ value: "delete", label: `Delete the folder and its ${n} game${n === 1 ? "" : "s"}`, tone: "danger" }] : [])],
    });
    if (!choice) return;
    await api(`/api/folders/${f.id}?games=${choice}`, { method: "DELETE" });
    toast(choice === "delete" ? "Folder and games deleted" : "Folder deleted");
    await loadSections();
  }

  function foldersTree(activeId, q) {
    const out = [h("button", { class: "new-folder", onclick: newFolder }, icon("plus"), "New folder")];
    const folders = state.folders.folders.map((f) => ({ ...f, shown: f.games.filter((g) => matches(g, f.name, q)) })).filter((f) => !q || f.shown.length);
    for (const f of folders) {
      const key = `f${f.id}`;
      const open = q ? true : f.shown.some((g) => String(g.id) === activeId) || openGroups.has(key);
      const group = h("div", { class: "tour", "data-open": open ? "true" : "false" });
      group.append(
        h("div", { class: "folder-h" },
          h("button", { "aria-expanded": open ? "true" : "false", onclick: () => toggleGroup(group, key) }, icon("chevron"), icon("folder"), h("span", { class: "gname" }, f.name), h("span", { class: "count" }, f.games.length)),
          h("button", { class: "row-del", title: "Rename folder", "aria-label": `Rename folder ${f.name}`, onclick: () => renameFolder(f) }, icon("edit")),
          h("button", { class: "row-del", title: "Delete folder", "aria-label": `Delete folder ${f.name}`, onclick: () => deleteFolder(f) }, icon("trash"))),
        h("div", { class: "games" }, f.shown.length ? f.shown.map((g) => gameRow(g, activeId)) : h("div", { class: "faint small", style: "padding:6px 10px" }, "Empty. Open a game and choose this folder to add it.")));
      out.push(group);
    }
    const loose = state.folders.unfiled.filter((g) => matches(g, "", q));
    if (loose.length) {
      const group = h("div", { class: "tour", "data-open": q || openGroups.has("unfiled") || loose.some((g) => String(g.id) === activeId) ? "true" : "false" });
      group.append(h("button", { onclick: () => toggleGroup(group, "unfiled") }, icon("chevron"), h("span", { class: "gname" }, "Not in a folder"), h("span", { class: "count" }, loose.length)),
        h("div", { class: "games" }, loose.map((g) => gameRow(g, activeId))));
      out.push(group);
    }
    if (!state.folders.folders.length) out.push(h("div", { class: "faint small", style: "padding:10px 14px" }, "Folders let you keep games together, for example “My best attacks” or “Games vs Sam”. Create one, then move games into it from the game page."));
    return out;
  }

  function renderTree() {
    const activeId = currentGameId();
    const q = query.trim().toLowerCase();
    const nodes = mode === "months" ? monthsTree(activeId, q) : foldersTree(activeId, q);
    if (mode === "months" && !nodes.length) { mount(tree, h("div", { class: "faint small", style: "padding:14px" }, "No games match that search.")); return; }
    mount(tree, nodes);
  }

  const modeTabs = h("div", { class: "side-tabs", role: "tablist" });
  function renderModeTabs() {
    mount(modeTabs, [["months", "By month"], ["folders", "Folders"]].map(([k, t]) =>
      h("button", { role: "tab", "aria-selected": mode === k ? "true" : "false", onclick: () => { mode = k; store.set("cc-tree", k); renderModeTabs(); renderTree(); } }, t)));
  }

  const search = h("div", { class: "search" }, h("input", { type: "search", placeholder: "Search my games…", "aria-label": "Search games", oninput: (e) => { query = e.target.value; renderTree(); } }));
  const initials = (state.user.display_name || "?").trim()[0].toUpperCase();
  const themeBtn = h("button", { class: "icon-btn", "aria-label": "Toggle dark mode", title: "Light / dark", onclick: () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    store.set("cc-theme", next); applyTheme(next);
  } }, icon("moon"));
  const feedbackBtn = h("button", { class: "icon-btn", "aria-label": "Send feedback", title: "Send feedback", onclick: async () => {
    const answer = await askFeedback();
    if (!answer) return;
    try {
      await api("/api/feedback", { method: "POST", body: { ...answer, page: location.hash.slice(0, 200) } });
      toast("Thanks! Your feedback was sent.");
    } catch (err) { toast(err.message); }
  } }, icon("message"));
  const boardBtn = h("button", { class: "icon-btn", "aria-label": "Board options", title: "Board options", onclick: openBoardOptions }, icon("gear"));
  const viewing = state.user.viewed_by
    ? h("div", { class: "alert warn", role: "status", style: "display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:14px;background:#fff4d6;color:#6b4e00" },
      h("span", {}, icon("shield"), ` You're viewing as `, h("b", {}, state.user.display_name), ` (${state.user.email}). Read-only: nothing you do here changes their account.`),
      h("button", { class: "btn small", onclick: async () => { await api("/api/auth/stop-viewing", { method: "POST" }); location.hash = "#/admin"; location.reload(); } }, "Stop viewing"))
    : null;
  const logout = h("button", { class: "icon-btn", "aria-label": "Sign out", title: "Sign out", onclick: async () => {
    if (!confirm("Sign out of Chess Varsity?")) return;      // it sits next to the theme switch: no accidental sign-outs
    await api("/api/auth/logout", { method: "POST" });
    clearSession(); location.hash = "#/login"; location.reload();
  } }, icon("logout"));
  const rating = state.player && state.player.rating ? h("span", { class: "rate" }, `${state.player.rating_system} rating ${state.player.rating}`) : null;

  const side = h("aside", { class: "side" },
    h("a", { class: "brand", href: "#/" }, h("span", { class: "logo" }, h("img", { src: "/static/logo.svg", alt: "" })), h("span", {}, "Chess Varsity", h("span", { class: "beta", title: "Chess Varsity is in beta: still improving, and your feedback helps" }, "BETA"), h("small", {}, "Personal chess coach"))),
    nav,
    h("div", { class: "games-h" }, "My games", h("a", { href: "#/add" }, "+ Add")),
    modeTabs, search, tree,
    h("div", { class: "side-foot" }, h("span", { class: "av" }, initials),
      h("a", { class: "name", href: "#/profile", title: "My profile" }, state.user.display_name, rating),
      h("div", { class: "side-actions" }, feedbackBtn, boardBtn, themeBtn, logout)));

  shell.append(side, h("div", {}, h("button", { class: "btn small menu-btn", "aria-label": "Open menu", onclick: () => { shell.dataset.menu = shell.dataset.menu === "open" ? "closed" : "open"; } }, icon("menu"), "Menu"), viewing, main));

  renderNav(); renderModeTabs(); renderTree();
  on("games-changed", renderTree);
  on("route", () => { renderNav(); renderTree(); });
  return { el: shell, main };
}
