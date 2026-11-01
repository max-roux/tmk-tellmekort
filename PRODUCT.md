# Product

<!-- impeccable:product-schema 1 -->

Inferred from SPEC.md and the redesign brief, confirmed by the user on 2026-11-01.

## Platform

web

## Users
One pilot maxillofacial surgeon (more may follow; the data model is per user). They read the weekly edition mostly on a phone, often early in the morning before clinic, and occasionally on a desktop. An operator (the admin) runs the weekly pipeline, checks spend and disputes, and leads rubric calibration with the surgeon.

## Product Purpose
Tell Me Kort (team name TMK) sends the surgeon one or two research papers by email each week and keeps a ranked feed of the ten best graded papers of the last 90 days for their profile. Success is the surgeon trusting the picks enough to read them, and their likes, reads and dismissals measurably improving later picks.

## Positioning
Every recommendation is explainable: an LLM grades each paper on four intrinsic criteria, embeddings measure a fifth (pertinence to the surgeon's profile), each score has a one-line reason, and the surgeon's own weights rank the result. The surgeon can dispute any score.

## Operating Context
- A weekly rhythm: the pipeline runs on Sunday, the email arrives on the surgeon's chosen day and time (default Monday 06:30 Copenhagen).
- One-tap email actions (like, mark read, not for me) open a confirmation page in the app.
- Sign-in is by magic link; there are no passwords.
- The surgeon is a domain expert and reads papers critically; the app summarises and grades but links out to the paper itself.

## Capabilities and Constraints
- Server-rendered Jinja2 with plain HTML forms that POST and redirect; no front-end framework and no build step.
- Must work well on a phone.
- No patient data, ever. Data hosted in the EU.
- The weighted score and ranking come from `app/domain`; templates display them and never recompute them.

## Brand Commitments
- Name: Tell Me Kort; team name and compact mark: TMK.
- The app reads as a carefully typeset weekly newspaper. References given by the user: Tablet magazine's section fronts (structure) and a calm editorial landing page (restraint).

## Evidence on Hand
Real PubMed papers with real grades in development and production. No testimonials, readership numbers or claims exist; none may be invented.

## Product Principles
1. Show the reasons with the score; a number on its own is not a recommendation.
2. The surgeon's time is the scarce resource: one edition a week, ten papers at most, the best first.
3. Calm and precise, not busy: nothing competes with the papers.
4. The surgeon stays in control: weights and minimums are theirs, suggestions are never applied silently.

## Accessibility & Inclusion
WCAG AA contrast in light and dark themes, tap targets of at least 44px, no horizontal scroll at 375px.
