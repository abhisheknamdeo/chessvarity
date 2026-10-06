// Tiny DOM helpers and icons. Text goes in via createTextNode, never innerHTML, so PGN names cannot inject markup.

export const $ = (selector, el = document) => el.querySelector(selector);

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k === "value") el.value = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function mount(el, ...kids) {
  el.replaceChildren();
  return append(el, kids);
}

const PATHS = {
  home: "M3 11l9-8 9 8M5 10v10h14V10",
  plus: "M12 5v14M5 12h14",
  target: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01",
  swords: "M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2",
  trophy: "M8 21h8M12 17v4M7 4h10v5a5 5 0 01-10 0V4zM17 5h3v2a3 3 0 01-3 3M7 5H4v2a3 3 0 003 3",
  book: "M4 19.5A2.5 2.5 0 016.5 17H20V3H6.5A2.5 2.5 0 004 5.5v14zM20 17v4H6.5A2.5 2.5 0 014 18.5",
  puzzle: "M10 3a2 2 0 014 0v2h4a1 1 0 011 1v4h-2a2 2 0 100 4h2v4a1 1 0 01-1 1h-4v-2a2 2 0 10-4 0v2H6a1 1 0 01-1-1v-4h2a2 2 0 100-4H5V6a1 1 0 011-1h4V3z",
  user: "M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z",
  chart: "M3 3v18h18M7 15l4-4 3 3 5-6",
  flame: "M12 22c4 0 7-3 7-7 0-3-2-5-3-7-1 2-2 3-3 3 0-4-2-7-5-9 0 4-3 6-3 10 0 5 3 10 7 10z",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9",
  search: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3",
  chevron: "M9 6l6 6-6 6",
  check: "M5 13l4 4L19 7",
  menu: "M4 6h16M4 12h16M4 18h16",
  sun: "M12 17a5 5 0 100-10 5 5 0 000 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z",
  crown: "M3 8l4 4 5-7 5 7 4-4-2 11H5L3 8z",
  bulb: "M9 18h6M10 22h4M12 2a7 7 0 00-4 12.7c.6.5 1 1.3 1 2.1V17h6v-.2c0-.8.4-1.6 1-2.1A7 7 0 0012 2z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  trash: "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6",
  alert: "M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  play: "M6 4l14 8-14 8V4z",
  download: "M12 3v12M7 10l5 5 5-5M4 21h16",
  refresh: "M21 12a9 9 0 11-3-6.7L21 8M21 3v5h-5",
  x: "M18 6L6 18M6 6l12 12",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  copy: "M9 9h11v11H9zM5 15V5a1 1 0 011-1h10",
  folder: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3h0a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5h0a1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8v0a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  message: "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
  star: "M12 2l3 7 7 .6-5.3 4.7 1.6 7.2L12 17.8 5.7 21.5l1.6-7.2L2 9.6 9 9z",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z",
  calendar: "M3 5h18v16H3zM3 10h18M8 3v4M16 3v4",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  table: "M3 5h18v14H3zM3 10h18M9 5v14",
  camera: "M4 7h3l2-3h6l2 3h3a1 1 0 011 1v11a1 1 0 01-1 1H4a1 1 0 01-1-1V8a1 1 0 011-1zM12 17a4 4 0 100-8 4 4 0 000 8z",
  users: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
  link: "M10 14a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 10a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1",
};

/** A player's page on the US Chess ratings site. */
export const uscfUrl = (id) => `https://ratings.uschess.org/player/${encodeURIComponent(String(id).trim())}`;

export function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "i");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", PATHS[name] || PATHS.target);
  svg.append(path);
  return svg;
}

export function toast(message) {
  const el = h("div", { class: "toast", role: "status" }, message);
  document.body.append(el);
  setTimeout(() => el.remove(), 3500);
}

export const pct = (n) => (n === null || n === undefined ? "–" : `${Math.round(n)}%`);
export const level = (score) => (score >= 75 ? "good" : score >= 50 ? "warn" : "bad");
export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function ring(score) {
  const el = h("div", { class: `ring ${level(score)}`, role: "img", "aria-label": `Score ${score} out of 100` }, h("b", {}, score));
  el.style.setProperty("--p", score);
  return el;
}

export function meter(score, tone) {
  const bar = h("i", {});
  bar.style.width = `${Math.max(0, Math.min(100, score))}%`;
  return h("div", { class: `meter ${tone || level(score)}` }, bar);
}

export function outcomeText(outcome) {
  return outcome === "win" ? "Win" : outcome === "loss" ? "Loss" : outcome === "draw" ? "Draw" : "In progress";
}

/** "2026.09.14" -> "Sep 14, 2026"; "2026.09.??" -> "Sep 2026". */
export function fmtDate(d) {
  if (!d) return "";
  const [y, m, day] = d.split(".");
  if (!y || !m || m.includes("?")) return d;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dayText = day && /^\d+$/.test(day) ? `${+day}, ` : "";
  return `${months[+m - 1] || m} ${dayText}${y}`;
}
