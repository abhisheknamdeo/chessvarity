// Add a game: paste, upload or enter the moves, see what was detected, confirm, and hand it to the coach.
// The PGN is read on the server as you type (POST /api/games/preview), so nothing the PGN already says is asked again.
import { h, icon, toast, mount } from "../dom.js";
import { uploadPhoto, openScoresheets } from "../scoresheets.js";
import { api } from "../api.js";
import { state, loadSections, on } from "../state.js";
import { askText } from "../dialogs.js";
import { drawBoard } from "../board.js";
import { go } from "../router.js";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const movetext = (sans) => sans.map((s, i) => (i % 2 === 0 ? `${i / 2 + 1}. ${s}` : s)).join(" ");
const option = (value, text, selected) => h("option", { value, selected: !!selected }, text);
const colorWord = (c) => (c === "white" ? "White" : c === "black" ? "Black" : "");
// "Namdeo, Ayaan" reads better as "Ayaan Namdeo".
const niceName = (n) => (n && n.includes(",") ? n.split(",").map((x) => x.trim()).reverse().join(" ") : n || "");
const niceDate = (iso) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");
const niceMonth = (ym) => (ym ? new Date(`${ym}-15T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "");
const todayIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const RESULT_TEXT = { "1-0": "1-0", "0-1": "0-1", "1/2-1/2": "½-½", "*": "Unfinished" };

// What the coach checks, shown before the button so the value is clear.
const COACH = [
  ["♟", "Tactics", "Missed checks, captures, forks, pins and combinations"],
  ["⚠", "Threats", "What your opponent was threatening, move by move"],
  ["🎯", "Missed opportunities", "Positions where you could have attacked or won more"],
  ["🧠", "Strategy", "Passive pieces, weak plans and positional slips"],
  ["♜", "Endgame", "Key endgame decisions and techniques"],
  ["📈", "Improvement patterns", "Mistakes that repeat across your games"],
];

/** Click-to-move board that writes SAN into `onChange`. Legality comes from the server. */
function boardEntry(onChange) {
  const bi = { fens: [START_FEN], sans: [], ucis: [], orient: "white", selected: null };
  const cache = new Map();
  const boardEl = h("div", { class: "board", style: "max-width:400px" });
  const status = h("div", { class: "muted small", "aria-live": "polite" });
  const list = h("div", { class: "mono small", style: "line-height:1.8;min-height:3em" });

  async function legal(fen) {
    if (!cache.has(fen)) cache.set(fen, await api(`/api/legal?fen=${encodeURIComponent(fen)}`));
    return cache.get(fen);
  }
  async function render() {
    const fen = bi.fens[bi.fens.length - 1];
    const info = await legal(fen);
    const last = bi.ucis[bi.ucis.length - 1];
    const targets = bi.selected ? info.moves.filter((m) => m.uci.startsWith(bi.selected)).map((m) => m.uci.slice(2, 4)) : [];
    drawBoard(boardEl, fen, { orient: bi.orient, selected: bi.selected, targets, lastMove: last, onSquare: click });
    status.textContent = info.over ? `Game over (${info.result}).` : `${info.turn === "white" ? "White" : "Black"} to move. Click a piece, then its square.`;
    list.textContent = bi.sans.length ? movetext(bi.sans) : "No moves yet.";
    onChange(bi.sans.length ? movetext(bi.sans) : "");
  }
  async function click(sq) {
    const info = await legal(bi.fens[bi.fens.length - 1]);
    if (info.over) return;
    if (bi.selected) {
      const options = info.moves.filter((m) => m.uci.slice(0, 2) === bi.selected && m.uci.slice(2, 4) === sq);
      if (options.length) {
        const m = options.find((x) => x.uci.length === 5 && x.uci[4] === "q") || options[0];
        bi.fens.push(m.fen); bi.sans.push(m.san); bi.ucis.push(m.uci); bi.selected = null;
        return render();
      }
    }
    bi.selected = info.moves.some((m) => m.uci.slice(0, 2) === sq) && bi.selected !== sq ? sq : null;
    render();
  }
  const el = h("div", { class: "row", style: "align-items:flex-start;gap:20px" },
    h("div", { style: "flex:1;min-width:260px;max-width:400px" }, boardEl),
    h("div", { style: "flex:1;min-width:220px" },
      h("div", { class: "row" },
        h("button", { class: "btn small", type: "button", onclick: () => { if (bi.sans.length) { bi.fens.pop(); bi.sans.pop(); bi.ucis.pop(); bi.selected = null; render(); } } }, "Undo"),
        h("button", { class: "btn small", type: "button", onclick: () => { Object.assign(bi, { fens: [START_FEN], sans: [], ucis: [], selected: null }); render(); } }, "Start over"),
        h("button", { class: "btn small", type: "button", onclick: () => { bi.orient = bi.orient === "white" ? "black" : "white"; render(); } }, "Flip board")),
      h("p", {}, status), list, h("p", { class: "muted small" }, "Pawns that reach the last rank become queens.")));
  el.start = render;
  return el;
}

export async function addView(_params, query = {}) {
  document.title = "Add a game · Chess Varsity";
  const firstName = (state.user.display_name || state.player.name || "").trim().split(/\s+/)[0];
  const whose = firstName ? `${firstName}'s` : "Your";

  // ---- tournaments and folders (unchanged behaviour) ----
  let events = [];
  try { events = await api(`/api/players/${state.player.id}/events`); } catch (_) { /* the page still works without tournaments */ }
  const openRounds = events.map((e) => ({ e, rounds: e.rounds.filter((r) => !r.game_id) })).filter((x) => x.rounds.length);
  const roundSel = h("select", { class: "select", id: "a-round-pick" },
    option("", "Not attached to a round"),
    openRounds.map(({ e, rounds }) => h("optgroup", { label: `${e.name}${e.start_date ? ` · ${e.start_date.slice(0, 7).replace(".", "-")}` : ""}` },
      rounds.map((r) => option(r.id, `Round ${r.round}${r.opponent ? ` · vs ${r.opponent}` : ""}${r.color ? ` (${colorWord(r.color)})` : ""}${r.result ? ` · ${r.result}` : ""}`, String(r.id) === String(query.round))))));
  const roundInfo = (id) => { for (const x of openRounds) { const r = x.rounds.find((q) => String(q.id) === String(id)); if (r) return { ...r, event: x.e }; } return null; };
  const knownEvents = Array.from(new Set([...events.map((e) => e.name), ...state.sections.flatMap((s) => s.tournaments.map((t) => t.event))]));

  const folder = h("select", { class: "select", id: "a-folder" });
  const fillFolders = () => {
    const chosen = folder.value;
    folder.replaceChildren(option("0", "No folder"), ...state.folders.folders.map((f) => option(f.id, f.name)), option("new", "+ New folder…"));
    if ([...folder.options].some((o) => o.value === chosen)) folder.value = chosen;
  };
  fillFolders();
  const stopWatching = on("games-changed", fillFolders);
  folder.addEventListener("change", async () => {
    if (folder.value !== "new") return;
    const name = await askText({ title: "New folder", label: "Folder name", confirmLabel: "Create folder" });
    if (!name) { folder.value = "0"; return; }
    try {
      const made = await api("/api/folders", { method: "POST", body: { name } });
      folder.insertBefore(option(made.id, made.name, true), folder.lastChild);
      folder.value = String(made.id);
      await loadSections();
    } catch (e) { toast(e.message); folder.value = "0"; }
  });

  // ---- ① the moves ----
  const text = h("textarea", { class: "textarea", id: "a-pgn", spellcheck: "false", rows: 9, "aria-describedby": "a-pgn-help",
    placeholder: "Paste your PGN here...\n\nExample:\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 ..." });
  const fileName = h("div", { class: "small muted", "aria-live": "polite" });
  const file = h("input", { type: "file", id: "a-file", accept: ".pgn,.txt", class: "visually-hidden" });
  const readFile = async (f) => { if (!f) return; text.value = await f.text(); fileName.textContent = `Loaded ${f.name}`; detect(true); };
  file.addEventListener("change", (e) => readFile(e.target.files[0]));
  const drop = h("label", { class: "dropzone", for: "a-file" },
    icon("upload"), h("b", {}, "Choose a .pgn file"), h("span", { class: "small muted" }, "or drop it here. Files with many games are fine."));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); readFile(e.dataTransfer.files[0]); });
  const board = boardEntry((t) => { if (mode === "board") { text.value = t; detect(); } });

  // ---- scoresheet photos: picked here (sent with the game, or saved for later) or from a saved notation ----
  const photos = photoPicker(() => { paintRef(); render(); });
  let active = null;               // the saved notation whose moves are being entered now
  let saved = [];                  // saved notations still waiting for their moves
  const nTitle = h("input", { class: "input", id: "a-ntitle", maxlength: 100, placeholder: "e.g. Round 3 vs John Smith" });
  const nDate = h("input", { class: "input", id: "a-ndate", type: "date", value: todayIso(), max: todayIso() });
  const saveLater = h("button", { class: "btn", type: "button", id: "a-save-later", onclick: () => saveForLater() }, icon("download"), "Save for later");
  const refBox = h("div", { class: "notation-ref hidden", "aria-label": "Your scoresheet" });
  const refSlot = h("div", {});      // where the scoresheet sits on the paste and upload tabs; on the board tab it moves beside the board
  const lightbox = h("div", { class: "lightbox", hidden: true, role: "dialog", "aria-label": "Scoresheet photo", onclick: () => { lightbox.hidden = true; } });
  const zoom = (im) => { mount(lightbox, h("img", { src: im.src, alt: im.alt }), h("div", { class: "small" }, "Tap anywhere to close")); lightbox.hidden = false; };
  const onEsc = (e) => { if (e.key === "Escape") lightbox.hidden = true; };
  document.addEventListener("keydown", onEsc);
  const refImages = () => [
    ...(active ? active.sheets.map((sh, i) => ({ src: `/api/scoresheets/${sh.id}`, alt: `Scoresheet photo ${i + 1}` })) : []),
    ...photos.pending.filter((x) => x.preview).map((x, i) => ({ src: x.preview, alt: `New scoresheet photo ${i + 1}` }))];
  // The scoresheet stays in view on every tab, so the moves can be copied from it.
  function paintRef() {
    const imgs = refImages();
    refBox.classList.toggle("hidden", !imgs.length || mode === "notation");
    const host = mode === "board" ? board.lastElementChild : refSlot;
    if (refBox.parentNode !== host) host.append(refBox);
    mount(refBox,
      h("div", { class: "row spread", style: "gap:8px" },
        h("b", { class: "small" }, active ? `📷 Entering the moves for: ${active.title || "your saved scoresheet"}` : "📷 Your scoresheet"),
        active ? h("button", { class: "linkish small", type: "button", onclick: () => { active = null; paintSaved(); paintRef(); render(); } }, "Stop using it") : null),
      h("div", { class: "ref-strip" }, imgs.map((im) => h("button", { type: "button", class: "ref-thumb", title: "Enlarge", onclick: () => zoom(im) }, h("img", { src: im.src, alt: im.alt })))),
      h("div", { class: "small muted" }, "Tap a photo to enlarge it while you enter the moves. It's kept with the game for future reference."));
  }
  async function saveForLater() {
    if (!photos.pending.length) { toast("Add a photo of the scoresheet first."); return; }
    saveLater.disabled = true;
    try {
      const n = await api("/api/notations", { method: "POST", body: { title: nTitle.value.trim(), played_on: nDate.value } });
      for (const x of photos.pending) await uploadPhoto(`/api/notations/${n.id}/scoresheets`, x.file);
      photos.clear(); nTitle.value = "";
      await loadSaved(); paintRef(); render();
      toast("Scoresheet saved. Enter its moves any time from the top of this page.");
      savedBox.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) { toast(err.message); } finally { saveLater.disabled = false; }
  }
  const savedBox = h("section", { class: "card stack-s saved-notations hidden", "aria-labelledby": "h-saved" });
  async function loadSaved() { try { saved = await api("/api/notations"); } catch (_) { saved = []; } paintSaved(); }
  function useNotation(n) {
    active = n;
    if (n.played_on && !touched.has("date")) { date.value = n.played_on; touched.add("date"); }
    setMode(text.value.trim() ? mode === "notation" ? "board" : mode : "board");
    paintSaved(); paintRef(); render();
    page.querySelector(".add-main").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function paintSaved() {
    savedBox.classList.toggle("hidden", !saved.length);
    mount(savedBox,
      h("div", { class: "row spread", style: "gap:8px" },
        h("h2", { id: "h-saved", style: "margin:0;font-size:1.02rem" }, `📷 Scoresheets waiting for moves (${saved.length})`),
        h("span", { class: "small muted" }, "Kept safely until you enter the moves")),
      saved.map((n) => {
        const first = n.sheets[0];
        const using = active && active.id === n.id;
        return h("div", { class: `saved-row${using ? " on" : ""}` },
          first ? h("button", { type: "button", class: "ref-thumb sm", title: "Enlarge", onclick: () => zoom({ src: `/api/scoresheets/${first.id}`, alt: n.title || "Scoresheet" }) },
            h("img", { src: `/api/scoresheets/${first.id}`, alt: `Scoresheet: ${n.title || "saved"}` })) : h("span", { class: "ref-thumb sm empty", "aria-hidden": "true" }, "📷"),
          h("div", { style: "flex:1;min-width:0" }, h("b", {}, n.title || "Scoresheet"),
            h("div", { class: "small muted" }, [n.played_on ? niceDate(n.played_on) : `Saved ${new Date(n.created_at * 1000).toLocaleDateString()}`, `${n.sheets.length} photo${n.sheets.length === 1 ? "" : "s"}`].join(" · "))),
          h("div", { class: "row", style: "gap:6px" },
            h("button", { class: `btn small ${using ? "" : "primary"}`, type: "button", disabled: using, onclick: () => useNotation(n) }, using ? "Entering now" : "Enter moves"),
            h("button", { class: "btn small", type: "button", onclick: () => openScoresheets({ title: n.title || "Scoresheet", sheets: n.sheets, uploadUrl: `/api/notations/${n.id}/scoresheets` },
              (list) => { n.sheets = list; paintSaved(); paintRef(); }) }, icon("camera"), "Photos"),
            h("button", { class: "btn small danger", type: "button", "aria-label": `Delete ${n.title || "this scoresheet"}`, title: "Delete", onclick: async () => {
              if (!confirm("Delete this saved scoresheet and its photos?")) return;
              try { await api(`/api/notations/${n.id}`, { method: "DELETE" }); } catch (err) { toast(err.message); return; }
              if (using) active = null;
              await loadSaved(); paintRef(); render();
            } }, icon("trash"))));
      }));
  }

  const panes = {
    paste: h("div", { class: "stack-s", role: "tabpanel", id: "pane-paste", "aria-labelledby": "tab-paste" },
      h("label", { for: "a-pgn", class: "visually-hidden" }, "PGN or moves"), text,
      h("div", { class: "small muted", id: "a-pgn-help" }, "Games from Chess.com, Lichess, or tournament PGNs are supported. A bare move list works too.")),
    upload: h("div", { class: "stack-s hidden", role: "tabpanel", id: "pane-upload", "aria-labelledby": "tab-upload" }, drop, file, fileName),
    board: h("div", { class: "hidden", role: "tabpanel", id: "pane-board", "aria-labelledby": "tab-board" }, board),
    notation: h("div", { class: "stack-s hidden", role: "tabpanel", id: "pane-notation", "aria-labelledby": "tab-notation" },
      h("p", { class: "small muted", style: "margin:0" }, "Snap the paper scoresheet. Copy the moves in now while looking at it, or save it and enter the moves later: it waits safely at the top of this page, and stays with the game afterwards for future reference."),
      photos.el,
      h("div", { class: "form-grid" },
        h("div", { class: "field" }, h("label", { for: "a-ntitle" }, "What game is it? (optional)"), nTitle),
        h("div", { class: "field" }, h("label", { for: "a-ndate" }, "Played on"), nDate)),
      h("div", { class: "row", style: "gap:8px" },
        h("button", { class: "btn primary", type: "button", onclick: () => setMode("board") }, "Enter the moves now →"),
        h("button", { class: "btn", type: "button", onclick: () => setMode("paste") }, "Type or paste them"),
        saveLater)),
  };
  let mode = "paste";
  const TAB_LIST = [["paste", "Paste PGN"], ["upload", "Upload PGN"], ["board", "Enter on board"], ["notation", "📷 Upload notation"]];
  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "How to add the game" },
    TAB_LIST.map(([k, t]) => h("button", { type: "button", role: "tab", id: `tab-${k}`, "aria-controls": `pane-${k}`, "aria-selected": k === mode ? "true" : "false",
      tabindex: k === mode ? "0" : "-1", onclick: () => setMode(k),
      onkeydown: (e) => {
        const i = TAB_LIST.findIndex(([x]) => x === k);
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          const next = TAB_LIST[(i + (e.key === "ArrowRight" ? 1 : TAB_LIST.length - 1)) % TAB_LIST.length][0];
          setMode(next); tabs.querySelector(`#tab-${next}`).focus();
        }
      } }, t)));
  let boardStarted = false;
  function setMode(m) {
    mode = m;
    for (const [k] of TAB_LIST) {
      const b = tabs.querySelector(`#tab-${k}`);
      b.setAttribute("aria-selected", k === m ? "true" : "false"); b.tabIndex = k === m ? 0 : -1;
      panes[k].classList.toggle("hidden", k !== m);
    }
    if (m === "board" && !boardStarted) { boardStarted = true; board.start(); }
    paintRef();
  }

  // ---- detection ----
  let preview = null;          // the last /api/games/preview answer
  let previewFor = "";         // the text it was for
  let checking = false;
  let seq = 0;
  let timer = null;
  const touched = new Set();   // fields the user changed by hand: detection never overwrites them
  const multi = { include: new Set(), sides: [] };

  async function detect(now = false) {
    clearTimeout(timer);
    const run = async () => {
      const pgn = text.value.trim();
      if (!pgn) { preview = null; previewFor = ""; checking = false; render(); return; }
      if (pgn === previewFor) return;
      const mine = ++seq;
      checking = true; render();
      let res;
      try { res = await api("/api/games/preview", { method: "POST", body: { pgn } }); }
      catch (err) { res = { ok: false, error: "We couldn't read this game.", hint: "" }; }
      if (mine !== seq) return;
      checking = false; preview = res; previewFor = pgn;
      applyDetected();
      render();
    };
    if (now) run(); else timer = setTimeout(run, 450);
  }
  text.addEventListener("input", () => detect());
  text.addEventListener("paste", () => setTimeout(() => detect(true), 0));

  // ---- ② game details ----
  const side = h("select", { class: "select", id: "a-side", onchange: () => { touched.add("side"); fillFromSide(); render(); } });
  const result = h("select", { class: "select", id: "a-res", onchange: () => { touched.add("result"); render(); } },
    [["", "From the game"], ["win", "I won"], ["loss", "I lost"], ["draw", "Draw"], ["unfinished", "Unfinished"]].map(([v, t]) => option(v, t)));
  const opponent = h("input", { class: "input", id: "a-opp", maxlength: 60, placeholder: "Opponent's name", oninput: () => touched.add("opponent") });
  const oppRating = h("input", { class: "input", id: "a-opprating", type: "number", inputmode: "numeric", min: 0, max: 3500, placeholder: "e.g. 1350", oninput: () => touched.add("oppRating") });
  const tournament = h("input", { class: "input", id: "a-event", list: "a-events", maxlength: 100, placeholder: "e.g. State Championship", oninput: () => { touched.add("event"); render(); } });
  const round = h("input", { class: "input", id: "a-round", maxlength: 20, placeholder: "e.g. 3", oninput: () => touched.add("round") });
  const date = h("input", { class: "input", id: "a-date", type: "date", value: todayIso(), max: todayIso(), onchange: () => { touched.add("date"); render(); } });
  const dateNote = h("div", { class: "small muted" });
  roundSel.addEventListener("change", () => {
    touched.add("roundSel");
    const r = roundInfo(roundSel.value);
    if (r) {
      if (!touched.has("event")) tournament.value = r.event.name;
      if (!touched.has("round")) round.value = r.round || "";
      if (r.color && !touched.has("side")) { side.value = r.color; fillFromSide(); }
    }
    render();
  });

  const single = () => (preview && preview.ok && preview.games.length === 1 ? preview.games[0] : null);

  function fillSideOptions(g) {
    const current = side.value;
    side.replaceChildren(option("", "Choose White or Black…"),
      option("white", `White${g && g.white ? ` · ${niceName(g.white)}` : ""}`), option("black", `Black${g && g.black ? ` · ${niceName(g.black)}` : ""}`));
    side.value = current;
  }
  // The opponent's name and rating follow from which side I played, unless typed by hand.
  function fillFromSide() {
    const g = single();
    if (!g || !side.value) return;
    const them = side.value === "white" ? "black" : "white";
    if (!touched.has("opponent")) opponent.value = niceName(g[them]);
    if (!touched.has("oppRating")) oppRating.value = g[`${them}_elo`] || "";
    if (!touched.has("result")) result.value = relResult(g.result, side.value);
  }
  const relResult = (res, s) => (res === "1/2-1/2" ? "draw" : res === "*" || !res ? "" : (res === "1-0") === (s === "white") ? "win" : "loss");
  const absResult = (rel, s) => (rel === "draw" ? "1/2-1/2" : rel === "unfinished" ? "*" : rel && s ? ((rel === "win") === (s === "white") ? "1-0" : "0-1") : "");

  function applyDetected() {
    const g = single();
    if (preview && preview.ok && preview.games.length > 1) {
      multi.include = new Set(preview.games.filter((x) => !x.duplicate).map((x) => x.index));
      multi.sides = preview.games.map((x) => x.side || "");
    }
    fillSideOptions(g);
    const fromRound = roundInfo(roundSel.value);
    if (!g) {
      // Several games (or none): nothing from an earlier paste may linger in fields that weren't typed by hand.
      if (!touched.has("event")) tournament.value = fromRound ? fromRound.event.name : "";
      if (!touched.has("round")) round.value = fromRound ? fromRound.round : "";
      if (!touched.has("date")) date.value = todayIso();
      if (!touched.has("side")) side.value = "";
      return;
    }
    if (!touched.has("side")) side.value = g.side || (fromRound && fromRound.color) || "";
    if (!touched.has("event")) tournament.value = g.event || (fromRound ? fromRound.event.name : "");
    if (!touched.has("round")) round.value = g.round || (fromRound ? fromRound.round : "");
    if (!touched.has("date")) date.value = g.date || todayIso();
    if (!touched.has("opponent")) opponent.value = "";
    if (!touched.has("oppRating")) oppRating.value = "";
    if (!touched.has("result")) result.value = "";
    fillFromSide();
    orgDetails.open = orgDetails.open || !!(g.event || g.round || roundSel.value || (g.match && g.match.event_id));
  }
  fillSideOptions(null);

  // ---- tournament & organization ----
  const suggestion = h("div", {});
  const orgDetails = h("details", { class: "org", open: !!roundSel.value },
    h("summary", {}, h("span", { class: "org-title" }, "Tournament & organization"), h("span", { class: "small muted org-sub" }, "Tournament, round, date and folder")),
    h("div", { class: "stack-s", style: "margin-top:12px" },
      suggestion,
      h("div", { class: "form-grid" },
        h("div", { class: "field" }, h("label", { for: "a-event" }, "Tournament"), tournament),
        h("div", { class: "field" }, h("label", { for: "a-round" }, "Round"), round),
        h("div", { class: "field" }, h("label", { for: "a-date" }, "Date"), date, dateNote),
        h("div", { class: "field" }, h("label", { for: "a-folder" }, "Folder"), folder),
        openRounds.length ? h("div", { class: "field", style: "grid-column:1/-1" }, h("label", { for: "a-round-pick" }, "Attach to a round from your Tournaments page"), roundSel,
          h("span", { class: "small muted" }, "The game then shows on that round, and the round's opponent, color and result fill in anything the PGN leaves out.")) : null),
      h("datalist", { id: "a-events" }, knownEvents.map((e) => h("option", { value: e })))));

  const detailsSection = h("section", { class: "stack-s", "aria-labelledby": "h-details" },
    h("div", { class: "step-h" }, h("span", { class: "step-n", "aria-hidden": "true" }, "2"), h("h2", { id: "h-details" }, "Game details")),
    h("div", { class: "card stack" }, h("div", { class: "form-grid", id: "a-details-grid" },
      h("div", { class: "field" }, h("label", { for: "a-side" }, "You played"), side),
      h("div", { class: "field" }, h("label", { for: "a-res" }, "Result"), result),
      h("div", { class: "field" }, h("label", { for: "a-opp" }, "Opponent"), opponent),
      h("div", { class: "field" }, h("label", { for: "a-opprating" }, "Opponent rating"), oppRating)),
    h("div", { class: "small muted hidden", id: "a-multi-note" }, "With several games, each game's own details come from its PGN. A tournament, round or date set below is used where a game leaves it out."),
    orgDetails));

  // ---- the detection panel under the input ----
  const detectBox = h("div", { "aria-live": "polite" });
  const viewGame = h("div", { class: "hidden", style: "margin-top:12px" });

  function playerLine(g, color) {
    const me = g.side === color || (!g.side && side.value === color);
    const name = niceName(g[color]) || colorWord(color);
    return h("div", { class: `mu-player ${color}` },
      h("span", { class: "mu-piece", "aria-hidden": "true" }, color === "white" ? "♔" : "♚"),
      h("span", { class: "mu-name" }, name), g[`${color}_elo`] ? h("span", { class: "mu-elo" }, g[`${color}_elo`]) : null,
      me ? h("span", { class: "pill brass", style: "font-size:.7rem" }, "You") : null);
  }

  function singlePanel(g) {
    const missing = !g.white || !g.black || !g.date || g.result === "*" || !g.event;
    const meta = [RESULT_TEXT[g.result] || g.result, `${g.moves} move${g.moves === 1 ? "" : "s"}`, g.date ? niceDate(g.date) : niceMonth(g.month)].filter(Boolean);
    const where = [g.event, g.round ? `Round ${g.round}` : "", g.site].filter(Boolean);
    const viewBtn = h("button", { class: "btn small", type: "button", "aria-expanded": "false", onclick: () => {
      const showing = viewGame.classList.toggle("hidden") === false;
      viewBtn.setAttribute("aria-expanded", String(showing)); viewBtn.textContent = showing ? "Hide game" : "View game";
      if (showing) {
        const b = h("div", { class: "board", style: "max-width:260px" });
        mount(viewGame, h("div", { class: "row", style: "gap:16px;align-items:flex-start" }, b,
          h("div", { class: "mono small", style: "flex:1;min-width:200px;max-height:260px;overflow:auto;line-height:1.8" },
            previewFor.replace(/^\s*\[[^\]]*\]\s*$/gm, "").replace(/\{[^}]*\}/g, "").replace(/\s+/g, " ").trim())));
        drawBoard(b, g.final_fen, { orient: side.value || g.side || "white" });
      }
    } }, "View game");
    return h("div", { class: "detect good" },
      h("div", { class: "row spread", style: "gap:8px" },
        h("div", { class: "detect-title" }, h("span", { class: "tick", "aria-hidden": "true" }, "✓"), "Game detected"),
        viewBtn),
      h("div", { class: "matchup" }, playerLine(g, "white"), h("span", { class: "mu-vs" }, "vs"), playerLine(g, "black")),
      h("div", { class: "detect-meta" }, meta.join("  •  ")),
      where.length ? h("div", { class: "detect-meta muted" }, where.join("  •  ")) : null,
      g.opening_name ? h("div", { class: "small muted" }, `${g.opening_eco ? `${g.opening_eco} · ` : ""}${g.opening_name}`) : null,
      g.duplicate ? h("div", { class: "alert warn", style: "margin:4px 0 0" }, "This game is already in your games.") : null,
      missing ? h("div", { class: "small muted" }, "Some game details weren't included in the PGN. You can add them below.") : null,
      viewGame);
  }

  function multiPanel(games) {
    const rows = games.map((g) => {
      const box = h("input", { type: "checkbox", checked: multi.include.has(g.index), disabled: g.duplicate, "aria-label": `Include game ${g.index + 1}`,
        onchange: () => { if (box.checked) multi.include.add(g.index); else multi.include.delete(g.index); render(); } });
      const sidePick = g.side ? h("span", { class: "small muted" }, `You: ${colorWord(g.side)}`)
        : h("select", { class: "select", style: "max-width:170px;padding:4px 8px", "aria-label": `Which side you played in game ${g.index + 1}`,
          onchange: (e) => { multi.sides[g.index] = e.target.value; render(); } },
          option("", "Which side?"), option("white", "I was White", multi.sides[g.index] === "white"), option("black", "I was Black", multi.sides[g.index] === "black"));
      return h("div", { class: `mg-row${g.duplicate ? " dup" : ""}` },
        box,
        h("div", { style: "min-width:0;flex:1" },
          h("div", {}, h("b", {}, `Game ${g.index + 1}`), "  ", `${niceName(g.white) || "White"} vs ${niceName(g.black) || "Black"}`),
          h("div", { class: "small muted" }, [RESULT_TEXT[g.result] || g.result, `${g.moves} moves`, g.date ? niceDate(g.date) : niceMonth(g.month), g.event].filter(Boolean).join(" · "))),
        g.duplicate ? h("span", { class: "pill gray" }, "Already added") : sidePick);
    });
    const selectable = games.filter((g) => !g.duplicate);
    return h("div", { class: "detect good" },
      h("div", { class: "row spread", style: "gap:8px" },
        h("div", { class: "detect-title" }, h("span", { class: "tick", "aria-hidden": "true" }, "✓"), `${games.length} games detected`),
        h("div", { class: "row small", style: "gap:10px" },
          h("button", { class: "linkish", type: "button", onclick: () => { multi.include = new Set(selectable.map((g) => g.index)); render(); } }, "Select all"),
          h("button", { class: "linkish", type: "button", onclick: () => { multi.include = new Set(); render(); } }, "Select none"))),
      h("div", { class: "mg-list" }, rows));
  }

  function badPanel() {
    return h("div", { class: "detect bad", role: "alert" },
      h("div", { class: "detect-title" }, h("span", { class: "tick", "aria-hidden": "true" }, "!"), preview.error || "We couldn't read this game."),
      h("div", { class: "small" }, preview.hint ? `${preview.hint} ` : "", "Check that the PGN contains valid chess moves and try again."),
      h("div", {}, h("button", { class: "btn small", type: "button", onclick: () => {
        text.value = ""; preview = null; previewFor = ""; fileName.textContent = ""; setMode("paste"); render(); text.focus();
      } }, "Try again")));
  }

  // ---- the sticky action bar ----
  const barIcon = h("span", { class: "bar-icon", "aria-hidden": "true" });
  const barTitle = h("div", { class: "bar-title" });
  const barSub = h("div", { class: "small muted" });
  const submit = h("button", { class: "btn primary cta", type: "button", id: "a-submit" });
  const saveOnly = h("button", { class: "linkish small", type: "button", id: "a-save-only" }, "Save without analysis");
  const barError = h("div", { class: "alert bad hidden", role: "alert", style: "margin:0" });
  let busy = false;

  // What the page is waiting for, and what the button says.
  function readiness() {
    if (checking) return { tone: "wait", title: "Reading your game…", sub: "Finding the players, result, date and tournament.", ready: false };
    if (!text.value.trim() && (active || photos.pending.length)) {
      return { tone: "idle", title: active ? "Enter the moves from your scoresheet" : "Scoresheet added", sub: "Enter the moves on the board or type them, or save the scoresheet for later.", ready: false };
    }
    if (!text.value.trim() || !preview) return { tone: "idle", title: "Add a game to get started", sub: "Paste a PGN above, enter the moves on a board, or upload a photo of your scoresheet.", ready: false };
    if (!preview.ok) return { tone: "bad", title: "We couldn't read this game", sub: "Check the moves above and try again.", ready: false };
    const g = single();
    if (g) {
      if (g.duplicate) return { tone: "warn", title: "Already in your games", sub: "This exact game was added before.", ready: false };
      if (!side.value) return { tone: "warn", title: "Which side did you play?", sub: "Choose White or Black under Game details.", ready: false };
      return { tone: "good", title: `✓ ${whose} game is ready`, sub: "Your coach will analyze tactics, threats, mistakes and missed opportunities.", ready: true, n: 1 };
    }
    const chosen = [...multi.include];
    const noSide = chosen.filter((i) => !multi.sides[i]).length;
    if (!chosen.length) return { tone: "warn", title: "Choose at least one game", sub: "Tick the games you want to add.", ready: false };
    if (noSide) return { tone: "warn", title: `Which side did you play in ${noSide} game${noSide === 1 ? "" : "s"}?`, sub: "Choose White or Black next to each game.", ready: false };
    return { tone: "good", title: `✓ ${chosen.length} game${chosen.length === 1 ? "" : "s"} ready`, sub: "Your coach will analyze each one: tactics, threats, mistakes and missed opportunities.", ready: true, n: chosen.length };
  }

  const detailsGrid = () => detailsSection.querySelector("#a-details-grid");
  function render() {
    const g = single();
    mount(detectBox, checking ? h("div", { class: "detect wait" }, h("span", { class: "spin", "aria-hidden": "true" }), " Reading your game…")
      : preview && !preview.ok ? badPanel()
        : preview && preview.ok && preview.games.length > 1 ? multiPanel(preview.games)
          : g ? singlePanel(g) : null);
    const many = preview && preview.ok && preview.games.length > 1;
    detailsGrid().classList.toggle("hidden", !!many);
    detailsSection.querySelector("#a-multi-note").classList.toggle("hidden", !many);
    side.classList.toggle("needs", !!g && !side.value);
    // Suggest my own tournament when the PGN's event looks like one of them.
    const m = g && g.match;
    const applied = m && (m.round_id ? String(roundSel.value) === String(m.round_id) : tournament.value === m.name);
    mount(suggestion, m && !applied ? h("div", { class: "suggest" },
      h("div", {}, h("div", { class: "small muted" }, "Possible match found"), h("b", {}, m.name), m.round ? h("span", { class: "muted" }, ` · Round ${m.round}`) : null),
      h("button", { class: "btn small", type: "button", onclick: () => {
        tournament.value = m.name; touched.add("event");
        if (m.round_id) { roundSel.value = String(m.round_id); touched.add("roundSel"); if (!touched.has("round")) round.value = m.round; }
        render();
      } }, "Use this tournament")) : null);
    dateNote.textContent = g && !g.date && g.month && !touched.has("date") ? `The PGN only says ${niceMonth(g.month)}; it's filed under that month.` : "";

    const r = readiness();
    barIcon.textContent = r.tone === "good" ? "✓" : r.tone === "bad" ? "!" : r.tone === "wait" ? "…" : r.tone === "warn" ? "?" : "♟";
    barIcon.className = `bar-icon ${r.tone}`;
    barTitle.textContent = r.title.replace(/^✓ /, "");
    barSub.textContent = r.sub;
    if (!busy) {
      submit.disabled = !r.ready; saveOnly.disabled = !r.ready;
      submit.replaceChildren(h("span", { "aria-hidden": "true" }, "🧠 "),
        !r.n || r.n === 1 ? "Add & Analyze Game" : r.n === preview.games.length ? `Analyze all ${r.n} games` : `Analyze ${r.n} games`,
        h("span", { "aria-hidden": "true" }, " →"));
    }
  }

  async function send(analyze) {
    if (busy) return;
    const r = readiness();
    if (!r.ready) return;
    busy = true; barError.classList.add("hidden");
    submit.disabled = true; saveOnly.disabled = true;
    submit.replaceChildren(h("span", { class: "spin", "aria-hidden": "true" }), analyze ? " Starting analysis…" : " Saving…");
    const g = single();
    const body = { pgn: text.value, analyze, folder_id: +folder.value || null, event: tournament.value.trim(), round: round.value.trim(),
      event_game_id: +roundSel.value || null, notation_id: active ? active.id : null };
    const pgnDate = g ? !!(g.date || g.month) : false;
    if (g) {
      // Only what was typed or changed here goes back: the PGN's own names, ratings and result stay exactly as they are.
      Object.assign(body, { color: side.value || "auto",
        opponent: touched.has("opponent") || !g[side.value === "white" ? "black" : "white"] ? opponent.value.trim() : "",
        opponent_rating: touched.has("oppRating") || !g[`${side.value === "white" ? "black" : "white"}_elo`] ? +oppRating.value || null : null,
        result: touched.has("result") || g.result === "*" ? absResult(result.value, side.value) : "" });
      // The PGN's own date wins unless the date was changed here; with no date at all, the chosen day is used
      // (or the tournament's month for a round, as before).
      if (touched.has("date") || (!pgnDate && !roundSel.value)) Object.assign(body, { date: date.value, prefer_pgn_date: false });
    } else {
      Object.assign(body, { include: [...multi.include], sides: multi.sides.map((s) => s || "auto"), prefer_pgn_date: true });
      if (touched.has("date")) body.date = date.value;
    }
    try {
      const res = await api("/api/games", { method: "POST", body });
      await loadSections();
      if (res.skipped.length && !res.games.length) throw new Error(res.skipped.join(" · "));
      if (photos.pending.length && res.games.length === 1) {
        let sent = 0;
        for (const x of photos.pending) {
          try { await uploadPhoto(`/api/games/${res.games[0].id}/scoresheets`, x.file); sent += 1; }
          catch (err) { toast(err.message); break; }
        }
        if (sent) toast(`${sent} scoresheet photo${sent === 1 ? "" : "s"} saved with the game.`);
      }
      if (active && res.games.length === 1) {
        toast("The saved scoresheet is now kept with the game. Open it from the game's Scoresheet button.");
      } else if (photos.pending.length) {
        toast("Several games were added, so the photos weren't attached. Open a game and use its Scoresheet button.");
      }
      const n = res.games.length;
      toast(analyze ? `${n} game${n === 1 ? "" : "s"} added. Your coach is analyzing ${n === 1 ? "it" : "them"} now.` : `${n} game${n === 1 ? "" : "s"} saved. Analyze any time from the game page.`);
      go(n === 1 ? `/game/${res.games[0].id}` : "/");
    } catch (err) {
      busy = false;
      barError.textContent = err.message; barError.classList.remove("hidden");
      render();
    }
  }
  submit.addEventListener("click", () => send(true));
  saveOnly.addEventListener("click", () => send(false));

  const actionBar = h("div", { class: "action-bar", role: "region", "aria-label": "Add and analyze" },
    h("div", { class: "row", style: "gap:12px;flex-wrap:nowrap;min-width:0;flex:1" }, barIcon, h("div", { style: "min-width:0" }, barTitle, barSub)),
    h("div", { class: "bar-actions" }, submit, saveOnly),
    barError);

  // ---- ③ what the coach looks for ----
  const coachSection = h("section", { class: "stack-s", "aria-labelledby": "h-coach" },
    h("div", { class: "step-h" }, h("span", { class: "step-n", "aria-hidden": "true" }, "3"), h("h2", { id: "h-coach" }, "What your coach will look for")),
    h("div", { class: "coach-grid" }, COACH.map(([ic, t, d]) => h("div", { class: "coach-item" },
      h("span", { class: "coach-ic", "aria-hidden": "true" }, ic), h("div", {}, h("b", {}, t), h("div", { class: "small muted" }, d))))),
    h("div", { class: "engine-note" }, h("b", {}, "More than a best-move engine. "),
      "Your coach explains what went wrong, what you should have noticed, and how to recognize similar positions next time."));

  const page = h("div", { class: "addg stack" },
    h("header", { class: "page-h" }, h("div", {},
      h("div", { class: "row", style: "gap:10px;align-items:center" }, h("h1", { style: "margin:0" }, "Add a game"), h("span", { class: "coach-badge" }, "COACH ANALYSIS")),
      h("p", {}, "Import your game and let your personal coach find the mistakes, missed opportunities, and patterns that will help you improve."))),
    savedBox,
    h("section", { class: "card add-main stack", "aria-labelledby": "h-add" },
      h("div", {}, h("div", { class: "step-h" }, h("span", { class: "step-n", "aria-hidden": "true" }, "1"), h("h2", { id: "h-add" }, "Add your game")),
        h("p", { class: "muted small", style: "margin:4px 0 0 40px" }, "Paste a PGN, upload a game, enter the moves on a board, or upload a photo of your scoresheet.")),
      tabs, panes.paste, panes.upload, panes.board, panes.notation, refSlot, detectBox),
    detailsSection,
    coachSection,
    actionBar, lightbox);
  // Opening straight on a round (from the Tournaments page) starts with it chosen.
  if (roundSel.value) roundSel.dispatchEvent(new Event("change"));
  touched.delete("roundSel");
  await loadSaved();
  if (query.mode === "notation") setMode("notation");
  render();
  page.cleanup = () => { stopWatching(); clearTimeout(timer); document.removeEventListener("keydown", onEsc); };
  return page;
}

