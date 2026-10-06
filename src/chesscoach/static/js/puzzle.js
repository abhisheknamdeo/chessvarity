// A click-to-move puzzle runner. `puzzle`: {fen, side, line[uci], fens[after each move], prompt, hint}.
// For workbook puzzles from a game, `goodMoves` lists every acceptable first move instead of a fixed line.
import { h } from "./dom.js";
import { drawBoard, parseFen, arrowFrom } from "./board.js";
import { confetti } from "./fun.js";

export function puzzleRunner(puzzle, { orient, onSolved, onNext, extraHint }) {
  const board = h("div", { class: "board", style: "max-width:480px" });
  const feedback = h("div", { class: "hidden", role: "status" });
  const line = puzzle.line;
  let step = 0; // index into line of the solver's next move
  let fen = puzzle.fen;
  let selected = null, arrows = [], last = null, solved = false, locked = false;
  const sideWhite = puzzle.fen.split(" ")[1] === "w";
  const mine = (ch) => ch && (sideWhite ? ch === ch.toUpperCase() : ch === ch.toLowerCase());
  const grid = () => parseFen(fen).grid;

  const say = (kind, text) => { feedback.className = `alert ${kind}`; feedback.textContent = text; };
  const draw = () => drawBoard(board, fen, { orient: orient || (sideWhite ? "white" : "black"), arrows, selected, lastMove: last, onSquare: click });

  function accepted(uci) {
    if (step === 0 && puzzle.goodMoves) return puzzle.goodMoves.includes(uci);
    return uci === line[step];
  }

  function click(sq, piece) {
    if (solved || locked) return;
    if (!selected) { if (mine(piece)) { selected = sq; draw(); } return; }
    if (sq === selected) { selected = null; draw(); return; }
    if (mine(piece)) { selected = sq; draw(); return; }
    let uci = selected + sq;
    const moving = grid()[selected];
    if (moving && moving.toLowerCase() === "p" && (sq[1] === "8" || sq[1] === "1")) uci += "q";
    selected = null;
    // King moving two files is castling: python-chess writes it as king-to-destination, as here.
    if (!accepted(uci)) {
      arrows = [];
      board.classList.remove("shake"); void board.offsetWidth; board.classList.add("shake");
      say("bad", "Not that one. Look for checks, captures and threats first, then try again.");
      draw();
      return;
    }
    if (puzzle.goodMoves) { arrows = [arrowFrom(uci, "best")]; finish(); return; } // single-move workbook position
    fen = puzzle.fens[step]; last = uci; step += 1;
    if (step >= line.length) { finish(); return; }
    locked = true;
    say("info", "Good move! Now watch the reply…");
    draw();
    setTimeout(() => { // opponent's forced reply
      fen = puzzle.fens[step]; last = line[step]; step += 1; locked = false;
      if (step >= line.length) { finish(); return; }
      say("info", "Your move again. Keep going!");
      draw();
    }, 650);
  }

  function finish() {
    solved = true; locked = false;
    draw();
    say("good", `Correct! ${puzzle.answer || ""} ${puzzle.lesson || ""}`.trim());
    confetti(60);
    if (onSolved) onSolved();
  }

  const hint = h("button", { class: "btn small", type: "button", onclick: () => {
    if (solved) return;
    if (puzzle.threat_uci && step === 0) { arrows = [arrowFrom(puzzle.threat_uci, "threat")]; say("info", puzzle.answer || "Look at what your opponent can do next."); }
    else { const next = puzzle.goodMoves && step === 0 ? puzzle.goodMoves[0] : line[step]; arrows = [{ from: next.slice(0, 2), to: next.slice(2, 4), kind: "best" }]; say("info", puzzle.hint || extraHint || "The green arrow shows the piece to move."); }
    draw(); } }, "Hint");
  const reveal = h("button", { class: "btn small", type: "button", onclick: () => {
    if (solved) return;
    const next = puzzle.goodMoves && step === 0 ? puzzle.goodMoves[0] : line[step];
    arrows = [...(puzzle.threat_uci && step === 0 ? [arrowFrom(puzzle.threat_uci, "threat")] : []), arrowFrom(next, "best")];
    solved = true;
    say("warn", puzzle.revealText || (puzzle.line_san ? `The solution: ${puzzle.line_san.join(" ")}` : "Here is the move."));
    draw(); } }, "Show answer");
  const next = h("button", { class: "btn small primary", type: "button", onclick: () => onNext && onNext() }, "Next ▶");

  draw();
  return h("div", { class: "stack-s" }, board, h("div", { class: "small muted" }, "Click a piece, then the square to move it to."),
    h("div", { class: "row" }, hint, reveal, onNext ? next : null), feedback);
}
