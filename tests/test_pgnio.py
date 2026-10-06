import io

import chess
import chess.pgn

from chesscoach import pgnio


def game(headers: str = "") -> chess.pgn.Game:
    return chess.pgn.read_game(io.StringIO(f"{headers}\n1. e4 e5 2. Nf3 Nc6"))


def prepare(g, **kw):
    pgnio.prepare(g, player_name="Duke", color=chess.WHITE, today=(2026, 9), **kw)
    return g.headers["Date"]


def test_parse_date_needs_a_year_and_month():
    assert pgnio.parse_date("2026.09.14") == (2026, 9, 14)
    assert pgnio.parse_date("2026.09.??") == (2026, 9, None)
    assert pgnio.parse_date("2026.??.??") is None
    assert pgnio.parse_date("????.??.??") is None
    assert pgnio.parse_date("2026.13.01") is None
    assert pgnio.parse_date("") is None and pgnio.parse_date(None) is None


def test_a_game_without_a_date_goes_in_the_current_month():
    assert prepare(game()) == "2026.09.??"


def test_chosen_year_and_month_are_used_when_the_pgn_has_no_date():
    assert prepare(game(), year=2025, month=12) == "2025.12.??"
    assert prepare(game(), month=3) == "2026.03.??"          # only the month changed
    assert prepare(game(), year=2024) == "2024.09.??"        # only the year changed


def test_the_pgn_date_is_kept_by_default_and_ignored_on_request():
    dated = '[Date "2024.05.17"]\n'
    assert prepare(game(dated), year=2025, month=12) == "2024.05.17"
    assert prepare(game(dated), year=2025, month=12, prefer_pgn_date=False) == "2025.12.??"
    assert prepare(game('[Date "2024.05.??"]\n')) == "2024.05.??"
    assert prepare(game('[Date "2024.??.??"]\n')) == "2026.09.??"   # a year alone cannot pick a month


def test_tournament_and_match_number_land_in_the_pgn_headers():
    g = game()
    pgnio.prepare(g, player_name="Duke", color=chess.WHITE, event="State Open", round_="3", opponent="Sam", today=(2026, 9))
    fields = pgnio.describe(g, chess.WHITE)
    assert (fields["event"], fields["round"], fields["opponent"], fields["date"]) == ("State Open", "3", "Sam", "2026.09.??")


def test_no_tournament_means_an_empty_event_not_a_casual_bucket():
    g = game()
    prepare(g)
    assert pgnio.describe(g, chess.WHITE)["event"] == ""
