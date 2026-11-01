# SPEC — Maxfac Paper Recommender (MVP)

A web app that sends a maxillofacial surgeon 1–2 research papers by email every week and keeps a ranked in-app feed of suggestions. Every paper is graded by an LLM on quality criteria; the surgeon picks topics, weights the criteria, and refines the profile by liking, reading and dismissing papers.

Status: design agreed, nothing built. This file is the source of truth; update it when decisions change.

---

## 1. Goals and non-goals

**Goals (MVP)**
- One pilot surgeon uses it weekly with real PubMed papers, real grades and a real email.
- Every recommendation is explainable: 5 visible scores, each with a one-line justification.
- Feedback (like / read / not for me) measurably changes what gets recommended.
- Data model is per-user from day one so a second user needs no migration.

**Non-goals (MVP)**
- Self-serve sign-up, billing, teams.
- Search across all graded papers (later).
- Languages other than English.
- Mobile app (responsive web only).
- Full-text hosting or PDF storage (link out only).

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Paper** | A PubMed record, keyed by PMID. |
| **Candidate** | A paper fetched by the weekly specialty query, before grading. |
| **Grade** | The 4 *intrinsic* scores for one paper under one rubric version + model. Shared by all users. |
| **Intrinsic criteria** | `proof_strength`, `novelty`, `depth`, `practical_usefulness`. Properties of the paper. |
| **Pertinence** | 5th criterion. Per-user: how well a paper matches that user's profile. Computed from embeddings, never by the LLM. |
| **Profile** | A user's topic chips, seed papers, criterion weights, criterion minimums, and feedback history. |
| **Weighted score** | The per-user ranking score combining all 5 criteria with the user's weights. |
| **Fresh pick** | Email slot 1: best paper whose PubMed entry date is within the last 7 days. |
| **Missed pick** | Email slot 2: best unread, never-sent paper from the last 90 days. |
| **Active window** | The last 90 days of papers. Rubric changes regrade this window only. |
| **Rubric version** | Integer identifying the grading prompt + scale definitions. Stored on every grade. |

---

## 3. Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Web | FastAPI + Jinja2 templates + HTMX | Server-rendered, no SPA build step. |
| DB | Postgres 16 + `pgvector` | Embeddings stored in the DB. |
| ORM / migrations | SQLAlchemy 2.x + Alembic | |
| LLM | Anthropic API, model `claude-sonnet-5-5` | Grading via **Message Batches API** (50% off). Structured output via a JSON schema (`output_config.format`). |
| Embeddings | Voyage AI `voyage-4` (1024 dims) | Free tier covers the pilot volume. Keep behind an interface so it can be swapped. |
| Paper source | NCBI E-utilities (PubMed + PMC `efetch`) | Register an API key (10 req/s). Send `tool` and `email` params. |
| Email | Postmark (transactional), subdomain of the ApS domain with SPF + DKIM | Free plan covers the pilot. Without `POSTMARK_SERVER_TOKEN` (local development) emails are written to a gitignored `var/outbox/` folder instead. |
| Hosting | Render, Frankfurt region: web service (Starter), Postgres (Basic), cron jobs | All data in the EU. |
| Auth | Magic link by email | Random token, single-use, 15 min expiry; only its hash is stored. |
| Signed links | `itsdangerous` | For one-tap email actions and magic links. |
| Tests | pytest, with recorded fixtures for PubMed / Anthropic / Voyage / Postmark | No live API calls in CI. |
| Tooling | `uv`, `ruff`, `mypy` (strict on `app/domain`) | |

Expected run cost for the pilot: ~$20–25/month (see §14).

---

## 4. Architecture

```
            ┌─────────────── weekly job (Sun 02:00 Europe/Copenhagen) ───────────────┐
 PubMed ──► │ 1 fetch ─► 2 embed ─► 3 narrow ─► 4 full-text ─► 5 grade (batch) ─► 6 store │
            └────────────────────────────────────────────────────────────────────────────┘
                                                │
            ┌──── hourly job ────┐              ▼
            │ 7 select picks per │ ◄──── Postgres (papers, grades, embeddings,
            │   due user ─► send │        users, profiles, feedback, sends)
            └────────────────────┘              ▲
                                                │
          Surgeon ◄── email (one-tap links) ────┤
          Surgeon ◄──► web app (feed, library, profile, settings)
```

