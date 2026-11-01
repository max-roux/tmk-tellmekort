---
name: Tell Me Kort
description: Graded papers in maxillofacial surgery, typeset as a weekly newspaper.
colors:
  paper: "#efe9dd"
  paper-deep: "#e6dfd1"
  ink: "#151515"
  ink-soft: "#55504a"
  rule: "rgb(21 21 21 / 0.22)"
  rule-strong: "rgb(21 21 21 / 0.85)"
  accent: "#d9472b"
  accent-text: "#b23a1f"
  on-ink: "#efe9dd"
  evening-paper: "#1d1b18"
  evening-paper-deep: "#26231f"
  evening-ink: "#ede5d3"
  evening-ink-soft: "#b3aa99"
  evening-rule: "rgb(237 229 211 / 0.2)"
  evening-rule-strong: "rgb(237 229 211 / 0.75)"
  evening-accent: "#e8603f"
  evening-accent-text: "#ef7556"
  evening-on-ink: "#1d1b18"
typography:
  nameplate:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "17.4cqi"
    fontWeight: 900
    lineHeight: 0.92
    letterSpacing: "-0.02em"
  section-title:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(2.5rem, 11vw, 6rem)"
    fontWeight: 900
    lineHeight: 0.95
    letterSpacing: "-0.01em"
  headline-lead:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.9rem, 6.5vw, 3rem)"
    fontWeight: 400
    lineHeight: 1.08
  headline-second:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.4rem, 4.6vw, 1.625rem)"
    fontWeight: 400
    lineHeight: 1.15
  headline-index:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.375rem"
    fontWeight: 400
    lineHeight: 1.2
  headline-brief:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.22
  pull:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.3rem, 3.6vw, 1.6rem)"
    fontWeight: 400
    lineHeight: 1.3
  numeral:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "4.25rem"
    fontWeight: 400
    lineHeight: 0.9
    letterSpacing: "-0.02em"
    fontFeature: "lnum, tnum"
  standfirst:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "lnum"
  label:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.6
    letterSpacing: "0.12em"
  button:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.14em"
rounded:
  none: "0px"
spacing:
  hair: "1px"
  gutter: "clamp(1rem, 3vw, 2rem)"
  measure: "38rem"
  tap: "2.75rem"
  row: "1rem"
  block: "1.5rem"
  story: "1.75rem"
  column-gap: "2rem"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "0 1.1rem"
    height: "{spacing.tap}"
  button-hover:
    backgroundColor: "{colors.paper-deep}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "0 1.1rem"
    height: "{spacing.tap}"
  button-small:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 0.8rem"
    height: "{spacing.tap}"
  button-small-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0.6rem 0.1rem"
    height: "{spacing.tap}"
  sidebar-box:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1rem 1rem"
  scorebox:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    width: "17rem"
  stamp:
    backgroundColor: "transparent"
    textColor: "{colors.accent-text}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0.05rem 0.4rem"
  section-link:
    textColor: "{colors.ink-soft}"
    typography: "{typography.label}"
    padding: "0 0.5rem"
    height: "{spacing.tap}"
  section-link-current:
    textColor: "{colors.ink}"
---

# Design System: Tell Me Kort

## Overview

**Creative North Star: "The Typeset Weekly"**

Tell Me Kort is a weekly newspaper with one reader. The ranked feed is this week's front page: a full-width nameplate, an edition rule (number, week, paper count), a section strip, a lead story, two second stories, a ruled field of briefs, and a right rail of framed sidebar boxes. Every surface sits inside one thin ruled page frame on warm newsprint, and structure is drawn with rules, not with fills, cards or shadows. The structure follows Tablet magazine's section fronts; the restraint follows a calm editorial page: generous whitespace, one accent, a comfortable reading size.

The page is quiet so the papers can speak. Scores are set as big Playfair numerals beside their reasons, because a number without its reason is not a recommendation. Labels, metadata, navigation and buttons share one voice, Inter in small tracked capitals, which keeps the apparatus of the page distinct from the reading text. There are two editions of the same paper: the light morning edition and the dark evening edition, chosen by the reader's system setting.

