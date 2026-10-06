# Deploying Dukes Mate AI on AWS

How the production copy of Dukes Mate AI (https://dukesmateai.com) runs on AWS, and how to operate it. There are no passwords or keys in this document or anywhere in the repository: they live only in AWS Secrets Manager. For how the app itself is designed, see [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).

## Architecture

```
Cloudflare DNS (dukesmateai.com, dukemateai.com)
        │
Internet ──80/443──▶ Elastic IP 77.112.68.164
                        │
                 EC2 "DukesMateAI-web" (Ubuntu 24.04, t3.small, us-east-2a, IAM role DukesMateAI-web)
                   Caddy :80/:443 (Let's Encrypt, redirects) ──▶ uvicorn 127.0.0.1:8000
                   one process: API + analysis thread + Stockfish 16 + mail thread
                        │  TLS (verify-full), port 5432, only from the web server's security group
                        ▼
                 RDS "dukesmateai-db" (PostgreSQL 18.3, db.t4g.micro, private subnets, encrypted)

Secrets Manager: DukesMateAI/app-db (app database user), DukesMateAI/oauth (Google/Apple keys),
                 rds!db-… (database admin, managed and rotated by RDS)
S3 s3-dukesmateai (private, encrypted): scoresheets/ (Standard-IA), backups/ (30 days), releases/ (90 days)
SES: sends as no-reply@dukesmateai.com (DKIM, SPF, DMARC)
Management: AWS Systems Manager (no SSH port open, no key pairs)
```

The project's Region is **us-east-2 (Ohio)**. Projects in the new AWS experience can only create Regional resources in their assigned Region.

## Names

Everything was renamed from the app's first name (Duke's King) to **Dukes Mate AI** on 28 Sep 2026: S3 bucket `s3-dukesmateai`, RDS `dukesmateai-db`, EC2 `DukesMateAI-web` with role and instance profile `DukesMateAI-web`, security groups `DukesMateAI-web` / `DukesMateAI-db`, secrets `DukesMateAI/app-db` and `DukesMateAI/oauth`, and on the server the `dukesmateai` user, service, folders (`/opt/dukesmateai`, `/etc/dukesmateai`) and Postgres database/user. AWS resources carry the tag `app=DukesMateAI`. Two names can't be changed by AWS: the DB subnet group `dukes-king-private` (tagged `DukesMateAI-private`) and the RDS-managed admin secret `rds!db-…`. The Python package is still called `chesscoach`.

## Resources

