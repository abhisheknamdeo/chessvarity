// The community: games other players shared (often with a question), replayed with their analysis, and discussed.
import { h, icon, mount, toast, pct } from "../dom.js";
import { api } from "../api.js";
import { drawBoard, arrowFrom } from "../board.js";
import { timelineChart } from "../charts.js";
import { askText, openDialog } from "../dialogs.js";
import { store } from "../state.js";
import { confetti } from "../fun.js";

const FILTERS = [["all", "All games"], ["questions", "Questions"], ["unanswered", "Unanswered"], ["mine", "My shared games"]];
const RESULT = { "1-0": "1–0", "0-1": "0–1", "1/2-1/2": "½–½", "*": "*" };

function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  const [n, u] = s < 3600 ? [s / 60, "minute"] : s < 86400 ? [s / 3600, "hour"] : s < 86400 * 30 ? [s / 86400, "day"] : [s / (86400 * 30), "month"];
  const k = Math.floor(n);
  return `${k} ${u}${k === 1 ? "" : "s"} ago`;
}

function moveLabel(moves, ply) {
  if (!ply) return "the start";
  const no = Math.ceil(ply / 2);
  return `${no}${ply % 2 ? "." : "…"} ${moves[ply - 1] ? moves[ply - 1].san : ""}`;
}

async function report(kind, id) {
  const reason = await askText({ title: "Report this", label: "What's wrong?", confirmLabel: "Report", maxlength: 300 });
  if (reason === null) return;
  try { await api("/api/community/report", { method: "POST", body: { kind, target_id: id, reason } }); toast("Thanks. An admin will take a look."); }
  catch (err) { toast(err.message); }
}

const LEVEL_TONES = ["gray", "gray", "brand", "brand", "good", "warn", "warn"];
function badge(lv) {
  if (!lv) return null;
  return h("span", { class: `pill ${LEVEL_TONES[lv.level - 1] || "gray"}`, style: "margin-left:6px", title: `Community level ${lv.level}: ${lv.name}` }, `${lv.name}`);
}

function card(s) {
  return h("a", { class: "card stack-s", href: `#/community/${s.id}`, style: "text-decoration:none;color:inherit" },
    h("div", { class: "row", style: "justify-content:space-between;gap:8px" },
      h("span", { class: "small" }, h("b", {}, s.author), badge(s.author_level), h("span", { class: "muted" }, ` · ${ago(s.updated_at)}`)),
      h("div", { class: "row", style: "gap:6px" },
        s.status === "hidden" ? h("span", { class: "pill bad" }, "Hidden by an admin") : null,
        s.question ? h("span", { class: "pill warn" }, "Question") : null)),
    s.question ? h("p", { style: "margin:0;font-weight:600" }, `“${s.question}”`) : null,
    h("div", {}, h("b", {}, `${s.white} vs ${s.black}`), h("span", { class: "muted" }, `  ${RESULT[s.result] || s.result}`)),
    h("div", { class: "small muted" }, [s.eco && s.opening ? `${s.eco} ${s.opening}` : s.opening, s.event, `${Math.ceil((s.plies || 0) / 2)} moves`,
      s.accuracy !== null && s.accuracy !== undefined ? `${pct(s.accuracy)} accuracy` : null].filter(Boolean).join(" · ")),
    h("div", { class: "row small muted", style: "gap:14px" },
      h("span", {}, icon("message"), ` ${s.comments} comment${s.comments === 1 ? "" : "s"}`),
      h("span", {}, s.liked ? "♥" : "♡", ` ${s.likes}`)));
}

