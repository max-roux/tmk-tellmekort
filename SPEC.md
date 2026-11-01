# SPEC — Tell Me Kort (MVP)

Tell Me Kort (team name TMK) is a web app that sends a maxillofacial surgeon 1–2 research papers by email every week and keeps a ranked in-app feed of suggestions. Every paper is graded by an LLM on quality criteria; the surgeon picks topics, weights the criteria, and refines the profile by liking, reading and dismissing papers.

Status: milestones 1-10 built (see §18); launch steps are in LAUNCH.md. This file is the source of truth; update it when decisions change.

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
| Web | FastAPI + Jinja2 templates | Server-rendered, no SPA build step. Actions are plain HTML forms that POST and redirect back. |
| DB | Postgres 16 + `pgvector` | Embeddings stored in the DB. |
| ORM / migrations | SQLAlchemy 2.x + Alembic | |
| LLM | Anthropic API, model `claude-sonnet-5-5` | Grading via **Message Batches API** (50% off). Structured output via a JSON schema (`output_config.format`). |
| Embeddings | Voyage AI `voyage-4` (1024 dims) | Free tier covers the pilot volume. Keep behind an interface so it can be swapped. |
| Paper source | NCBI E-utilities (PubMed + PMC `efetch`) | Register an API key (10 req/s). Send `tool` and `email` params. |
| Email | MVP: a dedicated Gmail account over SMTP (`smtp.gmail.com:587`, app password); free, no domain needed, ~500 emails/day. Later: Postmark (transactional) on a subdomain of the ApS domain with SPF + DKIM | Postmark is used when `POSTMARK_SERVER_TOKEN` is set, else SMTP when `SMTP_HOST` is set, else (local development) emails are written to a gitignored `var/outbox/` folder. Render blocks SMTP ports on free instances only; our services are paid. |
| Hosting | Render, Frankfurt region: web service (Starter), Postgres (Basic), cron jobs | All data in the EU. |
| Auth | Magic link by email | Random token, single-use, 15 min expiry; only its hash is stored. |
| Signed links | `itsdangerous` | For one-tap email actions and magic links. |
| Tests | pytest, with recorded fixtures for PubMed / Anthropic / Voyage / Postmark / SMTP | No live API calls in CI. |
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
  email/                 # templates + postmark and smtp clients
  web/                   # routes and templates
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

**criterion_settings**: `user_id` (PK), `w_pertinence`, `w_proof_strength`, `w_novelty`, `w_depth`, `w_practical_usefulness` (floats 0–5, default 1), `min_pertinence`, `min_proof_strength`, `min_novelty`, `min_depth`, `min_practical_usefulness` (smallint 1–5, nullable = no minimum), `hide_case_reports` (bool, default true), `study_types` (text[], nullable = all), `dismissed_suggestions` (text[]: weight suggestions the user dismissed, §8.5).

**feedback**: `id`, `user_id`, `pmid`, `kind` (`read` | `like` | `not_for_me` | `unlike` | `unread` | `undismiss`, which undoes `not_for_me`), `source` (`email` | `app`), `send_id` (nullable: the email an action came from; unique per `send_id`, `pmid`, `kind`), `created_at`. Append-only; current state is derived from it (§9).

**score_disputes**: `id`, `user_id`, `pmid`, `grade_id`, `criterion`, `user_score` (1–5, nullable), `comment`, `created_at`.

