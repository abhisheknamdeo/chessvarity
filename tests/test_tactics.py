import chess

from chesscoach import tactics as T


def test_scholars_mate_threat_is_found():
    # 1.e4 e5 2.Bc4 Nc6 3.Qh5 - Black to move, Qxf7# is threatened.
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3")
    threats = T.find_threats(board, chess.BLACK)
    assert threats[0].kind == "mate"
    assert threats[0].san == "Qxf7#"


def test_undefended_piece_is_a_capture_threat():
    board = chess.Board("4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1")
    threats = T.find_threats(board, chess.BLACK)
    capture = next(t for t in threats if t.kind == "capture")
    assert capture.san == "Qxd5"
    assert capture.gain == 3
    assert not capture.defended
    # Qh5+ is also found: it checks the king and attacks the same knight.
    assert any(t.kind == "fork" and t.san == "Qh5+" for t in threats)


def test_pawn_defended_piece_is_not_a_threat():
    board = chess.Board("4k3/8/4p3/3n4/8/8/8/3QK3 w - - 0 1")
    assert [t for t in T.find_threats(board, chess.BLACK) if t.kind == "capture"] == []


def test_victim_to_move_uses_null_move():
    # Same position as the first threat test but White has just moved; Black passes.
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3")
    assert T.find_threats(board, chess.WHITE) == [] or all(
        t.kind != "mate" for t in T.find_threats(board, chess.WHITE)
    )


def test_no_threats_when_victim_is_in_check():
    board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
    assert T.opponent_to_move(board, chess.WHITE) is None
    assert T.find_threats(board, chess.WHITE) == []


def test_knight_fork_king_and_rook():
    board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    threats = T.find_threats(board, chess.BLACK)
    fork = next(t for t in threats if t.kind == "fork")
    assert fork.san == "Nc7+"
    assert fork.gain == 5


def test_static_exchange():
    board = chess.Board("4k3/8/4p3/3n4/4P3/8/8/4K3 w - - 0 1")
    assert T.see_capture(board, chess.Move.from_uci("e4d5")) == 2
    # Board is restored afterwards.
    assert board.fen() == "4k3/8/4p3/3n4/4P3/8/8/4K3 w - - 0 1"


def test_describe_move_detects_fork_and_check():
    board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    info = T.describe_move(board, chess.Move.from_uci("d5c7"))
    assert info.is_check and info.fork is not None and info.forcing


def test_describe_move_detects_pin():
    board = chess.Board("4k3/4n3/8/8/8/8/8/K6R w - - 0 1")
    info = T.describe_move(board, chess.Move.from_uci("h1e1"))
    assert info.pin == (chess.E7, chess.KNIGHT)


def test_describe_move_flags_a_hanging_piece():
    board = chess.Board("4k3/8/8/2p5/8/8/8/3QK3 w - - 0 1")
    assert T.describe_move(board, chess.Move.from_uci("d1d4")).hangs_moved_piece
    assert not T.describe_move(board, chess.Move.from_uci("d1d3")).hangs_moved_piece


def test_attack_potential_grows_with_pressure():
    start = T.attack_potential(chess.Board(), chess.WHITE)["total"]
    scholar = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3")
    hot = T.attack_potential(scholar, chess.WHITE)
    assert start == 0
    assert hot["total"] > 20
    assert hot["checks_available"] > 0
