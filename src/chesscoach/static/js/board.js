// A chessboard drawn with real piece images, arrows, last-move and check highlights, and click handling.

const FILES = "abcdefgh";
const NS = "http://www.w3.org/2000/svg";
const ARROW_COLOR = { threat: "var(--arrow-threat)", played: "var(--arrow-played)", best: "var(--arrow-best)", second: "var(--arrow-second)", third: "var(--arrow-third)" };

export function parseFen(fen) {
  const [placement, turn] = fen.split(" ");
  const grid = {};
  placement.split("/").forEach((row, i) => {
    let f = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) f += +ch;
      else { grid[FILES[f] + (8 - i)] = ch; f += 1; }
    }
  });
  return { grid, turn };
}

export const flipTurn = (fen) => {
  const p = fen.split(" ");
  p[1] = p[1] === "w" ? "b" : "w";
  p[3] = "-";
  return p.join(" ");
};

const pieceSrc = (ch) => `/static/pieces/${ch === ch.toUpperCase() ? "w" : "b"}${ch.toUpperCase()}.svg`;

function arrowsSvg(arrows, orient) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 8 8");
  svg.setAttribute("class", "arrows");
  const pos = (sq) => {
    const f = FILES.indexOf(sq[0]), r = +sq[1] - 1;
    return orient === "white" ? [f + 0.5, 7 - r + 0.5] : [7 - f + 0.5, r + 0.5];
  };
  for (const a of arrows) {
    const [x1, y1] = pos(a.from), [x2, y2] = pos(a.to);
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
    const head = 0.42, bx = x2 - ux * head, by = y2 - uy * head;
    const line = document.createElementNS(NS, "line");
    line.setAttribute("x1", x1 + ux * 0.2); line.setAttribute("y1", y1 + uy * 0.2);
    line.setAttribute("x2", bx); line.setAttribute("y2", by);
    line.setAttribute("stroke", ARROW_COLOR[a.kind]); line.setAttribute("stroke-width", "0.15");
    line.setAttribute("stroke-linecap", "round"); line.setAttribute("opacity", "0.88");
    if (a.kind === "threat") line.setAttribute("stroke-dasharray", "0.32 0.2");
    const tri = document.createElementNS(NS, "polygon");
    tri.setAttribute("points", `${x2},${y2} ${bx - uy * 0.21},${by + ux * 0.21} ${bx + uy * 0.21},${by - ux * 0.21}`);
    tri.setAttribute("fill", ARROW_COLOR[a.kind]); tri.setAttribute("opacity", "0.92");
    svg.append(line, tri);
  }
  return svg;
}

/** Draw `fen` into `el`. Options: orient, arrows [{from,to,kind}], lastMove "e2e4", selected, targets [sq], onSquare(sq, piece). */
export function drawBoard(el, fen, { orient = "white", arrows = [], lastMove = null, selected = null, targets = [], onSquare = null } = {}) {
  const { grid, turn } = parseFen(fen);
  el.replaceChildren();
  el.classList.toggle("pointer", !!onSquare);
  const ranks = orient === "white" ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
  const files = orient === "white" ? [...FILES] : [...FILES].reverse();
  const last = lastMove ? [lastMove.slice(0, 2), lastMove.slice(2, 4)] : [];
  ranks.forEach((r, ri) => files.forEach((f, fi) => {
    const sq = f + r, piece = grid[sq];
    const light = (FILES.indexOf(f) + r) % 2 === 1;
    const cell = document.createElement("div");
    cell.className = `sq ${light ? "l" : "d"}${sq === selected ? " sel" : ""}${last.includes(sq) ? " last" : ""}${targets.includes(sq) ? " target" : ""}`;
    cell.dataset.sq = sq;
    if (piece) {
      const img = document.createElement("img");
      img.src = pieceSrc(piece); img.alt = ""; img.draggable = false;
      if (last[1] === sq) img.className = "moved";
      cell.append(img);
    }
    if (fi === 0) { const c = document.createElement("span"); c.className = "co r"; c.textContent = r; cell.append(c); }
    if (ri === 7) { const c = document.createElement("span"); c.className = "co f"; c.textContent = f; cell.append(c); }
    if (onSquare) cell.addEventListener("click", () => onSquare(sq, piece));
    el.append(cell);
  }));
  if (arrows.length) el.append(arrowsSvg(arrows, orient));
  return { turn };
}

export const arrowFrom = (uci, kind) => ({ from: uci.slice(0, 2), to: uci.slice(2, 4), kind });
