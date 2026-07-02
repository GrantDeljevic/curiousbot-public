# curiousbot

Discord utility bot for Emerald Library workflows, including author indexing,
author-score updates, follow-count lookups, and the Legacy Parke rent watcher.

## Configuration

Configuration is supplied through environment variables. Do not commit real
tokens, service account JSON, sheet IDs, guild IDs, channel IDs, role IDs, or
webhook IDs.

Required for the bot:

- `CURIOUSBOT_TOKEN`
- `CURIOUSBOT_APPLICATION_ID`
- `CURIOUSBOT_USER_ID`
- `OWNER_USER_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_FILE`

Required for author-sheet workflows:

- `AUTHORLIST_KEY`
- `BIWEEKLY_AUTHORLIST_KEY`
- `BIWEEKLY_AUTHORLIST_SHEET`
- `EL_GUILD_ID`
- `TESTING_GUILD_ID`
- `OPERATIONS_CHANNEL_ID`
- `BOTS_AND_UPDATES_CHANNEL_ID`

Required for FanFiction.net lookups through Weaver:

- `WEAVER_API_KEY`
- `WEAVER_BASIC_AUTH_USER`
- `WEAVER_BASIC_AUTH_PASSWORD`

See `.env.example` for the complete set of supported variables.

## Local Validation

```powershell
python -m unittest test_elupdate.py test_ffwebscrape.py test_legacyparke_watcher.py
python -m py_compile curiousbot.py elupdate.py ffwebscrape.py test_elupdate.py test_ffwebscrape.py test_legacyparke_watcher.py
```

## Deploy

The Heroku worker entrypoint is:

```text
worker: python curiousbot.py
```