Suggested layout:

```
app/
  main.py                # FastAPI app factory
  config.py              # pydantic-settings, all env vars
  db/                    # models, session, alembic
  domain/                # pure logic, no I/O: ranking, pick selection, pertinence, weight suggestions
  sources/pubmed.py      # esearch / efetch / PMC OA
  grading/
    rubric.py            # RUBRIC_VERSION + prompt text
    grader.py            # batch submit / poll / parse
  embeddings/            # interface + voyage impl
  email/                 # templates + postmark client
  web/                   # routes, templates, htmx partials
  jobs/
    weekly_ingest.py
    send_due_emails.py
    regrade_window.py
cli.py                   # typer: ingest, grade, regrade, calibrate, send-test
tests/
```

Keep `app/domain` free of I/O so ranking and pick selection are unit-testable with plain data.

---

## 5. Data model

All timestamps UTC. All IDs UUID unless noted.

**users**: `id`, `email` (unique), `name`, `timezone` (default `Europe/Copenhagen`), `send_weekday` (0–6, default Monday), `send_local_time` (default `06:30`), `created_at`, `is_admin`.

**papers**: `pmid` (PK, text), `doi`, `pmcid` (nullable), `title`, `abstract`, `journal`, `pub_types` (text[]), `mesh_terms` (text[]), `authors` (jsonb), `entrez_date` (date: when it entered PubMed; drives "fresh"), `pub_date`, `is_open_access` (bool), `fetched_at`.

**paper_embeddings**: `pmid` (PK/FK), `model`, `vector` (vector(1024)), `created_at`. Embedded text = title + abstract.

**candidates**: `pmid`, `week_of` (date: Monday of the ISO week the narrowing ran), `narrow_score` (float), `selected_for_grading` (bool). One row per paper per ingest week, for auditability; re-running narrowing in the same week overwrites that week's rows.

**grades**: `id`, `pmid`, `rubric_version` (int), `model` (text), `input_source` (`full_text` | `abstract`), `proof_strength`, `novelty`, `depth`, `practical_usefulness` (smallint 1–5 each), `justifications` (jsonb: one line per criterion), `summary` (2–3 sentences), `why_it_matters` (one sentence), `study_design` (text, extracted), `sample_size` (int, nullable), `input_tokens`, `output_tokens`, `created_at`. Unique on (`pmid`, `rubric_version`, `model`). **The current grade** = the latest row for the current `RUBRIC_VERSION`.

**topics**: `id`, `user_id`, `label` (e.g. "Orthognathic surgery: virtual surgical planning"), `description`, `embedding` (vector, nullable until embedded), `embedding_model`, `source` (`onboarding` | `manual`), `active` (bool), `created_at`.

**seed_papers**: `user_id`, `pmid`.

**criterion_settings**: `user_id` (PK), `w_pertinence`, `w_proof_strength`, `w_novelty`, `w_depth`, `w_practical_usefulness` (floats 0–5, default 1), `min_pertinence`, `min_proof_strength`, `min_novelty`, `min_depth`, `min_practical_usefulness` (smallint 1–5, nullable = no minimum), `hide_case_reports` (bool, default true), `study_types` (text[], nullable = all).

**feedback**: `id`, `user_id`, `pmid`, `kind` (`read` | `like` | `not_for_me` | `unlike` | `unread`), `source` (`email` | `app`), `created_at`. Append-only; current state is derived from it (§9).

**score_disputes**: `id`, `user_id`, `pmid`, `grade_id`, `criterion`, `user_score` (1–5, nullable), `comment`, `created_at`.

**email_sends**: `id`, `user_id`, `sent_at`, `postmark_message_id`, `fresh_pmid` (nullable), `missed_pmid` (nullable).

**profile_vectors**: `user_id` (PK), `model` (embedding model of the vector), `vector`, `updated_at`. Cached; recomputed on any topic, seed or feedback change. No row while nothing is embedded.

**llm_spend**: `month` (date), `usd` (numeric). Updated after every batch.

**magic_links**: `token_hash`, `user_id`, `expires_at`, `used_at`.

