import chess

from chesscoach import balance as B


def test_starting_position_is_balanced():
    d = B.describe(chess.Board(), chess.WHITE)
    assert d["verdict"]["label"] == "balanced"
    assert all(abs(v) < B.NOTABLE for v in d["scores"].values())


def test_material_advantage_is_reported_from_the_players_side():
    board = chess.Board("4k3/8/8/8/8/8/PPP5/3QK3 w - - 0 1")  # White has a queen and three pawns
    white = B.describe(board, chess.WHITE)
    black = B.describe(board, chess.BLACK)
    assert white["scores"]["material"] > 50 and black["scores"]["material"] < -50
    assert "ahead in material" in white["notes"][0]["text"] or any("ahead in material" in n["text"] for n in white["notes"])


def test_exposed_king_shows_up_as_king_safety():
    # Scholar's-mate position: Black's king is under fire from Qh5 and Bc4.
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3")
    black = B.describe(board, chess.BLACK)
    white = B.describe(board, chess.WHITE)
    assert black["scores"]["king_safety"] < 0 < white["scores"]["king_safety"]
    assert black["scores"]["initiative"] < 0  # White threatens mate


def test_opposing_imbalances_are_called_unbalanced():
    # White has an extra pawn but Black's pieces are far more active and White's king is open.
    board = chess.Board("r1bq1rk1/pp3ppp/2n1pn2/2bp4/8/2P2N2/PP2PPPP/RNBQK2R b KQ - 0 1")
    scores = B.scores(board, chess.BLACK)
    assert set(scores) == set(B.DIMENSIONS)
    d = B.describe(board, chess.BLACK, wp=55)
    assert d["verdict"]["text"] and "engine says" in d["verdict"]["text"]


def test_shift_lists_what_got_worse():
    before = {"scores": {k: 0 for k in B.DIMENSIONS}}
    after = {"scores": {**{k: 0 for k in B.DIMENSIONS}, "king_safety": -40, "material": -10}}
    shift = B.shift(before, after)
    assert [s["key"] for s in shift] == ["king_safety"]
    assert shift[0]["text"] == "It weakened your king."


def test_passed_and_isolated_pawns_are_counted():
    board = chess.Board("4k3/8/8/3P4/8/8/P6P/4K3 w - - 0 1")
    pawns = B._pawns(board, chess.WHITE)
    assert "d5" in pawns["passed"] and pawns["isolated"] == 3
