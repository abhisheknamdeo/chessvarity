import { h, icon, pct, ring, meter, level, outcomeText, fmtDate, toast, uscfUrl } from "../dom.js";
import { api } from "../api.js";
import { state, currentPlayer } from "../state.js";
import { seriesChart } from "../charts.js";
import { go } from "../router.js";
import { empty, emptyState, trainHref } from "../components.js";
import { puzzleRunner } from "../puzzle.js";
import { confetti } from "../fun.js";

const PHASE = { opening: "Opening", middlegame: "Middlegame", endgame: "Endgame" };
const RANK_PIECE = ["wP", "wN", "wB", "wR", "wQ", "wK"];

function kpi(label, value, detail, tone, ic) {
  return h("div", { class: "card kpi" }, h("div", { class: "kpi-ic" }, icon(ic || "chart")), h("div", { class: "l" }, label), h("div", { class: "v" }, value), detail ? h("div", { class: `d ${tone || "muted"}` }, detail) : null);
}

const AI_KEY = "cc-ai-dismissed";
const aiDismissed = () => { try { return localStorage.getItem(AI_KEY) === "1"; } catch (_) { return false; } };

/** What's coming: AI features, clearly marked as not here yet. Can be closed for good. */
function aiCard() {
  if (aiDismissed()) return null;
  const card = h("div", { class: "card ai-card stack-s" });
  card.append(
    h("div", { class: "row", style: "justify-content:space-between;gap:8px;flex-wrap:nowrap" },
      h("h3", { style: "margin:0" }, "✨ AI is coming to Chess Varsity"),
      h("div", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, h("span", { class: "pill warn" }, "Coming soon"),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Close this announcement", title: "Close", onclick: () => {
          try { localStorage.setItem(AI_KEY, "1"); } catch (_) { /* closed for this visit only */ }
          card.remove();
        } }, icon("x")))),
    h("p", { class: "small", style: "margin:0" }, "Today your coaching comes from Stockfish and chess rules, so the same game always gets the same advice. Next, we're adding AI to make it even more personal:"),
    h("ul", { class: "dots small" },
      h("li", {}, "Ask the AI coach about any position or move, and get an answer at your level"),
      h("li", {}, "Plain-words explanations of your biggest mistakes and how to avoid them"),
      h("li", {}, "A personal training plan that adapts as you play")),
    h("p", { class: "small muted", style: "margin:0" }, "Chess Varsity is in beta. ", h("a", { href: "#/contact" }, "Tell us"), " what you'd like the AI to do."));
  return card;
}

// The player's full name: their own display name, or the USCF name when that is a fuller version of it.
function fullName(player) {
  const mine = state.user.display_name.trim();
  const uscf = ((player && player.uscf_name) || state.player?.uscf_name || "").trim();
  return uscf && !mine.includes(" ") && uscf.toLowerCase().startsWith(mine.toLowerCase()) ? uscf : mine;
}

/** The one most useful thing to do next, from what's already on the page. */
function nextStep(d, events, dailyEl) {
  for (const e of events) {
    const r = e.rounds.find((x) => !x.game_id && x.result);
    if (r) return h("a", { class: "btn hero-cta", href: `#/add?round=${r.id}` }, icon("plus"), `Enter moves for your ${e.name} games`);
  }
  if ((d.games || 0) < 3) return h("a", { class: "btn hero-cta", href: "#/add" }, icon("plus"), d.games ? "Add a game to unlock your patterns" : "Add your first game");
  if (dailyEl && dailyEl.dataset.solved !== "1") {
    return h("button", { class: "btn hero-cta", type: "button", onclick: () => dailyEl.scrollIntoView({ behavior: "smooth", block: "center" }) }, icon("puzzle"), "Solve today's puzzle");
  }
  return h("a", { class: "btn hero-cta", href: "#/roadmap" }, icon("flame"), "Continue your roadmap");
}

