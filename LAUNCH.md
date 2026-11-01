# Launch checklist

Steps to take the app from this repo to the pilot surgeon's inbox, in order. Commands
marked **(Render shell)** run in the `maxfac-web` service's Shell tab on Render, with
`uv run --no-sync python cli.py …`; locally, use `uv run python cli.py …`.

## 1. Accounts and keys

- [ ] **Anthropic** API key (already in local `.env`).
- [ ] **Voyage AI** API key. Add a payment method: without one, Voyage limits requests to
      about 3 a minute.
- [ ] **NCBI** API key and a contact email (https://account.ncbi.nlm.nih.gov/settings/).
- [ ] **Postmark**: create a server, add a sending subdomain of the company domain
      (e.g. `papers.example.com`), and verify its SPF and DKIM records. Note the server
      token and the From address (e.g. `Maxfac Papers <papers@papers.example.com>`).

## 2. Check embeddings locally

- [ ] Add `VOYAGE_API_KEY` to `.env` (never to `.env.example`).
- [ ] `uv run python cli.py embed`: about 1,000 papers, well inside Voyage's free tier.
- [ ] `uv run python cli.py narrow`: should report candidates and selections.

## 3. Deploy on Render

- [ ] New → Blueprint → this repository. It creates the database, the web service and two
      cron jobs (`maxfac-send` hourly, `maxfac-weekly` on Sundays), all in Frankfurt.
- [ ] Fill in the variables Render asks for, on each service that lists them:
      `BASE_URL` (the https address of the web service), `ANTHROPIC_API_KEY`,
      `VOYAGE_API_KEY`, `NCBI_API_KEY`, `NCBI_EMAIL`, `POSTMARK_SERVER_TOKEN`,
      `EMAIL_FROM`, `ADMIN_EMAIL`. `SECRET_KEY` is generated and shared automatically.
      The web service and jobs refuse to start if Postmark or the secret key is missing.
- [ ] Open `BASE_URL/healthz`: `{"status": "ok", "db": "ok"}`.

## 4. Accounts

- [ ] **(Render shell)** `users add YOUR_EMAIL --name "Your name" --admin`
- [ ] **(Render shell)** `users add SURGEON_EMAIL --name "Their name" --calibrator`
- [ ] Sign in at `BASE_URL/login` with your address; the email should arrive within a
      minute. Tap **Sign in** on the page the link opens.

## 5. First papers

- [ ] **(Render shell)** `ingest --backfill` (90 days, about 1,000 papers).
- [ ] **(Render shell)** `embed`
- [ ] **(Render shell)** `narrow --limit 1200` (selects the whole backfill once).
- [ ] **(Render shell)** `grade --batch`: about $6–10 for the backfill, usually done within
      an hour. Later weeks run by themselves under `LLM_MONTHLY_CAP_USD`.

## 6. Calibrate with the surgeon (SPEC §12)

- [ ] **(Render shell)** `calibrate sample --n 20`, then `calibrate grade`.
- [ ] The surgeon signs in and opens **Calibration** in the header: 20 papers, scored
      blind.
- [ ] **(Render shell)** `calibrate report`. Launch bar: within ±1 on at least 80% for every
      criterion and 90% for proof strength.
- [ ] If it is not met: revise the rubric text, bump `RUBRIC_VERSION`, deploy,
      `calibrate grade`, `calibrate report` again. Then `regrade` so the feed uses the new
      version (it is capped by the monthly spend guard too).

## 7. The surgeon's profile

- [ ] The surgeon finishes setup after signing in: interests, topics, seed papers, weights.
- [ ] Their feed (`/`) should show graded papers. If it is empty, check `/admin` and that
      `embed` has run since they saved topics.
- [ ] In **Settings**, check their weekly day, time and timezone (default Monday 06:30,
      Copenhagen).

## 8. Test email

- [ ] `/admin` → **Send test email**: check it arrives (not in spam), reads well on a phone,
      and that the links open the app. Its buttons deliberately do not work.

## 9. Live

- [ ] After the first Sunday: `/admin` shows a weekly run with status `ok`.
- [ ] After the first send slot: the surgeon has their email; `/admin` spend is as expected.
- [ ] Weekly: glance at `/admin` for failed runs, spend and score disputes. Alerts (failed
      run, spend cap, 80% of the cap, quiet weeks) go to `ADMIN_EMAIL`.