The system refuses the card-list feed: no rounded cards, no score pills, no rounded buttons, no drop shadows. It is server-rendered with plain forms; the look is made entirely from type, rules and two surface tones.

**Key Characteristics:**
- One ruled page frame around everything; hairline rules divide stories, rows and columns.
- Three self-hosted OFL families with fixed roles: Playfair Display (nameplate, headlines, numerals), Source Serif 4 (reading text), Inter (tracked-capital apparatus).
- Square corners everywhere, including checkboxes and range thumbs.
- One vermilion accent, for rules, frames, the nameplate initials and large type; a darker vermilion for small text.
- Phone first: one column, the multi-column grid from 900px, every target at least 44px.

## Colors

Newsprint and ink with one vermilion, printed twice: a morning edition on warm paper and an evening edition on warm charcoal.

### Primary
- **Vermilion** (`accent`): the only accent. The T, M and K of the nameplate, the bar under the compact TMK mark, the rule above a pull line, sidebar box frames, the "Open access" stamp border, the current section's underline, the focus ring, the warning progress bar and the selected calibration level outline. On paper it measures 3.5:1, so it carries rules, frames and large type only, never small text.
- **Vermilion for Text** (`accent-text`): the same hue darkened to 4.9:1 on paper for small text: labels such as "Why it matters", sidebar box headings, the "Disagree?" control, form row numbers, sidebar figures, error text, link hover.

### Neutral
- **Newsprint** (`paper`): the page. Also the text colour on filled ink (`on-ink`).
- **Deep Newsprint** (`paper-deep`): the one tonal step, used for hover on buttons and calibration levels and for a checked calibration level. Never a resting card fill.
- **Ink** (`ink`): text, the primary button fill, pressed toggle fill, checkbox and range thumb fill, progress fill. 15.1:1 on paper.
- **Soft Ink** (`ink-soft`): standfirsts, metadata, section links at rest, the section dek, table headers, placeholders. 6.6:1 on paper.
- **Hairline** (`rule`): ink at 22% for rules between stories, rows, briefs and scorecard lines.
- **Strong Rule** (`rule-strong`): ink at 85% for the page frame, the edition and section rules, button and input borders, the scorebox, and the top rule of index listings.

### Evening edition
Under `prefers-color-scheme: dark` the same token names take the `evening-*` values: warm charcoal paper, a slightly lighter charcoal for `paper-deep`, cream ink, soft ink at 7.5:1, rules in cream at 20% and 75%. The vermilion is lightened to pass AA on charcoal: accent 5.0:1, accent-text 6.0:1. Text on filled ink becomes charcoal.

### Named Rules
**The One Vermilion Rule.** Vermilion is the only hue. It draws rules, frames and the nameplate initials and marks state; it never fills a surface or a button.

**The Small Text Rule.** Any vermilion text under display size uses `accent-text`, never `accent`. `accent` on morning paper is 3.5:1 and is reserved for large type and non-text marks.

**The Two Editions Rule.** Every colour is a custom property on `:root` with a morning and an evening value; components never hard-code a colour, so both editions come from the same rules.

## Typography

**Display Font:** Playfair Display (with Iowan Old Style, Georgia, serif)
**Body Font:** Source Serif 4 (with Iowan Old Style, Georgia, serif)
**Label Font:** Inter (with system-ui, -apple-system, Segoe UI, sans-serif)

**Character:** A high-contrast transitional display face for the voice of the paper, a sturdy text serif with optical sizes for reading, and a neutral grotesque in tracked capitals for the apparatus. Three families, each with one job.

All three are SIL Open Font License, self-hosted as variable WOFF2 in `app/web/static/fonts/` with their OFL texts beside them, `font-display: swap`, and the Playfair and Source Serif roman files preloaded. No font is fetched from a third party.