/** The top banner: rank, XP towards the next rank, streak, and the one next step. */
function heroCard(player, journey, cta) {
  const r = journey.rank, s = journey.streak;
  const bar = h("i", {}); bar.style.width = `${r.progress}%`;
  return h("div", { class: "card hero" },
    h("div", { class: "row spread", style: "position:relative;z-index:1" },
      h("div", { class: "row", style: "gap:18px;flex-wrap:nowrap" },
        h("div", { class: "rank-badge", title: `Rank: ${r.name}` }, h("img", { src: `/static/pieces/${RANK_PIECE[r.index]}.svg`, alt: "" })),
        h("div", {},
          h("div", { style: "font-size:1.25rem;font-weight:800;letter-spacing:-.01em" }, `Hello ${fullName(player)}`),
          h("h1", { style: "margin:2px 0 6px" }, `${r.name} rank`),
          h("div", { class: "xpbar", role: "img", "aria-label": `${journey.xp} experience points` }, bar),
          h("div", { class: "small", style: "opacity:.9;margin-top:4px" }, r.next ? `${journey.xp} XP · ${r.next.needed} more to become a ${r.next.name}` : `${journey.xp} XP · the highest rank!`))),
      h("div", { class: "row", style: "gap:10px" },
        s.current
          ? h("div", { class: "streak", title: s.today_done ? "You practiced today" : "Practice today to keep your streak" },
            h("span", { class: "flame on" }, icon("flame")), h("b", {}, s.current), h("span", { class: "small" }, s.current === 1 ? "day" : "days"))
          : h("span", { class: "streak-start", title: "Solve a puzzle or review a game to start one" }, icon("flame"), "Start a streak today"),
        cta)));
}