/** Scoresheet photos picked on this page (up to 6): sent with the game, or saved for later. */
function photoPicker(onChange = () => {}) {
  const pending = [];
  const previews = h("div", { style: "display:flex;gap:10px;flex-wrap:wrap" });
  const input = h("input", { type: "file", accept: "image/*", multiple: true, style: "display:none", "aria-label": "Scoresheet photos" });
  const btn = h("button", { class: "btn primary", type: "button", id: "a-photo-btn", onclick: () => input.click() }, icon("camera"), "Take or choose photos");
  const render = () => {
    mount(previews, pending.map((p, i) => h("div", { style: "position:relative" },
      h("img", { src: p.preview, alt: `Scoresheet photo ${i + 1}`, style: "width:120px;height:160px;object-fit:cover;border-radius:10px;border:1px solid var(--line-2);display:block" }),
      h("button", { type: "button", class: "icon-btn", "aria-label": `Remove photo ${i + 1}`, title: "Remove",
        style: "position:absolute;top:4px;right:4px;background:var(--surface);border-radius:99px;width:24px;height:24px",
        onclick: () => { pending.splice(i, 1); render(); } }, icon("x")))));
    btn.disabled = pending.length >= 6;
    onChange();
  };
  input.addEventListener("change", () => {
    for (const f of [...input.files].slice(0, 6 - pending.length)) {
      const item = { file: f, preview: "" };
      pending.push(item);
      // Previews as data: URLs (the page's security policy doesn't allow blob: images).
      const reader = new FileReader();
      reader.onload = () => { item.preview = reader.result; render(); };
      reader.readAsDataURL(f);
    }
    input.value = "";
    render();
  });
  const el = h("div", { class: "stack-s" },
    h("div", { class: "row", style: "gap:10px" }, btn, input, h("span", { class: "small muted" }, "Up to 6 photos. Private to you.")),
    previews);
  const clear = () => { pending.splice(0, pending.length); render(); };
  return { el, pending, clear };
}