| Resource | Details |
|---|---|
| EC2 instance | `i-0e396869f220e9c6c`, tag `Name=DukesMateAI-web`, t3.small (2 vCPU, 2 GB), 20 GB gp3 encrypted, IMDSv2 required |
| Elastic IP | `77.112.68.164` (tagged `DukesMateAI-web`) |
| IAM role | `DukesMateAI-web` (and instance profile of the same name): AmazonSSMManagedInstanceCore, plus the inline policy `DukesMateAI-app`: read the `DukesMateAI/app-db`, `DukesMateAI/oauth` and RDS admin secrets; read `releases/*`; write `backups/*`; read, write and delete `scoresheets/*`; send email only from `@dukesmateai.com` |
| RDS | `dukesmateai-db`, PostgreSQL 18.3, db.t4g.micro, 20 GB gp3, encrypted (aws/rds key), not publicly accessible, deletion protection on, automated backups 1 day (the Free plan maximum), window 08:00-08:30 UTC |
| RDS endpoint | `dukesmateai-db.clkcymyc4adv.us-east-2.rds.amazonaws.com:5432`, database `dukesmateai`, user `dukesmateai` (and `dukesmateai_test` for the test suite) |
| DB subnets | `dukes-king-private` subnet group (its original name: AWS can't rename subnet groups; it is tagged `DukesMateAI-private`): subnets `DukesMateAI-db-a` 172.31.128.0/24 (2a) and `DukesMateAI-db-b` 172.31.129.0/24 (2b), with route table `DukesMateAI-private`, which has no internet route |
| S3 bucket | `s3-dukesmateai`, public access blocked, SSE-S3 encryption, lifecycle rules for `backups/` (30 days) and `releases/` (90 days) |
| Secrets | `DukesMateAI/app-db` (`username`, `password`, `dbname`), `DukesMateAI/oauth` (Google/Apple keys), `rds!db-…` (database admin, rotated by RDS) |
| SES | Domain identity `dukesmateai.com` (Easy DKIM, MAIL FROM `mail.dukesmateai.com`), verified address for feedback notices |
| Domains | `dukesmateai.com` (main) and `dukemateai.com` (redirects), both registered and hosted at Cloudflare |

## Security groups and ports

| Group | Inbound | Notes |
|---|---|---|
| `DukesMateAI-web` (`sg-06da612f89a1f5dbb`) | TCP 80, 443 from anywhere (IPv4 and IPv6) | No SSH. Port 8000 is bound to localhost only. |
| `DukesMateAI-db` (`sg-066401e51866521de`) | TCP 5432 from `DukesMateAI-web` only | No outbound rules. |

## Configuration

The server's settings are in `/etc/dukesmateai/app.env` (source: [dukesmateai.env](dukesmateai.env)). `install.sh` writes it only on the first install, so edits made on the server are kept; settings that are new in a release are added, but values already there are never changed. Secrets are not in this file: `run-with-secret.sh` fetches them from Secrets Manager each time the service starts.

| Variable | Value | Meaning |
|---|---|---|
| `AWS_REGION` | `us-east-2` | Region for Secrets Manager and S3 |
| `DB_SECRET_ID` | `DukesMateAI/app-db` | Secret holding `username`, `password`, `dbname` |
| `DB_HOST`, `DB_PORT` | RDS endpoint, `5432` | Database address |
| `DB_SSLROOTCERT` | `/opt/dukesmateai/rds-ca.pem` | RDS certificate bundle; connections use `sslmode=verify-full` |
| `DATABASE_URL` | built at start-up, never stored | Set by `run-with-secret.sh` from the secret; its presence switches the app to PostgreSQL |
| `CHESSCOACH_DATA` | `/var/lib/dukesmateai` | Unused with PostgreSQL; kept for completeness |
| `STOCKFISH_PATH` | `/usr/games/stockfish` | Ubuntu's Stockfish 16 |
| `CHESSCOACH_DEPTH`, `CHESSCOACH_THREADS` | `12`, `1` | Analysis depth and threads |
| `CHESSCOACH_COOKIE_SECURE` | `true` | Session cookies only over HTTPS |
| `CHESSCOACH_ALLOW_SIGNUP` | `true` | Set to `false` once your account exists |
| `CHESSCOACH_SESSION_DAYS` | `30` | Sign-in length |
| `APP_HOST`, `APP_PORT` | `127.0.0.1`, `8000` | Only Caddy can reach the app |
| `BACKUP_BUCKET` | the S3 bucket | Nightly `pg_dump` destination |
| `CHESSCOACH_MAIL_BACKEND` | `ses` | `log` writes emails to the app log instead of sending them |
| `CHESSCOACH_VERIFY_EMAIL` | `false` until SES production access is granted, then `true` | New accounts must confirm their email before signing in |
| `CHESSCOACH_MAIL_FROM` | `"Dukes Mate AI <no-reply@dukesmateai.com>"` | Sender; keep the quotes (the apostrophe) |
| `CHESSCOACH_PUBLIC_URL` | `https://dukesmateai.com` | Base of links in emails; required when the backend is `ses` |
| `CHESSCOACH_FEEDBACK_TO` | the owner's address | Where feedback and contact-form messages go; empty means they are only saved |
| `CHESSCOACH_ADMIN_EMAILS` | the owner's address | Accounts that see **Admin** in the sidebar (registration stats at `#/admin`). The account's email must be confirmed first: Profile → *Send confirmation link* |
| `CHESSCOACH_CONTACT_EMAIL` | empty | An address shown publicly on the contact page (`#/contact`); empty shows only the form |
| `OAUTH_SECRET_ID` | `DukesMateAI/oauth` | Secret with the Google/Apple keys; its `CHESSCOACH_*` values are loaded at start-up |
| `CHESSCOACH_STORAGE`, `CHESSCOACH_S3_BUCKET` | `s3`, `s3-dukesmateai` | Where scoresheet photos are kept |

The web interface calls the API on the same address it was loaded from, so there are no API URLs or CORS settings to configure.

## Running commands on the server

There is no SSH. Use Systems Manager:

- **Browser:** EC2 console → Instances → `DukesMateAI-web` → Connect → Session Manager.
- **CLI:** `aws ssm start-session --target i-0e396869f220e9c6c --region us-east-2` (needs the Session Manager plugin), or `aws ssm send-command` as `deploy.sh` does.

Once on the server (`sudo -i` for root):

| Task | Command |
|---|---|
| Status | `systemctl status dukesmateai caddy` |
| Restart the app | `systemctl restart dukesmateai` |
| Stop / start | `systemctl stop dukesmateai` / `systemctl start dukesmateai` |
| App logs (live) | `journalctl -u dukesmateai -f` |
| App logs since boot | `journalctl -u dukesmateai -b` |
| Web access log | `tail -f /var/log/caddy/access.log` |
| Caddy logs | `journalctl -u caddy -f` |
| Health | `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}` |
| Backup now | `systemctl start dukesmateai-backup` then `journalctl -u dukesmateai-backup -n 5` |
| Next backup | `systemctl list-timers dukesmateai-backup.timer` |
| Open psql as the app | `set -a; . /etc/dukesmateai/app.env; set +a; sudo -E -u dukesmateai /opt/dukesmateai/bin/run-with-secret.sh psql` |

## Deploying a new version

From the project root on your computer, signed in with `aws login`:

```
deploy/aws/deploy.sh
```

It finds the server by its `Name=DukesMateAI-web` tag, packs `src`, `tools`, `tests` and `deploy` into `s3://s3-dukesmateai/releases/<timestamp>.tar.gz`, and through Systems Manager unpacks it into `/opt/dukesmateai/releases/<timestamp>`, installs the pinned dependencies from [requirements.txt](requirements.txt), installs the service files and [Caddyfile](Caddyfile), points `/opt/dukesmateai/current` at it, restarts the service and waits up to 40 seconds for `/api/health` (printing the app's log if it doesn't come up). Database changes are applied by the app itself when it starts. The five newest releases are kept on the server. A deploy restarts the app, so the site is unavailable for a few seconds.

On Windows, run it from Git Bash with the AWS CLI on the `PATH`. Keep shell scripts and service files with Unix line endings (LF): a CRLF in `install.sh` stops the deploy.

If you change dependencies, regenerate the pinned list first:

```
uv export --extra postgres --extra aws --extra apple --no-dev --no-hashes --no-emit-project --frozen > deploy/aws/requirements.txt
```

**Rolling back:** on the server, `ln -sfn /opt/dukesmateai/releases/<older> /opt/dukesmateai/current && systemctl restart dukesmateai`.

## HTTPS and DNS

The site is **https://dukesmateai.com**. `www.dukesmateai.com`, `dukemateai.com`, `www.dukemateai.com` and the bare IP address all redirect there. Both domains are registered at **Cloudflare**, and their DNS is hosted there (not in Route 53).

| Zone | Record | Value |
|---|---|---|
| dukesmateai.com | A `@`, A `www` | `77.112.68.164`, **DNS only** (grey cloud) |
| dukesmateai.com | CNAME `<token>._domainkey` ×3 | `<token>.dkim.amazonses.com` (SES Easy DKIM) |
| dukesmateai.com | MX `mail` (10), TXT `mail` | `feedback-smtp.us-east-2.amazonses.com`, `v=spf1 include:amazonses.com ~all` (SES custom MAIL FROM) |
| dukesmateai.com | TXT `_dmarc` | `v=DMARC1; p=none;` (tighten to `p=quarantine` once mail flows cleanly) |
| dukemateai.com | A `@`, A `www` | `77.112.68.164`, DNS only |
| dukemateai.com | TXT `@`, TXT `_dmarc` | `v=spf1 -all`, `v=DMARC1; p=reject;` (this name never sends mail) |

Keep the A records **DNS only**: Caddy on the server obtains the Let's Encrypt certificates itself. [Caddyfile](Caddyfile) is installed on every deploy, so change it in the repository. `CHESSCOACH_COOKIE_SECURE=true` must be set once HTTPS works.

Check: `curl -I http://dukemateai.com` gives a 308 to `https://dukesmateai.com/`, and `https://dukesmateai.com/api/health` returns `{"status":"ok"}`.

A load balancer and an ACM certificate are not needed for one server. Add them if you ever run more than one instance.

## Email

Verification links, password resets and feedback notices are sent with **Amazon SES** in us-east-2. The instance's role may send only from `@dukesmateai.com` addresses (statement `SendAsDukesMateAI` in the role's `DukesMateAI-app` policy); no email passwords are stored anywhere.

