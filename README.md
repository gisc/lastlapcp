# LastLapCP

Mobile-first, gamified revision app for A-level H2 Computing (9569) Papers 1 and 2.
Python + Flask + SQLite, server-rendered Jinja, vanilla JS/CSS, installable PWA.

- Tier 1 question types: single-answer MCQ and multi-select (checkbox) misconception
  questions, each with an explanation and a "common trap" note.
- Gamification: XP per correct answer (first-correct full XP, repeats 2 XP), daily
  streaks, per-topic mastery bars. No public leaderboard.
- Google sign-in restricted to a class allowlist. Teacher accounts get a class
  dashboard (per-student XP, streak, accuracy and per-topic mastery).

## Privacy / configuration (nothing sensitive in this repo)

All identity data is supplied through environment variables (set in the Olares app
settings, never committed):

| Var | Meaning |
| --- | --- |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth web client from Google Cloud Console |
| `SECRET_KEY` | Flask session signing key (any long random string) |
| `ALLOWED_EMAILS` | Comma-separated student Gmail addresses |
| `TEACHER_EMAILS` | Comma-separated teacher Gmail addresses (also allowed in) |
| `DATABASE_PATH` | SQLite path, defaults to `/data/lastlapcp.db` |

The SQLite database lives on a persistent volume (`/data`), so progress survives
app restarts and updates.

## Deploy on Olares (same flow as ThereSG)

1. Push this repo to `github.com/gisc/lastlapcp`. The GitHub Action builds
   `ghcr.io/gisc/lastlapcp:latest` on every push to `main`.
2. Olares Market > upload/install custom app from the `olares/` chart
   (same method used for ThereSG).
3. Fill in the five env vars above in the app settings.
4. The app is served at `https://lastlapcp.huatbigbig888.olares.com`
   (public entrance; the app itself does the Google sign-in + allowlist).
5. After every push: Olares Settings > Applications > LastLapCP > Stop, then Resume.

## Google OAuth client setup (one time)

1. <https://console.cloud.google.com> > create project **LastLapCP**.
2. APIs & Services > OAuth consent screen > **External** > app name `LastLapCP`,
   your Gmail as support email. No scopes beyond the default openid/email/profile.
3. Keep the app in **Testing** mode and add the 41 class emails as test users
   (Testing allows up to 100; this avoids Google's verification process).
4. Credentials > Create Credentials > OAuth client ID > **Web application**:
   - Authorised JavaScript origin: `https://lastlapcp.huatbigbig888.olares.com`
   - Authorised redirect URI: `https://lastlapcp.huatbigbig888.olares.com/login/callback`
5. Copy the client ID and secret into the Olares app env settings.

## Local dev

```
pip install -r requirements.txt
DATABASE_PATH=/tmp/lastlapcp.db SECRET_KEY=dev flask --app app run
```

## Adding questions

Append to `seed_questions.json` (one object per question; see existing entries for
the schema). Seed only applies to a fresh database; to reload, stop the app, delete
`/data/lastlapcp.db`, and resume.