**email_sends**: `id`, `user_id`, `week_of` (Monday of the week in the user's timezone), `sent_at`, `postmark_message_id`, `fresh_pmid` (nullable), `missed_pmid` (nullable; both null = quiet week). Unique on (`user_id`, `week_of`): the row is claimed before sending, so a week's email cannot go twice; a failed send deletes it for the next run to retry.

**profile_vectors**: `user_id` (PK), `model` (embedding model of the vector), `vector`, `updated_at`. Cached; recomputed on any topic, seed or feedback change. No row while nothing is embedded.

**llm_spend**: `month` (date), `usd` (numeric). Updated after every batch.

**magic_links**: `token_hash`, `user_id`, `expires_at`, `used_at`.

**login_attempts**: `id`, `email`, `created_at`. For the `/login` rate limit; rows older than an hour are pruned.

**pipeline_runs**: `id`, `started_at`, `finished_at`, `status` (`running` | `ok` | `failed`), `stats` (jsonb, per step), `error`.

**calibration_items**: `id`, `pmid`, `rubric_version`, `surgeon_scores` (jsonb), `model_scores` (jsonb), `created_at`.

**grading_batches**: `id` (Anthropic batch id, PK), `rubric_version`, `model`, `pmids` (text[]), `input_sources` (jsonb: pmid → source), `submitted_at`, `ended_at` (nullable), `status` (`submitted` | `collected` | `failed`). Lets a re-run resume an open batch instead of paying for a new one.

---

## 6. Weekly ingest pipeline

Runs as a Render cron job (`cli.py weekly`), Sundays at 01:00 UTC (Render schedules in UTC: 02:00 Copenhagen in winter, 03:00 in summer). Every step is idempotent and resumable: re-running for the same week must not duplicate rows or re-grade already graded papers. Each run is recorded in `pipeline_runs` with per-step stats; a failed run is recorded, the admin is emailed, and the job exits non-zero.

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
Submit one Message Batch with one request per paper (see §7). Poll until it finishes (batches usually complete well within an hour). Render stops a cron run after 12 h, so the run waits at most 10 h, then fails with an alert; the next run (or a manual `cli.py weekly`) collects the still-open batch instead of paying for a new one. Parse results, validate them (§7.4), and store them in `grades`. Failed or invalid items are retried once individually, then logged and skipped.

### 6.6 Spend guard
Before submitting, estimate each paper's batch cost from its prompt length (4 characters per token, plus 800 output tokens; real v1 grades use at most ~610; prompt caching is ignored, so the estimate errs high). If `llm_spend` for the month + estimate > `LLM_MONTHLY_CAP_USD` (default 30), grade only the top N that fit, best narrowing score first, stopping at the first paper that does not fit; email the admin. The rest stay selected and are graded in a later run. Email the admin when the month's spend crosses 80% of the cap (once, on crossing).

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
`cos = cosine(paper, profile_vector)`. Map to 1–5 with configured thresholds `[0.50, 0.58, 0.65, 0.72]` for 2/3/4/5. These were tuned on the first real run (2026-11-01): narrowing keeps papers close to the profile, so the graded papers' cosines span ~0.55–0.71 (10th–90th percentile), and the starting guess `[0.30, 0.40, 0.50, 0.60]` gave 82 of 102 eligible papers a 5. Recheck once the pilot surgeon's own topics are saved. Also keep the max cosine to any single topic, so a paper strongly matching one niche topic isn't diluted: `pertinence_cos = max(cos_profile, max_topic_cos)`.

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
After ≥ 10 likes, compare the mean score of liked papers with the mean of shown-but-not-liked papers on each criterion ("shown" = emailed to the user or given any feedback; feed views are not logged). Suggest the criterion with the widest gap if it is ≥ 0.75, its weight is not the sole highest and is below 5 (the default even weights tie every criterion at the top), and the user has not dismissed it: a banner on the feed, "Papers you like score high on proof strength. Raise its weight?" Apply sets it one above the highest weight (at most 5); "No thanks" records the dismissal so it never returns. Never change weights silently.

---

## 9. Feedback

- Events are appended to `feedback`. A paper's current state per user is derived as `read: bool`, `liked: bool`, `dismissed: bool` (the last event of each pair wins: like/unlike, read/unread).
- `like` and `read` are independent: a surgeon may like a paper to save it for later without having read it.
- `not_for_me` removes the paper from the feed and feeds the negative term in §8.1. It can be undone from history.
- **Score dispute**: every score on a paper card has a "disagree" control (user's score + optional comment) that writes to `score_disputes`. It is shown on the admin page and used in recalibration. It does not change the shared grade.

---

## 10. Weekly email

### 10.1 Scheduling
An hourly cron job (`cli.py send-due`) finds onboarded users whose local send slot (weekday and time) has passed this week and who have no `email_sends` row for that week, then builds and sends their email. Being due from the slot onwards, rather than only in the hour after it, means a missed run catches up.

### 10.2 Pick selection (`app/domain/picks.py`)
1. **Fresh pick**: the top eligible paper by weighted score with `entrez_date` in the last 7 days and never sent to this user.
2. **Missed pick**: the top eligible paper from the active window (90 days), excluding the fresh pick and anything previously sent.
3. **Quality cutoff**: a pick is sent only if `weighted ≥ EMAIL_MIN_WEIGHTED` (default 3.2). Lowered from 3.5 once pertinence thresholds were tuned (§8.2): on the first real run, 13 of 102 eligible papers clear 3.2 (about the top 13%) against 2 at 3.5, so the fresh slot would otherwise be empty most weeks. Recheck after the surgeon's first weeks.
4. **Never zero**: if neither pick clears the cutoff, send the single best eligible unsent paper anyway, labelled fresh or missed by its date. If nothing at all is eligible, send a short "quiet week" email with a link to the feed and alert the admin (that means the profile or query needs attention).
5. The email therefore contains 1 or 2 papers.

### 10.3 Content per paper
Title, journal, year, the label "Fresh this week" or "You may have missed", 5 score pills with justifications (shown on tap in the app; shown inline in the email for the 2 intrinsic criteria the user weights most; pertinence has no written justification), the summary, the why-it-matters line, a link to the paper (DOI → PubMed fallback) and an "Open access" badge when applicable.

Action buttons: **Like**, **Mark read**, **Not for me**, **Open in app**.

### 10.4 One-tap links
- `GET /a/<action>#<token>` (token in the URL fragment, out of server logs, as for sign-in links; the action in the path only labels the button) where the token is signed with `itsdangerous` and carries `user_id`, `pmid`, `action`, `send_id`; it expires after 30 days.
- A GET only renders a page with one button ("Like this paper", "Mark as read", "Not for me"); nothing is recorded until the surgeon taps it, which POSTs the token. Email security scanners that open links, even ones that run scripts (e.g. Microsoft Safe Links), therefore record nothing. This costs one extra tap.
- The POST records the event (idempotent per `send_id` + `action`), then shows "Saved ✓ — open your feed".
- No login is required for these actions; opening the app itself still requires a session.

### 10.5 Delivery
Postmark transactional stream (or SMTP in the MVP), with HTML and a plain-text part. Store the provider's message id in `postmark_message_id`. No open or click tracking pixels (privacy, and the feedback links already give the signal).

---

## 11. Web app

Server-rendered; actions are plain forms that POST and redirect back to the page they came from (no front-end JavaScript library). Must work well on a phone.

| Route | Purpose |
|---|---|
| `/login` | Enter email → magic link. |
| `/auth#<token>` | The emailed link. The token is in the URL fragment, so it never reaches the server or its logs. GET only renders a page with a "Sign in" button, and the tap POSTs the token, so mail scanners that open links (even ones that run scripts) cannot use it up; the POST consumes it and sets a session cookie (30-day, httpOnly, secure), then goes to `/onboarding` or `/`. |
| `/onboarding` | Step 1: free-text interests. Step 2: confirm or edit topic chips. Step 3: optional seed PMIDs/DOIs. Step 4: weights and minimums (defaults shown). |
| `/` (feed) | Top 10 eligible papers by weighted score, read hidden. Each card shows its scores, summary, actions and a "graded from abstract/full text" label. |
| `/paper/{pmid}` | Full card: all 5 justifications, metadata, actions, dispute control. |
| `/library` | Liked papers, newest first. |
| `/history` | Read and dismissed papers, with undo. |
| `/profile` | Topics (add/edit/deactivate), seed papers, weights (5 sliders), minimums, hard filters. Changes re-rank the feed immediately. |
| `/settings` | Send day/time, timezone, and account deletion. Changing the email address is not offered: it would need verification. |
| `/privacy` | Public one-page privacy note (§16). |
| `/admin` | Admin only: the last 5 weekly runs (status, stored, graded, cut by the cap, error), this month's LLM spend vs cap, recent score disputes (model score beside the surgeon's), the calibration agreement table, and a "send test email" button that emails the admin their own weekly email preview (not recorded as a send). |

### 11.1 Onboarding topic extraction
The free text goes to Sonnet (normal API, not batch) with JSON-schema output (as for grading: forced tool use is not available on this model) → 4–12 topics, each with `label` and a 1–2 sentence `description` written in PubMed vocabulary. The free text itself is not stored. The user confirms or edits them; each confirmed topic's description is embedded. Seed PMIDs/DOIs/PubMed links are resolved via `esearch`/`efetch`; DOIs are resolved through esearch `[doi]`. Seeds without an abstract are not used (nothing to embed).

Without `ANTHROPIC_API_KEY`, or if the call fails, the surgeon types topics by hand. Embedding is best effort: if Voyage is unavailable, topics and seeds are saved unembedded and `cli.py embed` embeds them and refreshes profile vectors later.

Users are added by the operator (`cli.py users add EMAIL [--admin]`); `cli.py users link EMAIL` prints a sign-in link without sending email.


### 11.2 Visual design

The web app reads as a typeset weekly newspaper called **Tell Me Kort**. Structure follows Tablet magazine's section fronts (masthead, column grid, hairline rules, boxed sidebars, big numerals); restraint follows a calm editorial page (whitespace, one accent, a comfortable reading size). DESIGN.md records the shipped system.

- **Constraints**: server-rendered Jinja2, plain forms, no JavaScript added, no build step, no external requests. Fonts are self-hosted WOFF2 under `app/web/static/fonts/`, served by a `/static` mount.
- **Phone first**: one column by default; the multi-column grid starts at 900px. Tap targets of at least 44px, no horizontal scroll at 375px.
- **Identity**: every page opens with a small wordmark "Tell Me Kort" in ink (regular weight, T, M and K in Black, so "TMK" reads out by weight alone), then, as on Tablet's section fronts, a large section word in heavy grotesque capitals: THIS WEEK on the front page, LIBRARY, HISTORY, PROFILE, SETTINGS and so on inside. Under the front page's word, an edition rule between rules: `No. <ISO week> · Week of <Monday> · <n> papers in this edition`, from data passed to the template (never the clock inside a template). The inline SVG favicon is the compact mark "TMK". Every title, the email From name and the email subjects say Tell Me Kort.
- **Type** (OFL, self-hosted): Playfair Display for the nameplate, headlines and numerals; Source Serif 4 (optical sizes) for body text; Libre Franklin (a Franklin Gothic revival) in tracked capitals for labels, metadata, navigation and buttons.
- **Colour**: CSS custom properties on `:root`. Light "morning edition": newsprint `#EFE9DD`, ink `#151515`, hairlines in ink at low opacity, vermilion `#D9472B` for rules and large type and `#B23A1F` for small text. Dark "evening edition": warm charcoal paper, cream ink, the vermilion lightened to pass AA. One accent only; AA contrast in both. The reader picks the edition in the footer of every page (Auto · Morning · Evening): a plain form posts to `/theme`, which stores the choice in a `theme` cookie (no schema change, works signed out) and sets `data-theme` on `<html>`; Auto clears it and the page follows `prefers-color-scheme`.
- **Layout**: a thin ruled page frame; a section strip under the masthead (Front page · Library · History · Profile, plus Calibration and Admin where allowed, and Sign out) between hairlines, the current page in bold ink with a vermilion underline.
- **Front page**: a grid of ruled cells after Tablet: four columns from 900px, each cell closed by a rule on its right and bottom. Row 1: the lead (#1) across three columns, opening with a score plate (the weighted score and five criterion bars, standing where Tablet runs a photograph), then a centred headline, the summary as a short sans dek, the meta line, "Why it matters" as a pull line and the actions; beside it "Your beat" in a red-text box and "This edition" (papers found, screened and graded, from the latest pipeline run's stats) in an inverted ink box. Row 2: stories #2 and #3, two columns each, with a small score plate. Row 3: stories #4 to #7 with score, headline, dek and meta. Row 4: briefs #8 to #10 (score, headline, meta) and a big-numeral cell: the paper count, "picked for you from <n> papers graded this week". Scores are the weighted score already on the ranked item. On a phone the cells stack in one column: lead, second stories, the two boxes, short stories, briefs.
- **Paper page**: set like a feature: study design · n, headline, meta line, big numeral, standfirst, a print-style "Read the paper" button, then "Scores and reasons" as five ruled entries with the dispute control.
- **Library and History**: an index listing with hairline separators. Auth, one-tap actions, onboarding (a numbered printed form), calibration, admin, empty and error states share the frame, compact masthead and type.
- **Components**: square corners everywhere; buttons have a hairline border and a capitals label, pressed or primary is filled ink; inputs are square with a vermilion focus ring; "Open access" is a small capitals stamp with a vermilion border.
- **Out of scope**: the weekly email's styling (a later change); only its From name and subjects are renamed.

---

## 12. Calibration (before launch)

1. `cli.py calibrate sample --n 20` picks 20 recent candidates stratified by study design.
2. The surgeon grades them blind on `/admin/calibrate` against the rubric text (model scores hidden). Access needs sign-in: admins, and users marked as calibrators (`cli.py users add EMAIL --calibrator`), which is how the surgeon gets in. `cli.py calibrate grade` grades the set and snapshots the model's scores into `calibration_items`.
3. `cli.py calibrate report` shows, per criterion: exact agreement, agreement within ±1, quadratic-weighted kappa, and the papers with the biggest disagreements alongside the model's justifications.
4. Revise the rubric wording, bump `RUBRIC_VERSION`, rerun on the same 20 (`calibrate grade` creates rows for the new version and carries the surgeon's scores forward).
5. **Launch bar**: within-±1 agreement ≥ 80% on every criterion, and ≥ 90% on proof strength.

Later, disputes (§9) feed periodic recalibration.

---

## 13. Regrading

`cli.py regrade [--window 90]` grades every paper in the window that has only older-version grades, newest first, under the current `RUBRIC_VERSION`, with the same spend guard and alerts as the weekly run. Old grade rows stay for comparison. Ranking always uses the current version; papers without a current-version grade are ineligible until regraded.

---

## 14. Cost envelope

| Item | Basis | ~USD / month |
|---|---|---|
| Grading | ~430 papers × ~6.4k input + ~600 output tokens at $2 / $10 per M, Batch −50% | 4–8 |
| Embeddings | ~1M tokens/month, within the Voyage free tier | 0 |
| Email | Gmail SMTP for the MVP; later Postmark free tier (100/month), Basic $15 above that | 0 |
| Hosting | Render Starter web $7 + Basic Postgres ~$7 + cron jobs (cents) | ~14 |
| **Total (pilot)** | | **~20–25** |

Each regrade of the 90-day window costs ~$10–25 one-off. Re-check list prices before quoting.

---

## 15. Config (env vars)

`DATABASE_URL`, `SECRET_KEY`, `BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-sonnet-5-5`, `GRADING_EFFORT=low`, `VOYAGE_API_KEY`, `EMBEDDING_MODEL=voyage-4`, `NCBI_API_KEY`, `NCBI_EMAIL`, `NCBI_TOOL`, `POSTMARK_SERVER_TOKEN`, `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `ADMIN_EMAIL`, `GRADE_LIMIT_PER_WEEK=100`, `FULLTEXT_MAX_TOKENS=12000`, `LLM_MONTHLY_CAP_USD=30`, `PERTINENCE_GATE=0.30`, `PERTINENCE_THRESHOLDS=[0.50, 0.58, 0.65, 0.72]` (§8.2, ascending), `EMAIL_MIN_WEIGHTED=3.2`, `ACTIVE_WINDOW_DAYS=90`, `PROFILE_COEF_TOPICS=1.0`, `PROFILE_COEF_SEEDS=1.0`, `PROFILE_COEF_LIKED=0.5`, `PROFILE_COEF_NOT_FOR_ME=0.3` (§8.1).

---

## 16. Privacy and security

- Personal data stored: the surgeon's email, name, interests and feedback only. No patient data, ever.
- Hosted in the EU (Render Frankfurt). The email provider (Postmark, or Google for Gmail SMTP), Anthropic and Voyage receive only paper text, profile text and the email address (email provider only); `/privacy` names whichever provider is configured. List them as sub-processors in a one-page privacy note.
- Account deletion endpoint: `/settings` → delete (type "delete" to confirm) removes all of the user's rows (by cascade, plus login attempts by email) and signs them out. Papers and grades are shared and stay.
- `/privacy` lists what is stored, the sub-processors and what each receives, retention, deletion and the contact (`ADMIN_EMAIL`).
- Magic links and action tokens are single-purpose, signed and expiring; only their hashes are stored.
- In production (on Render, which sets `RENDER=true`, or whenever `BASE_URL` is `https://`), the web app and the jobs refuse to start unless `BASE_URL` is an `https://` address, `SECRET_KEY` is set and not a placeholder, `EMAIL_FROM` and a way to send are set (`POSTMARK_SERVER_TOKEN`, or `SMTP_HOST` with its username and password), and `ADMIN_EMAIL` is set for alerts. Better not to start than to run with forgeable sessions, links to the wrong host, silently unsent sign-in emails or alerts that go nowhere.
- Rate-limit `/login`: 5 per hour per email and 50 per hour overall, counting only addresses that have an account, so requests for unknown addresses cannot use up everyone's sign-ins. Over the limit, the page is the same "check your email" page and no email is sent (no hint which addresses exist). No per-IP limit: behind Render's proxy the client address comes from a header the client can forge, and IPs are personal data we would rather not keep.

---

## 17. Testing

- **Unit tests** (`app/domain`): profile vector maths, pertinence mapping, eligibility, weighted score, pick selection (including the never-zero and quiet-week cases), weight suggestions.
- **Parser tests**: PubMed/PMC XML fixtures, including missing abstracts, missing DOIs and non-OA papers.
- **Grader tests**: recorded batch responses; validation and retry paths; spend-guard truncation.
- **Web tests**: FastAPI TestClient for magic-link login, one-tap GET→POST flow (prefetch-safe), idempotency, onboarding.
- **E2E smoke**: `cli.py send-test EMAIL` renders the email that user would get now to `var/outbox/` (text and HTML) without sending or recording it.

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

- Server-rendered templates with plain forms rather than a JS front end (HTMX was dropped in milestone 7: a full-page reload after each action is fast enough).
- Voyage `voyage-4` for embeddings and `pgvector` for storage.
- Render Frankfurt rather than Railway.
- Default send time Monday 06:30 Copenhagen; the surgeon can change it in settings.
- Numeric thresholds (pertinence gate, email cutoff, embedding coefficients, calibration launch bar) are starting values, to be tuned on real data.
- Liking and reading are independent states.
- Pertinence thresholds are one fixed scale for all users (each user's cosines are their own). A per-user relative scale was considered and deferred: revisit if several users with profiles of different breadth get consistently flat or thin feeds.