**login_attempts**: `id`, `email`, `ip_hash` (HMAC of the IP with `SECRET_KEY`), `created_at`. For the `/login` rate limit; rows older than an hour are pruned.

**calibration_items**: `id`, `pmid`, `rubric_version`, `surgeon_scores` (jsonb), `model_scores` (jsonb), `created_at`.

**grading_batches**: `id` (Anthropic batch id, PK), `rubric_version`, `model`, `pmids` (text[]), `input_sources` (jsonb: pmid → source), `submitted_at`, `ended_at` (nullable), `status` (`submitted` | `collected` | `failed`). Lets a re-run resume an open batch instead of paying for a new one.

---

## 6. Weekly ingest pipeline

Runs as a Render cron job, Sunday 02:00 Europe/Copenhagen. Every step is idempotent and resumable: re-running for the same week must not duplicate rows or re-grade already graded papers.

### 6.1 Fetch
- `esearch` on PubMed with the **specialty query** (config file `app/sources/specialty_query.txt`), restricted to `entrez_date` in the last 14 days (overlapping the previous run, so papers entered on its day after it ran are not missed; stored papers are skipped), plus a backfill mode for the first run (90 days).
- Starting query (to be tuned with the surgeon):
  - MeSH: `"Surgery, Oral"[Mesh]`, `"Orthognathic Surgery"[Mesh]`, `"Orthognathic Surgical Procedures"[Mesh]`, `"Maxillofacial Injuries"[Mesh]`, `"Mandibular Fractures"[Mesh]`, `"Temporomandibular Joint Disorders"[Mesh]`, `"Cleft Lip"[Mesh]`, `"Cleft Palate"[Mesh]`, `"Mouth Neoplasms"[Mesh]`, `"Jaw Neoplasms"[Mesh]`, `"Dental Implants"[Mesh]`, `"Osteonecrosis of the Jaw"`…
  - OR journal: *J Oral Maxillofac Surg*, *Int J Oral Maxillofac Surg*, *J Craniomaxillofac Surg*, *Br J Oral Maxillofac Surg*, *Oral Surg Oral Med Oral Pathol Oral Radiol*, *Oral Maxillofac Surg*, *Head Face Med*, *J Oral Maxillofac Surg Med Pathol*, *Craniomaxillofac Trauma Reconstr*.
  - Exclude: `Comment`, `Editorial`, `Erratum`, `Retraction of Publication`, `Letter` publication types.
- `efetch` in batches of 200 PMIDs; parse title, abstract, journal, publication types, MeSH, DOI, PMCID, dates. Skip papers with no abstract.
- Respect NCBI rate limits (≤10 req/s with API key) with retry + backoff.

### 6.2 Embed
Embed title + abstract for every new paper (`voyage-4`, input_type `document`). Batch up to the provider's limit.

### 6.3 Narrow
Papers are embedded with `input_type: document`; the anchor, topics and other query-like texts with `input_type: query`. Compute `narrow_score` = max cosine similarity between the paper and (a) every user's profile vector and each active topic embedding (so one niche topic is not diluted by the rest of a profile) and (b) a fixed **specialty anchor** vector (embedding of a paragraph describing the whole OMFS field, so new users aren't starved). The pool is every paper in the active window that has not been a candidate in an earlier week, so a paper stored late is still scored once. Select the top `GRADE_LIMIT_PER_WEEK` (default 100) for grading. Always include papers that already appear in a user's seed list.

### 6.4 Full text
For selected papers with a PMCID, fetch the article with PMC `efetch` (JATS XML). (NCBI retired the PMC OA Web Service in August 2026, and BioC returns nothing for recent articles.) A paper is **open access** when its XML carries a Creative Commons licence; set `is_open_access` then. Use the full text only when it is open access *and* the XML includes the body. Strip references, figures, tables and back matter, and truncate to `FULLTEXT_MAX_TOKENS` (default 12,000, estimated at 4 characters per token) keeping Methods and Results first. Otherwise grade from the abstract plus metadata. Record `input_source`. Full text is fetched at grading time and not stored.

### 6.5 Grade
Submit one Message Batch with one request per paper (see §7). Poll until it finishes (batches usually complete well within an hour; timeout after 24 h with an alert). Parse results, validate them (§7.4), and store them in `grades`. Failed or invalid items are retried once individually, then logged and skipped.

