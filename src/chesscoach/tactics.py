"""Deterministic chess pattern detection: threats, tactics, and attack potential.

Nothing here calls an engine. Stockfish tells us *how much* a position changed;
these functions tell us *what* changed, in terms a young player can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
# Order in which the cheapest attacker is used during an exchange.
ORDER = {**VALUE, chess.KING: 100}
NAME = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def sq_name(square: int) -> str:
    return chess.square_name(square)


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(
        VALUE[p.piece_type] for p in board.piece_map().values() if p.color == color
    )


# --------------------------------------------------------------------------
# Exchanges
# --------------------------------------------------------------------------


def _cheapest_capture(board: chess.Board, square: int) -> chess.Move | None:
    best, best_order = None, 1000
    for move in board.legal_moves:
        if move.to_square == square and board.is_capture(move):
            order = ORDER[board.piece_at(move.from_square).piece_type]
            if order < best_order:
                best, best_order = move, order
    return best


def see_capture(board: chess.Board, move: chess.Move) -> int:
    """Net material (in pawns) the mover wins if both sides keep capturing on the square.

    Either side may stop capturing when continuing would lose material. The board
    is restored before returning.
    """
    if board.is_en_passant(move):
        gain = 1
    else:
        captured = board.piece_at(move.to_square)
        gain = VALUE[captured.piece_type] if captured else 0
    if move.promotion:
        gain += VALUE[move.promotion] - 1
    board.push(move)
    try:
        reply = _cheapest_capture(board, move.to_square)
        if reply is None:
            return gain
        return gain - max(0, see_capture(board, reply))
    finally:
        board.pop()


# --------------------------------------------------------------------------
# Threats
# --------------------------------------------------------------------------


@dataclass
class Threat:
    """Something `attacker` could do next move that would hurt the victim."""

    kind: str  # "mate" | "capture" | "fork"
    move: chess.Move
    san: str
    piece_type: int  # the piece making the threat
    from_square: int
    targets: list[tuple[int, int]] = field(default_factory=list)  # (square, piece_type)
    gain: int = 0  # pawns of material at stake; 100 for mate
    defended: bool = False  # for captures: is the target protected?


def opponent_to_move(board: chess.Board, victim: chess.Color) -> chess.Board | None:
    """A copy of `board` where the victim's opponent is on move (the victim 'passes').

    Returns None when the victim is in check: the check *is* the threat.
    """
    b = board.copy(stack=False)
    if b.turn == victim:
        if b.is_check():
            return None
        b.push(chess.Move.null())
    return b


def _gives_mate(board: chess.Board, move: chess.Move) -> bool:
    if not board.gives_check(move):
        return False
    board.push(move)
    try:
        return board.is_checkmate()
    finally:
        board.pop()


def _fork(board: chess.Board, move: chess.Move, victim: chess.Color) -> Threat | None:
    """If `move` forks two victim pieces and the forking piece can't just be taken."""
    san = board.san(move)
    from_piece = board.piece_at(move.from_square)
    board.push(move)
    try:
        square = move.to_square
        forker = board.piece_at(square)
        for reply in board.legal_moves:
            if reply.to_square == square and see_capture(board, reply) >= 0:
                return None
        targets: list[tuple[int, int]] = []
        for target in board.attacks(square):
            piece = board.piece_at(target)
            if piece is None or piece.color != victim:
                continue
            if piece.piece_type == chess.KING:
                targets.append((target, chess.KING))
            elif VALUE[piece.piece_type] > VALUE[forker.piece_type] or not board.is_attacked_by(
                victim, target
            ):
                targets.append((target, piece.piece_type))
        if len(targets) < 2:
            return None
        values = sorted(
            (VALUE[t[1]] for t in targets if t[1] != chess.KING), reverse=True
        )
        has_king = any(t[1] == chess.KING for t in targets)
        if has_king:
            gain = values[0] if values else 0
        elif len(values) >= 2:
            gain = values[1]
        else:
            return None
        if gain < 1 or (not has_king and values[0] < 3):
            return None
        return Threat(
            "fork", move, san, from_piece.piece_type, move.from_square, targets, gain
        )
    finally:
        board.pop()


