import io

import chess
import chess.pgn

from chesscoach.commentary import Voice, annotate, game_notes


def prepare(engine, moves: str):
    game = chess.pgn.read_game(io.StringIO(moves))
    board = game.board()
    boards, played = [board.copy()], []
    for move in game.mainline_moves():
        board.push(move)
        played.append(move)
        boards.append(board.copy())
    engine.new_game()
    return boards, played, [engine.analyse(b) for b in boards]


def test_every_move_gets_a_sentence_and_the_voice_follows_the_viewpoint(engine):
    boards, moves, evals = prepare(engine, "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5")
    you = annotate(boards, moves, evals, viewpoint=chess.WHITE)
    assert [c["ply"] for c in you] == [1, 2, 3, 4, 5, 6] and all(c["text"].endswith(".") for c in you)
    assert you[0]["text"].startswith("You ") and you[1]["text"].startswith("Your opponent ")
    neutral = annotate(boards, moves, evals)
    assert neutral[0]["text"].startswith("White ") and neutral[1]["text"].startswith("Black ")
    assert "develops the knight" in neutral[2]["text"]


def test_a_missed_mate_threat_and_the_mate_are_explained(engine):
    boards, moves, evals = prepare(engine, "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#")
    com = annotate(boards, moves, evals, viewpoint=chess.BLACK)
    blunder = com[5]
    assert "blunder" in blunder["tags"] and "missed-threat" in blunder["tags"]
    assert "Qxf7#" in blunder["text"] and "was better" in blunder["text"]
    assert "mate" in com[6]["tags"] and "Checkmate!" in com[6]["text"]
    notes = game_notes(com, "1-0", 7)
    assert "White won by checkmate" in notes["summary"] and "mate" in notes["themes"]


def test_a_defence_and_a_sacrifice_are_recognised(engine):
    # 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7: the classic Fried Liver sacrifice.
    boards, moves, evals = prepare(engine, "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7")
    com = annotate(boards, moves, evals)
    assert "sacrifice" in com[-1]["tags"] or "capture" in com[-1]["tags"]
    assert any("threatens" in c["text"] or "attacks" in c["text"] for c in com)


def test_voice_verbs():
    assert Voice(chess.WHITE).verb(chess.WHITE, "push") == "push"
    assert Voice(chess.WHITE).verb(chess.BLACK, "push") == "pushes"
    assert Voice(None).verb(chess.WHITE, "castle") == "castles"
    assert Voice(None).verb(chess.BLACK, "match") == "matches"