### 6.6 Spend guard
Before submitting, estimate cost from token counts. If `llm_spend` for the month + estimate > `LLM_MONTHLY_CAP_USD` (default 30), grade only the top N that fit and email the admin. Alert at 80% of the cap.

---

## 7. Grading

### 7.1 Call shape
- Model `claude-sonnet-5-5` via Batch API. No `temperature`: the API rejects sampling parameters since version 2026-10-21.
- Adaptive thinking at effort `GRADING_EFFORT` (default `low`); calibration (§12) sets the final level. Thinking tokens bill as output.
- System prompt = the rubric (§7.3); mark it with prompt caching.
- User content = metadata block (title, journal, publication types, MeSH terms, dates) + `<abstract>` + optional `<full_text>`.
- Structured outputs (`output_config.format`, JSON schema §7.2) guarantee schema-valid JSON. (Sonnet 5.5 rejects forced tool calls, so no `record_grade` tool.)
- A refusal (`stop_reason: "refusal"`) counts as a failed item. The individual retry (§6.5) runs synchronously with server-side `fallbacks: "default"`, which the Batch API does not accept; the grade records the model that actually answered.

### 7.2 Output schema

```json
{
  "study_design": "string (e.g. 'RCT', 'retrospective cohort', 'systematic review with meta-analysis', 'case report')",
  "sample_size": "integer | null",
  "proof_strength": {"score": 1, "justification": "≤ 25 words"},
  "novelty": {"score": 1, "justification": "≤ 25 words"},
  "depth": {"score": 1, "justification": "≤ 25 words"},
  "practical_usefulness": {"score": 1, "justification": "≤ 25 words"},
  "summary": "2–3 sentences, plain clinical English",
  "why_it_matters": "1 sentence on what a practising maxillofacial surgeon could do differently"
}
```

### 7.3 Rubric v1 (draft, to be calibrated with the surgeon; see §12)

**Proof strength**: how strong the evidence is that the main claim is true.
- 5: Systematic review/meta-analysis of RCTs, or a large well-conducted multicentre RCT.
- 4: Single RCT with adequate size and low risk of bias, or systematic review of mostly non-randomised studies.
- 3: Prospective cohort or well-controlled comparative study; small or open-label RCT with notable limitations.
- 2: Retrospective cohort, case-control or case series with comparison; cadaver or in-vitro biomechanics study.
- 1: Case report, small uncontrolled case series, narrative review, expert opinion, technical note.
- Adjust by at most 1 point for size, follow-up length and risk of bias; justify the adjustment.

**Novelty**: what the paper adds to existing knowledge (not how recent it is).
- 5: First evidence for a new technique, finding or concept, or overturns current practice.
- 4: Substantial new evidence on an open question (e.g. first RCT where only cohorts existed).
- 3: Meaningful extension: new population, longer follow-up, head-to-head comparison.
- 2: Mostly confirms known results with minor variation.
- 1: Replicates well-established knowledge; nothing new for a specialist.

**Depth**: how thorough and rigorous the work is.
- 5: Rigorous methods fully reported, appropriate statistics, long follow-up, limitations and confounders addressed.
- 4: Solid methods and reporting with minor gaps.
- 3: Adequate but with clear gaps (short follow-up, limited outcomes, thin statistics).
- 2: Superficial: few outcomes, weak analysis, unclear methods.
- 1: Anecdotal or descriptive only.
- If grading from the abstract only, cap at 4 and say so.

**Practical usefulness**: whether a practising maxillofacial surgeon could act on it.
- 5: Directly changes or confirms a common clinical decision; ready to apply.
- 4: Clear clinical implication for a common scenario, with some caveats.
- 3: Relevant to practice, but niche or needing more evidence first.
- 2: Mainly of research or academic interest.
- 1: No foreseeable clinical application.

Rubric text lives in `app/grading/rubric.py` with `RUBRIC_VERSION = 1`. Any wording change bumps the version.

### 7.4 Validation
Reject and retry if any score is outside 1–5, a justification is empty, or the summary is missing. If `input_source = abstract` and `depth = 5`, clamp to 4.

---

## 8. Pertinence and ranking (per user)

