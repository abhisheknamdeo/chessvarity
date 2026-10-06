import { h, icon, mount, pct, level, meter } from "../dom.js";
import { api } from "../api.js";
import { roadmapStrip } from "../roadmaplinks.js";
import { currentPlayer, store } from "../state.js";
import { drawBoard, arrowFrom } from "../board.js";
import { go } from "../router.js";
import { empty } from "../components.js";
import { boardTools } from "../explorer.js";

const TABS = [["repertoire", "Repertoire ideas"], ["library", "Library"], ["mine", "My openings"]];

export async function openingsView({ tab }, query) {
  const current = tab || "repertoire";
  document.title = "Openings · Chess Varsity";
  const tabs = h("div", { class: "tabs", role: "tablist" }, TABS.map(([k, t]) => h("a", { role: "tab", href: `#/openings/${k}`, "aria-selected": current === k ? "true" : "false" }, t)));
  const body = current === "library" ? await libraryPane(query) : current === "repertoire" ? await repertoirePane() : await minePane();
  return h("div", { class: "stack" }, h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Openings"), h("p", {}, "Your results by opening, a library of named variations, and openings that suit an attacking player.")), tabs), roadmapStrip("#/openings"), body);
}

async function minePane() {
  const player = currentPlayer();
  const r = await api(`/api/players/${player.id}/openings`);
  if (!r.families.length) return empty("wB", "No openings yet", "Openings are recognized automatically from your games.", h("a", { class: "btn primary", href: "#/add" }, "Add games"));
  return h("div", { class: "stack" },
    r.advice.length ? h("div", { class: "card" }, h("h3", {}, "Worth a look"), h("ul", { class: "dots" }, r.advice.map((a) => h("li", {}, a)))) : null,
    h("div", { class: "card", style: "overflow:auto" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Opening", "Side", "Games", "W-D-L", "Score", "Left the book", "Accuracy"].map((t) => h("th", {}, t)))),
      h("tbody", {}, r.families.map((o) => h("tr", { class: "click", onclick: () => go(`/openings/library?q=${encodeURIComponent(o.family)}`) },
        h("td", {}, h("b", {}, o.family), o.eco ? h("span", { class: "muted small" }, ` ${o.eco}`) : null),
        h("td", {}, o.color === "white" ? "White" : "Black"), h("td", {}, o.games), h("td", {}, `${o.wins}-${o.draws}-${o.losses}`),
        h("td", { style: "min-width:120px" }, h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, meter(o.score, level(o.score)), h("span", { class: "small" }, pct(o.score)))),
        h("td", { class: "muted" }, `move ${Math.ceil(o.book_plies / 2) + 1}`), h("td", { class: "muted" }, pct(o.accuracy))))))),
    h("p", { class: "muted small" }, "Click an opening to look it up in the library."));
}

