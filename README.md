# Chess Varsity

A personal chess coach. You add the games you play, and Chess Varsity shows you **what went wrong**, the **habits behind your mistakes** ("not attacking", "playing too passively", "missing tactics"), **wins that slipped away**, and builds **practice** from your own positions, plus an attack academy, model games and an opening library.

It is made for one student learning on their own. There is no coach or teacher view, and no class list: one account is one student, and the account holder sees only their own games, apart from games other players choose to share in the **community**.

Stockfish measures how much each move cost. Deterministic chess logic (`tactics.py`, `balance.py`) names *what* happened. All wording is templated; no language model judges the chess, so the same game always gets the same coaching.

The live site is **https://dukesmateai.com**. It is in **beta**: still improving, and feedback is welcome. **AI features are on the way** (an AI coach you can ask about any position, plain-words explanations of your mistakes, and an adaptive training plan); they are marked *coming soon* in the app, and today's coaching comes from Stockfish and chess rules only.

## Documentation

| Document | For |
|---|---|
| This README | What the app does, running it locally, settings |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design and architecture: components, data model, main flows, security, trade-offs |
| [deploy/aws/DEPLOYMENT.md](deploy/aws/DEPLOYMENT.md) | The production setup on AWS and how to operate it (deploys, logs, backups, DNS, email, sign-in keys) |
| [NOTICE.md](NOTICE.md) | Licences of Stockfish, python-chess and the data used |

## What you can do

### Your games and coaching

