---
version: 1
slug: "app-web-templates-feed-feed-html"
primary_target: "app/web/templates/feed/feed.html"
related_targets: ["app/web/templates/feed/paper.html"]
---

# Front page (feed) and the whole web app

Scope: every template under app/web/templates (front page, paper page, library, history, auth, one-tap actions, onboarding, calibration, admin). Mode: Read (front page, paper page) and Operate (forms, admin).
Audience: one pilot maxillofacial surgeon, mostly on a phone before clinic. Job: see this week's best graded papers, judge them by visible scores and reasons, act (like, read, not for me, dispute).
Constraints: Jinja2, plain forms, no JavaScript added, self-hosted fonts, no external requests, phone first (grid from 900px), 44px targets, WCAG AA in both themes.

## Direction contract

THESIS: The app is a weekly newspaper, Tell Me Kort; the ranked feed is this week's front page. It refuses the card-list feed with score pills and rounded buttons.

OWN-WORLD: Newsprint #EFE9DD / ink #151515 (evening edition: charcoal #1D1B18 / cream #EDE5D3), one vermilion (#D9472B; #B23A1F for small text). Playfair Display (900 nameplate, 400 headlines and numerals), Source Serif 4 body, Inter tracked capitals for labels. Hairline rules, a ruled page frame, square-cornered hairline buttons (primary filled ink), vermilion-framed sidebar boxes, big light numerals.

STORY: The reader sees the edition at a glance (No. 44, week of, n papers), reads the lead story with its why-it-matters line and score, scans second stories and briefs, and opens the paper page for the five reasons; they trust the pick because every score shows its reason.

FIRST VIEWPORT: Full-width nameplate "Tell Me Kort" with T, M, K in vermilion; edition rule between hairlines; section strip; lead headline centred (desktop) or left (phone) with standfirst, then pull line beside a boxed numeral and scorecard; sidebar boxes "Your beat" and "This edition" in a right rail from 900px.

FORM: Brief-pinned (user named Tablet magazine section fronts plus a calm editorial landing page, with fonts and palette); the roll was not run. seed: none (brief-pinned; roll not run)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