1. **Verify the domain:** the SES domain identity `dukesmateai.com` (Easy DKIM, custom MAIL FROM `mail.dukesmateai.com`) exists; its records are in the table above. `aws sesv2 get-email-identity --email-identity dukesmateai.com` shows `VerifiedForSendingStatus: true` once SES has seen them.
2. **Leave the sandbox:** new SES accounts can only send to verified addresses (200 a day). Request production access (`aws sesv2 put-account-details`, or the SES console) with the site URL and a description of the emails (sign-up confirmation, password reset, feedback notices; no marketing). AWS usually answers within a day.
3. **Switch on confirmation:** once production access is granted, set `CHESSCOACH_VERIFY_EMAIL=true` in `/etc/dukesmateai/app.env` (the backend is already `ses`), then `systemctl restart dukesmateai`.
4. **Check:** create an account with a real address, open the link, send feedback, and use "Forgot password?". Failures show in `journalctl -u dukesmateai | grep -i email`.

**Current status (28 Sep 2026):** the domain and MAIL FROM are verified and the backend is `ses`, so feedback, contact and report emails reach the owner. SES production access was requested and is pending; until AWS grants it, SES can only email verified addresses, so `CHESSCOACH_VERIFY_EMAIL` stays `false` and password-reset emails reach only verified addresses. Once granted, set `CHESSCOACH_VERIFY_EMAIL=true` (step 3). Bounced and complaining addresses are suppressed automatically (account-level suppression list).