All in `app/domain/ranking.py`, pure functions.

### 8.1 Profile vector
```
v = normalize(
      1.0 * mean(active topic embeddings)
    + 1.0 * mean(seed paper embeddings)            # if any
    + 0.5 * mean(liked paper embeddings)           # if any
    - 0.3 * mean(not_for_me paper embeddings)      # if any
)
```
Coefficients live in config. Recompute on any topic or feedback change.

### 8.2 Pertinence score
`cos = cosine(paper, profile_vector)`. Map to 1–5 with configured thresholds (start with `[0.30, 0.40, 0.50, 0.60]` for 2/3/4/5, then tune from real data). Also keep the max cosine to any single topic, so a paper strongly matching one niche topic isn't diluted: `pertinence_cos = max(cos_profile, max_topic_cos)`.

### 8.3 Eligibility
A paper is eligible for a user if all of these hold:
- It has a current grade.
- `pertinence_cos ≥ PERTINENCE_GATE` (default 0.30).
- Every criterion meets the user's minimum, if one is set.
- It passes the hard filters: `hide_case_reports`, `study_types`.
- Its current state for that user is not `read` and not `not_for_me`.

### 8.4 Weighted score
```
weighted = Σ w_c · s_c / Σ w_c       over the 5 criteria, s_c ∈ 1..5
```
Ties are broken by `pertinence_cos`, then the newest `entrez_date`.

### 8.5 Weight suggestions (never automatic)
After ≥ 10 likes, compare the mean score of liked papers with the mean of shown-but-not-liked papers on each criterion. If one criterion's gap is ≥ 0.75 and its weight is not already the highest, show a dismissible banner: "Papers you like score high on proof strength. Raise its weight?" with a one-click apply. Never change weights silently.

---

## 9. Feedback

