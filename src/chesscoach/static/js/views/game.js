import { h, icon, mount, pct, outcomeText, fmtDate, toast } from "../dom.js";
import { openShareDialog } from "../share.js";
import { openScoresheets, photoCount } from "../scoresheets.js";
import { api } from "../api.js";
import { drawBoard, arrowFrom, flipTurn } from "../board.js";
import { timelineChart } from "../charts.js";
import { momentBody, momentArrows, legend, lineViewer, dimensionBars } from "../components.js";
import { state, loadSections, MONTHS } from "../state.js";
import { boardTools, explorer } from "../explorer.js";
import { go } from "../router.js";

const MARK = (loss) => (loss >= 20 ? "bl" : loss >= 10 ? "mi" : loss >= 5 ? "in" : "");

function statusView(game, refresh) {
  const bar = h("i", {});
  bar.style.width = `${Math.max(3, game.progress * 100)}%`;
  const meterEl = h("div", { class: "meter" }, bar);
  const box = h("div", { class: "card", style: "max-width:560px;margin:40px auto;text-align:center" },
    h("div", { class: "spin", style: "margin:0 auto 12px;width:28px;height:28px;border-width:3px" }),
    h("h2", {}, game.status === "queued" ? "Your coach is getting ready…" : "Your coach is analyzing the game…"),
    h("p", { class: "muted" }, "Checking every move for tactics, threats, mistakes and missed chances. This takes about 30 seconds."), meterEl);
  const timer = setInterval(async () => {
    try {
      const s = await api(`/api/games/${game.id}/status`);
      bar.style.width = `${Math.max(3, s.progress * 100)}%`;
      if (s.status === "done" || s.status === "error") { clearInterval(timer); loadSections(); refresh(); }
    } catch (_) { clearInterval(timer); }
  }, 1500);
  box.cleanup = () => clearInterval(timer);
  return box;
}