function daysUntil(pgnDate) {
  const [y, m, d] = (pgnDate || "").split(".").map(Number);
  if (!y || !m || !d) return null;
  const start = new Date(y, m - 1, d), today = new Date();
  return Math.round((start - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
}

/** Tournaments and USCF, right under the banner: rating, the next event, the latest result and rounds that still need moves. */
async function tournamentCard(player, events) {
  let uscf;
  try { uscf = await api("/api/uscf"); } catch (_) { return null; }
  const next = events.find((e) => e.kind === "upcoming");
  const last = events.find((e) => e.kind !== "upcoming");
  const waiting = events.flatMap((e) => e.rounds.filter((r) => !r.game_id && r.result).map((r) => ({ e, r })));
  const when = next ? daysUntil(next.start_date) : null;
  const block = (title, ...body) => h("div", { class: "stack-s", style: "min-width:200px;flex:1" }, h("div", { class: "small muted", style: "font-weight:700;text-transform:uppercase;letter-spacing:.05em" }, title), ...body);
  const ratings = Object.entries(uscf.ratings || {}).map(([k, v]) => h("span", { class: "pill brand" }, `${k[0].toUpperCase()}${k.slice(1)} ${v}`));
  return h("div", { class: "card tournament-card", id: "tournament-card" },
    h("div", { class: "row spread" },
      h("h2", { style: "margin:0" }, icon("calendar"), " Tournaments & USCF"),
      h("div", { class: "row", style: "gap:8px" }, h("a", { class: "btn small", href: "#/tournaments" }, "Open tournaments"), h("a", { class: "btn small", href: "#/stats" }, "My results"))),
    h("div", { class: "row", style: "align-items:flex-start;gap:24px;margin-top:12px" },
      uscf.uscf_id
        ? h("div", { class: "stack-s", style: "flex:1.25;min-width:min(290px,100%)" },
          h("div", { class: "row", style: "gap:10px;align-items:baseline;font-size:1.25rem;font-weight:800;font-variant-numeric:tabular-nums" },
            h("span", {}, "USCF ID"),
            h("a", { href: uscfUrl(uscf.uscf_id), target: "_blank", rel: "noopener", title: "Open this USCF profile", style: "letter-spacing:.5px" }, uscf.uscf_id)),
          ratings.length ? h("div", { class: "stack-s", style: "gap:4px" }, h("span", { class: "small muted" }, "Rating"), h("div", { class: "row", style: "gap:6px" }, ratings))
            : h("span", { class: "muted small" }, "Import to see ratings"),
          h("a", { class: "small", href: "#/tournaments" }, uscf.synced_at ? "Import the latest results" : "Import your tournaments"))
        : block("USCF ID", h("div", { class: "stack-s" }, h("span", { class: "muted small" }, "Save your USCF ID and import every tournament in one click."), h("a", { class: "btn small primary", href: "#/tournaments" }, icon("link"), "Connect USCF"))),
      block("Next tournament",
        next ? h("div", { class: "stack-s" }, h("b", {}, next.name), h("div", { class: "muted small" }, [next.start_date ? fmtDate(next.start_date) : "", when === null ? "" : when < 0 ? "under way" : when === 0 ? "today" : when === 1 ? "tomorrow" : `in ${when} days`].filter(Boolean).join(" · ")),
          h("div", { class: "row", style: "gap:6px" },
            next.plan.attending === "skip" ? h("span", { class: "pill gray" }, "Not going")
              : [["reg_status", "Registered"], ["hotel_status", "Hotel"], ["travel_status", "Travel"]].filter(([k]) => next.plan[k] !== "na").map(([k, t]) =>
                h("span", { class: `pill ${next.plan[k] === "done" ? "good" : "warn"}`, title: next.plan[k] === "done" ? "Done" : "Still to do" }, `${next.plan[k] === "done" ? "✓" : "⚑"} ${t}`))),
          h("a", { class: "small", href: `#/planner?event=${next.id}` }, "Open in the planner"))
          : h("div", { class: "stack-s" }, h("span", { class: "muted small" }, "Nothing coming up yet."), h("a", { class: "small", href: "#/tournaments" }, "Add the next tournament"))),
      block("Latest",
        last ? h("div", { class: "stack-s" }, h("b", {}, last.name), h("div", { class: "row", style: "gap:6px" }, h("span", { class: "pill gray", title: "Won-Drawn-Lost" }, `${last.wins}-${last.draws}-${last.losses}`),
          last.rating_before !== null && last.rating_after !== null && last.rating_before !== undefined ? h("span", { class: `pill ${last.rating_after >= last.rating_before ? "good" : "bad"}` }, `${last.rating_after >= last.rating_before ? "+" : ""}${last.rating_after - last.rating_before} rating`) : null))
          : h("span", { class: "muted small" }, "No tournaments played yet.")),
      waiting.length ? block("To do", h("div", { class: "stack-s" }, h("b", {}, `${waiting.length} game${waiting.length === 1 ? "" : "s"} need moves`),
        h("a", { class: "btn small primary", href: `#/add?round=${waiting[0].r.id}` }, icon("plus"), `Add moves: ${waiting[0].e.name}, round ${waiting[0].r.round}`))) : null));
}

const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const clock12 = (t) => { if (!t) return "all day"; const [hh, mm] = t.split(":").map(Number); return `${hh % 12 || 12}:${String(mm).padStart(2, "0")} ${hh < 12 ? "am" : "pm"}`; };

/** The next few training sessions, so a class or lesson is never a surprise. */
async function scheduleCard(player) {
  const from = new Date(), to = new Date();
  to.setDate(to.getDate() + 13);
  let occ;
  try { occ = await api(`/api/players/${player.id}/training/occurrences?start=${isoDay(from)}&end=${isoDay(to)}`); } catch (_) { return null; }
  const upcoming = occ.items.filter((o) => !o.skipped).slice(0, 4);
  const day = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); };
  return h("div", { class: "card schedule-card", id: "schedule-card" },
    h("div", { class: "row spread" }, h("h2", { style: "margin:0" }, "Training this fortnight"),
      h("div", { class: "row", style: "gap:8px" }, h("a", { class: "btn small", href: "#/training" }, "Training schedule"), h("a", { class: "btn small", href: "#/calendar" }, "Calendar"))),
    upcoming.length
      ? h("div", { class: "stack-s", style: "margin-top:10px" }, upcoming.map((o) => h("div", { class: "row", style: "gap:12px;flex-wrap:nowrap" },
        h("span", { class: "mono small", style: "min-width:8.5em" }, day(o.date)), h("span", { class: "small", style: "min-width:6em" }, clock12(o.start_time)),
        h("b", {}, o.title), h("span", { class: "muted small" }, [o.location, o.coach && `with ${o.coach}`].filter(Boolean).join(" · ")))))
      : h("p", { class: "muted", style: "margin:8px 0 0" }, "No training planned for the next two weeks. ", h("a", { href: "#/training" }, "Add a class, lesson or club night"), " and it shows here and on the calendar."));
}