function levelCard(me) {
  const pct = Math.round((me.progress || 0) * 100);
  return h("div", { class: "card stack-s" },
    h("div", { class: "row", style: "justify-content:space-between;gap:8px" },
      h("div", {}, h("div", { class: "small muted" }, "Your community level"),
        h("div", { style: "font-size:1.35rem;font-weight:800" }, `${me.name}`, h("span", { class: "muted", style: "font-size:.95rem;font-weight:600" }, `  · level ${me.level} of ${me.levels.length}`))),
      h("div", { style: "text-align:right" }, h("div", { style: "font-size:1.35rem;font-weight:800" }, `${me.points}`), h("div", { class: "small muted" }, me.rank ? `points · #${me.rank} overall` : "points"))),
    h("div", { role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": pct, "aria-label": "Progress to the next level",
      style: "height:10px;border-radius:99px;background:var(--line-2);overflow:hidden" },
      h("div", { style: `height:100%;width:${pct}%;background:var(--brand);border-radius:99px` })),
    h("div", { class: "small muted" }, me.next_name ? `${me.next_at - me.points} more points to reach ${me.next_name}.` : "Top level reached. You're a Grandmaster of the community!"),
    h("details", { class: "small" }, h("summary", { style: "cursor:pointer;color:var(--brand);font-weight:600" }, "How to earn points"),
      h("ul", { class: "dots", style: "margin:8px 0" }, me.how_to_earn.map((r) => h("li", {}, `${r.what}: +${r.points}`))),
      h("div", { class: "muted" }, "Liking your own posts doesn't count, and up to 5 shares and 10 comments a day earn points."),
      h("div", { class: "row", style: "gap:6px;margin-top:8px" }, me.levels.map((l) => h("span", { class: `pill ${l.level <= me.level ? "brand" : "gray"}` }, `${l.name} ${l.at}+`)))));
}

function leaderboardCard() {
  const body = h("div", { class: "stack-s" });
  let period = "month";
  const tabs = h("div", { class: "tabs", role: "tablist", style: "align-self:flex-start" });
  const load = async () => {
    mount(tabs, [["month", "This month"], ["all", "All time"]].map(([k, t]) => h("button", { role: "tab", "aria-selected": period === k ? "true" : "false", onclick: () => { period = k; load(); } }, t)));
    const r = await api(`/api/community/leaderboard?period=${period}`);
    mount(body, r.leaders.length ? h("ol", { style: "margin:0;padding-left:1.4em" }, r.leaders.slice(0, 10).map((l) => h("li", { style: `padding:3px 0;${l.me ? "font-weight:700" : ""}` },
      h("span", {}, l.name, l.me ? " (you)" : ""), h("span", { class: "muted small" }, ` · ${l.level} · ${l.points} pts`))))
      : h("p", { class: "muted", style: "margin:0" }, period === "month" ? "No points yet this month. Share a game or answer a question to lead!" : "No points yet."));
  };
  load();
  return h("div", { class: "card stack-s" }, h("div", { class: "row", style: "justify-content:space-between;gap:8px" }, h("h3", { style: "margin:0" }, "Top helpers"), tabs), body);
}

/** Ask the community about one of my analysed games. */
async function askDialog() {
  const { games } = await api("/api/community/my-games");
  const shareId = await openDialog((done) => {
    if (!games.length) {
      return h("div", { class: "stack" }, h("h2", { style: "margin:0" }, "Ask the community"),
        h("p", {}, "Questions are asked about one of your own games, so others can replay it with you. Add a game first; once its analysis is ready, come back here."),
        h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: () => done(null) }, "Close"), h("a", { class: "btn primary", href: "#/add", onclick: () => done(null) }, "Add a game")));
    }
    const pick = h("select", { class: "select", id: "ask-game" }, games.map((g) => h("option", { value: g.id }, `${g.label}${g.detail ? ` · ${g.detail}` : ""}`)));
    const q = h("textarea", { class: "textarea", id: "ask-q", rows: 3, maxlength: 500, required: true, style: "font-family:inherit;font-size:.95rem;min-height:80px",
      placeholder: "e.g. Where did it go wrong? Was 12.Bxh7+ sound? How should I handle this opening?" });
    const opp = h("input", { type: "checkbox" });
    const msg = h("div", { class: "alert bad hidden" });
    return h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      if (!q.value.trim()) { q.focus(); return; }
      try {
        const r = await api(`/api/games/${pick.value}/share`, { method: "PUT", body: { question: q.value, show_opponent: opp.checked } });
        toast("Your question is up. You earned points for asking!");
        done(r.share.id);
      } catch (err) { msg.textContent = err.message; msg.classList.remove("hidden"); }
    } },
      h("h2", { style: "margin:0" }, "Ask the community"),
      h("p", { class: "muted small", style: "margin:0" }, "Pick the game your question is about. Others can replay it with the coach's analysis and answer."),
      h("div", { class: "field" }, h("label", { for: "ask-game" }, "Game"), pick),
      h("div", { class: "field" }, h("label", { for: "ask-q" }, "Your question"), q),
      h("label", { class: "small", style: "display:flex;gap:8px;align-items:center;cursor:pointer" }, opp, "Show my opponent's name and the tournament"),
      msg,
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"),
        h("button", { class: "btn primary", type: "submit" }, "Post my question")));
  });
  if (shareId) location.hash = `#/community/${shareId}`;
}

