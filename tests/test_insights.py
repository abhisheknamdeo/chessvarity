from chesscoach import insights


def fake_game(gid, outcome="loss", *, color="white", opening_name="Italian Game: Giuoco Piano", **habits):
    """A game shaped like the real per-game analysis, with knobs for the habit counts."""
    raw = {
        "moves": 30, "by_phase": {"opening": {"moves": 10, "loss": 10.0}, "middlegame": {"moves": 15, "loss": 60.0},
                                   "endgame": {"moves": 5, "loss": 10.0}},
        "free_moves": 20, "free_attacking": 8, "checks": 2, "captures": 4, "made_threat": 8, "retreats": 2,
        "reactive": 4, "spiral_moves": 0, "zone_pressure": 1.0,
        "opening": {"developed": 3, "castled_by": 6, "early_queen": 0, "repeats": 0}, "moments": {},
    }
    raw.update(habits)
    skills = {k: {"opportunities": 4, "handled": 3, "score": 75} for k in
              ("threat_recognition", "blunder_check", "tactics", "attacking", "initiative")}
    return {
        "id": gid, "color": color, "result": {"win": "1-0", "loss": "0-1", "draw": "1/2-1/2"}[outcome],
        "event": "Club", "round": "1", "date": f"2026.09.{gid:02d}", "opponent": f"Opp{gid}",
        "opening_eco": "C50", "opening_name": opening_name, "opening_plies": 7, "plies": 60,
        "accuracy": 80.0, "outcome": outcome,
        "analysis": {"habits": raw, "skills": skills, "moments": [], "how_to_win": []},
    }


def test_habits_wait_for_enough_moves():
    report = insights.habits([fake_game(1, moves=8)])
    assert report["ready"] is False and report["habits"] == []


def test_passive_and_unaggressive_player_gets_generic_problems():
    games = [
        fake_game(i, free_attacking=1, reactive=14, retreats=8, spiral_moves=6, made_threat=1)
        for i in range(1, 4)
    ]
    for g in games:
        g["analysis"]["skills"]["attacking"] = {"opportunities": 5, "handled": 0, "score": 0}
        g["analysis"]["moments"] = [{"category": "defensive_spiral", "ply": 30, "move_number": 15, "loss": 5,
                                     "importance": 12, "headline": "Defensive spiral", "fen": "x", "side": "white",
                                     "played": {"san": "Be2"}, "best": {"san": "Nf5"}}]
    report = insights.habits(games)
    by_id = {h["id"]: h for h in report["habits"]}
    assert by_id["attack"]["level"] == "work" and "not attacking" in by_id["attack"]["headline"]
    assert by_id["passive"]["level"] == "work" and "passively" in by_id["passive"]["headline"]
    assert by_id["passive"]["evidence"][0]["game_id"] in (1, 2, 3)
    assert by_id["attack"]["advice"] and by_id["attack"]["train"][0]["kind"] == "academy"
    assert report["habits"][0]["score"] <= report["habits"][-1]["score"]  # weakest first


def test_active_player_is_told_what_they_do_well():
    games = [fake_game(i, free_attacking=12, reactive=2, retreats=0) for i in range(1, 4)]
    by_id = {h["id"]: h for h in insights.habits(games)["habits"]}
    assert by_id["attack"]["level"] == "strong" and by_id["attack"]["headline"] == "You attack your opponent well."
    assert by_id["passive"]["level"] == "strong"


def test_opening_discipline_notices_no_castling():
    games = [fake_game(i, opening={"developed": 1, "castled_by": None, "early_queen": 2, "repeats": 2}) for i in (1, 2)]
    opening = {h["id"]: h for h in insights.habits(games)["habits"]}["opening"]
    assert opening["level"] == "work" and opening["evidence"][0]["headline"] == "Did not castle by move 10"


def test_slipped_wins_reduce_the_converting_score_and_are_listed():
    win = {"kind": "threw_away_win", "ply": 31, "move_number": 16, "headline": "A win slipped away at move 16",
           "fen": "8/8/8/8/8/8/8/8 w - - 0 1", "side": "white", "played": {"san": "Qh5"}, "best": {"san": "Qxh7+"},
           "wp_before": 80.0, "wp_after": 30.0, "loss": 50.0}
    slipped, fine = fake_game(1, "loss"), fake_game(2, "win")
    slipped["analysis"]["how_to_win"] = [win]
    games = [slipped, fine, fake_game(3, "loss")]
    converting = {h["id"]: h for h in insights.habits(games)["habits"]}["converting"]
    assert converting["score"] == 50 and converting["evidence"][0]["game_id"] == 1
    listed = insights.wins(games)
    assert len(listed) == 1 and listed[0]["game_id"] == 1 and listed[0]["opponent"] == "Opp1"


def test_openings_are_grouped_by_family_and_weak_ones_flagged():
    games = [fake_game(1, "loss"), fake_game(2, "loss"), fake_game(3, "win", opening_name="French Defense: Advance")]
    report = insights.openings(games)
    italian = next(o for o in report["families"] if o["family"] == "Italian Game")
    assert (italian["games"], italian["losses"], italian["score"]) == (2, 2, 0)
    assert any("Italian Game" in a for a in report["advice"])


def test_dashboard_summarises_record_and_accuracy_trend():
    games = [fake_game(i, "win" if i % 2 else "loss") for i in range(1, 8)]
    for i, g in enumerate(games):
        g["accuracy"] = 60.0 + 5 * i
    d = insights.dashboard(games)
    assert d["games"] == 7 and d["record"]["wins"] == 4 and d["record"]["losses"] == 3
    assert d["record"]["score"] == 57
    assert d["accuracy"]["change"] > 0
    assert len(d["series"]) == 7 and d["recent"][0]["id"] == 7
    assert insights.dashboard([]) == {"games": 0}