const TILES = [
  ["/play", "wN", "Play the computer", "Spar at your level", "t-play"],
  ["/academy", "wR", "Attack academy", "Puzzles that teach attacking", "t-academy"],
  ["/models", "wB", "Model games", "300+ games with commentary", "t-model"],
  ["/openings", "wP", "Openings", "Learn variations and traps", "t-open"],
];

function tiles() {
  return h("div", { class: "grid g4 tiles" }, TILES.map(([href, ic, title, sub, cls]) =>
    h("a", { class: `tile ${cls}`, href: `#${href}` }, h("span", { class: "tile-ic" }, h("img", { src: `/static/pieces/${ic}.svg`, alt: "" })), h("b", {}, title), h("span", { class: "small" }, sub))));
}

async function dailyCard(player) {
  let daily, progress;
  try { [daily, progress] = await Promise.all([api("/api/library/academy/daily"), api(`/api/players/${player.id}/progress`)]); } catch (_) { return null; }
  const done = progress.solved.includes(daily.id);
  const sideText = daily.side === "white" ? "White" : "Black";
  const runner = puzzleRunner({ ...daily, prompt: `${sideText} to move` }, {
    orient: daily.side,
    onSolved: async () => { try { await api(`/api/players/${player.id}/puzzles/${daily.id}/solved`, { method: "POST" }); toast("+8 XP! Puzzle of the day solved"); } catch (_) { /* offline */ } },
  });
  return h("div", { class: "card daily", id: "daily-puzzle", "data-solved": done ? "1" : "0" },
    h("div", { class: "row spread" }, h("div", {}, h("span", { class: "pill brand" }, "Puzzle of the day"), h("h3", { style: "margin:8px 0 2px" }, daily.title)),
      done ? h("span", { class: "pill good" }, icon("check"), "Solved today") : h("span", { class: "pill warn" }, `${sideText} to move`)),
    h("p", { class: "muted small" }, daily.idea), h("div", { style: "max-width:380px" }, runner));
}

function badgeShelf(journey) {
  const card = (b) => {
    const bar = h("i", {}); bar.style.width = `${Math.round(100 * b.progress / b.target)}%`;
    return h("div", { class: `badge-card ${b.earned ? "earned" : ""}`, title: b.desc },
      h("img", { class: "b-ic", src: `/static/pieces/${b.icon}.svg`, alt: "" }), h("b", {}, b.title),
      h("span", { class: "small muted" }, b.earned ? "Earned!" : `${b.progress}/${b.target}`),
      b.earned ? null : h("div", { class: "meter", style: "height:6px" }, bar));
  };
  const earned = journey.badges.filter((b) => b.earned);
  const closest = journey.badges.filter((b) => !b.earned).sort((a, b) => b.progress / b.target - a.progress / a.target).slice(0, 2);
  const grid = h("div", { class: "badges" }, [...earned, ...closest].map(card));
  let all = false;
  const toggle = h("button", { class: "linkish small", type: "button", "aria-expanded": "false", onclick: () => {
    all = !all;
    grid.replaceChildren(...(all ? journey.badges : [...earned, ...closest]).map(card));
    toggle.textContent = all ? "Show fewer" : `View all badges (${journey.earned} of ${journey.badges.length})`;
    toggle.setAttribute("aria-expanded", String(all));
  } }, `View all badges (${journey.earned} of ${journey.badges.length})`);
  return h("div", { class: "card" },
    h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, "My badges"), h("span", { class: "pill brand" }, `${journey.earned} of ${journey.badges.length}`)),
    !earned.length ? h("p", { class: "small muted", style: "margin:6px 0 0" }, "Your closest badges. Earn them by playing, solving and reviewing.") : null,
    grid, h("div", { style: "margin-top:8px" }, toggle));
}