function celebrate(me) {
  // A little party the first time we notice a new level on this device.
  let seen = 0;
  try { seen = +store.get("cc-community-level") || 0; } catch (_) { /* private mode */ }
  if (seen && me.level > seen) { confetti(); toast(`Level up! You're now a ${me.name}.`); }
  if (me.level !== seen) store.set("cc-community-level", String(me.level));
}

async function feedView(query) {
  const filter = FILTERS.some(([k]) => k === query.filter) ? query.filter : "all";
  const list = h("div", { class: "grid g2" });
  const more = h("div", {});
  let page = 0;
  async function load() {
    const r = await api(`/api/community?filter=${filter}&page=${page}`);
    if (!page && !r.items.length) {
      mount(list, h("div", { class: "card", style: "grid-column:1/-1" }, h("h3", {}, filter === "mine" ? "You haven't shared a game yet" : "Nothing here yet"),
        h("p", { class: "muted", style: "margin:0" }, "Open one of your analyzed games (or a round on the Tournaments page) and press ", h("b", {}, "Share"), ". You can ask a question too.")));
      return;
    }
    list.append(...r.items.map(card));
    mount(more, r.more ? h("button", { class: "btn", onclick: () => { page += 1; load(); } }, "Show more") : null);
  }
  const [, me] = await Promise.all([load(), api("/api/community/me")]);
  celebrate(me);
  const askButton = () => h("button", { class: "btn primary", onclick: askDialog }, icon("message"), "Ask the community");
  return h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Community"),
      h("p", {}, "Games other players shared. Replay them with the coach's analysis, answer their questions, and learn from each other."))),
    h("div", { class: "grid g2" }, levelCard(me), leaderboardCard()),
    // The one "Ask the community" button, on every tab.
    h("div", { class: "callout row", style: "justify-content:space-between;gap:10px" },
      h("span", {}, icon("bulb"), " Stuck on a position or a move? Ask about one of your games and other players will help."), askButton()),
    h("div", { class: "tabs", role: "tablist" }, FILTERS.map(([k, t]) => h("a", { role: "tab", href: `#/community?filter=${k}`, "aria-selected": k === filter ? "true" : "false" }, t))),
    h("div", { class: "callout small" }, icon("shield"), " Be kind and helpful. Only your display name is shown. Use ", h("b", {}, "Report"), " if something isn't right."),
    list, more);
}