Accounts that existed before verification was added count as verified. Feedback and contact messages are saved in the `feedback` table whether or not the email goes out: `SELECT created_at, category, email, message FROM feedback ORDER BY id DESC;` (see "Open psql as the app"), and they are listed on the admin dashboard.

## Sign in with Google and Apple

The buttons appear only for providers whose keys are set. The keys live in the Secrets Manager secret **`DukesMateAI/oauth`** (JSON), which `run-with-secret.sh` loads at start-up; nothing goes in the repository or in `app.env`.

| Key | Where it comes from |
|---|---|
| `CHESSCOACH_GOOGLE_CLIENT_ID`, `CHESSCOACH_GOOGLE_CLIENT_SECRET` | Google Cloud Console → Google Auth Platform → Clients → *Web application* |
| `CHESSCOACH_APPLE_CLIENT_ID` | Apple Developer → Identifiers → the **Services ID** (e.g. `com.dukesmateai.web`) |
| `CHESSCOACH_APPLE_TEAM_ID` | Apple Developer → Membership details |
| `CHESSCOACH_APPLE_KEY_ID`, `CHESSCOACH_APPLE_PRIVATE_KEY` | Apple Developer → Keys → a key with *Sign in with Apple*; the private key is the whole `.p8` file |

Redirect URLs to register with the providers:

