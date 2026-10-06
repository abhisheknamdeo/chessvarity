import { h, icon, mount, meter, toast } from "../dom.js";
import { api } from "../api.js";
import { drawBoard } from "../board.js";
import { boardTools, explorer } from "../explorer.js";
import { go } from "../router.js";

const THEME_LABEL = { sacrifice: "Sacrifice", fork: "Fork", pin: "Pin", discovered: "Discovered attack", check: "Checks", "open-file": "Open file", mate: "Checkmate", castle: "Castling", attack: "Attack", traps: "Trap" };
const RESULT = { "1-0": "White wins", "0-1": "Black wins", "1/2-1/2": "Draw" };
const PAGE = 24;

function themeChips(themes) {
  return (themes || []).slice(0, 4).map((t) => h("span", { class: "pill gray" }, THEME_LABEL[t] || t));
}

const STATUSES = [["", "Any"], ["new", "Not started"], ["in_progress", "In progress"], ["completed", "Completed"]];

/** "Completed" once every move has been stepped through; "In progress" after some of them. */
function reviewPill(review) {
  if (!review || review.status === "new") return null;
  return review.status === "completed"
    ? h("span", { class: "pill good", "data-review": "completed" }, "✓ Completed")
    : h("span", { class: "pill warn progress", "data-review": "in_progress", title: `${review.seen} of ${review.total} moves reviewed` }, `In progress · ${review.percent}%`);
}

export async function modelsView({ id }, query) {
  document.title = "Model games · Chess Varsity";
  if (id) return detailView(id);
  const bands = await api("/api/library/model-games/bands");
  const total = bands.reduce((n, b) => n + b.count, 0);
  const st = { band: (query && query.band) || "", q: "", status: (query && query.status) || "", offset: 0 };
  const statusBar = h("div", { class: "filters" });
  const grid = h("div", { class: "grid g2" });
  const more = h("div", { class: "row", style: "justify-content:center;margin-top:8px" });
  const count = h("div", { class: "muted small" });
  const chips = h("div", { class: "row", style: "gap:8px" });

  function renderChips() {
    mount(chips,
      h("button", { class: "chip", "aria-pressed": st.band === "" ? "true" : "false", onclick: () => { st.band = ""; reload(); } }, `All (${total})`),
      bands.map((b) => h("button", { class: "chip", "aria-pressed": st.band === b.key ? "true" : "false", onclick: () => { st.band = b.key; reload(); } }, `${b.label} · ${b.count}`)));
  }

  let summary = { completed: 0, in_progress: 0 };
  function renderStatus() {
    mount(statusBar, h("span", { class: "muted small" }, "Show:"),
      STATUSES.map(([k, t]) => h("button", { class: "chip", "data-status": k, "aria-pressed": st.status === k ? "true" : "false", onclick: () => { st.status = k; reload(); } },
        k === "completed" ? `${t} · ${summary.completed}` : k === "in_progress" ? `${t} · ${summary.in_progress}` : t)));
  }

  async function load(append) {
    const params = new URLSearchParams({ limit: PAGE, offset: st.offset });
    if (st.band) params.set("band", st.band);
    if (st.q) params.set("q", st.q);
    if (st.status) params.set("status", st.status);
    const r = await api(`/api/library/model-games?${params}`);
    summary = r.summary; renderStatus();
    const cards = r.games.map((g) => h("a", { class: "card theme-card model-card", href: `#/models/${g.id}`, "data-game": g.id, style: "text-decoration:none;color:inherit" },
      h("div", { class: "row spread" },
        h("div", { class: "row", style: "gap:6px" }, h("span", { class: "pill brand" }, g.rating ? `${g.rating} rated` : "Historic"), reviewPill(g.review)),
        h("span", { class: "muted small" }, `${RESULT[g.result] || g.result} · ${Math.ceil(g.plies / 2)} moves`)),
      h("h3", { style: "margin-top:8px" }, g.title),
      h("div", { class: "small muted" }, g.rating ? "An online game between two players of similar strength" : `${g.white} vs ${g.black}, ${g.year}`),
      h("p", { style: "margin:8px 0" }, g.summary),
      h("div", { class: "row", style: "gap:6px" }, themeChips(g.themes)),
      g.review && g.review.status === "in_progress" ? h("div", { style: "margin-top:10px" }, meter(g.review.percent, "warn")) : null));
    if (append) grid.append(...cards); else mount(grid, cards.length ? cards : h("div", { class: "card muted" }, "No games match. Try another rating band, status or search."));
    st.offset += r.games.length;
    count.textContent = `${Math.min(st.offset, r.total)} of ${r.total} games`;
    mount(more, st.offset < r.total ? h("button", { class: "btn", onclick: () => load(true) }, `Show ${Math.min(PAGE, r.total - st.offset)} more`) : null);
  }
  function reload() { st.offset = 0; renderChips(); renderStatus(); load(false); }

  let timer;
  const search = h("input", { class: "input", type: "search", placeholder: "Search by opening or theme (Sicilian, sacrifice, fork…)", "aria-label": "Search model games", oninput: (e) => { clearTimeout(timer); timer = setTimeout(() => { st.q = e.target.value; reload(); }, 250); } });

  reload();
  return h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Model games"),
      h("p", {}, "Attacking games to learn from, grouped by playing strength. Start with your own rating band, then move up. Step through every move to complete a game."))),
    h("div", { class: "card stack-s" }, search, chips, statusBar, count),
    grid, more,
    h("p", { class: "muted small" }, "Rated games come from the Lichess open database (public domain); player names are never shown."));
}