export async function dashboardView() {
  const player = currentPlayer();
  const [d, habits, journey] = await Promise.all([
    api(`/api/players/${player.id}/dashboard`),
    api(`/api/players/${player.id}/habits`),
    api(`/api/players/${player.id}/journey`),
  ]);
  document.title = "My dashboard · Chess Varsity";

  let events = [];
  try { events = await api(`/api/players/${player.id}/events`); } catch (_) { /* the page works without tournaments */ }
  const [daily, tCard, sCard] = await Promise.all([dailyCard(player), tournamentCard(player, events), scheduleCard(player)]);
  const hero = heroCard(player, journey, nextStep(d, events, daily));
  const notes = [];
  if (d.pending) notes.push(h("div", { class: "alert info" }, `${d.pending} game${d.pending > 1 ? "s are" : " is"} being analyzed. Numbers update when they finish (about a minute each).`));
  if (d.failed) notes.push(h("div", { class: "alert bad" }, `${d.failed} game${d.failed > 1 ? "s" : ""} could not be analyzed. Open ${d.failed > 1 ? "them" : "it"} from the sidebar to try again.`));

  if (!d.games) {
    return h("div", { class: "stack" }, hero, ...notes, tCard, sCard, tiles(),
      h("div", { class: "split-eq" }, h("div", { class: "card stack-s" }, h("h3", { style: "margin:0" }, "Your coaching starts with a game"),
        emptyState({ icon: "♟", title: "No analyzed games yet", text: "Paste a PGN, upload a file, snap a scoresheet or enter the moves on a board. Your coach finds the habits behind your mistakes.", progress: "0 of 3 games to unlock your patterns" })), daily),
      badgeShelf(journey), aiCard());
  }

  const rec = d.record;
  const change = d.accuracy.change;
  const kpis = h("div", { class: "grid g4" },
    kpi("Games analyzed", d.games, `${rec.wins + rec.draws + rec.losses} finished`, "muted", "chart"),
    kpi("Record", `${rec.wins}–${rec.draws}–${rec.losses}`, rec.score === null ? "" : `${rec.score}% score`, "muted", "trophy"),
    kpi("Average accuracy", pct(d.accuracy.average), change === null ? `Recent ${pct(d.accuracy.recent)}` : `${change >= 0 ? "▲" : "▼"} ${Math.abs(change)} vs earlier games`, change === null ? "muted" : change >= 0 ? "up" : "down", "target"),
    h("div", { class: "card focus-callout" },
      h("div", { class: "l" }, icon("flame"), " Focus"),
      h("b", { class: "fc-title" }, d.focus[0] ? d.focus[0].title : habits.ready ? "No weak habits right now" : "Patterns are on the way"),
      h("span", { class: "small muted" }, d.focus[0] ? `Score ${d.focus[0].score}/100 · your weakest habit right now` : habits.ready ? "Keep playing and reviewing to stay sharp." : "They appear after about 20 moves of analyzed games."),
      d.focus[0] || habits.ready ? h("a", { class: "btn small", href: "#/patterns", style: "align-self:flex-start;margin-top:auto" }, "See my patterns") : null));

  const points = d.series.filter((x) => x.accuracy !== null && x.accuracy !== undefined).length;
  const series = h("div", { class: "card" }, h("div", { class: "row spread" }, h("h3", {}, "My accuracy, game by game"),
    points >= 3 ? h("div", { class: "legend", style: "margin:0" }, h("span", {}, h("i", { style: "background:var(--good)" }), "win"), h("span", {}, h("i", { style: "background:var(--bad)" }), "loss"), h("span", {}, h("i", { style: "background:var(--faint)" }), "draw")) : null),
    points >= 3 ? seriesChart(d.series.map((x) => ({ ...x, label: x.label })), { onSelect: (p) => go(`/game/${p.game_id}`) })
      : emptyState({ icon: "📈", title: "Your accuracy trend appears after 3 analyzed games", progress: `${points} of 3 games` }));

  const focus = h("div", { class: "card" }, h("h3", {}, "What to work on"),
    d.focus.length ? h("div", { class: "stack-s" }, d.focus.map((f) => h("a", { href: "#/patterns", class: "row", style: "text-decoration:none;color:inherit;flex-wrap:nowrap;padding:6px 0" }, ring(f.score), h("div", {}, h("b", {}, f.headline), h("div", { class: "small muted" }, f.detail.split(". ")[0].replace(/\.$/, "") + "."))))) :
      habits.ready ? emptyState({ icon: "🏅", title: "No weak habits found", text: "Nice work! Keep adding games to stay on top of them." })
        : emptyState({ icon: "🔍", title: "Your habits appear after a few games", text: habits.message || "Add a few more games to see patterns." }),
    d.focus.length ? h("a", { class: "btn small", href: "#/patterns" }, "See all patterns") : null);

  const PHASE_NOTE = "Average winning-chance points lost per move. Lower is better.";
  const withData = Object.values(d.phases).filter((v) => v.moves).length;
  const phases = h("div", { class: "card" },
    h("h3", { class: "row", style: "gap:6px" }, "Where points are lost",
      h("span", { class: "info-tip", tabindex: "0", role: "img", "aria-label": PHASE_NOTE, title: PHASE_NOTE }, "ⓘ")),
    Object.entries(d.phases).map(([k, v]) => v.moves ? h("div", { class: "dual", style: "grid-template-columns:100px 1fr 50px" }, h("span", {}, PHASE[k]),
      meter(100 - Math.min(100, v.loss * 8), level(100 - Math.min(100, v.loss * 8))), h("span", { class: "small muted" }, v.loss)) : null),
    withData <= 1 ? emptyState({ icon: "⏳", title: "The other phases fill in as your games get longer", text: "Middlegames and endgames show here once your games reach them." }) : null);

  const colors = h("div", { class: "card" }, h("h3", {}, "White and Black"),
    ["white", "black"].map((c) => { const v = d.by_color[c]; return h("div", { class: "row spread", style: "padding:6px 0;border-bottom:1px solid var(--line)" }, h("span", {}, c === "white" ? "As White" : "As Black"), h("span", { class: "muted" }, v.games ? `${v.wins}–${v.draws}–${v.losses}` : "no games")); }),
    d.strengths.length ? h("div", { class: "callout lesson", style: "margin-top:12px" }, h("b", {}, "Strength: "), d.strengths[0].headline) : null);

  const recent = h("div", { class: "card" }, h("div", { class: "row spread" }, h("h3", {}, "My recent games")),
    h("div", { class: "game-rows" }, d.recent.map((g) => {
      const who = g.opponent ? h("b", {}, `vs ${g.opponent}`, g.opponent_rating ? h("span", { class: "muted", style: "font-weight:600" }, ` (${g.opponent_rating})`) : null) : g.event ? h("b", {}, g.event) : null;
      const meta = [g.date ? fmtDate(g.date) : "", g.opponent ? g.event : "", g.round ? `Round ${g.round}` : "", g.opening].filter(Boolean).join(" · ");
      return h("a", { class: "game-row", href: `#/game/${g.id}`, "aria-label": `${outcomeText(g.outcome) || "Game"}${g.opponent ? ` vs ${g.opponent}` : ""}${g.date ? `, ${fmtDate(g.date)}` : ""}` },
        g.outcome ? h("span", { class: `pill ${g.outcome === "win" ? "good" : g.outcome === "loss" ? "bad" : "gray"}` }, outcomeText(g.outcome)) : null,
        g.color ? h("span", { class: "gr-color", title: g.color === "white" ? "You played White" : "You played Black", "aria-hidden": "true" }, g.color === "white" ? "♔" : "♚") : null,
        h("div", { class: "gr-main" }, who, meta ? h("div", { class: "small muted" }, meta) : null),
        g.accuracy !== null && g.accuracy !== undefined ? h("span", { class: "gr-acc", title: "Accuracy" }, pct(g.accuracy)) : null);
    })));

  const plan = habits.recommendations && habits.recommendations.length ? h("div", { class: "card" }, h("h3", {}, "This week's plan"),
    h("div", { class: "stack-s" }, habits.recommendations.slice(0, 3).map((r) => h("div", { class: "callout" }, h("b", {}, r.title), h("div", { class: "small muted" }, (r.actions && r.actions[0]) || r.why),
      r.train && r.train[0] ? h("a", { class: "btn small", style: "margin-top:8px", href: trainHref(r.train[0]) }, r.train[0].label) : null)))) : null;

  return h("div", { class: "stack" }, hero, ...notes, tCard, sCard, tiles(), kpis,
    h("div", { class: "split" }, series, focus),
    h("div", { class: "split" }, plan || badgeShelf(journey), daily),
    plan ? badgeShelf(journey) : null,
    h("div", { class: "split-eq" }, phases, colors),
    recent, aiCard());
}
