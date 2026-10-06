// For parents: a guided journey to a rated tournament (join US Chess, find, register, play, review) plus
// "good to know" topics. Steps tick themselves from what the family has already done in the app.
import { h, icon, mount, fmtDate } from "../dom.js";
import { api } from "../api.js";
import { state, currentPlayer } from "../state.js";

const STATUS = { reg_status: "Registered", paid_status: "Entry fee paid", hotel_status: "Hotel booked", travel_status: "Travel sorted" };
const PACK = ["USCF ID (and proof of membership if just renewed)", "Chess set and clock, if the event asks for them", "Two pens or pencils",
  "Water and snacks", "A sweater: playing halls are often cold", "Something quiet to do between rounds"];
const PACK_KEY = "cc-pack";

const ext = (href, text) => h("a", { href, target: "_blank", rel: "noopener" }, text, " ↗");
const steps = (items) => h("ol", { class: "pj-steps" }, items.map(([t, d]) => h("li", {}, h("b", {}, t), d ? h("span", { class: "muted" }, " ", d) : null)));
const facts = (items) => h("ul", { class: "pj-facts" }, items.map(([t, d]) => h("li", {}, h("b", {}, t), " ", h("span", { class: "muted" }, d))));
const tip = (text) => h("div", { class: "pj-tip" }, h("span", { "aria-hidden": "true" }, "💡"), h("span", {}, text));
const appCard = (title, text, ...actions) => h("aside", { class: "pj-app" },
  h("div", { class: "pj-app-h" }, h("img", { src: "/static/logo.svg", alt: "", width: 22, height: 22 }), "In Chess Varsity"),
  h("b", {}, title), h("p", { class: "small muted", style: "margin:0" }, text), h("div", { class: "pj-app-actions" }, actions));

function readPack() { try { return new Set(JSON.parse(localStorage.getItem(PACK_KEY) || "[]")); } catch (_) { return new Set(); } }
function writePack(set) { try { localStorage.setItem(PACK_KEY, JSON.stringify([...set])); } catch (_) { /* a private window: ticks just aren't remembered */ } }