def threat_for_move(
    board: chess.Board, move: chess.Move, victim: chess.Color
) -> Threat | None:
    """Classify one opponent move (board has the opponent on move) as a threat, or None."""
    piece = board.piece_at(move.from_square)
    if _gives_mate(board, move):
        return Threat("mate", move, board.san(move), piece.piece_type, move.from_square, gain=100)

    best: Threat | None = None
    if board.is_capture(move):
        gain = see_capture(board, move)
        if gain > 0:
            target = board.piece_at(move.to_square)
            target_type = target.piece_type if target else chess.PAWN
            best = Threat(
                "capture",
                move,
                board.san(move),
                piece.piece_type,
                move.from_square,
                [(move.to_square, target_type)],
                gain,
                defended=board.is_attacked_by(victim, move.to_square),
            )
    fork = _fork(board, move, victim)
    if fork and (best is None or fork.gain > best.gain):
        best = fork
    return best


def find_threats(board: chess.Board, victim: chess.Color) -> list[Threat]:
    """Every distinct thing the victim's opponent could do next move that wins material or mates."""
    b = opponent_to_move(board, victim)
    if b is None:
        return []
    found = []
    for move in list(b.legal_moves):
        threat = threat_for_move(b, move, victim)
        if threat:
            found.append(threat)
    found.sort(key=lambda t: t.gain, reverse=True)
    return found


# --------------------------------------------------------------------------
# What a move does
# --------------------------------------------------------------------------


@dataclass
class MoveInfo:
    san: str
    uci: str
    piece_type: int
    is_check: bool = False
    is_capture: bool = False
    is_mate: bool = False
    captured: int | None = None
    promotion: bool = False
    fork: Threat | None = None
    pin: tuple[int, int] | None = None  # (pinned square, pinned piece type)
    discovered: tuple[int, int] | None = None  # (target square, piece type)
    hangs_moved_piece: bool = False

    @property
    def forcing(self) -> bool:
        return self.is_check or self.is_capture or self.promotion


def describe_move(board: chess.Board, move: chess.Move) -> MoveInfo:
    mover = board.turn
    enemy = not mover
    piece = board.piece_at(move.from_square)
    info = MoveInfo(
        san=board.san(move),
        uci=move.uci(),
        piece_type=piece.piece_type,
        is_check=board.gives_check(move),
        is_capture=board.is_capture(move),
        promotion=move.promotion is not None,
    )
    if info.is_capture:
        target = board.piece_at(move.to_square)
        info.captured = target.piece_type if target else chess.PAWN
    info.is_mate = _gives_mate(board, move)

    # Fork: evaluated as if the mover's own move were an opponent-style move.
    info.fork = _fork(board, move, enemy)

    before_attacks = {
        sq: board.attacks(sq)
        for sq in chess.scan_forward(board.occupied_co[mover])
        if board.piece_type_at(sq) in (chess.BISHOP, chess.ROOK, chess.QUEEN)
    }
    board.push(move)
    try:
        dest = move.to_square
        moved = board.piece_at(dest)
        # Absolute pin created by the moved piece.
        for sq in chess.scan_forward(board.occupied_co[enemy]):
            p = board.piece_at(sq)
            if p.piece_type in (chess.KING, chess.PAWN) or VALUE[p.piece_type] < 3:
                continue
            if board.is_pinned(enemy, sq) and dest in board.pin(enemy, sq):
                info.pin = (sq, p.piece_type)
                break
        # Discovered attack: another slider now hits something valuable.
        for sq, before in before_attacks.items():
            if sq == move.from_square or board.piece_at(sq) is None:
                continue
            for target in board.attacks(sq) & ~before:
                p = board.piece_at(target)
                if p and p.color == enemy and (
                    p.piece_type == chess.KING or VALUE[p.piece_type] >= 3
                ):
                    info.discovered = (target, p.piece_type)
        # Would the enemy win the moved piece?
        for reply in board.legal_moves:
            if reply.to_square == dest and see_capture(board, reply) > 0:
                info.hangs_moved_piece = True
                break
    finally:
        board.pop()
    return info


def mover_threats(board: chess.Board, move: chess.Move) -> list[Threat]:
    """Threats the mover creates with `move` (what they'd do next if the opponent passed)."""
    mover = board.turn
    b = board.copy(stack=False)
    b.push(move)
    if b.is_checkmate():
        return [Threat("mate", move, board.san(move), board.piece_at(move.from_square).piece_type,
                       move.from_square, gain=100)]
    return find_threats(b, not mover)