- **Upload notation.** On Add a game, the *Upload notation* tab takes photos of the paper scoresheet. Copy the moves in straight away (the photo stays in view beside the board, tap to enlarge), or **Save for later**: saved scoresheets wait at the top of the page under *Scoresheets waiting for moves* until you enter them. When the game is added its photos move to the game, so they're there for future reference and corrections (the game's Scoresheet button adds, views or removes photos).
- **Add a game.** Paste a PGN, upload a .pgn file, or enter the moves on a board. The game is read as you paste it: a *Game detected* card shows both players and ratings, the result, number of moves, date, tournament, round, site and opening, and fills in **Game details** (which side you played, found by your name, USCF name or account name; result; opponent; opponent's rating). If the PGN's event looks like one of your own tournaments, it offers to attach the game to that tournament's round. *Tournament & organization* holds the tournament, round, an exact date, the folder and optional scoresheet photos. A PGN with several games lists them all with checkboxes (games you already added are marked), so you can analyze all or some. The bottom bar says when the game is ready and holds **Add & Analyze Game**, or **Save without analysis** (analyze later from the game page). An unreadable PGN gets a plain message and a *Try again* button.
- **A short sidebar.** Eight links: Dashboard, **Tournaments** (highlighted, with USCF), Add games, **Improve**, **Study**, **Schedule**, **Community** and **Parents** (plus **Admin** at the very end, for admins): a guided journey to a rated tournament in five steps (Join US Chess, Find a tournament, Register, Tournament day, After the games), each with a short checklist, a "do it in the app" card and Back/Next. Steps tick themselves from what you've done (USCF ID saved, tournament added, registered, packing list, games added). *Good to know* covers rules, ratings, supporting your player and questions. Each step has its own link, e.g. `#/parents/register`. Related pages are tabs along the top: Tournaments has *Tournaments & USCF*, *My results* and *Tournament plan*; Schedule has *Calendar*, *Training* and *Planner*; Improve has *My roadmap* (where the Improve link opens), *Mistake patterns*, *Wins I missed*, *My workbook* and *My goals*; Study has *Openings*, *Model games*, *Attack academy*, *Think like a Grandmaster* and *Play the computer* (also a tile on the dashboard). The dashboard shows your USCF rating, the next tournament, the latest result and any rounds still waiting for their moves right under the banner. The sidebar footer has buttons for feedback, board options, light/dark theme and signing out.
- **Find your games** in the sidebar: by month (with tournaments grouped inside each month) or in **folders you create**. Rename folders, move games between them, and **delete** a game or a whole folder (you choose whether its games are kept).
- **Review a game.** A board with arrows for the opponent's threat, your move and the better move; a clickable evaluation timeline; and **move-by-move commentary** in plain language: what each move does, what it attacks or defends, tactics like forks and sacrifices, and mistakes with the better move.
- **Try your own moves** on any board. Play a different move from any position, see your moves listed, take them back, copy the position, or let the computer answer. The **best moves** are drawn on the board (green for the best, orange for the second, purple for the third). Each comes from about a second of engine search and says what the move does (captures, checks, forks, pins, the threat it stops, the piece it attacks or protects, development, open lines), how good it is against the best move (Best, Good alternative, Weaker, Not recommended) with a score, warnings such as what it allows, the likely reply, and the engine's line. A short read on the position sits above them. The Hint button on the Play page gives the same explanation. Choose to see 1, 2 or 3 of them (2 is the default and the choice is remembered), or switch them off.
- **Your rating from USCF.** Saving a USCF ID (on *Tournaments & USCF* or your profile) looks the player up straight away and uses their USCF rating (regular, else quick) as the app's rating, for the roadmap level and everywhere else, unless you chose another rating system on your profile. It stays up to date each time you import from USCF.
- **Rating after every tournament.** Each imported tournament shows every rating it changed, for example *Regular 1443 → 1405 (−38) · Quick 1278 → 1240 (−38)* for a dual-rated event, and a chart draws your regular, quick, blitz and online ratings after each tournament. Your most recent tournament is highlighted and starts open.
- **Calendar: my chess plan.** *Next up* shows the next few things that matter (training, registration deadlines still to do, tournaments with what's left to sort out and how prepared you are, goals). One control row has the month, *Today*, *Month / Agenda* and **+ Add** (tournament, training, registration deadline, hotel, goal, other). Filter chips show or hide tournaments, training, deadlines, travel and goals. Click anything for a details panel (a sheet from the bottom on a phone): a tournament shows registration, fee, hotel and travel status, games with moves, results and rating change, and for an upcoming one a **preparation checklist** (review recent games and tactical practice tick themselves from what you did; endgame, openings and practice games you tick) with a *Start preparation* link. The agenda groups everything by *This week*, *Next week* and month, one heading per day.
- **My roadmap.** A personal development plan for your rating level (from under 500 to 2000+): your level and next milestone, your **3 priorities** worked out from your own analysed games (with *Show me why* and *See an example*), eight areas (tactics, thinking process, calculation, opening, middlegame, attack and defence, endgame, repertoire) with a mastery meter and the topics to learn now, to review, and coming next, plus a weekly training plan and practice guidelines. Look at any other level; future levels are clearly marked as not yet your focus. Tick a topic when you've got it.
- **Roadmap, Openings and Attack academy work together.** Each roadmap area links to where it is practised (Attack academy themes, the Openings library or repertoire, Model games, *Think like a Grandmaster*). The Openings and Attack academy pages show an **On your roadmap** card with the milestones for your level that belong there, as checkboxes, and a link back. A tick in either place is the same tick.
- **See your patterns.** Eight habits scored 0-100 with examples from your games and specific advice: attacking, playing actively, tactics, spotting threats, blunder check, opening discipline, converting good positions, endgames.
- **Wins I missed.** Positions from games you lost or drew where you were better, with the winning line to step through.
- **Practise.** A workbook built from your own mistakes (each position shows the game, tournament, match and move it came from), plus 30+ engine-verified puzzles: mating patterns, attacking sacrifices, opening traps, tactics. There is a puzzle of the day.

### Tournaments and planning

- **Tournaments.** Keep each tournament round by round and add the moves of every game to its round. Enter tournaments by hand (including ones coming up) or **connect a USCF ID** (saved once, remembered) and import tournaments, opponents, colours and results from USCF's public ratings service. USCF keeps results but not moves, so you still add the moves yourself. The USCF service is unofficial and may change; nothing is sent to it except the ID, and only when you press a button. Each round has a **Share** button for its game and a place for **scoresheet photos**.
- **Tournament planner.** A tracker for every tournament you might play. Each has four flags you set to *To do*, *Done* or *N/A* (registered, entry fee paid, hotel booked, travel arranged), a "going / thinking about it / not going" choice, the venue and website, the entry fee, a registration deadline that turns red when it is close or missed, and the hotel with its dates and confirmation number. Cards show how many things are still to do, and the summary counts registrations, hotels and the next deadline. Filter by going, maybe, not going or needs attention.
- **Training schedule.** Classes, private lessons, club nights, practice and home study, one-off or repeating (every week on chosen days, every other week, or every month, with an optional end date). The page shows a week at a time with the time, place and coach, tick each session as attended, cancel a single session without touching the rest, and see the regular timetable underneath. Repeating sessions are worked out as needed, so nothing has to be entered twice.
- **Calendar.** A month view and an agenda of everything with a date: tournaments (across their days, flagged when something is still to do), training sessions with their times, registration deadlines, hotel stays and goal due dates. Hide any kind with its tick box, click a day to see what is on it, or add a tournament straight from a day. The dashboard's next-tournament block also shows its flags.
- **My results.** A table of games, wins, draws, losses, score, accuracy, blunders per game and rating change, by month and by year, that you can download as CSV or print. Each game is counted once, and practice games against the computer are kept separate.
- **My goals.** A short-term and long-term goal sheet. Goals can be measured automatically from your games (accuracy, blunders per game, a habit score, puzzles, streak, USCF rating) or ticked off by hand, with small steps and suggestions based on your habits.
- **Tournament plan.** For your next tournament: an opening for each colour chosen from your results and habits, the attacking position to aim for (drawn with piece routes and targets, with the line to get there and a board to try it), a countdown and a checklist.

### Study and play

- **Think like a Grandmaster.** The seven questions strong players ask every move, how common traps work, and a trainer that asks the questions about a position and describes the answers (threats, loose pieces, king safety, a plan from the imbalances) without ever naming a move. It also works inside any "try your own moves" board.
- **Play the computer** from the start or from any position you copied, at eight levels from beginner (about 800) to full strength. The computer opens with real named openings, then searches at full strength and chooses the way a player of that level would: usually a good move, sometimes a weaker one, and never a blunder from 1700 up. The levels were tuned by measuring move quality, so each one really is stronger than the one below. The default is **1700**; tick **Remember my difficulty and side** to keep your choice on that device. Ask for a hint with a reason, take moves back, and save the game to be analysed like any other.
- **Learn from model games.** 330+ attacking games in checkmate finishes, grouped by playing strength (under 1200 up to 2300+), each with commentary on every move, plus five historic classics. The commentary sits beside the board with the story and lessons under it. Step through every move of a game to mark it **Completed**; part-way shows **In progress**, and you can filter the list by status. Rated games come from the Lichess open database and show ratings only, never names.
- **Explore openings.** 3,800 named openings to browse by variation; attacking repertoires for White and Black (the first tab, one colour at a time, with each opening's plans and traps folded away until you open them); and your own results by opening.
- **Stay motivated.** XP and a rank from Pawn up to King, a daily streak, and badges to earn.
- **Make it yours.** Board colours (15 of them, from Green and Wood to Midnight and High contrast), board size and coordinates can be changed (gear icon in the sidebar), and there is a light and a dark theme. The design is clean and modern with a royal theme: a deep navy sidebar and dashboard banner, gold for highlights, royal blue for actions, tinted accents for each kind of information, an ivory-and-walnut board, and a matching navy dark mode. The fonts (Figtree for text, IBM Plex Mono for chess notation) are bundled, so it looks the same offline.

### Your account

- **Sign up with email, or continue with Google** (and Apple once it's configured). Google and Apple share your name and email, and the email counts as confirmed. A Google or Apple account whose verified email matches an existing account is connected to it.
- **Email confirmation** for new accounts (switched on by the site owner once email sending is fully set up). The link works once and lasts 48 hours, and you can ask for it again.
- **Forgot password?** emails a one-hour, single-use link. Using it signs you out everywhere else.
- **Profile:** your name, email (with its confirmation status), rating, phone number and state (both optional and private: only you and the admins see them), USCF ID, sign-in methods (connect or disconnect Google/Apple, or set a password if you only used Google/Apple), change password, download all your games as PGN, and **Delete my profile**, which removes everything, including photos and community posts.

### Scoresheet photos

Snap your paper notation sheet so the paper can't get lost. Add photos on the **Add games** page, from a game's **Scoresheet** button, or beside each tournament round. Photos are shrunk in your browser before uploading (about 2,200 px, JPEG, so iPhone photos work too), kept privately (only you can see them), up to 6 per game or round. Tap one to see it full size.

### Community

- **Share a link.** A game's **Share** button makes a private link anyone can open to replay the game with the coach's analysis, without an account (the opponent's name is hidden unless you choose to show it). Copy it, see how many times it was opened, and turn it off at any time.
- **Share a game** with other players from the same Share dialog or a tournament round, or use **Ask the community** to pick a game and ask a question about it. Others see your display name only; your opponent's name and the tournament stay hidden unless you choose to show them.
- **Browse** all shared games, questions, unanswered questions, or your own. Replay any game with the coach's analysis, the evaluation chart and the coach's notes, and **comment**, optionally about a specific move (the comment then has a button that jumps to it).
- **Like** games and mark comments **Helpful**. **Report** anything that isn't right; admins review reports.
- **Points and levels.** Share a game +10, ask a question +5, comment on someone else's game +3, be first to answer a question +5, get a like on your game +2, get a Helpful on your comment +3. Seven levels: Newcomer, Helper (20), Contributor (60), Mentor (150), Coach (300), Master Coach (600) and Grandmaster (1000). Your level shows next to your name, there's a progress card and a *Top helpers* leaderboard (this month / all time), and a little celebration when you level up. Liking your own posts earns nothing, and only 5 shares and 10 comments a day count.

### Feedback and contact

- **Send feedback** from the speech-bubble button in the sidebar: an idea, a problem, praise or anything else. It is saved and emailed to the site owner, who can reply to you directly.
- **Contact us** is on the sign-in pages, your profile and the feedback dialog, and works without an account. It is protected against spam.

### Admin dashboard (for the site owner)

Registration numbers (accounts, new this week and month, confirmed emails, active this week, games), a sign-ups-per-day chart, the accounts table (with rating, USCF profile link, games, shared games, community level and last sign-in), reported content to hide or keep, feedback and contact messages (reply by email from the dashboard, with the reply kept on the message, or delete them), and managing admins. An admin can **view the app as any user** (read-only, for up to an hour, with a banner and *Stop viewing*) and can **delete an account** after typing its email.

## Run it locally

Python is managed by [uv](https://docs.astral.sh/uv/); nothing is installed system-wide.

```
uv sync
uv run chesscoach-serve            # then open http://127.0.0.1:8000
uv run pytest                      # run the tests (217)
uv run chesscoach game.pgn --color both   # command-line report, no account needed
```

Stockfish is expected at `engines/stockfish/` (or set `STOCKFISH_PATH`). Analysis takes about 30-60 seconds per game. Locally, everything is stored in one SQLite file under `data/`, emails are written to the log instead of being sent (so you can copy verification and reset links from the console), and photos are kept under `data/uploads/`.

Optional extras: `uv sync --extra postgres` (PostgreSQL storage), `--extra aws` (Amazon SES email and S3 photo storage), `--extra apple` (Sign in with Apple).

## Configuration

All settings are optional environment variables (see `.env.example`). The production values are in [deploy/aws/dukesmateai.env](deploy/aws/dukesmateai.env) and [DEPLOYMENT.md](deploy/aws/DEPLOYMENT.md#configuration).

**Storage and analysis**

| Variable | Default | Meaning |
|---|---|---|
| `CHESSCOACH_DATA` | `./data` | Folder for the SQLite database and local photos. **Back this up.** |
| `DATABASE_URL` | unset | A `postgresql://` URL stores everything in PostgreSQL instead (needs `--extra postgres`) |
| `CHESSCOACH_STORAGE` | `local` | Where scoresheet photos go: `local` (under the data folder) or `s3` |
| `CHESSCOACH_S3_BUCKET` | unset | The private bucket for `s3` storage |
| `AWS_REGION` | unset | Region for S3 and SES |
| `STOCKFISH_PATH` | bundled | Path to a Stockfish binary |
| `CHESSCOACH_DEPTH` | `12` | Search depth per position |
| `CHESSCOACH_THREADS` | `1` | `1` makes results reproducible; more is faster but can vary |

**Accounts and security**

| Variable | Default | Meaning |
|---|---|---|
| `CHESSCOACH_COOKIE_SECURE` | `false` | Set `true` when served over HTTPS |
| `CHESSCOACH_ALLOW_SIGNUP` | `true` | Set `false` to stop new accounts |
| `CHESSCOACH_SESSION_DAYS` | `30` | How long a sign-in lasts |
| `CHESSCOACH_VERIFY_EMAIL` | `false` | New accounts must confirm their email before signing in (needs working email) |
| `CHESSCOACH_ADMIN_EMAILS` | unset | Comma-separated admin accounts (their email must be confirmed); more can be added on the dashboard |
| `CHESSCOACH_GOOGLE_CLIENT_ID`, `CHESSCOACH_GOOGLE_CLIENT_SECRET` | unset | Turns on "Continue with Google" |
| `CHESSCOACH_APPLE_CLIENT_ID`, `CHESSCOACH_APPLE_TEAM_ID`, `CHESSCOACH_APPLE_KEY_ID`, `CHESSCOACH_APPLE_PRIVATE_KEY` | unset | Turns on "Continue with Apple" (needs `--extra apple`) |

**Email and contact**

| Variable | Default | Meaning |
|---|---|---|
| `CHESSCOACH_MAIL_BACKEND` | `log` | `log` (print emails to the log) or `ses` (Amazon SES, needs `--extra aws`) |
| `CHESSCOACH_MAIL_FROM` | `Chess Varsity <no-reply@localhost>` | Sender address |
| `CHESSCOACH_PUBLIC_URL` | unset | The site's address, used in email links; required with `ses` |
| `CHESSCOACH_FEEDBACK_TO` | unset | Where feedback, contact messages and reports are emailed; empty saves them only |
| `CHESSCOACH_CONTACT_EMAIL` | unset | An address shown publicly on the contact page; empty shows only the form |

## Publishing it

The production copy runs on AWS (EC2, RDS PostgreSQL, S3, SES) behind Caddy at https://dukesmateai.com; [deploy/aws/DEPLOYMENT.md](deploy/aws/DEPLOYMENT.md) describes it step by step, and `deploy/aws/deploy.sh` ships a new version.

For a simpler setup, `docker compose up -d --build` runs the app with SQLite; put an HTTPS reverse proxy in front of port 8000 (with Caddy, `your.domain { reverse_proxy 127.0.0.1:8000 }` is the whole config). The Docker image installs Debian's Stockfish, so exact numbers can differ slightly, and it has not been built or run in this repository's tests.

Checklist before sharing the link:

1. Serve over HTTPS and set `CHESSCOACH_COOKIE_SECURE=true`.
2. Set up email (`ses`, `CHESSCOACH_PUBLIC_URL`, `CHESSCOACH_MAIL_FROM`) so password resets work, then turn on `CHESSCOACH_VERIFY_EMAIL`.
3. Set `CHESSCOACH_ADMIN_EMAILS` to your address and confirm it (Profile → *Send confirmation link*).
4. Back up the database (the AWS setup does this nightly).
5. Read `NOTICE.md`: Stockfish and python-chess are GPL-3.0, which affects how you may distribute the app.
6. This holds young people's data. Publish a privacy notice (what you store; that shared games are visible to other members; that admins can view accounts read-only), consider a parent's approval before sharing, and check the rules where you operate (for example COPPA in the US or GDPR in the EU).

## How it is built

A FastAPI app (one process, with a background analysis worker and Stockfish) serving a plain-JavaScript interface with no build step, storing data in SQLite or PostgreSQL. The chess coaching is deterministic: Stockfish measures, rule-based code explains. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the components, data model, main flows, security design and trade-offs.

```
src/chesscoach/
  engine.py, tactics.py, balance.py, analyzer.py, commentary.py, explain.py, suggest.py, thinking.py   chess analysis and wording
  openings.py, academy.py, prep.py, pgnio.py                                                          openings, learning content, PGN
  insights.py, journey.py, goals.py, stats.py, training.py, gamify.py, uscf.py                        product logic
  config.py, db.py, security.py, mailer.py, storage.py, oauth.py, worker.py                           infrastructure
  api.py, deps.py, routes_*.py                                                                        the web API (about 120 endpoints)
  static/                                                                                             the interface (ES modules, CSS, fonts, pieces)
tools/mine_puzzles.py         finds puzzles with Stockfish
tools/build_model_games.py    builds the rated model-games library from the Lichess open database
tools/sqlite_to_postgres.py   copies a local SQLite database into an empty PostgreSQL one
deploy/aws/                   production scripts, service files and Caddyfile
tests/                        pytest suite (SQLite by default; PostgreSQL with TEST_DATABASE_URL)
```

## Known limits

- The USCF import relies on an unofficial, undocumented service that could change or block requests. It has been checked against the public response format and tested with a fake, but not against the live service inside the test suite. USCF gives results and opponents' names but no moves and no round numbers (rounds are numbered in the order USCF lists them).
- Suggested moves are searched for about a second, so the same position can occasionally rank two near-equal moves differently between runs. The reasons are facts about the board, so a quiet move (a slow pawn move, say) may get a short or general reason: often several moves are truly about equal, and the app says so.
- The tournament plan's target positions are well-known typical positions for each opening, not what your opponent will necessarily play.
- Thresholds for the habits (for example "about 50% of your free moves should attack") are coaching heuristics, not chess facts. They need checking against real games.
- Threat detection covers captures, forks and mates. Quieter threats (pins, skewers, trapped pieces, slow plans) are found only when the engine's evaluation shows them.
- In an already-lost position the evaluation cannot fall further, so later mistakes are not flagged.
- Clock times are not read, so time-trouble habits are not measured yet.
- The Attack Academy has about 8 attack puzzles among 33; it is easy to extend (`academy.py`, `tools/mine_puzzles.py`).
- Commentary is written from rules and engine numbers, so it explains what a move does but not deep plans. It can occasionally call an ordinary move a "sacrifice" or miss a quiet idea.
- The rated model games are chosen by rules (a fair fight, decided by checkmate, real attacking play), not by a human editor. Rebuild them with `tools/build_model_games.py`.
- Email confirmation for new users is off in production until Amazon SES grants production access (until then SES can only email verified addresses).
- Sign in with Apple needs an Apple Developer Program membership and keys; until then only Google is offered.
- The app runs as one process on one server: rate limits reset when it restarts, and it grows by using a bigger server rather than more servers.
- Community points are recalculated on every request, which is fine for a small community but would need caching for thousands of active members.
- Scoresheet photos are kept for reference only; the moves are not read from them automatically.