export async function parentsView({ tab } = {}) {
  document.title = "Parents · Chess Varsity";
  const player = currentPlayer();
  let events = [];
  try { events = await api(`/api/players/${player.id}/events`); } catch (_) { /* the guide works without it */ }
  const upcoming = events.filter((e) => e.kind === "upcoming" && e.plan.attending !== "skip");
  const next = upcoming[0];
  const games = state.sections.reduce((n, s) => n + s.games.length, 0);
  const pack = readPack();
  const uscfId = player.uscf_id || (state.player && state.player.uscf_id) || "";

  // The journey. `done` comes from what the family has already done in the app.
  const JOURNEY = [
    { key: "join", n: 1, ic: "🪪", title: "Join US Chess", short: "Join", done: !!uscfId },
    { key: "find", n: 2, ic: "🔎", title: "Find a tournament", short: "Find", done: upcoming.length > 0 },
    { key: "register", n: 3, ic: "📝", title: "Register", short: "Register", done: !!next && next.plan.reg_status === "done" },
    { key: "day", n: 4, ic: "🎒", title: "Tournament day", short: "Game day", done: PACK.every((_, i) => pack.has(i)) },
    { key: "after", n: 5, ic: "🧠", title: "After the games", short: "Review", done: games > 0 },
  ];
  const EXTRAS = [
    { key: "rules", ic: "⚖️", title: "Rules" }, { key: "ratings", ic: "📈", title: "Ratings" },
    { key: "support", ic: "💛", title: "Supporting your player" }, { key: "faq", ic: "❓", title: "Questions" },
  ];
  const ALL = [...JOURNEY, ...EXTRAS];
  let current = ALL.some((s) => s.key === tab) ? tab : (JOURNEY.find((s) => !s.done) || JOURNEY[0]).key;

  // ---- what each step says ----
  function tournamentStatus() {
    if (!upcoming.length) return null;
    return h("div", { class: "pj-mine" }, h("div", { class: "pj-mine-h" }, "Your upcoming tournaments"),
      ...upcoming.slice(0, 3).map((e) => h("div", { class: "pj-event" },
        h("div", { style: "min-width:0;flex:1" }, h("b", {}, e.name),
          h("div", { class: "small muted" }, [e.start_date ? fmtDate(e.start_date) : "Date not set",
            e.days_until !== null && e.days_until >= 0 ? (e.days_until === 0 ? "today" : `in ${e.days_until} day${e.days_until === 1 ? "" : "s"}`) : "",
            e.deadline_in !== null && e.deadline_in >= 0 && e.plan.reg_status !== "done" ? `register within ${e.deadline_in} day${e.deadline_in === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · "))),
        h("div", { class: "row", style: "gap:6px" }, Object.entries(STATUS).filter(([k]) => e.plan[k] !== "na").map(([k, t]) =>
          h("span", { class: `pill ${e.plan[k] === "done" ? "good" : "warn"}` }, `${e.plan[k] === "done" ? "✓" : "⚑"} ${t}`))),
        h("a", { class: "btn small", href: `#/planner?event=${e.id}` }, Object.keys(STATUS).some((k) => e.plan[k] === "todo") ? "Finish" : "Open"))));
  }

  function packingList() {
    const box = h("div", { class: "pj-pack" });
    const paint = () => mount(box, PACK.map((item, i) => h("label", { class: `pj-check${pack.has(i) ? " on" : ""}` },
      h("input", { type: "checkbox", checked: pack.has(i), onchange: (e) => {
        if (e.target.checked) pack.add(i); else pack.delete(i);
        writePack(pack); paint();
        JOURNEY[3].done = PACK.every((_, j) => pack.has(j)); paintNav(); paintKicker();
      } }), h("span", {}, item))),
      h("button", { class: "linkish small", type: "button", onclick: () => { pack.clear(); writePack(pack); paint(); JOURNEY[3].done = false; paintNav(); paintKicker(); } }, "Clear the list for the next tournament"));
    paint();
    return box;
  }

  function content(key) {
    switch (key) {
      case "join": return [
        h("p", { class: "pj-lead" }, "Rated tournaments in the US run under US Chess (also called USCF). Every player needs a current membership, which comes with an 8-digit ", h("b", {}, "USCF ID"), ". The ID stays the same for life."),
        steps([
          ["Join or renew at US Chess.", "Choose a youth or scholastic membership for a child. Many tournaments also let you join when you register."],
          ["Write the ID down.", "Every entry form asks for it. It's on the membership card and the player's US Chess page."],
          ["Save it in Chess Varsity.", "Do it once and every rated tournament, round, opponent and result fills in by itself."],
        ]),
        tip("Membership has to be current on the day of the tournament. Check the expiry date before you register."),
      ];
      case "find": return [
        h("p", { class: "pj-lead" }, "Start small: a one-day event with shorter games is the friendliest first tournament."),
        facts([
          ["US Chess listings:", "search by state and date (the Tournament Life Announcements)."],
          ["Your chess club or school club:", "they know the scholastic events nearby, and many run monthly rated quads."],
          ["State chess association:", "runs the state scholastic championships."],
          ["Good first events:", "a scholastic tournament (grouped by grade or rating) or a quad (four similar players, three games)."],
        ]),
        h("div", {}, ext("https://new.uschess.org/upcoming-tournaments", "Browse upcoming tournaments")),
        tip("Once you've picked one, add it here. Its dates and registration deadline then show up on your calendar."),
      ];
      case "register": return [
        h("p", { class: "pj-lead" }, "Most entries are online. Here's what the form asks, in plain words."),
        steps([
          ["Section.", "Sections are by rating (like Under 1000) or grade. Players can enter their own section or \"play up\" in a stronger one, but not a lower one."],
          ["Time control.", "Written like G/45;d5: 45 minutes each, with a 5-second delay per move."],
          ["Deadline and fee.", "Online entry usually closes a day or two before, and fees often rise near the date."],
          ["Byes.", "A half-point bye lets a player skip a round and still score half a point. Ask in advance."],
          ["Hotel.", "Big events have a tournament hotel at a reduced rate that sells out early."],
        ]),
        tournamentStatus(),
      ];
      case "day": return [
        h("p", { class: "pj-lead" }, "Arrive 30–45 minutes early, check in at the front desk, and find the pairings sheet before each round. It shows the board and the color."),
        h("div", { class: "pj-sub" }, "Packing list"),
        packingList(),
        tip("Players report each result to the tournament director (TD) and keep their scoresheet. Snap a photo of it in the app so it's never lost."),
      ];
      case "after": return [
        h("p", { class: "pj-lead" }, "The games are where the learning is. A few minutes after each tournament makes the next one better."),
        steps([
          ["Add each game.", "Paste or type the moves, or snap the scoresheet now and enter the moves later."],
          ["Let the coach analyze them.", "It finds the mistakes, the missed chances and the habits that keep coming back."],
          ["Follow the roadmap.", "It turns those habits into the next three things to practice."],
        ]),
        tip("After a tough loss, give it a day before going through the game together."),
      ];
      case "rules": return [facts([
        ["Touch-move:", "a piece touched on purpose must be moved, if it can be."],
        ["Writing the moves:", "required in longer games; usually not in quick games (under 30 minutes). Check the event's rules."],
        ["Parents wait outside:", "parents and coaches can't be in the playing area during games, and players can't get help."],
        ["Questions go to the TD:", "if something goes wrong, the player stops the clock and raises a hand."],
        ["Phones:", "off or outside the playing hall. A ringing phone can cost the game."],
      ])];
      case "ratings": return [facts([
        ["Regular, Quick, Blitz:", "separate ratings for different game lengths. Dual-rated events change two."],
        ["Provisional:", "a new player's rating moves a lot for the first games, then settles."],
        ["When it updates:", "a few days after the event is sent to US Chess. Re-import in the app to see the change for each tournament."],
        ["Ups and downs:", "a tough event against stronger players can drop the rating and still be great practice."],
      ]), h("div", {}, h("a", { href: "#/tournaments" }, "See the rating after every tournament →"))];
      case "support": return [h("ul", { class: "pj-hearts" }, [
        "Praise effort and good decisions, not just results.",
        "After a loss, ask what they noticed rather than telling them.",
        "Keep the routine simple: sleep, breakfast, water and a snack.",
        "A little tactics most days beats one long session a week.",
        "Celebrate milestones: ratings, ranks and roadmap topics completed.",
      ].map((t) => h("li", {}, t)))];
      case "faq": return [h("div", { class: "pj-faq" }, [
        ["My child has no rating. Can they play?", "Yes. They're \"unrated\" for the first event and get a provisional rating afterwards. Many events have sections for new players."],
        ["How long is a tournament day?", "It depends on the time control and the rounds. A five-round scholastic with G/30 games often takes most of the day; a quad, a morning or an afternoon."],
        ["Do we need our own set and clock?", "At many US events, yes: the announcement says so. A tournament set and a digital clock with delay are a good investment."],
        ["What if we need to leave early?", "Tell the tournament director before the next round's pairings. Asking for a bye in advance is better still."],
        ["Is the app free?", "Yes. Chess Varsity is free to use."],
      ].map(([q, a]) => h("details", {}, h("summary", {}, q), h("p", { class: "muted", style: "margin:8px 0 0" }, a))))];
      default: return [];
    }
  }

  // The "do it in the app" card beside each step.
  function action(key) {
    switch (key) {
      case "join": return appCard(uscfId ? `USCF ID ${uscfId} is saved` : "Save the USCF ID",
        uscfId ? "Tournaments, rounds and ratings import from US Chess." : "Your tournaments, opponents, results and rating then fill in by themselves.",
        h("a", { class: "btn small primary", href: "#/tournaments" }, uscfId ? "Open Tournaments & USCF" : "Save the ID"),
        ext("https://new.uschess.org/join-us-chess", "Join or renew"));
      case "find": return appCard(upcoming.length ? `${upcoming.length} upcoming tournament${upcoming.length === 1 ? "" : "s"}` : "Add the tournament you picked",
        "The planner tracks registration, the fee, hotel and travel, and puts the deadline on your calendar.",
        h("a", { class: "btn small primary", href: "#/planner" }, icon("plus"), "Add a tournament"), h("a", { class: "btn small", href: "#/calendar" }, "Calendar"));
      case "register": return appCard(next ? (next.plan.reg_status === "done" ? `Registered for ${next.name}` : `Register for ${next.name}`) : "No tournament yet",
        next ? "Tick each item in the planner as you go, so nothing is forgotten." : "Add a tournament first, then come back here.",
        h("a", { class: "btn small primary", href: next ? `#/planner?event=${next.id}` : "#/planner" }, icon("flag"), next ? "Open in the planner" : "Add a tournament"));
      case "day": return appCard("Prepare the week before", "The tournament plan suggests openings to bring and counts down to the first round.",
        h("a", { class: "btn small primary", href: next ? `#/prep?event=${next.id}` : "#/prep" }, "Tournament plan"), h("a", { class: "btn small", href: "#/add?mode=notation" }, icon("camera"), "Scoresheet photo"));
      case "after": return appCard(games ? `${games} game${games === 1 ? "" : "s"} added` : "Add the first game", "Your coach reviews every move and updates the roadmap.",
        h("a", { class: "btn small primary", href: "#/add" }, icon("plus"), "Add a game"), h("a", { class: "btn small", href: "#/roadmap" }, "Roadmap"));
      default: return null;
    }
  }

  // ---- layout ----
  const nav = h("div", { class: "pj-nav" });
  const extrasNav = h("div", { class: "pj-extras", role: "tablist", "aria-label": "Good to know" });
  const panel = h("section", { class: "pj-panel card", role: "tabpanel", tabindex: "-1" });
  const progress = h("div", { class: "pj-progress" });
  const kicker = h("div", { class: "pj-kicker" });

  function paintNav() {
    const n = JOURNEY.filter((s) => s.done).length;
    mount(progress, h("div", { class: "pj-bar", role: "progressbar", "aria-label": "Journey progress", "aria-valuenow": n, "aria-valuemin": 0, "aria-valuemax": JOURNEY.length },
      h("i", { style: `width:${(n / JOURNEY.length) * 100}%` })), h("span", { class: "small" }, n === JOURNEY.length ? "All five steps done. Nice work!" : `${n} of ${JOURNEY.length} steps done`));
    mount(nav, h("ol", { class: "pj-stepper", role: "tablist", "aria-label": "Tournament journey" }, JOURNEY.map((s) =>
      h("li", { class: s.key === current ? "on" : "" },
        h("button", { type: "button", role: "tab", id: `pj-tab-${s.key}`, "aria-selected": s.key === current ? "true" : "false", tabindex: s.key === current ? "0" : "-1",
          "aria-label": `Step ${s.n}: ${s.title}`, onclick: () => show(s.key), onkeydown: keys },
          h("span", { class: "pj-dot", "aria-hidden": "true" }, s.n),
          h("span", { class: "pj-label" }, h("span", { class: "pj-label-long" }, s.title), h("span", { class: "pj-label-short" }, s.short)))))));
    mount(extrasNav, h("span", { class: "pj-extras-h" }, "Good to know"), EXTRAS.map((s) => h("button", { type: "button", role: "tab", id: `pj-tab-${s.key}`,
      class: "pj-chip", "aria-selected": s.key === current ? "true" : "false", tabindex: s.key === current ? "0" : "-1", onclick: () => show(s.key), onkeydown: keys },
      h("span", { "aria-hidden": "true" }, s.ic), s.title)));
  }
  function paintKicker() {
    const s = ALL.find((x) => x.key === current);
    mount(kicker, s.n ? [`Step ${s.n} of ${JOURNEY.length}`, s.done ? h("span", { class: "pill good", style: "margin-left:8px" }, "✓ Done") : null] : "Good to know");
  }
  function keys(e) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = ALL.findIndex((s) => s.key === current);
    const nextKey = ALL[(i + (e.key === "ArrowRight" ? 1 : ALL.length - 1)) % ALL.length].key;
    show(nextKey, { scroll: false }); document.getElementById(`pj-tab-${nextKey}`).focus();
  }

  function paintPanel() {
    const s = ALL.find((x) => x.key === current);
    const i = JOURNEY.findIndex((x) => x.key === current);
    const prev = i > 0 ? JOURNEY[i - 1] : null;
    const nxt = i >= 0 && i < JOURNEY.length - 1 ? JOURNEY[i + 1] : null;
    const side = action(current);
    panel.setAttribute("aria-labelledby", `pj-tab-${current}`);
    paintKicker();
    mount(panel,
      h("div", { class: "pj-panel-h" },
        h("span", { class: "pj-big-ic", "aria-hidden": "true" }, s.ic),
        h("div", {}, kicker, h("h2", { style: "margin:2px 0 0" }, s.title))),
      h("div", { class: `pj-body${side ? "" : " full"}` }, h("div", { class: "pj-main" }, content(current)), side),
      i >= 0 ? h("div", { class: "pj-foot" },
        prev ? h("button", { class: "btn", type: "button", onclick: () => show(prev.key) }, `← ${prev.title}`) : h("span"),
        nxt ? h("button", { class: "btn primary", type: "button", onclick: () => show(nxt.key) }, `Next: ${nxt.title} →`)
          : h("button", { class: "btn primary", type: "button", onclick: () => show("rules") }, "Good to know →")) : null);
  }

  function show(key, { scroll = true } = {}) {
    current = key;
    try { history.replaceState(null, "", `#/parents/${key}`); } catch (_) { /* fine without it */ }
    paintNav(); paintPanel();
    if (scroll) {
      const top = nav.getBoundingClientRect().top;
      if (top < 0) nav.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  paintNav(); paintPanel();
  return h("div", { class: "stack pj", style: "max-width:1000px" },
    h("header", { class: "pj-hero" },
      h("div", { class: "pj-hero-text" },
        h("div", { class: "pj-hero-kicker" }, "For parents"),
        h("h1", {}, "Your path to a rated tournament"),
        h("p", {}, "Five short steps, from US Chess membership to reviewing the games, with the app doing the bookkeeping. Pick up wherever you are."),
        progress),
      h("div", { class: "pj-hero-art", "aria-hidden": "true" }, "♞")),
    nav, extrasNav, panel,
    h("p", { class: "small muted", style: "margin:0" }, "Steps tick themselves as you use the app. Rules, fees and membership options are set by US Chess and each organizer; always check the official announcement for the event you enter."));
}
