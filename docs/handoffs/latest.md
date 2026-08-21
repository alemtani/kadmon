# Handoff

Repo: `alemtani/kadmon` (fork of `ayuan153/kadmon`).
North star: `VISION.md` (v2). Score: `docs/success-criteria.md`.
Sign-in: `docs/subscription-auth.md`.

Open PR: https://github.com/alemtani/kadmon/pull/1 (`docs/vision-2`).
Git: branch + PR, never commit to `main`. `origin` is this fork.

## Next after that PR merges

Grok subscription login so SuperGrok is usable without `XAI_API_KEY`.
Spec of record: `docs/subscription-auth.md`. Implement from `main`.
Do not start from `feat/multi-provider`.

v1 bar: `kadmon login grok` (device-code), tokens in
`~/.config/kadmon/tokens.toml` mode 0600, OAuth host
`cli-chat-proxy.grok.com/v1`. Pool 402/426: stop or ask, no silent key
fallback.
