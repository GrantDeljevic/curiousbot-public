# curiousbot

`curiousbot` is a Discord utility bot for Emerald Library operations. It manages
author-list workflows, author score updates, profile follow-count lookups,
registry webhook routing, and a Legacy Parke rent watcher.

This repository is a public-safe export. Runtime-specific IDs, Google service
account credentials, Discord tokens, sheet IDs, webhook IDs, and third-party API
credentials are configured with environment variables instead of committed
source values.

## Features

- `/follows` profile score lookup for FanFiction.net, AO3, and Tapas.
- `/biweekly` author score updater backed by Google Sheets.
- `/index`, `autoindex`, and rank update helpers for author-list operations.
- Registry webhook parsing for author/editor/applicant/playtester workflows.
- Legacy Parke rent watcher with scheduled and manual runs.
- Focused unit coverage for biweekly row alignment, AO3 handling, and Legacy
  Parke watcher behavior.

## Repository Notes

The live bot is expected to run as a single Heroku-style worker:

```text
worker: python curiousbot.py
```

The public repo intentionally does not include:

- Google service account JSON.
- Discord bot tokens.
- Private spreadsheet IDs.
- Private Discord guild/channel/role/webhook IDs.
- Local browser binaries or generated Python cache files.

Use `.env.example` as the configuration template.

## Requirements

- Python 3.12, matching `runtime.txt`.
- A Discord application and bot token.
- Discord privileged intents enabled where needed:
  - Server Members Intent.
  - Message Content Intent.
- A Google service account with access to the relevant spreadsheets.
- Weaver credentials for FanFiction.net scraping, if FFN lookups are used.
- Chrome and Chromedriver for Selenium fallback paths, or Heroku's Chrome for
  Testing buildpack.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in real values locally or in Heroku
config vars:

```powershell
Copy-Item .env.example .env
```

Never commit `.env`, service account JSON, or real config values.

### Required Core Variables

- `CURIOUSBOT_TOKEN`: Discord bot token.
- `CURIOUSBOT_APPLICATION_ID`: Discord application ID.
- `CURIOUSBOT_USER_ID`: Discord bot user ID.
- `OWNER_USER_ID`: bot owner or alert recipient user ID.
- `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_FILE`: Google Sheets auth.

For Heroku, prefer `GOOGLE_SERVICE_ACCOUNT_JSON` containing the full service
account JSON as one config var. For local development, `GOOGLE_SERVICE_FILE` can
point at an untracked JSON file.

### Discord Routing Variables

The bot reads guild, channel, role, and webhook IDs from env vars. Comma-separated
lists are accepted for list-style values.

Important examples:

- `EL_GUILD_ID`
- `TESTING_GUILD_ID`
- `OPERATIONS_CHANNEL_ID`
- `BOTS_AND_UPDATES_CHANNEL_ID`
- `BIWEEKLY_ALLOWED_CHANNEL_IDS`
- `BIWEEKLY_ALLOWED_ROLE_IDS`
- `AUTHOR_WEBHOOK_IDS`

See `.env.example` for the complete list.

### Sheet Variables

- `AUTHORLIST_KEY`
- `BIWEEKLY_AUTHORLIST_KEY`
- `BIWEEKLY_AUTHORLIST_SHEET`
- `SENATE_ROSTER_KEY`
- `HYPIXEL_SHEET_KEY`

The Google service account must be explicitly shared onto any spreadsheet the
bot reads or writes.

### Scraper Variables

FanFiction.net lookups use the Weaver proxy:

- `WEAVER_API_KEY`
- `WEAVER_BASIC_AUTH_USER`
- `WEAVER_BASIC_AUTH_PASSWORD`
- `WEAVER_CRAWL_URL`

AO3 requests are intentionally conservative and serialized for the biweekly
path. If AO3 returns its bot-restriction teapot response, the job aborts early
and asks the user to try again later instead of burning through every row.

## Running Locally

After configuring `.env`:

```powershell
python curiousbot.py
```

For a syntax-only check:

```powershell
python -m py_compile curiousbot.py elupdate.py ffwebscrape.py activity.py auto_index.py auto_register.py hypixel.py indexupdate.py legacyparke_watcher.py rankupdater.py registry_ping.py bot_config.py
```

## Tests

Run the local test suite:

```powershell
python -m unittest test_elupdate.py test_ffwebscrape.py test_legacyparke_watcher.py
```

The tests cover:

- Row-aligned biweekly score writes.
- Carrying forward fallback scores.
- AO3 URL normalization, retry policy, and bot-restriction detection.
- Legacy Parke rent watcher parsing and message behavior.

## Heroku Deploy

The app is a worker process. A typical Heroku setup uses:

```powershell
heroku buildpacks:add heroku/python
heroku buildpacks:add https://github.com/heroku/heroku-buildpack-chrome-for-testing
heroku config:set CURIOUSBOT_TOKEN=...
heroku config:set GOOGLE_SERVICE_ACCOUNT_JSON=...
git push heroku main
```

Set every required variable from `.env.example` as a Heroku config var. Do not
commit a `.env` file or service account file for deployment.

## Security

If a credential has ever been committed to a public repo, rotate it. Removing it
from a later commit is not enough because git history preserves old contents.

This export was created as a fresh repository to avoid carrying old private git
history forward. Keep it that way by committing only source code, tests,
documentation, and placeholder config templates.

## Operational Notes

- The biweekly update is a long-running job. It can take more than two hours on
  a full sheet.
- The Discord command layer is thin; the important biweekly behavior lives in
  `elupdate.py` and `ffwebscrape.py`.
- Legacy Parke watcher constants are intentionally present in source in this
  public export. Runtime overrides for channel, ping user, worksheet title,
  move-in date, interval, and data source are still available through env vars.