export async function gameView({ id, ply: plyParam }) {
  const game = await api(`/api/games/${id}`);
  document.title = `${game.white} vs ${game.black} · Chess Varsity`;
  const root = h("div", {});
  const refresh = async () => mount(root, await gameView({ id, ply: plyParam }));
  if (game.status === "queued" || game.status === "analyzing") {
    const box = statusView(game, refresh); root.cleanup = box.cleanup; root.append(box); return root;
  }
  if (game.status === "saved") {
    return h("div", { class: "card stack-s", style: "max-width:560px;margin:40px auto;text-align:center" },
      h("h2", { style: "margin:0" }, "Not analyzed yet"),
      h("p", { class: "muted", style: "margin:0" }, `${game.white} vs ${game.black} is saved. Analyze it whenever you're ready, and your coach will go through every move.`),
      h("div", {}, h("button", { class: "btn primary", onclick: async (e) => { e.currentTarget.disabled = true; await api(`/api/games/${id}/reanalyze`, { method: "POST" }); loadSections(); refresh(); } }, "🧠 Analyze this game")));
  }
  if (game.status === "error" || !game.analysis) {
    return h("div", { class: "card", style: "max-width:560px;margin:40px auto" }, h("h2", {}, "This game could not be analyzed"), h("p", { class: "muted" }, game.error || "Something went wrong."),
      h("button", { class: "btn primary", onclick: async () => { await api(`/api/games/${id}/reanalyze`, { method: "POST" }); loadSections(); location.reload(); } }, icon("refresh"), "Try again"));
  }

  const a = game.analysis;
  const orient = game.color;
  const playerWhite = game.color === "white";
  const fenAt = (p) => (p === 0 ? a.start_fen : a.moves[p - 1].fen);
  const n = a.moves.length;
  const view = { ply: 0, moment: null, line: null, tab: "wrong", flip: false };

  const board = h("div", { class: "board big" });
  const nowNote = h("div", { class: "callout commentary hidden" });
  const leftBox = h("div", { class: "left" });
  const chartBox = h("div", {});
  const moveLabel = h("div", { class: "center small muted", style: "text-align:center;margin-top:6px;min-height:1.4em" });
  const lineBar = h("div", { class: "card tight hidden", style: "margin-top:12px" });
  const panel = h("div", { class: "stack" });
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const balanceCache = new Map();

  function moveName(p) {
    if (p === 0) return "Starting position";
    const no = Math.ceil(p / 2);
    return `${no}${p % 2 ? "." : "…"} ${a.moves[p - 1].san}`;
  }

  function renderBoard() {
    if (view.line) {
      const { startFen, steps, idx } = view.line;
      const fen = idx === 0 ? startFen : steps[idx - 1].fen;
      drawBoard(board, fen, { orient: view.flip ? (orient === "white" ? "black" : "white") : orient, lastMove: idx ? steps[idx - 1].uci : null, arrows: idx ? [arrowFrom(steps[idx - 1].uci, view.line.kind)] : view.line.arrows || [] });
      return;
    }
    const arrows = view.moment && view.moment.ply - 1 === view.ply ? momentArrows(view.moment) : [];
    drawBoard(board, fenAt(view.ply), { orient: view.flip ? (orient === "white" ? "black" : "white") : orient, lastMove: view.ply ? a.moves[view.ply - 1].uci : null, arrows });
    moveLabel.textContent = `${moveName(view.ply)}  ·  ${view.ply}/${n}`;
    const note = a.commentary && view.ply ? a.commentary[view.ply - 1] : null;
    mount(nowNote, note ? [h("b", {}, `${moveName(view.ply)}  `), note.text] : null);
    nowNote.classList.toggle("hidden", !note);
    mount(chartBox, timelineChart(a.timeline, { playerWhite, ply: view.ply, onSelect: (p) => setPly(p) }));
  }

  function setPly(p, keepMoment = false) {
    view.line = null; lineBar.classList.add("hidden");
    view.ply = Math.max(0, Math.min(n, p));
    if (!keepMoment && view.moment && view.moment.ply - 1 !== view.ply) view.moment = null;
    renderBoard();
    if (view.tab === "moves" || view.tab === "balance" || view.tab === "commentary") renderPanel();
    if (view.tab === "wrong") highlightMoments();
  }

  function startLine(label, startFen, steps, kind, arrows) {
    view.line = { startFen, steps, idx: steps.length ? 1 : 0, kind, arrows };
    const draw = () => {
      const { idx } = view.line;
      const turnWhite = startFen.split(" ")[1] === "w";
      const no0 = +startFen.split(" ")[5] || 1;
      const lab = (i) => {
        const white = turnWhite ? i % 2 === 0 : i % 2 === 1;
        const no = no0 + (turnWhite ? Math.floor(i / 2) : Math.floor((i + 1) / 2));
        return white ? `${no}. ${steps[i].san}` : i === 0 ? `${no}… ${steps[i].san}` : steps[i].san;
      };
      mount(lineBar,
        h("div", { class: "row spread" }, h("b", {}, label), h("button", { class: "btn small", onclick: () => setPly(view.ply, true) }, icon("x"), "Back to the game")),
        h("div", { class: "steps" },
          h("button", { class: "btn small", "aria-label": "Back", onclick: () => { view.line.idx = Math.max(0, idx - 1); draw(); renderBoard(); } }, "◀"),
          steps.map((s, i) => h("button", { class: "step", "aria-current": idx === i + 1 ? "true" : "false", onclick: () => { view.line.idx = i + 1; draw(); renderBoard(); } }, lab(i))),
          h("button", { class: "btn small", "aria-label": "Forward", onclick: () => { view.line.idx = Math.min(steps.length, idx + 1); draw(); renderBoard(); } }, "▶")));
    };
    draw(); lineBar.classList.remove("hidden"); renderBoard();
  }

  function selectMoment(m) {
    view.moment = m; view.line = null; lineBar.classList.add("hidden");
    view.ply = m.ply - 1;
    renderBoard(); highlightMoments();
    board.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function highlightMoments() {
    panel.querySelectorAll(".moment").forEach((el) => el.classList.toggle("active", view.moment && el.dataset.ply === String(view.moment.ply)));
  }

  // ---- panels ----
  function wrongPanel() {
    const s = a.summary;
    const head = h("div", { class: "card" },
      h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, "In a nutshell")),
      h("p", { style: "margin:8px 0" }, s.headline),
      s.problems.length ? h("ul", { class: "dots" }, s.problems.map((p) => h("li", {}, p.text))) : null,
      h("div", { class: "callout lesson" }, h("b", {}, "Today's lesson: "), s.todays_lesson));
    const cards = a.moments.map((m) => {
      const card = h("div", { class: "moment", "data-ply": m.ply, onclick: () => selectMoment(m) },
        momentBody(m),
        h("div", { class: "row", style: "margin-top:10px" },
          h("button", { class: "btn small", onclick: (e) => { e.stopPropagation(); selectMoment(m); } }, "Show on board"),
          m.actual.length ? h("button", { class: "btn small", onclick: (e) => { e.stopPropagation(); selectMoment(m); startLine("What happened", m.fen, m.actual, "played"); } }, "What happened") : null,
          m.threat && m.threat.variation.length ? h("button", { class: "btn small", onclick: (e) => { e.stopPropagation(); selectMoment(m); startLine("If you ignore the threat", flipTurn(m.fen), m.threat.variation, "threat"); } }, "The threat") : null,
          h("button", { class: "btn small", onclick: (e) => { e.stopPropagation(); selectMoment(m); startLine("A better line", m.fen, m.variation, "best"); } }, "Better line")));
      return card;
    });
    return [head, legend(a.moments.find((m) => m.threat) || null), a.moments.length ? cards : h("div", { class: "card muted" }, "No big problems stood out in this game. Nice work!")];
  }

  function movesPanel() {
    const rows = [];
    for (let i = 0; i < n; i += 2) {
      const cell = (p) => {
        if (p > n) return h("span", {});
        const t = a.timeline[p];
        const mine = t.white_moved === playerWhite;
        const mk = mine ? MARK(t.loss) : "";
        return h("button", { "aria-current": view.ply === p ? "true" : "false", onclick: () => setPly(p), title: mine && t.loss >= 5 ? `Cost about ${Math.round(t.loss)} points` : "" }, a.moves[p - 1].san, mk ? h("span", { class: `mk ${mk}` }) : null);
      };
      rows.push(h("div", { class: "n" }, `${i / 2 + 1}.`), cell(i + 1), cell(i + 2));
    }
    return [h("div", { class: "card" }, h("div", { class: "movelist" }, rows),
      h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--bad)" }), "blunder"), h("span", {}, h("i", { style: "background:#ea580c" }), "mistake"), h("span", {}, h("i", { style: "background:#eab308" }), "inaccuracy")))];
  }

  async function balancePanel() {
    const box = h("div", { class: "card" }, h("p", { class: "muted" }, "Reading the position…"));
    const p = view.ply;
    if (!balanceCache.has(p)) balanceCache.set(p, api(`/api/games/${id}/balance?ply=${p}`));
    balanceCache.get(p).then((b) => {
      if (view.ply !== p || view.tab !== "balance") return;
      mount(box,
        h("h3", {}, `Balance after ${moveName(p)}`),
        h("p", {}, b.verdict.text),
        h("div", { class: "small muted", style: "margin-bottom:6px" }, "Each bar is from your side's point of view: right (green) is good for you, left (red) is good for your opponent."),
        dimensionBars(b.scores, b.labels),
        b.notes.length ? h("ul", { class: "dots" }, b.notes.map((x) => h("li", {}, x.text))) : null,
        h("div", { class: "callout" }, h("b", {}, "How to use this: "), "If a position is unbalanced, ask which imbalance you can play for. If the bars are against you, look for a move that improves the worst one."));
    }).catch(() => mount(box, h("p", { class: "muted" }, "Could not read this position.")));
    return [box];
  }

  function winPanel() {
    if (!a.how_to_win.length) return [h("div", { class: "card muted" }, game.outcome === "win" ? "You won this one, so there is nothing to fix here!" : "No clear turning point stood out in this game.")];
    return a.how_to_win.map((m) => h("div", { class: "card" },
      h("span", { class: `pill ${m.kind === "threw_away_win" ? "bad" : "warn"}` }, m.kind === "threw_away_win" ? "A win slipped away" : m.kind === "turning_point" ? "Turning point" : "Better position"),
      h("h3", { style: "margin-top:8px" }, m.headline),
      h("ul", { class: "dots" }, m.story.map((s) => h("li", {}, s))),
      h("div", { class: "callout lesson" }, h("b", {}, "The line: "), h("span", { class: "mono" }, m.line_text)),
      lineViewer({ startFen: m.fen, steps: m.variation, orient, arrows: [arrowFrom(m.played.uci, "played"), arrowFrom(m.best.uci, "best")], label: `Position before ${moveName(m.ply)}. Step through the better line:` }),
      h("div", { class: "callout" }, m.lesson),
      h("button", { class: "btn small", onclick: () => { view.tab = "moves"; setPly(m.ply - 1); renderTabs(); renderPanel(); window.scrollTo({ top: 0, behavior: "smooth" }); } }, "Show in the game")));
  }

  function commentaryPanel() {
    const list = a.commentary || [];
    if (!list.length) return [h("div", { class: "card muted" }, "Commentary is added when a game is analyzed. Press \"Analyze again\" in Edit details to add it to this game.")];
    const toneOf = (tags) => (tags.includes("blunder") || tags.includes("mistake") ? "bad" : tags.includes("mate") || tags.includes("sacrifice") || tags.includes("fork") ? "good" : "");
    const rows = list.map((c) => {
      const mine = a.timeline[c.ply].white_moved === playerWhite;
      return h("button", { class: `com ${toneOf(c.tags)} ${mine ? "mine" : ""}`, "aria-current": view.ply === c.ply ? "true" : "false", "data-ply": c.ply, onclick: () => setPly(c.ply) },
        h("span", { class: "com-n mono" }, moveName(c.ply)),
        h("span", { class: "com-t" }, c.text));
    });
    return [h("div", { class: "card" }, h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, "Move by move"),
      h("span", { class: "small muted" }, "Click a move to see it on the board")), h("div", { class: "comlist" }, rows))];
  }

  function renderPanel() {
    const build = { wrong: wrongPanel, commentary: commentaryPanel, moves: movesPanel, balance: balancePanel, win: winPanel }[view.tab];
    Promise.resolve(build()).then((nodes) => {
      mount(panel, nodes); highlightMoments();
      if (view.tab === "commentary") { const cur = panel.querySelector('.com[aria-current="true"]'); if (cur) cur.scrollIntoView({ block: "nearest" }); }
    });
  }
  function renderTabs() {
    mount(tabs, [["wrong", "What went wrong"], ["commentary", "Commentary"], ["moves", "Moves"], ["balance", "Balance"], ["win", "How to win"]].map(([key, label]) =>
      h("button", { role: "tab", "aria-selected": view.tab === key ? "true" : "false", onclick: () => { view.tab = key; renderTabs(); renderPanel(); } }, label)));
  }

  // ---- scoresheet photos ----
  const sheetBtn = h("button", { class: "btn small", style: "white-space:nowrap", title: "Photos of the paper scoresheet" });
  let sheets = [];
  const showSheets = (list) => { sheets = list; photoCount(sheetBtn, list); };
  showSheets([]);
  api(`/api/games/${id}/scoresheets`).then((r) => showSheets(r.sheets)).catch(() => {});
  sheetBtn.addEventListener("click", () => openScoresheets({ title: "Scoresheet photos", sheets, uploadUrl: `/api/games/${id}/scoresheets`, deleteQuery: `?game=${id}` }, showSheets));

  // ---- header + details ----
  const c = a.counts;
  const header = h("div", { class: "card" },
    h("div", { class: "row spread" },
      h("div", {}, h("h2", { style: "margin:0" }, `${game.white}${game.white_elo ? ` (${game.white_elo})` : ""} vs ${game.black}${game.black_elo ? ` (${game.black_elo})` : ""}`),
        h("div", { class: "muted small" }, [game.event, game.round && `Match #${game.round}`, fmtDate(game.date)].filter(Boolean).join(" · "))),
      h("div", { class: "row" }, h("span", { class: `pill ${game.outcome === "win" ? "good" : game.outcome === "loss" ? "bad" : "gray"}` }, outcomeText(game.outcome)),
        h("span", { class: "pill brand" }, `${game.color === "white" ? "White" : "Black"} · ${pct(a.accuracy)} accuracy`))),
    h("div", { class: "row small muted", style: "margin-top:8px" },
      game.opening_name ? h("span", {}, icon("book"), ` ${game.opening_eco} ${game.opening_name}${game.opening_plies ? ` · left the book at move ${Math.ceil(game.opening_plies / 2) + 1}` : ""}`) : null,
      h("span", {}, `${c.blunders} blunders · ${c.mistakes} mistakes · ${c.inaccuracies} inaccuracies`)),
    h("div", { class: "row", style: "margin-top:10px" }, folderPicker(),
      h("button", { class: "btn small primary", onclick: () => openShareDialog(id) }, icon("link"), "Share"),
      sheetBtn,
      h("button", { class: "btn small danger", onclick: deleteGame }, icon("trash"), "Delete game")),
    detailsForm());

  async function deleteGame() {
    if (!confirm(`Delete this game (${game.white} vs ${game.black}) and its analysis? This cannot be undone.`)) return;
    await api(`/api/games/${id}`, { method: "DELETE" });
    await loadSections();
    toast("Game deleted");
    go("/");
  }

  function folderPicker() {
    const select = h("select", { class: "select", style: "max-width:230px", "aria-label": "Folder" }, h("option", { value: "0" }, "No folder"));
    api(`/api/players/${state.player.id}/folders`).then((data) => {
      select.replaceChildren(h("option", { value: "0" }, "No folder"),
        ...data.folders.map((f) => h("option", { value: f.id, selected: f.id === game.folder_id }, f.name)),
        h("option", { value: "new" }, "+ New folder…"));
    }).catch(() => {});
    select.addEventListener("change", async () => {
      try {
        let target = select.value;
        if (target === "new") {
          const name = prompt("Name for the new folder");
          if (!name || !name.trim()) { select.value = String(game.folder_id || 0); return; }
          target = (await api("/api/folders", { method: "POST", body: { name } })).id;
        }
        await api(`/api/games/${id}`, { method: "PATCH", body: { folder_id: +target } });
        game.folder_id = +target || null;
        await loadSections();
        toast(+target ? "Moved to the folder" : "Taken out of the folder");
        refresh();
      } catch (err) { toast(err.message); }
    });
    return h("div", { class: "row", style: "gap:6px" }, icon("folder"), select);
  }

  function detailsForm() {
    const field = (label, control) => h("div", { class: "field" }, h("label", {}, label), control);
    const event = h("input", { class: "input", value: game.event, maxlength: 100, placeholder: "Optional" });
    const match = h("input", { class: "input", value: game.round, maxlength: 20 });
    const opp = h("input", { class: "input", value: game.opponent, maxlength: 60 });
    const oppRating = h("input", { class: "input", type: "number", min: 0, max: 3500, value: (game.color === "white" ? game.black_elo : game.white_elo) || "", placeholder: "Optional" });
    const parts = (game.date || "").split(".");
    const nowYear = new Date().getFullYear();
    const curYear = +parts[0] || nowYear, curMonth = +parts[1] || new Date().getMonth() + 1;
    const years = Array.from({ length: 12 }, (_, i) => nowYear - i);
    if (!years.includes(curYear)) years.push(curYear);
    const year = h("select", { class: "select" }, years.map((y) => h("option", { value: y, selected: y === curYear }, y)));
    const month = h("select", { class: "select" }, MONTHS.map((m, i) => h("option", { value: i + 1, selected: i + 1 === curMonth }, m)));
    const res = h("select", { class: "select" }, ["1-0", "0-1", "1/2-1/2", "*"].map((r) => h("option", { value: r, selected: r === game.result }, r)));
    return h("details", { style: "margin-top:12px" }, h("summary", { style: "cursor:pointer;font-weight:650" }, "Edit details"),
      h("div", { class: "form-grid", style: "margin-top:12px" }, field("Year", year), field("Month", month), field("Tournament", event), field("Match #", match), field("Opponent", opp), field("Opponent's rating", oppRating), field("Result", res)),
      h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "btn small primary", onclick: async () => {
          try { await api(`/api/games/${id}`, { method: "PATCH", body: { event: event.value, round: match.value, opponent: opp.value, opponent_rating: +oppRating.value || 0, year: +year.value, month: +month.value, result: res.value } }); await loadSections(); toast("Saved"); refresh(); } catch (err) { toast(err.message); } } }, "Save"),
        h("button", { class: "btn small", onclick: async () => { await api(`/api/games/${id}/reanalyze`, { method: "POST" }); loadSections(); refresh(); } }, icon("refresh"), "Analyze again"),
        h("button", { class: "btn small danger", onclick: async () => { if (confirm("Delete this game and its analysis?")) { await api(`/api/games/${id}`, { method: "DELETE" }); await loadSections(); go("/"); } } }, icon("trash"), "Delete")));
  }

  const flip = h("button", { class: "btn small", "aria-label": "Flip board", onclick: () => { view.flip = !view.flip; renderBoard(); } }, "Flip");
  const ctl = h("div", { class: "bctl" },
    h("button", { class: "btn small", "aria-label": "First move", onclick: () => setPly(0) }, "⏮"),
    h("button", { class: "btn small", "aria-label": "Previous move", onclick: () => setPly(view.ply - 1) }, "◀"),
    h("button", { class: "btn small", "aria-label": "Next move", onclick: () => setPly(view.ply + 1) }, "▶"),
    h("button", { class: "btn small", "aria-label": "Last move", onclick: () => setPly(n) }, "⏭"), flip);

  const currentFen = () => {
    if (view.line) return view.line.idx === 0 ? view.line.startFen : view.line.steps[view.line.idx - 1].fen;
    return fenAt(view.ply);
  };
  const tools = boardTools(currentFen, { onTry: () => enterExplore() });
  const mainLeft = () => [board, moveLabel, ctl, nowNote, tools, lineBar, chartCard];
  function enterExplore() {
    const orientNow = view.flip ? (orient === "white" ? "black" : "white") : orient;
    mount(leftBox, explorer({ fen: currentFen(), orient: orientNow, title: `Try your own moves from ${view.line ? "this position" : moveName(view.ply)}`,
      onBack: () => { mount(leftBox, mainLeft()); renderBoard(); } }));
  }
  const chartCard = h("div", {}, h("div", { class: "card tight", style: "margin-top:12px" }, h("div", { class: "small muted", style: "margin-bottom:4px" }, "How the game went for you (click to jump)"), chartBox),
      h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--bad)" }), "your mistakes"), h("span", {}, h("i", { style: "background:var(--good)" }), "opponent slipped")));
  mount(leftBox, mainLeft());
  const layout = h("div", { class: "review" },
    leftBox,
    h("div", { class: "stack" }, header, tabs, panel));
  mount(root, layout);

  const onKey = (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); view.line ? (view.line.idx = Math.max(0, view.line.idx - 1), renderBoard()) : setPly(view.ply - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); view.line ? (view.line.idx = Math.min(view.line.steps.length, view.line.idx + 1), renderBoard()) : setPly(view.ply + 1); }
  };
  document.addEventListener("keydown", onKey);
  root.cleanup = () => document.removeEventListener("keydown", onKey);

  renderTabs(); renderBoard(); renderPanel();
  if (plyParam !== undefined) {
    const target = +plyParam;
    const m = a.moments.find((x) => x.ply === target);
    if (m) setTimeout(() => selectMoment(m), 0); else setPly(target);
  } else if (a.moments.length) {
    setTimeout(() => selectMoment(a.moments[0]), 0);
  }
  return root;
}
