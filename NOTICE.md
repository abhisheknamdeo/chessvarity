# Third-party components (Chess Varsity)

| Component | Used for | Licence |
|---|---|---|
| [Stockfish](https://stockfishchess.org) | Position evaluation (run as a separate process) | GPL-3.0 |
| [python-chess](https://github.com/niklasf/python-chess) | Move generation, PGN and engine protocol | GPL-3.0-or-later |
| [lichess chess-openings](https://github.com/lichess-org/chess-openings) | Opening names and lines (`data/openings.tsv`) | CC0 (public domain) |
| [Lichess open database](https://database.lichess.org) | The rated model games (`data/model_games_lichess.json`): moves and ratings only, no player names | CC0 (public domain); please confirm the current terms on the site |
| Chess piece images by Colin M.L. Burnett ("cburnett"), via [lichess](https://github.com/lichess-org/lila/tree/master/public/piece/cburnett) | Board pieces (`static/pieces/`) | GPL-2.0-or-later (also offered under GFDL / BSD / CC-BY-SA on Wikimedia Commons) |
| [Figtree](https://github.com/erikdkennedy/figtree) and [IBM Plex Mono](https://github.com/IBM/plex) | The typefaces (`static/fonts/`, Latin subsets from [Fontsource](https://fontsource.org)) | SIL Open Font License 1.1 |
| [FastAPI](https://fastapi.tiangolo.com), [Starlette](https://www.starlette.io), [Pydantic](https://docs.pydantic.dev) | Web framework | MIT |
| [Uvicorn](https://www.uvicorn.org) | Web server | BSD-3-Clause |
| [psycopg](https://www.psycopg.org) and psycopg-pool | PostgreSQL driver and connection pool (optional extra `postgres`) | LGPL-3.0-or-later |
| [boto3](https://github.com/boto/boto3) | Amazon SES email and S3 photo storage (optional extra `aws`) | Apache-2.0 |
| [PyJWT](https://github.com/jpadilla/pyjwt) with [cryptography](https://github.com/pyca/cryptography) | Signing Sign in with Apple's client secret (optional extra `apple`) | MIT; Apache-2.0 or BSD-3-Clause |
| [Caddy](https://caddyserver.com) | HTTPS reverse proxy on the production server (installed from Ubuntu, not bundled) | Apache-2.0 |

Famous games in the model-game library (for example the Opera Game and the Immortal Game) are historical
games and are not subject to copyright. The teaching text is original to this project.

## Before you publish

This project depends on GPL-3.0 software (python-chess, and Stockfish, which the Docker image ships).
If you **distribute** the application (publish the source, share the Docker image, or hand out copies),
the combined work should be released under a GPL-3.0-compatible licence, and you must offer the source of the
GPL components. Running it as a hosted website you operate is treated differently from distribution, but the
rules depend on where you are and how you deploy: please get advice if this will be a commercial product.
Choosing the licence for your own code is your decision, so no `LICENSE` file has been added.
