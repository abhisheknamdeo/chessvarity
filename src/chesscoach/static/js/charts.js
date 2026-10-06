// Small SVG charts drawn by hand: no chart library, so nothing to load or license.

const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const kid of kids) node.append(kid);
  return node;
};
const text = (t) => document.createTextNode(t);

/**
 * How the game went for the coached side. Up is good for them.
 * timeline: [{ply, wp (White's chances), loss, white_moved}], onSelect(ply).
 */
export function timelineChart(timeline, { playerWhite, ply, onSelect }) {
  const W = 640, H = 170, padL = 30, padR = 10, padT = 10, padB = 20;
  const n = timeline.length - 1 || 1;
  const x = (i) => padL + (i / n) * (W - padL - padR);
  const y = (wp) => padT + (1 - wp / 100) * (H - padT - padB);
  const mine = (t) => (playerWhite ? t.wp : 100 - t.wp);
  const pts = timeline.map((t, i) => [x(i), y(mine(t))]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${x(n)},${y(50)} L${x(0)},${y(50)} Z`;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Evaluation over the game" });
  svg.append(
    el("defs", {},
      el("clipPath", { id: "clip-up" }, el("rect", { x: 0, y: 0, width: W, height: y(50) })),
      el("clipPath", { id: "clip-down" }, el("rect", { x: 0, y: y(50), width: W, height: H }))),
  );
  for (const g of [0, 25, 50, 75, 100]) {
    svg.append(
      el("line", { x1: padL, x2: W - padR, y1: y(g), y2: y(g), stroke: "var(--line)", "stroke-width": g === 50 ? 1.5 : 1 }),
      el("text", { x: padL - 6, y: y(g) + 4, "text-anchor": "end" }, text(g)),
    );
  }
  svg.append(
    el("path", { d: area, fill: "var(--good)", opacity: ".28", "clip-path": "url(#clip-up)" }),
    el("path", { d: area, fill: "var(--bad)", opacity: ".28", "clip-path": "url(#clip-down)" }),
    el("path", { d: line, fill: "none", stroke: "var(--ink)", "stroke-width": 2, "stroke-linejoin": "round" }),
  );
  timeline.forEach((t, i) => {
    if (i === 0) return;
    const isMine = t.white_moved === playerWhite;
    if (isMine && t.loss >= 10) {
      const c = el("circle", { cx: pts[i][0], cy: pts[i][1], r: t.loss >= 20 ? 5.5 : 4.5, fill: t.loss >= 20 ? "var(--bad)" : "#ea580c", stroke: "var(--surface)", "stroke-width": 1.5 });
      c.append(el("title", {}, text(`Move ${Math.ceil(i / 2)}: this cost about ${Math.round(t.loss)} points of winning chances`)));
      svg.append(c);
    } else if (!isMine && t.loss >= 10) {
      const c = el("circle", { cx: pts[i][0], cy: pts[i][1], r: 4, fill: "var(--surface)", stroke: "var(--good)", "stroke-width": 2 });
      c.append(el("title", {}, text(`Move ${Math.ceil(i / 2)}: your opponent slipped here`)));
      svg.append(c);
    }
  });
  if (ply !== undefined) svg.append(el("line", { x1: x(ply), x2: x(ply), y1: padT, y2: H - padB, stroke: "var(--brand)", "stroke-width": 2 }));
  svg.append(el("text", { x: padL, y: H - 4 }, text("Start")), el("text", { x: W - padR, y: H - 4, "text-anchor": "end" }, text(`Move ${Math.ceil(n / 2)}`)));
  if (onSelect) {
    const hit = el("rect", { x: padL, y: 0, width: W - padL - padR, height: H, fill: "transparent", class: "clickable" });
    hit.addEventListener("click", (e) => {
      const box = svg.getBoundingClientRect();
      const px = ((e.clientX - box.left) / box.width) * W;
      onSelect(Math.max(0, Math.min(n, Math.round(((px - padL) / (W - padL - padR)) * n))));
    });
    svg.append(hit);
  }
  return svg;
}

/** Accuracy per game, oldest to newest. points: [{accuracy, outcome, label, game_id}] */
export function seriesChart(points, { onSelect } = {}) {
  const W = 640, H = 190, padL = 32, padR = 12, padT = 12, padB = 26;
  const n = Math.max(points.length - 1, 1);
  const x = (i) => (points.length === 1 ? (W + padL) / 2 : padL + (i / n) * (W - padL - padR));
  const y = (v) => padT + (1 - v / 100) * (H - padT - padB);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Accuracy for each game" });
  for (const g of [0, 25, 50, 75, 100]) {
    svg.append(
      el("line", { x1: padL, x2: W - padR, y1: y(g), y2: y(g), stroke: "var(--line)" }),
      el("text", { x: padL - 6, y: y(g) + 4, "text-anchor": "end" }, text(g)),
    );
  }
  const valid = points.map((p, i) => [p, i]).filter(([p]) => p.accuracy !== null && p.accuracy !== undefined);
  if (valid.length > 1) {
    svg.append(el("path", { d: valid.map(([p, i], k) => `${k ? "L" : "M"}${x(i)},${y(p.accuracy)}`).join(" "), fill: "none", stroke: "var(--brand)", "stroke-width": 2.5, "stroke-linejoin": "round" }));
  }
  const color = { win: "var(--good)", loss: "var(--bad)", draw: "var(--faint)" };
  for (const [p, i] of valid) {
    const c = el("circle", { cx: x(i), cy: y(p.accuracy), r: 6, fill: color[p.outcome] || "var(--brand)", stroke: "var(--surface)", "stroke-width": 2, class: onSelect ? "clickable" : "" });
    c.append(el("title", {}, text(`${p.label || "Game"}: ${Math.round(p.accuracy)}% accuracy${p.outcome ? " (" + p.outcome + ")" : ""}`)));
    if (onSelect) c.addEventListener("click", () => onSelect(p));
    svg.append(c);
  }
  svg.append(el("text", { x: padL, y: H - 6 }, text("Older")), el("text", { x: W - padR, y: H - 6, "text-anchor": "end" }, text("Newer")));
  return svg;
}

/**
 * Ratings over time, one line per rating system. series: [{name, color, points: [{x, value, title}]}], x from 0 to count - 1.
 */
export function ratingChart(series, count) {
  const W = 640, H = 210, padL = 40, padR = 12, padT = 12, padB = 26;
  const values = series.flatMap((s) => s.points.map((p) => p.value));
  const lo = Math.floor((Math.min(...values) - 15) / 50) * 50, hi = Math.ceil((Math.max(...values) + 15) / 50) * 50;
  const x = (i) => (count <= 1 ? (W + padL) / 2 : padL + (i / (count - 1)) * (W - padL - padR));
  const y = (v) => padT + (1 - (v - lo) / (hi - lo || 1)) * (H - padT - padB);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Rating after each tournament" });
  const step = Math.max(50, Math.ceil((hi - lo) / 4 / 50) * 50);
  for (let g = lo; g <= hi; g += step) {
    svg.append(el("line", { x1: padL, x2: W - padR, y1: y(g), y2: y(g), stroke: "var(--line)" }),
      el("text", { x: padL - 6, y: y(g) + 4, "text-anchor": "end" }, text(g)));
  }
  for (const s of series) {
    if (s.points.length > 1) {
      svg.append(el("path", { d: s.points.map((p, k) => `${k ? "L" : "M"}${x(p.x)},${y(p.value)}`).join(" "), fill: "none", stroke: s.color, "stroke-width": 2.5, "stroke-linejoin": "round" }));
    }
    for (const p of s.points) {
      const c = el("circle", { cx: x(p.x), cy: y(p.value), r: 4.5, fill: s.color, stroke: "var(--surface)", "stroke-width": 1.5 });
      c.append(el("title", {}, text(p.title)));
      svg.append(c);
    }
  }
  svg.append(el("text", { x: padL, y: H - 6 }, text("Older")), el("text", { x: W - padR, y: H - 6, "text-anchor": "end" }, text("Newer")));
  return svg;
}
