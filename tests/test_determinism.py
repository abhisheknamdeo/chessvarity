import io
import json

import chess
import chess.pgn

from chesscoach.analyzer import analyze_game

MOVES = "1. e4 e6 2. d4 d5 3. Bd3 dxe4 4. Bxe4 Nf6 5. Bf3 Nc6 6. c3 Bd6 7. Nd2 O-O 8. Ne4 Nxe4 9. Bxe4 Bd7 10. Be3 Rb8"


def test_analysing_the_same_game_twice_gives_identical_coaching(engine):
    def run():
        game = chess.pgn.read_game(io.StringIO(MOVES))
        return json.dumps(analyze_game(game, engine, chess.WHITE), sort_keys=True)

    first = run()
    # Analyse something else in between so leftover engine state would show up as a difference.
    analyze_game(chess.pgn.read_game(io.StringIO("1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Nbd7")), engine, chess.BLACK)
    assert run() == first