- Events are appended to `feedback`. A paper's current state per user is derived as `read: bool`, `liked: bool`, `dismissed: bool` (the last event of each pair wins: like/unlike, read/unread).
- `like` and `read` are independent: a surgeon may like a paper to save it for later without having read it.
- `not_for_me` removes the paper from the feed and feeds the negative term in §8.1. It can be undone from history.
- **Score dispute**: every score on a paper card has a "disagree" control (user's score + optional comment) that writes to `score_disputes`. It is shown on the admin page and used in recalibration. It does not change the shared grade.

---

## 10. Weekly email

### 10.1 Scheduling
An hourly cron job finds users whose local send time fell in the past hour and who have no `email_sends` row for the current ISO week, then builds and sends their email.

### 10.2 Pick selection (`app/domain/picks.py`)
1. **Fresh pick**: the top eligible paper by weighted score with `entrez_date` in the last 7 days and never sent to this user.
2. **Missed pick**: the top eligible paper from the active window (90 days), excluding the fresh pick and anything previously sent.
3. **Quality cutoff**: a pick is sent only if `weighted ≥ EMAIL_MIN_WEIGHTED` (default 3.5).
4. **Never zero**: if neither pick clears the cutoff, send the single best eligible missed pick anyway. If nothing at all is eligible, send a short "quiet week" email with a link to the feed and alert the admin (that means the profile or query needs attention).
5. The email therefore contains 1 or 2 papers.

### 10.3 Content per paper
Title, journal, year, the label "Fresh this week" or "You may have missed", 5 score pills with justifications (shown on tap in the app; shown inline in the email for the top 2 criteria by the user's weights), the summary, the why-it-matters line, a link to the paper (DOI → PubMed fallback) and an "Open access" badge when applicable.

Action buttons: **Like**, **Mark read**, **Not for me**, **Open in app**.

### 10.4 One-tap links
- `GET /a/{token}` where the token is signed with `itsdangerous` and carries `user_id`, `pmid`, `action`, `send_id`; it expires after 30 days.
- A GET only renders a confirmation page whose form auto-submits a POST. This keeps email security scanners that prefetch links from recording likes.
- The POST records the event (idempotent per `send_id` + `action`), then shows "Saved ✓ — open your feed".
- No login is required for these actions; opening the app itself still requires a session.

### 10.5 Delivery
Postmark transactional stream, with HTML and a plain-text part. Store `postmark_message_id`. No open or click tracking pixels (privacy, and the feedback links already give the signal).

---

## 11. Web app

Server-rendered with HTMX for in-place updates. Must work well on a phone.

| Route | Purpose |
|---|---|
| `/login` | Enter email → magic link. |
| `/auth#<token>` | The emailed link. The token is in the URL fragment, so it never reaches the server or its logs. GET only renders a page that POSTs the token (mail scanners that prefetch links cannot use it up); the POST consumes it and sets a session cookie (30-day, httpOnly, secure), then goes to `/onboarding` or `/`. |
| `/onboarding` | Step 1: free-text interests. Step 2: confirm or edit topic chips. Step 3: optional seed PMIDs/DOIs. Step 4: weights and minimums (defaults shown). |
| `/` (feed) | Top 10 eligible papers by weighted score, read hidden. Each card shows its scores, summary, actions and a "graded from abstract/full text" label. |
| `/paper/{pmid}` | Full card: all 5 justifications, metadata, actions, dispute control. |
| `/library` | Liked papers, newest first. |
| `/history` | Read and dismissed papers, with undo. |
| `/profile` | Topics (add/edit/deactivate), seed papers, weights (5 sliders), minimums, hard filters. Changes re-rank the feed immediately. |
| `/settings` | Send day/time, timezone, email address. |
| `/admin` | Admin only: last ingest run stats, spend vs cap, disputes, calibration report, "send test email" button. |

### 11.1 Onboarding topic extraction
The free text goes to Sonnet (normal API, not batch) with JSON-schema output (as for grading: forced tool use is not available on this model) → 4–12 topics, each with `label` and a 1–2 sentence `description` written in PubMed vocabulary. The free text itself is not stored. The user confirms or edits them; each confirmed topic's description is embedded. Seed PMIDs/DOIs/PubMed links are resolved via `esearch`/`efetch`; DOIs are resolved through esearch `[doi]`. Seeds without an abstract are not used (nothing to embed).

Without `ANTHROPIC_API_KEY`, or if the call fails, the surgeon types topics by hand. Embedding is best effort: if Voyage is unavailable, topics and seeds are saved unembedded and `cli.py embed` embeds them and refreshes profile vectors later.

Users are added by the operator (`cli.py users add EMAIL [--admin]`); `cli.py users link EMAIL` prints a sign-in link without sending email.

---

## 12. Calibration (before launch)

1. `cli.py calibrate sample --n 20` picks 20 recent candidates stratified by study design.
2. The surgeon grades them blind on `/admin/calibrate` against the rubric text (model scores hidden). Signed-in admins have access; a surgeon without an admin account uses a signed link from `cli.py calibrate link` (30-day expiry, token in the URL fragment so it never reaches server logs, then an httpOnly cookie). `cli.py calibrate grade` grades the set and snapshots the model's scores into `calibration_items`.
3. `cli.py calibrate report` shows, per criterion: exact agreement, agreement within ±1, quadratic-weighted kappa, and the papers with the biggest disagreements alongside the model's justifications.
4. Revise the rubric wording, bump `RUBRIC_VERSION`, rerun on the same 20 (`calibrate grade` creates rows for the new version and carries the surgeon's scores forward).
5. **Launch bar**: within-±1 agreement ≥ 80% on every criterion, and ≥ 90% on proof strength.

Later, disputes (§9) feed periodic recalibration.

---

## 13. Regrading

`cli.py regrade --window 90` re-grades every paper in the active window under the current `RUBRIC_VERSION`, with the same spend guard. Old grade rows stay for comparison. Ranking always uses the current version; papers without a current-version grade are ineligible until regraded.

---

## 14. Cost envelope

| Item | Basis | ~USD / month |
|---|---|---|
| Grading | ~430 papers × ~6.4k input + ~600 output tokens at $2 / $10 per M, Batch −50% | 4–8 |
| Embeddings | ~1M tokens/month, within the Voyage free tier | 0 |
| Email | Postmark free tier (100/month) for the pilot; Basic $15 above that | 0 |
| Hosting | Render Starter web $7 + Basic Postgres ~$7 + cron jobs (cents) | ~14 |
| **Total (pilot)** | | **~20–25** |

Each regrade of the 90-day window costs ~$10–25 one-off. Re-check list prices before quoting.

---

## 15. Config (env vars)

`DATABASE_URL`, `SECRET_KEY`, `BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-sonnet-5-5`, `GRADING_EFFORT=low`, `VOYAGE_API_KEY`, `EMBEDDING_MODEL=voyage-4`, `NCBI_API_KEY`, `NCBI_EMAIL`, `NCBI_TOOL`, `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `ADMIN_EMAIL`, `GRADE_LIMIT_PER_WEEK=100`, `FULLTEXT_MAX_TOKENS=12000`, `LLM_MONTHLY_CAP_USD=30`, `PERTINENCE_GATE=0.30`, `EMAIL_MIN_WEIGHTED=3.5`, `ACTIVE_WINDOW_DAYS=90`, `PROFILE_COEF_TOPICS=1.0`, `PROFILE_COEF_SEEDS=1.0`, `PROFILE_COEF_LIKED=0.5`, `PROFILE_COEF_NOT_FOR_ME=0.3` (§8.1).

---

## 16. Privacy and security

- Personal data stored: the surgeon's email, name, interests and feedback only. No patient data, ever.
- Hosted in the EU (Render Frankfurt). Postmark, Anthropic and Voyage receive only paper text, profile text and the email address (Postmark only). List them as sub-processors in a one-page privacy note.
- Account deletion endpoint: `/settings` → delete removes all of the user's rows.
- Magic links and action tokens are single-purpose, signed and expiring; only their hashes are stored.
- When `BASE_URL` is `https://`, the web app refuses to start with a missing or placeholder `SECRET_KEY`, or without `POSTMARK_SERVER_TOKEN` and `EMAIL_FROM`, rather than run with forgeable sessions or silently unsent sign-in emails.
- Rate-limit `/login` (5 per hour per email and per IP).

---

## 17. Testing

- **Unit tests** (`app/domain`): profile vector maths, pertinence mapping, eligibility, weighted score, pick selection (including the never-zero and quiet-week cases), weight suggestions.
- **Parser tests**: PubMed/PMC XML fixtures, including missing abstracts, missing DOIs and non-OA papers.
- **Grader tests**: recorded batch responses; validation and retry paths; spend-guard truncation.
- **Web tests**: FastAPI TestClient for magic-link login, one-tap GET→POST flow (prefetch-safe), idempotency, onboarding.
- **E2E smoke**: `cli.py send-test --user me` runs the full pipeline on a 10-paper fixture and renders the email to HTML locally.

---

## 18. Build order (tracer bullets)

Each milestone is shippable and demoable.

1. **Skeleton**: repo, uv, FastAPI hello, Postgres + pgvector, Alembic, Render deploy (Frankfurt), CI with ruff/mypy/pytest.
2. **PubMed ingest**: specialty query, fetch + parse + store, with a 90-day backfill via the CLI.
3. **Grading v1**: rubric, `record_grade` tool, a single synchronous call for one PMID via the CLI, then the batch path, validation and spend tracking.
4. **Calibration**: admin blind-grading page + report. *Run this with the surgeon now, while the rest is built.*
5. **Embeddings + narrowing**: embed papers, specialty anchor, top-N selection, full-text fetch for OA.
6. **Users + onboarding**: magic link, free text → topics → confirm, seeds, weights and minimums.
7. **Ranking + feed**: pertinence, eligibility, weighted score, feed / paper / library / history pages, in-app feedback, disputes.
8. **Weekly email**: pick selection, templates, Postmark, one-tap links, hourly send job.
9. **Weekly job wiring**: Sunday cron for the full pipeline, spend guard and alerts, admin dashboard.
10. **Polish + launch**: weight-suggestion banner, privacy note, account deletion, regrade command, launch with the pilot surgeon.

---

## 19. Assumptions to confirm (chosen during spec writing, not discussed)

- HTMX + server-rendered templates rather than a JS front end.
- Voyage `voyage-4` for embeddings and `pgvector` for storage.
- Render Frankfurt rather than Railway.
- Default send time Monday 06:30 Copenhagen; the surgeon can change it in settings.
- Numeric thresholds (pertinence gate, email cutoff, embedding coefficients, calibration launch bar) are starting values, to be tuned on real data.
- Liking and reading are independent states.