**Why Playfair Display, not Abril Fatface.** Abril Fatface ships a single weight. The system needs a 900 nameplate and section titles, 400 headlines and 400 numerals from one family so the masthead, the stories and the scores read as one typeface at different pitches. Playfair Display is a variable font across 400 to 900 with an italic (used for pull lines). Its lightest weight, 400, is the "light" numeral: large, regular-weight and high-contrast, it reads light against the 900 nameplate.

**Why Source Serif 4.** A text serif drawn for screens, with an optical size axis: `font-optical-sizing: auto` gives the 17px body and the 19px standfirst their own cuts, so small text stays sturdy and larger text gains finesse. Lining figures are set on the body so PMIDs, years and sample sizes align with the Playfair numerals.

**Why Inter in tracked capitals.** Labels, metadata, navigation and buttons are set in Inter at 11 to 12px, uppercase, tracked 0.10 to 0.14em. This is a deliberate, brief-pinned choice: a sans in small capitals reads as the newspaper's furniture (datelines, section heads, the edition line) and keeps every interactive control visually distinct from the serif reading text. The design detector's overused-font finding for Inter is suppressed for this project in `.impeccable/config.json`.

### Hierarchy
- **Nameplate** (Playfair 900, 17.4% of the masthead's inline size via container units, 0.92, -0.02em): the front page's "Tell Me Kort", set to the full width of the page frame. Front page only.
- **Section title** (Playfair 900, clamp 2.5rem to 6rem, 0.95): the title of an inner section front (Library, History, Calibration, Admin, Not found), centred, with a soft-ink dek under it at most 34rem wide.
- **Compact mark** (Playfair 900, 1.75rem): "TMK" with a 2px vermilion bar under it, the masthead of every inner page.
- **Lead headline** (Playfair 400, clamp 1.9rem to 3rem, 1.08, max 24ch): the lead story and the paper page's feature title (max 26ch).
- **Second headline** (Playfair 400, clamp 1.4rem to 1.625rem, 1.15).
- **Index headline** (Playfair 400, 1.375rem, 1.2): library, history and listing rows.
- **Brief headline** (Playfair 400, 1.1875rem, 1.22).
- **Pull line** (Playfair 400 italic, clamp 1.3rem to 1.6rem, 1.3): "Why it matters", under a 2px vermilion rule.
- **Numeral** (Playfair 400, lining tabular figures, 0.9, -0.02em): scores and counts. Sizes step by importance: 5rem paper page, 4.25rem lead, 2.6rem reasons, 2.25rem second stories, 2.1rem sidebar figures, 2rem briefs on desktop, 1.75rem briefs on phone and index rows, 1.5rem form steps.
- **Standfirst** (Source Serif 4 400, 1.1875rem to 1.25rem, 1.5, soft ink, max 40rem): the grade's summary under a headline.
- **Body** (Source Serif 4 400, 1.0625rem, 1.55, lining figures): reading text; forms and notices sit in a 38rem column.
- **Label** (Inter 500, 0.6875rem, 0.12em, uppercase, 1.6): metadata lines, scorecard criteria, form field labels (600, 0.14em), the edition rule (0.14em), section links (0.10em).
- **Button** (Inter 600, 0.75rem, 0.14em, uppercase); small buttons at 0.6875rem.

### Named Rules
**The One Family Per Job Rule.** Playfair speaks (nameplate, headlines, numerals, pull lines), Source Serif reads (body, standfirsts, summaries), Inter labels (metadata, navigation, buttons, field labels). Never swap a role.

**The Numeral Rule.** Every score is a Playfair numeral with lining tabular figures, set beside the reason or label that explains it. Never a pill, a badge or a coloured chip.

**The Data Label Rule.** A tracked-capital label above or beside content names a field of the data ("Why it matters", "for you", "Scores and reasons") or carries the data itself. The paper page's line above the feature title, the grade's study design and sample size ("<study design> · n = <sample size>"), is intentional and pinned by the brief and SPEC.md §11.2. Never invent a kicker or eyebrow line that carries no data.

## Layout

One ruled page frame (1px strong rule), at most 76rem wide, padded by the fluid gutter (1rem to 2rem). On a phone it sits 0.5rem from the viewport edges; from 900px it gains a 1.5rem margin on each side.

Phone first. Every surface is one column by default, in reading order. The multi-column grid starts at 900px:
- **Front page:** main column plus a 16.5rem right rail, separated by a hairline and 2rem of space either side. The lead story's headline centres; its standfirst, meta line and everything below share one left edge, 36rem wide and centred. Its body becomes pull line and actions on the left, a 17rem scorebox on the right.
- **Second stories:** two columns divided by a vertical hairline; each centres its headline and left-aligns the rest in a 30rem block.
- **Briefs:** a ruled list on a phone (headline and meta left, numeral right); three ruled cells from 900px and four from 1200px, numeral on top, with hairlines between cells and none at the outer edges.
- **Paper page:** a 52rem feature column; from 900px a 12rem score column beside the text.
- **Onboarding steps:** two columns on a phone, four from 640px.

Narrow reading columns: 38rem for forms, notices and the welcome page; 44rem for onboarding and calibration forms; 52rem for index listings and the paper page; 60rem for the admin desk.

Rhythm is set in rem and follows a short ladder: 0.5 to 0.75rem inside rows, 1rem to 1.25rem for row padding, 1.5rem between blocks, 1.75rem between stories and below the section strip, 2rem to 2.5rem between major sections and columns.

### Named Rules
**The 900 Rule.** One column below 900px, the column grid from 900px. Same content order at every width; nothing is hidden on a phone.

**The 44 Rule.** Every link, button, toggle, summary, select and checkbox row is at least 44px tall (`tap`), including the section strip, the skip link and the compact mark. No horizontal scroll at 375px.

## Elevation & Depth

Flat. The system has no elevation shadows. Depth comes from rules: a 1px strong rule for frames and control borders, a 1px hairline for divisions, a 3px double rule above the front-page edition line, a 2px vermilion rule above a pull line. The one tonal step, deep newsprint, appears only on hover and selection. `box-shadow` appears only as a drawn mark: an inset 3px paper ring that turns a filled checkbox into a printed tick box, and an inset 2px vermilion underline on the current onboarding step.

### Named Rules
**The Ruled, Not Raised Rule.** Separate things with a rule, never with a shadow, a fill or a floating card.

## Shapes

Square corners everywhere (`rounded.none`): buttons, inputs, selects, textareas, checkboxes, range thumbs, sidebar boxes, the scorebox, the stamp, progress bars. Frames are 1px. Text inputs are open at the top and sides, a single strong underline like a printed form blank; textareas and selects are fully framed. The range control is a 1px track with a square ink thumb (1rem by 1.25rem) that turns vermilion while in use. The favicon is the TMK mark drawn from Playfair's outlines on a newsprint square over a vermilion bar.

## Components

### Buttons
Print-style, square and hairline-framed: they look like boxed type, not pills.
- **Shape:** square (0px), 1px strong-rule border, at least 44px tall.
- **Default:** transparent on paper, ink label in Inter 600 capitals, 0.75rem, 0.14em tracking, 0 1.1rem padding.
- **Primary:** filled ink with a paper label ("Read the paper", confirm pages, form submits). Hover keeps the fill and underlines the label.
- **Small:** 0.6875rem label, 0 0.8rem padding; used for the like, mark read and not-for-me row. A pressed toggle (`aria-pressed="true"`, e.g. "Liked") fills with ink like a primary.
- **Hover / Focus:** hover fills with deep newsprint; focus is a 2px vermilion outline offset 2px. Background and colour transition over 120ms ease-out only when the reader allows motion. Disabled is 55% opacity.
- **Link-like:** a form button set as an underlined inline link, for actions that sit in running text.

### Stamp
"Open access" in the meta line: Inter 600 capitals in vermilion text inside a 1px vermilion frame, square, never wrapped onto two lines.

### Sidebar boxes
"Your beat" and "This edition" in the right rail: a 1px vermilion frame, centred content, a tracked-capital heading in vermilion text over a 1px vermilion rule, list items divided by hairlines, and for "This edition" three vermilion numerals (found, screened, graded) with soft-ink labels.

### Scorebox and scorecard
The lead story's score: a 1px strong-rule frame holding the big overall numeral with "for you", then the five criteria as label and numeral pairs on hairline rows. On the paper page the overall numeral stands alone in its frame and the five criteria become numbered reasons: a 2.6rem numeral beside the criterion label, its one-line reason, and a "Disagree?" disclosure that opens a small dispute form.

### Inputs / Fields
- **Style:** transparent, square; text inputs have a single 1px strong underline, textareas and selects a full 1px frame. Body serif at 1.0625rem; labels above in Inter capitals.
- **Focus:** 2px vermilion outline, offset 2px.
- **Checkbox:** a square 1.25rem box with a 1px strong rule; checked fills ink inside a 3px paper inset.
- **Radio:** native, tinted vermilion.
- **Error:** vermilion-text, semibold; a notice or error block sits between two vermilion rules.

### Navigation
- **Masthead:** the front page carries the full nameplate with T, M and K in vermilion, then the edition rule (No., week of, paper count) in Inter capitals between a 3px double rule and a hairline, separated by vermilion dots. Inner pages carry the compact TMK mark.
- **Section strip:** Front page, Library, History, Profile, Calibration and Admin where allowed, and Sign out, centred between rules in Inter capitals at 0.10em, soft ink at rest, ink on hover. The current section is bold ink with a 2px vermilion underline offset 0.55em. It wraps on a phone; every item is 44px tall.
- **Onboarding steps:** a ruled four-cell strip (two cells on a phone) of numeral and label; the current step is ink, bold, with a vermilion numeral and a 2px vermilion underline.

### Front-page stories
Lead, second and brief share one anatomy at three pitches: headline (linked, no underline until hover), standfirst (lead and second only), meta line in soft-ink capitals with dot separators, and a numeral with "for you". The lead adds the pull line and the scorebox; seconds clamp their standfirst to four lines.

### Printed forms
Onboarding reads as a numbered printed form: each row is a 2rem vermilion Playfair row number beside the field, rows divided by hairlines, the first row under a strong rule. Weight sliders pair the square range control with a Playfair numeral readout.

## Do's and Don'ts

### Do:
- **Do** draw every division with a rule: 1px `rule` between items, 1px `rule-strong` for frames and controls, 2px `accent` above a pull line.
- **Do** keep every corner square (0px), including form controls.
- **Do** set every score as a Playfair 400 numeral with lining tabular figures, next to the label or reason that explains it.
- **Do** use `accent-text` for any small vermilion text and keep `accent` for rules, frames, the nameplate initials and large type.
- **Do** define colours only as `:root` custom properties with morning and evening values, and keep AA contrast in both editions.
- **Do** keep labels, metadata, navigation and buttons in Inter capitals at 0.6875rem to 0.75rem, tracked 0.10em to 0.14em.
- **Do** make every interactive element at least 44px tall and keep one column below 900px.
- **Do** self-host every font and asset; the page makes no external requests.

### Don't:
- **Don't** add JavaScript; plain forms that POST and redirect carry every action.
- **Don't** round a corner, fill a resting card, or add an elevation shadow.
- **Don't** put a score in a pill, badge or coloured chip.
- **Don't** introduce a second accent hue or fill a button or surface with vermilion.
- **Don't** set small text in `accent` (#d9472b is 3.5:1 on paper).
- **Don't** add a kicker or eyebrow line that carries no data; a label above a headline must state a field of the paper, as the study design and sample size line does on the paper page.
- **Don't** swap the type roles: no Inter headlines, no Playfair labels, no serif buttons.