async function gameView(id) {
  let d = await api(`/api/community/${id}`);
  const playerWhite = d.color === "white";
  let ply = 0;
  const boardEl = h("div", { class: "board", style: "max-width:480px" });
  const chartBox = h("div", {});
  const note = h("div", { class: "small", style: "min-height:2.6em" });
  const moveList = h("div", { class: "steps", style: "max-height:160px;overflow:auto" });
  const commentsBox = h("div", { class: "stack-s" });
  const commentsTitle = h("h3", { style: "margin:0" });
  const aboutMove = h("input", { type: "checkbox" });
  const aboutLabel = h("span", {});
  const text = h("textarea", { class: "textarea", rows: 3, maxlength: 2000, style: "font-family:inherit;font-size:.95rem;min-height:80px",
    placeholder: d.question ? "Answer their question or share an idea…" : "Say something helpful about the game…" });
  const likeBtn = h("button", { class: "btn small" });

  function setPly(p) {
    ply = Math.max(0, Math.min(d.moves.length, p));
    const fen = ply ? d.moves[ply - 1].fen : d.start_fen;
    drawBoard(boardEl, fen, { orient: d.color, lastMove: ply ? d.moves[ply - 1].uci : null, arrows: ply ? [] : [] });
    if (d.timeline && d.timeline.length) mount(chartBox, timelineChart(d.timeline, { playerWhite, ply, onSelect: setPly }));
    const c = ply ? (d.commentary || []).find((x) => x.ply === ply) : null;
    mount(note, c ? [h("b", {}, `${moveLabel(d.moves, ply)}  `), c.text] : h("span", { class: "muted" }, ply ? "" : "Step through the game with ◀ ▶ or click a move."));
    [...moveList.children].forEach((b, i) => b.setAttribute("aria-current", i === ply - 1 ? "true" : "false"));
    aboutLabel.textContent = ply ? `About move ${moveLabel(d.moves, ply)}` : "About a move (step to it first)";
    aboutMove.disabled = !ply;
    if (!ply) aboutMove.checked = false;
  }

  function renderComments() {
    commentsTitle.textContent = `Comments (${d.comments.filter((c) => !c.hidden).length})`;
    mount(commentsBox, d.comments.length ? d.comments.map((c) => h("div", { class: "stack-s", style: `border-top:1px solid var(--line);padding-top:10px;${c.hidden ? "opacity:.55" : ""}` },
      h("div", { class: "row", style: "justify-content:space-between;gap:8px;flex-wrap:wrap" },
        h("span", { class: "small" }, h("b", {}, c.author), badge(c.author_level), c.by_sharer ? h("span", { class: "pill brand", style: "margin-left:6px" }, "Shared this game") : null,
          h("span", { class: "muted" }, ` · ${ago(c.created_at)}`), c.hidden ? h("span", { class: "pill bad", style: "margin-left:6px" }, "Hidden") : null),
        h("div", { class: "row", style: "gap:4px" },
          c.ply !== null && c.ply !== undefined ? h("button", { class: "chip", onclick: () => setPly(c.ply), title: "Show this move" }, moveLabel(d.moves, c.ply)) : null,
          c.can_delete ? h("button", { class: "btn small", onclick: async () => {
            if (!confirm("Delete this comment?")) return;
            await api(`/api/community/comments/${c.id}`, { method: "DELETE" }); d = await api(`/api/community/${id}`); renderComments();
          } }, "Delete") : null,
          !c.mine && !c.hidden ? h("button", { class: "btn small", "aria-pressed": c.marked ? "true" : "false", title: "Mark as helpful (gives them points)",
            "aria-label": `${c.marked ? "Unmark helpful" : "Mark helpful"} (${c.helpful})`, onclick: async () => {
              try { Object.assign(c, await api(`/api/community/comments/${c.id}/helpful`, { method: "POST" })); renderComments(); } catch (err) { toast(err.message); }
            } }, `👍 ${c.helpful || ""}`.trim()) : c.helpful ? h("span", { class: "small muted" }, `👍 ${c.helpful}`) : null,
          !c.mine ? h("button", { class: "btn small", onclick: () => report("comment", c.id) }, "Report") : null)),
      h("p", { style: "margin:0;white-space:pre-wrap" }, c.body)))
      : h("p", { class: "muted", style: "margin:0" }, d.question ? "No answers yet. Be the first to help!" : "No comments yet."));
  }

  function renderLike() {
    mount(likeBtn, d.liked ? "♥" : "♡", ` ${d.likes}`);
    likeBtn.setAttribute("aria-pressed", d.liked ? "true" : "false");
    likeBtn.title = d.liked ? "Unlike" : "Like this game";
    likeBtn.setAttribute("aria-label", `${d.liked ? "Unlike" : "Like this game"} (${d.likes} like${d.likes === 1 ? "" : "s"})`);
  }
  likeBtn.addEventListener("click", async () => {
    try { Object.assign(d, await api(`/api/community/${id}/like`, { method: "POST" })); renderLike(); } catch (err) { toast(err.message); }
  });

  moveList.append(...d.moves.map((m, i) => h("button", { class: "step", onclick: () => setPly(i + 1) }, i % 2 === 0 ? `${i / 2 + 1}. ${m.san}` : m.san)));
  const send = h("button", { class: "btn primary", type: "submit" }, "Post comment");
  const form = h("form", { class: "stack-s", onsubmit: async (e) => {
    e.preventDefault();
    if (!text.value.trim()) return;
    send.disabled = true;
    try {
      d = await api(`/api/community/${id}/comments`, { method: "POST", body: { body: text.value, ply: aboutMove.checked ? ply : null } });
      text.value = ""; aboutMove.checked = false; renderComments();
    } catch (err) { toast(err.message); }
    send.disabled = false;
  } }, text, h("label", { class: "small muted", style: "display:flex;gap:6px;align-items:center;cursor:pointer" }, aboutMove, aboutLabel), h("div", {}, send));

  document.addEventListener("keydown", onKey);
  function onKey(e) {
    if (e.target.closest && e.target.closest("input,textarea,select")) return;
    if (e.key === "ArrowLeft") setPly(ply - 1);
    if (e.key === "ArrowRight") setPly(ply + 1);
  }

  setPly(0); renderComments(); renderLike();
  const node = h("div", { class: "stack" },
    h("div", { class: "row", style: "gap:8px" }, h("a", { class: "btn small", href: "#/community" }, "← Community")),
    h("div", { class: "split-lib" },
      h("div", { class: "stack-s" }, boardEl,
        h("div", { class: "row", style: "gap:6px" },
          h("button", { class: "btn small", "aria-label": "First move", onclick: () => setPly(0) }, "⏮"),
          h("button", { class: "btn small", "aria-label": "Previous move", onclick: () => setPly(ply - 1) }, "◀"),
          h("button", { class: "btn small", "aria-label": "Next move", onclick: () => setPly(ply + 1) }, "▶"),
          h("button", { class: "btn small", "aria-label": "Last move", onclick: () => setPly(d.moves.length) }, "⏭")),
        chartBox, moveList,
        h("div", { class: "card", style: "padding:12px" }, h("div", { class: "small muted", style: "margin-bottom:4px" }, `Coach's note (written for ${d.author})`), note)),
      h("div", { class: "stack" },
        h("div", { class: "card stack-s" },
          h("div", { class: "row", style: "justify-content:space-between;gap:8px" },
            h("span", { class: "small" }, "Shared by ", h("b", {}, d.author), badge(d.author_level), h("span", { class: "muted" }, ` · ${ago(d.created_at)}`)),
            h("div", { class: "row", style: "gap:6px" }, likeBtn, !d.mine ? h("button", { class: "btn small", onclick: () => report("share", d.id) }, "Report") : null)),
          d.status === "hidden" ? h("div", { class: "alert bad" }, "Hidden by an admin: only you (and admins) can see this.") : null,
          d.question ? h("p", { style: "margin:0;font-size:1.1rem;font-weight:650" }, `“${d.question}”`) : null,
          h("div", {}, h("b", {}, `${d.white} vs ${d.black}`), h("span", { class: "muted" }, `  ${RESULT[d.result] || d.result}`)),
          h("div", { class: "small muted" }, [d.eco && d.opening ? `${d.eco} ${d.opening}` : d.opening, d.event,
            d.accuracy !== null && d.accuracy !== undefined ? `${pct(d.accuracy)} accuracy for ${d.author}` : null].filter(Boolean).join(" · ")),
          d.headline ? h("div", { class: "callout small" }, icon("bulb"), " ", d.headline) : null),
        h("div", { class: "card stack-s" }, commentsTitle, commentsBox),
        h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, "Add a comment"), form))));
  node.cleanup = () => document.removeEventListener("keydown", onKey);
  return node;
}

export async function communityView({ id }, query) {
  document.title = "Community · Chess Varsity";
  return id ? gameView(id) : feedView(query || {});
}