def pv_gain(board: chess.Board, pv: list[chess.Move]) -> int:
    """Material the side to move nets over the first few plies of a principal variation."""
    mover = board.turn
    b = board.copy(stack=False)
    plies = min(len(pv), 4)
    if plies >= 2:
        plies -= plies % 2
    start = material(b, mover) - material(b, not mover)
    for move in pv[:plies]:
        if move not in b.legal_moves:
            break
        b.push(move)
    return material(b, mover) - material(b, not mover) - start


def variation_sans(board: chess.Board, pv: list[chess.Move], limit: int = 6) -> list[dict]:
    """The PV as [{san, fen}] so a UI can step through it."""
    b = board.copy(stack=False)
    out = []
    for move in pv[:limit]:
        if move not in b.legal_moves:
            break
        san = b.san(move)
        b.push(move)
        out.append({"san": san, "uci": move.uci(), "fen": b.fen()})
    return out


# --------------------------------------------------------------------------
# Attack potential
# --------------------------------------------------------------------------


def king_zone(board: chess.Board, color: chess.Color) -> chess.SquareSet:
    ks = board.king(color)
    return chess.SquareSet(chess.BB_KING_ATTACKS[ks] | chess.BB_SQUARES[ks])


def pieces_hitting(board: chess.Board, color: chess.Color, zone: chess.SquareSet) -> dict[int, int]:
    """Non-pawn, non-king pieces of `color` attacking any square of the zone."""
    hitting: dict[int, int] = {}
    for square in zone:
        for a in board.attackers(color, square):
            p = board.piece_type_at(a)
            if p not in (chess.PAWN, chess.KING):
                hitting[a] = p
    return hitting


def attack_potential(board: chess.Board, attacker: chess.Color) -> dict:
    """A coaching heuristic (not a chess truth): how promising is an attack on the enemy king?

    Components are scored so the total lands roughly on a 0-100 scale.
    """
    defender = not attacker
    ks = board.king(defender)
    if ks is None:
        return {"total": 0}
    kf, kr = chess.square_file(ks), chess.square_rank(ks)
    home_rank = 7 if defender == chess.BLACK else 0
    direction = -1 if defender == chess.BLACK else 1

    # King exposure: missing pawn shield, or a king that never castled / walked out.
    files = [f for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7]
    covered = 0
    for f in files:
        for step in (1, 2):
            r = kr + direction * step
            if 0 <= r <= 7:
                p = board.piece_at(chess.square(f, r))
                if p and p.piece_type == chess.PAWN and p.color == defender:
                    covered += 1
                    break
    exposure = 5 * (len(files) - covered)
    if kr != home_rank:
        exposure += 10
    elif kf in (3, 4) and not board.has_castling_rights(defender):
        exposure += 8
    exposure = min(exposure, 25)

    # Open and half-open files next to the king, plus heavy pieces using them.
    open_files = 0
    for f in files:
        file_pawns = [
            board.piece_at(chess.square(f, r)) for r in range(8)
        ]
        pawns = [p for p in file_pawns if p and p.piece_type == chess.PAWN]
        defender_pawn = any(p.color == defender for p in pawns)
        attacker_pawn = any(p.color == attacker for p in pawns)
        if not pawns:
            open_files += 8
        elif not defender_pawn and attacker_pawn:
            open_files += 4
        if not defender_pawn and any(
            (p := board.piece_at(chess.square(f, r)))
            and p.color == attacker
            and p.piece_type in (chess.ROOK, chess.QUEEN)
            for r in range(8)
        ):
            open_files += 5
    open_files = min(open_files, 25)

    zone = king_zone(board, defender)
    hitters = pieces_hitting(board, attacker, zone)
    attackers = min(len(hitters) * 5, 20)
    sliders = sum(1 for p in hitters.values() if p in (chess.BISHOP, chess.ROOK, chess.QUEEN))
    lines = min(sliders * 4, 12)

    defenders = len(pieces_hitting(board, defender, zone))
    weak_defence = max(0, min(15, 5 * (len(hitters) - defenders)))

    probe = board.copy(stack=False)
    probe.turn = attacker
    checks = sum(1 for m in probe.legal_moves if probe.gives_check(m)) if not probe.is_check() else 0
    checks_score = min(checks * 5, 15)

    total = exposure + open_files + attackers + lines + weak_defence + checks_score
    return {
        "total": min(total, 100),
        "king_exposure": exposure,
        "open_files": open_files,
        "attackers": attackers,
        "lines_to_king": lines,
        "weak_defence": weak_defence,
        "checks_available": checks_score,
    }