async function libraryPane(query) {
  const boardEl = h("div", { class: "board", style: "max-width:420px" });
  const crumbs = h("div", { class: "row small", style: "gap:6px" });
  const next = h("div", { class: "stack-s" });
  const name = h("div", {});
  const results = h("div", { class: "stack-s" });
  let sans = [];
  let currentFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

  async function show(moves) {
    let data;
    try { data = await api(`/api/library/openings/browse?moves=${encodeURIComponent(moves.join(","))}`); }
    catch (e) { mount(next, h("div", { class: "alert bad" }, e.message)); return; }
    sans = data.sans;
    currentFen = data.fen;
    drawBoard(boardEl, data.fen, { orient: "white" });
    mount(crumbs, h("button", { class: "chip", onclick: () => show([]) }, "Start"),
      sans.map((s, i) => h("button", { class: "chip", onclick: () => show(sans.slice(0, i + 1)) }, `${Math.floor(i / 2) + 1}${i % 2 ? "…" : "."} ${s}`)));
    const known = data.opening;
    mount(name, known ? h("div", {}, h("span", { class: "pill brand" }, known.eco), h("h3", { style: "margin-top:6px" }, known.name)) : h("div", { class: "muted" }, data.path.length ? `Last named line: ${data.path[data.path.length - 1].name}` : "Choose a first move."));
    mount(next, data.next.length ? [h("div", { class: "small muted" }, "Next moves (most variations first)"), data.next.slice(0, 14).map((o) =>
      h("button", { class: "btn", style: "justify-content:space-between", onclick: () => show([...sans, o.san]) },
        h("span", {}, h("b", { class: "mono" }, o.san), o.opening ? h("span", { class: "muted small" }, `  ${o.opening.name}`) : null),
        h("span", { class: "muted small" }, `${o.variations} line${o.variations === 1 ? "" : "s"}`)))] : h("div", { class: "muted" }, "End of the named lines. You are out of the book here."));
  }

  const search = h("input", { class: "input", type: "search", placeholder: "Search openings (e.g. Sicilian, Evans, King's Indian)…", "aria-label": "Search openings", value: (query && query.q) || "" });
  async function doSearch() {
    const q = search.value.trim();
    if (q.length < 2) { mount(results); return; }
    const hits = await api(`/api/library/openings/search?q=${encodeURIComponent(q)}`);
    mount(results, hits.length ? hits.map((o) => h("button", { class: "btn", style: "justify-content:flex-start", onclick: () => { show(o.sans); window.scrollTo({ top: 0, behavior: "smooth" }); } }, h("span", { class: "pill gray" }, o.eco), h("span", {}, o.name))) : h("div", { class: "muted" }, "No matching openings."));
  }
  search.addEventListener("input", doSearch);
  const fams = await api("/api/library/openings/families");

  const startMoves = query && query.moves ? query.moves.split(",") : [];
  await show(startMoves);
  if (query && query.q) doSearch();

  return h("div", { class: "split-lib" },
    h("div", { class: "stack-s" }, boardEl, crumbs, boardTools(() => currentFen)),
    h("div", { class: "stack" },
      h("div", { class: "card stack-s" }, name, next),
      h("div", { class: "card stack-s" }, h("h3", {}, "Find an opening"), search, results,
        h("div", { class: "small muted" }, "Popular families:"),
        h("div", { class: "row", style: "gap:6px" }, fams.slice(0, 14).map((f) => h("button", { class: "chip", onclick: () => show(f.sans) }, `${f.name} (${f.lines})`))))));
}

async function repertoirePane() {
  const list = await api("/api/library/repertoire");
  let side = store.get("cc-rep-side") === "black" ? "black" : "white";
  const grid = h("div", { class: "grid g2" });

  const card = (r) => {
    const board = h("div", { class: "board", style: "width:132px;flex:none" });
    drawBoard(board, r.fen, { orient: r.side });
    const extra = r.plans.length + r.traps.length;
    return h("div", { class: "card stack-s", style: "padding:14px" },
      h("div", { class: "row", style: "align-items:flex-start;flex-wrap:nowrap;gap:14px" }, board,
        h("div", { class: "stack-s", style: "min-width:0;flex:1" },
          h("div", { class: "row", style: "gap:6px" }, h("h3", { style: "margin:0;font-size:1.02rem" }, r.name),
            h("span", { class: `pill ${r.style === "attacking" ? "warn" : "gray"}` }, r.style)),
          h("div", { class: "mono small muted" }, r.moves.map((m, i) => (i % 2 === 0 ? `${i / 2 + 1}. ` : "") + m).join(" ")),
          h("p", { class: "small", style: "margin:0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden", title: r.idea }, r.idea),
          h("a", { class: "btn small", style: "justify-self:start", href: `#/openings/library?moves=${encodeURIComponent(r.moves.join(","))}` }, icon("arrow"), "Explore"))),
      extra ? h("details", { class: "small" },
        h("summary", { style: "cursor:pointer;color:var(--brand);font-weight:600" }, `Plans${r.traps.length ? " and traps" : ""} (${extra})`),
        h("p", { style: "margin:8px 0 6px" }, r.idea),
        h("ul", { class: "dots", style: "margin:0 0 6px" }, r.plans.map((pl) => h("li", {}, pl))),
        r.traps.map((t) => h("div", { class: "callout warn small" }, h("b", {}, `Trap: ${t.name}. `), t.note))) : null);
  };

  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "Colour" });
  const render = () => {
    mount(grid, list.filter((r) => r.side === side).map(card));
    mount(tabs, [["white", "As White"], ["black", "As Black"]].map(([k, t]) => h("button", { role: "tab", "aria-selected": side === k ? "true" : "false",
      onclick: () => { side = k; store.set("cc-rep-side", k); render(); } }, `${t} (${list.filter((r) => r.side === k).length})`)));
  };
  render();
  return h("div", { class: "stack" },
    h("div", { class: "row", style: "justify-content:space-between;gap:12px;flex-wrap:wrap" },
      h("p", { class: "muted", style: "margin:0;max-width:62ch" }, "Openings for an attacking player: simple ideas, open lines and quick development. Pick one for White and one for each answer as Black, then play it for a few months."),
      tabs),
    grid);
}