- Google: `https://dukesmateai.com/api/auth/oauth/google/callback` (authorised JavaScript origin `https://dukesmateai.com`)
- Apple: domain `dukesmateai.com`, return URL `https://dukesmateai.com/api/auth/oauth/apple/callback`

Create or update the secret, then restart the app:

```
aws secretsmanager create-secret --region us-east-2 --name DukesMateAI/oauth --secret-string file://oauth.json
aws secretsmanager put-secret-value --region us-east-2 --secret-id DukesMateAI/oauth --secret-string file://oauth.json   # later changes
```

How accounts are matched: a Google/Apple account seen before signs in to its account; otherwise one whose **verified** email matches an existing account is connected to it; otherwise a new account is made with the email already confirmed and no password (the person can set one on the profile page). Apple users may share a private relay address (`…@privaterelay.appleid.com`); to email them, register `dukesmateai.com` / `no-reply@dukesmateai.com` under Apple Developer → *Sign in with Apple for Email Communication*.

## Scoresheet photos

Photos of paper scoresheets (Add games, a game's *Scoresheet* button, or Tournaments → a round → *Add photo*; a game also shows its round's photos) are shrunk to at most 2,200 px and saved as JPEG in the browser, then stored in the private bucket under `scoresheets/<user id>/` with the **Standard-IA** storage class (about half the price of Standard for files that are rarely read). The app streams them only to their owner, so there are no public links. Deleting a photo, round, tournament or account deletes the stored files too. Settings: `CHESSCOACH_STORAGE=s3`, `CHESSCOACH_S3_BUCKET`; the role's `Scoresheets` statement allows Get/Put/Delete on that prefix only.

## Community, admins and moderation

- **Sharing:** from a game page or a tournament round, *Share* makes a finished game public, with an optional question. Others see the sharer's display name only; the opponent and tournament are hidden unless the sharer ticks the box. Only signed-in users can see the community.
- **Reports:** anyone can report a shared game or a comment; the owner gets an email and it appears under *Reported content* on the admin dashboard, where an admin can hide it or dismiss the report.
- **Admins:** `CHESSCOACH_ADMIN_EMAILS` are permanent; more can be added or removed on the dashboard (`admins` table). Every admin must have confirmed their email.
- **Points and levels:** worked out live from community activity (never stored), in `gamify.py`: share +10, question +5, comment on someone else's game +3, first answer +5, like on your game +2, "helpful" on your comment +3; self-likes and hidden content earn nothing, and only 5 shares and 10 comments a day count. Levels: Newcomer 0, Helper 20, Contributor 60, Mentor 150, Coach 300, Master Coach 600, Grandmaster 1000.
- **Deleting accounts:** people delete their own profile on the Profile page; admins can delete any account (not their own or a permanent admin) from the accounts table by typing its email.
- **View as:** an admin can open any account read-only for up to an hour (the server refuses every change while viewing, and a banner says so). These sessions are marked in `sessions.impersonator_id`, logged, and not counted as the user's sign-ins. Mention this in your privacy notice.

## Backups and restore

- **Nightly logical backups:** `dukesmateai-backup.timer` runs `pg_dump` at about 07:30 UTC into `s3://s3-dukesmateai/backups/`. Backups are kept for 30 days.
- **RDS automated backups:** 1 day of point-in-time recovery, the Free plan maximum.

To restore a dump into the app database (this replaces its contents; stop the app first):

```
aws s3 cp s3://s3-dukesmateai/backups/<file>.dump /tmp/restore.dump
systemctl stop dukesmateai
set -a; . /etc/dukesmateai/app.env; set +a
sudo -E -u dukesmateai /opt/dukesmateai/bin/run-with-secret.sh pg_restore --clean --if-exists --no-owner -d dukesmateai /tmp/restore.dump
systemctl start dukesmateai
```

## Moving data from a local SQLite database

To copy an existing `data/chesscoach.sqlite3` into an **empty** production database, upload the file to the server (for example through `s3://…/releases/`), then run:

