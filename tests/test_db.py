import sqlite3

from chesscoach.db import SCHEMA, Database


def test_an_older_database_gains_the_folder_column(tmp_path):
    # The schema as it was before folders: the same tables without games.folder_id.
    old_schema = SCHEMA.replace("    folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,\n", "")
    assert "folder_id INTEGER" not in old_schema
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(old_schema)
    conn.execute("INSERT INTO users(id, email, display_name, password_hash, created_at) VALUES (1, 'a@b.co', 'A', 'x', 0)")
    conn.execute("INSERT INTO players(id, user_id, name, created_at) VALUES (1, 1, 'A', 0)")
    conn.execute("INSERT INTO games(id, user_id, player_id, color, pgn, white, black, created_at) "
                 "VALUES (1, 1, 1, 'white', '', 'a', 'b', 0)")
    conn.commit()
    conn.close()

    db = Database(path)   # opening it upgrades it in place
    assert "folder_id" in {r["name"] for r in db.all("PRAGMA table_info(games)")}
    assert db.one("SELECT folder_id FROM games WHERE id = 1")["folder_id"] is None
    # ...and folders work on the upgraded database.
    fid = db.run("INSERT INTO folders(user_id, player_id, name, created_at) VALUES (1, 1, 'F', 0)")
    db.run("UPDATE games SET folder_id = ? WHERE id = 1", (fid,))
    db.run("DELETE FROM folders WHERE id = ?", (fid,))
    assert db.one("SELECT folder_id FROM games WHERE id = 1")["folder_id"] is None   # ON DELETE SET NULL
