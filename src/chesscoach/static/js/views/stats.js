// The results table: games, wins, draws and losses by month and by year.
import { h, icon, pct, level, meter } from "../dom.js";
import { api } from "../api.js";
import { currentPlayer } from "../state.js";
import { empty } from "../components.js";

const dash = (v, suffix = "") => (v === null || v === undefined ? "–" : `${v}${suffix}`);
const signed = (n) => (n === null || n === undefined ? "–" : `${n > 0 ? "+" : ""}${n}`);

function scoreCell(row) {
  if (row.score === null) return h("td", {}, "–");
  return h("td", { style: "min-width:130px" }, h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, h("div", { style: "width:80px;flex:none" }, meter(row.score, level(row.score))), h("b", { class: "small" }, pct(row.score))));
}

function sideCell(side) {
  return h("td", { class: "muted small", title: "Games and score as this color" }, side.games ? `${side.games} · ${pct(side.score)}` : "–");
}

function ratingCell(row) {
  if (row.rating_change === null) return h("td", { class: "muted" }, "–");
  return h("td", { title: `${row.rating_start} → ${row.rating_end}` },
    h("span", { class: `pill ${row.rating_change >= 0 ? "good" : "bad"}` }, signed(row.rating_change)), h("span", { class: "muted small" }, ` ${row.rating_end}`));
}

function tableRow(row, { strong = false } = {}) {
  const cell = (v) => h("td", {}, strong ? h("b", {}, v) : v);
  return h("tr", { class: strong ? "total" : "", "data-row": row.key },
    h("td", {}, h("b", {}, row.label), row.unfinished ? h("span", { class: "muted small" }, ` +${row.unfinished} unfinished`) : null),
    cell(row.games), h("td", { class: "w" }, row.wins), h("td", { class: "d" }, row.draws), h("td", { class: "l" }, row.losses),
    scoreCell(row), sideCell(row.white), sideCell(row.black),
    h("td", {}, dash(row.accuracy, "%")), h("td", {}, dash(row.blunders_per_game)), ratingCell(row));
}

const HEAD = ["Period", "Games", "Won", "Drawn", "Lost", "Score", "As White", "As Black", "Accuracy", "Blunders / game", "Rating"];

export async function statsView() {
  document.title = "My results · Chess Varsity";
  const player = currentPlayer();
  const table = await api(`/api/players/${player.id}/stats`);
  const t = table.total;
  if (!table.months.length) {
    return h("div", { class: "stack" }, h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My results"), h("p", {}, "Wins, draws and losses by month and year."))),
      empty("wR", "No results yet", "Add games, or import your tournaments from USCF, and this table fills itself in.",
        h("a", { class: "btn primary", href: "#/add" }, "Add a game"), h("a", { class: "btn", href: "#/tournaments" }, "Tournaments and USCF")));
  }

  let mode = "months";
  const body = h("div", { class: "card", style: "overflow:auto" });
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const paint = () => {
    const rows = mode === "months" ? table.months : table.years;
    body.replaceChildren(h("table", { class: "results", id: "results-table" },
      h("thead", {}, h("tr", {}, HEAD.map((x) => h("th", {}, x)))),
      h("tbody", {}, rows.map((r) => tableRow(r))),
      h("tfoot", {}, tableRow(t, { strong: true }))));
    tabs.replaceChildren(...[["months", "By month"], ["years", "By year"]].map(([k, text]) =>
      h("button", { role: "tab", "aria-selected": mode === k ? "true" : "false", onclick: () => { mode = k; paint(); } }, text)));
  };
  paint();

  const kpi = (label, value, note) => h("div", { class: "card tight kpi" }, h("div", { class: "l" }, label), h("div", { class: "v" }, value), note ? h("div", { class: "d muted" }, note) : null);
  const best = [...table.months].filter((r) => r.games >= 2 && r.score !== null).sort((a, b) => b.score - a.score)[0];
  const practice = table.practice;
  return h("div", { class: "stack" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My results"), h("p", {}, "Every game and tournament round, by month and year.")),
      h("div", { class: "row", style: "gap:8px" },
        h("a", { class: "btn small", href: `/api/players/${player.id}/stats.csv`, download: "" }, icon("download"), "Download as a spreadsheet (CSV)"),
        h("button", { class: "btn small", onclick: () => window.print() }, "Print"))),
    h("div", { class: "grid g4" },
      kpi("Games", t.games, `${t.events} tournament${t.events === 1 ? "" : "s"}`),
      kpi("Won · Drawn · Lost", `${t.wins} · ${t.draws} · ${t.losses}`),
      kpi("Score", pct(t.score), "a win is 1 point, a draw ½"),
      kpi("Average accuracy", dash(t.accuracy, "%"), t.analysed ? `from ${t.analysed} analyzed game${t.analysed === 1 ? "" : "s"}` : "add game moves to see it")),
    h("div", { class: "row spread" }, tabs, best ? h("span", { class: "muted small" }, `Best month so far: ${best.label} (${pct(best.score)})`) : null),
    body,
    h("p", { class: "muted small", style: "margin:0" },
      "Accuracy and blunders come from games whose moves you added. Tournament rounds with only a result (for example from USCF) count toward the record but have no accuracy. ",
      "Rating change is the regular USCF rating before and after that month's tournaments.",
      practice.games ? ` Not counted above: ${practice.games} practice game${practice.games === 1 ? "" : "s"} against the computer (${practice.wins}-${practice.draws}-${practice.losses}).` : ""));
}