```
set -a; . /etc/dukesmateai/app.env; set +a
sudo -E -u dukesmateai /opt/dukesmateai/bin/run-with-secret.sh bash -c \
  '/opt/dukesmateai/venv/bin/python /opt/dukesmateai/current/tools/sqlite_to_postgres.py /tmp/chesscoach.sqlite3 "$DATABASE_URL"'
systemctl restart dukesmateai
```

The tool refuses to run if the database already has accounts.

## Running the tests against PostgreSQL

The test suite runs against PostgreSQL when `TEST_DATABASE_URL` is set; each test gets its own schema, which is dropped afterwards. On the server, use the `dukesmateai_test` database, never the app database.

Run it from a copy of the release with its own virtual environment (with `pytest` and `httpx`), as the `dukesmateai` user under `run-with-secret.sh`, then point `TEST_DATABASE_URL` at `dukesmateai_test` and **unset every `CHESSCOACH_*` production setting** first: for example, `CHESSCOACH_COOKIE_SECURE=true` stops the test client from signing in over plain HTTP, which makes most tests fail with `KeyError: 'player'`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Site does not load | `systemctl status caddy dukesmateai`; the security group still allows 80/443; the Elastic IP is still associated |
| 502 from Caddy | The app is down: `journalctl -u dukesmateai -n 50` |
| `PoolTimeout` or `password authentication failed` in the logs | Secret or RDS problem: check that `aws secretsmanager get-secret-value --secret-id DukesMateAI/app-db` works on the server and that RDS is `available` |
| `Stockfish not found` | `ls -l /usr/games/stockfish`; `STOCKFISH_PATH` in app.env |
| Games stay "queued" | Analysis runs one game at a time; `journalctl -u dukesmateai | grep analysis` |
| HTTPS certificate not issued | DNS must point at the Elastic IP before Caddy can obtain it: `journalctl -u caddy -n 50` |
| Sudden "Access Denied" from AWS | Check the project's spend status in AWS Settings → Billing |
| Everything was denied in a Region | Regional resources must be in us-east-2, the project's Region |
| Emails don't arrive | `journalctl -u dukesmateai \| grep -i email`; in the SES sandbox only verified recipients get mail; check spam folders and the domain's DKIM status |
| "Set CHESSCOACH_PUBLIC_URL" at start-up | The `ses` backend needs the public address for links in emails |
| "CHESSCOACH_STORAGE=s3 needs CHESSCOACH_S3_BUCKET" at start-up | Add `CHESSCOACH_S3_BUCKET=s3-dukesmateai` to `app.env` |
| Scoresheet photos don't load | The role's `Scoresheets` statement and the bucket name; `journalctl -u dukesmateai \| grep -i scoresheet` |
| "Continue with Google" missing | `curl http://127.0.0.1:8000/api/auth/providers`; the `DukesMateAI/oauth` secret and `OAUTH_SECRET_ID` |
| Deploy says `set: pipefail: invalid option` | A script has Windows (CRLF) line endings; convert it to LF |

## Monitoring

There is no alerting yet. Worth adding: a CloudWatch alarm on the instance status check and CPU, an RDS alarm on free storage and CPU, and an outside uptime check of `https://dukesmateai.com/api/health`. Until then, the admin dashboard, `journalctl -u dukesmateai` and the Caddy access log are the places to look.

## Cost (approximate, on-demand)

| Item | Approximate cost |
|---|---|
| EC2 t3.small | ~$15/month |
| RDS db.t4g.micro + 20 GB gp3 | ~$15/month |
| Public IPv4 address | ~$3.60/month |
| Secrets Manager (3 secrets) | ~$1.20/month |
| S3 (photos in Standard-IA, backups, releases) | cents |
| SES | $0.10 per 1,000 emails |
| Domains at Cloudflare (2 × .com) | ~$21/year |

About **$35/month** plus the domains. The project's Free-plan credits cover the AWS part until they run out (the plan must then be upgraded to keep running).