async function detailView(id) {
  const [g, review] = await Promise.all([
    api(`/api/library/model-games/${id}`),
    api(`/api/library/model-games/${id}/review`).catch(() => ({ plies: [] })),
  ]);
  const total = g.moves.length;
  const seen = new Set(review.plies);          // moves stepped through so far (saved on the server)
  const unsent = new Set();
  let timer = null;
  let ply = 0;
  const board = h("div", { class: "board big" });
  const label = h("div", { class: "muted small", style: "text-align:center;margin-top:6px;min-height:1.4em" });
  const nowNote = h("div", { class: "callout commentary hidden" });
  const keyNote = h("div", { class: "callout warn hidden" });
  const list = h("div", { class: "comlist" });
  const leftBox = h("div", { class: "left" });
  const progressBox = h("div", { class: "row", style: "gap:10px;flex-wrap:nowrap", id: "review-progress" });
  const fenAt = (p) => (p === 0 ? g.start_fen : g.moves[p - 1].fen);
  const nameOf = (p) => (p === 0 ? "Starting position" : `${Math.ceil(p / 2)}${p % 2 ? "." : "…"} ${g.moves[p - 1].san}`);
  const commentary = g.commentary || [];

  async function flush() {
    clearTimeout(timer); timer = null;
    if (!unsent.size) return;
    const plies = [...unsent]; unsent.clear();
    try { await api(`/api/library/model-games/${id}/review`, { method: "POST", body: { plies } }); }
    catch (_) { plies.forEach((p) => unsent.add(p)); }
  }

  function visit(p) {
    if (p < 1 || seen.has(p)) return;
    seen.add(p); unsent.add(p);
    clearTimeout(timer); timer = setTimeout(flush, 600);
    if (seen.size === total) { toast("Game completed! You stepped through every move."); flush(); }
  }

  function paintProgress() {
    const percent = total ? Math.round((100 * seen.size) / total) : 0;
    const status = seen.size >= total ? "completed" : seen.size ? "in_progress" : "new";
    mount(progressBox,
      status === "completed" ? h("span", { class: "pill good", "data-review": "completed" }, "✓ Completed")
        : status === "in_progress" ? h("span", { class: "pill warn progress", "data-review": "in_progress" }, `In progress · ${percent}%`)
          : h("span", { class: "pill gray", "data-review": "new" }, "Not started"),
      h("span", { class: "muted small" }, status === "new" ? "Step through the moves to review this game." : `${seen.size} of ${total} moves reviewed`),
      seen.size ? h("button", { class: "btn small", title: "Forget my progress on this game", onclick: async () => {
        seen.clear(); unsent.clear(); clearTimeout(timer);
        try { await api(`/api/library/model-games/${id}/review`, { method: "DELETE" }); } catch (e) { toast(e.message); }
        render();
      } }, "Start over") : null);
  }

  function setPly(p) { ply = Math.max(0, Math.min(total, p)); render(); }

  function render() {
    visit(ply);
    drawBoard(board, fenAt(ply), { lastMove: ply ? g.moves[ply - 1].uci : null });
    label.textContent = `${nameOf(ply)}  ·  ${ply}/${total}`;
    const c = commentary[ply - 1];
    mount(nowNote, c ? [h("b", {}, `${nameOf(ply)}  `), c.text] : null);
    nowNote.classList.toggle("hidden", !c);
    const key = (g.notes || []).find((x) => x.ply === ply);
    mount(keyNote, key ? [h("b", {}, "Key moment: "), key.text] : null);
    keyNote.classList.toggle("hidden", !key);
    mount(list, commentary.length ? commentary.map((x) => {
      const tone = x.tags.includes("mistake") || x.tags.includes("blunder") ? "bad" : x.tags.includes("mate") || x.tags.includes("sacrifice") || x.tags.includes("fork") ? "good" : "";
      return h("button", { class: `com ${tone}${seen.has(x.ply) ? " seen" : ""}`, "aria-current": ply === x.ply ? "true" : "false", onclick: () => setPly(x.ply) }, h("span", { class: "com-n mono" }, nameOf(x.ply)), h("span", {}, x.text));
    }) : g.moves.map((m, i) => h("button", { class: `com${seen.has(i + 1) ? " seen" : ""}`, "aria-current": ply === i + 1 ? "true" : "false", onclick: () => setPly(i + 1) }, h("span", { class: "com-n mono" }, nameOf(i + 1)))));
    const cur = list.querySelector('[aria-current="true"]');
    if (cur) cur.scrollIntoView({ block: "nearest" });
    paintProgress();
  }

  const controls = h("div", { class: "bctl" },
    h("button", { class: "btn small", onclick: () => setPly(0) }, "⏮"), h("button", { class: "btn small", onclick: () => setPly(ply - 1) }, "◀"),
    h("button", { class: "btn small", onclick: () => setPly(ply + 1) }, "▶"), h("button", { class: "btn small", onclick: () => setPly(total) }, "⏭"));
  const tools = boardTools(() => fenAt(ply), { onTry: () => mount(leftBox, explorer({ fen: fenAt(ply), title: `Try your own moves from ${nameOf(ply)}`, onBack: () => { mount(leftBox, mainLeft()); render(); }, backLabel: "Back to the game" })) });
  const mainLeft = () => [board, label, controls, nowNote, keyNote, tools];
  mount(leftBox, mainLeft());

  const key = (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") setPly(ply - 1);
    if (e.key === "ArrowRight") setPly(ply + 1);
  };
  document.addEventListener("keydown", key);
  render();

  const commentaryCard = h("div", { class: "card com-card", id: "commentary" },
    h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, "Commentary"), h("span", { class: "small muted" }, "Click a move · arrow keys step")), list);
  const extras = h("div", { class: "stack extras" },
    h("div", { class: "card", id: "story" }, h("h3", {}, "The story"), h("p", { style: "margin:0" }, g.summary),
      g.opening ? h("div", { class: "small muted", style: "margin-top:8px" }, icon("book"), ` ${g.opening}`) : null,
      h("div", { class: "row", style: "gap:6px;margin-top:8px" }, themeChips(g.themes))),
    g.lessons && g.lessons.length ? h("div", { class: "card", id: "learn" }, h("h3", {}, "What to learn"), h("ul", { class: "dots" }, g.lessons.map((l) => h("li", {}, l)))) : null);

  const root = h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("a", { href: "#/models", class: "small" }, "← All model games"), h("h1", {}, g.title),
      h("div", { class: "row", style: "gap:8px" }, g.rating ? h("span", { class: "pill brand" }, `${g.rating} rated`) : h("span", { class: "pill brand" }, "Historic masters"),
        h("span", { class: "muted" }, `${g.white} vs ${g.black} · ${g.event} ${g.year}`)),
      h("div", { style: "margin-top:8px" }, progressBox))),
    h("div", { class: "review review-model" }, leftBox, commentaryCard, extras));
  root.cleanup = () => { document.removeEventListener("keydown", key); flush(); };
  return root;
}
