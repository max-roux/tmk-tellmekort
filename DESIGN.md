---
name: Tell Me Kort
description: Graded papers in maxillofacial surgery, typeset as a weekly newspaper.
colors:
  paper: "#efe9dd"
  paper-deep: "#e6dfd1"
  ink: "#151515"
  ink-soft: "#55504a"
  rule: "rgb(21 21 21 / 0.22)"
  rule-mid: "rgb(21 21 21 / 0.45)"
  rule-strong: "rgb(21 21 21 / 0.85)"
  accent: "#d9472b"
  accent-text: "#b23a1f"
  on-ink: "#efe9dd"
  evening-paper: "#1d1b18"
  evening-paper-deep: "#26231f"
  evening-ink: "#ede5d3"
  evening-ink-soft: "#b3aa99"
  evening-rule: "rgb(237 229 211 / 0.2)"
  evening-rule-mid: "rgb(237 229 211 / 0.4)"
  evening-rule-strong: "rgb(237 229 211 / 0.75)"
  evening-accent: "#e8603f"
  evening-accent-text: "#ef7556"
  evening-on-ink: "#1d1b18"
typography:
  wordmark:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.5rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.01em"
  section-word:
    fontFamily: "Libre Franklin, Franklin Gothic Medium, system-ui, sans-serif"
    fontSize: "min(7.5rem, 11.5cqi)"
    fontWeight: 900
    lineHeight: 0.9
    letterSpacing: "-0.01em"
  headline-lead:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.9rem, 4.2vw, 3rem)"
    fontWeight: 400
    lineHeight: 1.08
  headline-second:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.4rem, 3vw, 1.75rem)"
    fontWeight: 400
    lineHeight: 1.12
  headline-index:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.375rem"
    fontWeight: 400
    lineHeight: 1.2
  headline-story:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.2
  headline-brief:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.25
  pull:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "clamp(1.3rem, 3.6vw, 1.6rem)"
    fontWeight: 400
    lineHeight: 1.3
  numeral:
    fontFamily: "Playfair Display, Iowan Old Style, Georgia, serif"
    fontSize: "4.5rem"
    fontWeight: 400
    lineHeight: 0.9
    letterSpacing: "-0.02em"
    fontFeature: "lnum, tnum"
  standfirst:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.25rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "lnum"
  dek:
    fontFamily: "Libre Franklin, Franklin Gothic Medium, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Libre Franklin, Franklin Gothic Medium, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.6
    letterSpacing: "0.12em"
  button:
    fontFamily: "Libre Franklin, Franklin Gothic Medium, system-ui, sans-serif"
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
  cell-gap: "1rem"
  block: "1.5rem"
  story: "1.75rem"
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
  wordmark:
    textColor: "{colors.ink}"
    typography: "{typography.wordmark}"
    padding: "0.65rem 0.5rem"
  section-word:
    textColor: "{colors.ink}"
    typography: "{typography.section-word}"
  cell:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.25rem 1.1rem 1.4rem 0"
  score-plate:
    backgroundColor: "{colors.paper-deep}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "1.1rem 1.25rem 1.25rem"
  score-plate-small:
    backgroundColor: "{colors.paper-deep}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.8rem 1rem"
  box-red:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1rem 1rem"
  box-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1rem 1rem"
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
  edition-switch:
    textColor: "{colors.ink-soft}"
    typography: "{typography.label}"
    padding: "0 0.6rem"
    height: "{spacing.tap}"
  edition-switch-current:
    textColor: "{colors.ink}"
---

# Design System: Tell Me Kort

## Overview

**Creative North Star: "The Typeset Weekly"**

Tell Me Kort is a weekly newspaper with one reader, set after Tablet magazine's section fronts. Every page opens the same way: a small "Tell Me Kort" wordmark on a ruled line, then, where the page has one, a huge section word in heavy grotesque capitals (THIS WEEK, LIBRARY, HISTORY, PROFILE, SETTINGS, CALIBRATION, ADMIN, PRIVACY, WELCOME, NOT FOUND). The front page follows its word with the edition rule (number, week, paper count) and then a dense grid of ruled cells: the lead with its score plate, a red-text box and an inverted ink box beside it, two second stories, four short stories, three briefs and a big-numeral cell. Every surface sits inside one thin ruled page frame on warm newsprint; structure is drawn with rules, and the only resting fills are the score plates and the ink box.

The page is quiet so the papers can speak. Scores are set as big Playfair numerals beside their reasons, because a number without its reason is not a recommendation; on the front page the five criteria stand beside the score as ink bars, where Tablet would run a photograph. Labels, metadata, navigation and buttons share one voice, Libre Franklin in small tracked capitals; the same family, at Black weight, announces the section word. There are two editions of the same paper: the light morning edition and the dark evening edition, chosen by the reader in every page's footer (Auto follows the device).

The system refuses the card-list feed: no rounded cards, no score pills, no rounded buttons, no drop shadows, and no vertical side rail. It is server-rendered with plain forms; the look is made from type, rules, two surface tones and one inverted box.

**Key Characteristics:**
- Small wordmark, big section word: the name is quiet and identical on every page; the section word is the loudest type.
- One ruled page frame around everything; front-page cells are closed by rules on their right and bottom, never by a side rail.
- Three self-hosted OFL families with fixed roles: Playfair Display (wordmark, headlines, numerals), Source Serif 4 (reading text), Libre Franklin (tracked-capital apparatus, the section word and front-page deks).
- Square corners everywhere, including checkboxes, range thumbs, plates and boxes.
- One vermilion accent, for rules, frames, large type and the red-text box; a darker vermilion for small text.
- Phone first: one column, the four-column grid from 900px, every target at least 44px.

## Colors

Newsprint and ink with one vermilion, printed twice: a morning edition on warm paper and an evening edition on warm charcoal.

### Primary
- **Vermilion** (`accent`): the only accent. The rule above a pull line, box frames, the dividers inside the red-text box, the "Open access" stamp border, the dots of the edition rule, the underline under the current section and the current edition, the focus ring, the warning progress bar and the selected calibration level outline. On paper it measures 3.5:1, so it carries rules, frames and large type only, never small text.
- **Vermilion for Text** (`accent-text`): the same hue darkened to 4.9:1 on paper for small text: every word of the red-text box ("Your beat"), labels such as "Why it matters", box headings, the "Disagree?" control, form row numbers, error text, link hover.

### Neutral
- **Newsprint** (`paper`): the page, and the text on the inverted ink box.
- **Deep Newsprint** (`paper-deep`): the one tonal step. At rest it fills only the score plates; otherwise it marks hover on buttons and calibration levels and a checked calibration level.
- **Ink** (`ink`): text, the inverted box, the primary button fill, pressed toggle fill, score bars, checkbox and range thumb fill, progress fill. 15.1:1 on paper.
- **Soft Ink** (`ink-soft`): standfirsts, deks, metadata, section and edition-switch links at rest, the section dek, the big-numeral cell's caption, table headers, placeholders. 6.6:1 on paper.
- **Hairline** (`rule`): ink at 22% for rules between rows, list items, reasons and index entries.
- **Cell Rule** (`rule-mid`): ink at 45% for the right and bottom rules of front-page cells and the baseline under each score bar.
- **Strong Rule** (`rule-strong`): ink at 85% for the page frame, the wordmark line, the edition and section rules, button and input borders, the paper page's score frame, and the top rule of index listings.

### Evening edition
The same token names take the `evening-*` values when the reader picks Evening (`data-theme="dark"` on `<html>`), or when the device prefers dark and the reader has not picked Morning: warm charcoal paper, a slightly lighter charcoal for `paper-deep`, cream ink, soft ink at 7.5:1, rules in cream at 20%, 40% and 75%. The vermilion is lightened to pass AA on charcoal: accent 5.0:1, accent-text 6.0:1. Filled ink becomes cream with charcoal text, so the ink box inverts with the edition.

### Named Rules
**The One Vermilion Rule.** Vermilion is the only hue. It draws rules, frames and large numerals, sets the words of the red-text box and marks state; it never fills a surface or a button.

**The Small Text Rule.** Any vermilion text under display size uses `accent-text`, never `accent`. `accent` on morning paper is 3.5:1 and is reserved for large type and non-text marks.

**The Two Editions Rule.** Every colour is a custom property on `:root` with a morning and an evening value; components never hard-code a colour, so both editions come from the same rules. The evening values live in two blocks (the reader's choice and the device's preference) that must stay identical.

## Typography

**Display Font:** Playfair Display (with Iowan Old Style, Georgia, serif)
**Body Font:** Source Serif 4 (with Iowan Old Style, Georgia, serif)
**Label Font:** Libre Franklin (with Franklin Gothic Medium, system-ui, sans-serif)

**Character:** A high-contrast transitional display face for the voice of the paper, a sturdy text serif with optical sizes for reading, and a Franklin Gothic revival for the apparatus and the section word. Three families, each with its own jobs.

All three are SIL Open Font License, self-hosted as variable WOFF2 in `app/web/static/fonts/` with their OFL texts beside them, `font-display: swap`, and the Playfair and Source Serif roman files preloaded. No font is fetched from a third party.

**Why Playfair Display.** The wordmark mixes 400 and 900 within one name, and headlines and numerals are 400, all from one variable family (400 to 900, with an italic for pull lines), so the name, the stories and the scores read as one typeface at different pitches. Its 400 numerals are large, regular-weight and high-contrast.

**Why Source Serif 4.** A text serif drawn for screens, with an optical size axis: `font-optical-sizing: auto` gives the 17px body and the 20px standfirst their own cuts. Lining figures are set on the body so PMIDs, years and sample sizes align with the Playfair numerals.

**Why Libre Franklin.** A revival of Franklin Gothic, the sans newspapers have long used for datelines and section heads. In tracked capitals at 11 to 12px it sets labels, metadata, navigation and buttons, so the page's furniture reads as print rather than as app chrome. At 900 it sets the section word, as Tablet sets its section names; at 400 it sets the short deks of front-page stories. The user chose Libre Franklin on 2026-11-01 after a side-by-side comparison.

### Hierarchy
- **Section word** (Libre Franklin 900, uppercase, `min(7.5rem, 11.5cqi)` of the masthead's inline size, 0.9, -0.01em): the page's name, centred under the wordmark. The biggest type on any page.
- **Wordmark** (Playfair 400 with T, M and K at 900, 1.5rem, 1, -0.01em): "Tell Me Kort" in ink, linking to the front page, on every page.
- **Lead headline** (Playfair 400, clamp 1.9rem to 3rem, 1.08, max 26ch): the front-page lead, centred from 900px. The paper page's feature title uses the same range on a steeper slope (clamp 1.9rem, 6.5vw, 3rem).
- **Second headline** (Playfair 400, clamp 1.4rem to 1.75rem, 1.12, centred).
- **Index headline** (Playfair 400, 1.375rem, 1.2): library, history and listing rows.
- **Story headline** (Playfair 400, 1.1875rem, 1.2): short stories #4 to #7, left-set.
- **Brief headline** (Playfair 400, 1.0625rem, 1.25): briefs #8 to #10, centred.
- **Pull line** (Playfair 400 italic, clamp 1.3rem to 1.6rem, 1.3): "Why it matters", under a 2px vermilion rule.
- **Numeral** (Playfair 400, lining tabular figures, 0.9, -0.02em): scores and counts. Sizes step by importance: 5rem paper page; 4.5rem lead plate and big-numeral cell; 2.75rem small plate; 2.6rem reasons; 2.1rem box figures; 1.75rem short stories, briefs and index rows; 1.5rem form steps; 1.125rem and 0.9375rem bar values.
- **Standfirst** (Source Serif 4 400, 1.25rem, 1.5, soft ink): the grade's summary on the paper page.
- **Dek** (Libre Franklin 400, 0.875rem, 1.5, soft ink): the grade's summary in a front-page cell, clamped to four lines.
- **Body** (Source Serif 4 400, 1.0625rem, 1.55, lining figures): reading text; forms and notices sit in a 38rem column.
- **Label** (Libre Franklin 500, 0.6875rem, 0.12em, uppercase, 1.6): metadata lines, criterion names on the plate, form field labels (600, 0.14em), the edition rule (0.14em), section links (0.10em).
- **Button** (Libre Franklin 600, 0.75rem, 0.14em, uppercase); small buttons at 0.6875rem.

### Named Rules
**The Small Name, Big Word Rule.** The wordmark is small and the same on every page; the section word is the loudest type on the page. Never grow the wordmark into a nameplate, and never set a section word in Playfair.

**The One Family Per Job Rule.** Playfair speaks (wordmark, headlines, numerals, pull lines), Source Serif reads (body, standfirsts, forms), Libre Franklin labels and announces (metadata, navigation, buttons, field labels, the section word, front-page deks). Never swap a role.

**The Numeral Rule.** Every score is a Playfair numeral with lining tabular figures, set beside the reason, label or bar that explains it. Never a pill, a badge or a coloured chip.

**The Data Label Rule.** A tracked-capital label above or beside content names a field of the data ("Why it matters", "for you", "Your beat", "This edition", "Scores and reasons") or carries the data itself. The paper page's line above the feature title, the grade's study design and sample size ("<study design> · n = <sample size>"), is intentional: pinned by the brief and SPEC.md §11.2, and kept by the user on 2026-11-01 after the finish review questioned it. Never invent a kicker or eyebrow line that carries no data.

## Layout

One ruled page frame (1px strong rule), at most 76rem wide, padded by the fluid gutter (1rem to 2rem). On a phone it sits 0.5rem from the viewport edges; from 900px it gains a 1.5rem margin on each side. The masthead is a size container, so the section word scales with the frame, not the viewport.

Every page stacks the same head: the wordmark line (closed by a strong rule); the section word where the page has one (the paper page, sign-in and one-tap pages carry the wordmark alone); on the front page, the edition rule under a 3px double rule; then, for signed-in readers, the section strip between strong rules.

Phone first. Every surface is one column by default. The grid starts at 900px:
- **Front page:** four equal columns with a 1rem gap. Every cell is padded 0.25rem 1.1rem 1.4rem 0 and closed by a 1px cell rule on its right and bottom. Row 1: the lead spans three columns; the two boxes stack in the fourth (no cell rules; their own frames do the work). Row 2: two second stories of two columns each. Row 3: four short stories. Row 4: three briefs and the big-numeral cell. A weight suggestion, when present, spans the full width above. On a phone the cells stack with bottom rules only in source order: lead, second stories, the two boxes, short stories, briefs, big numeral. The boxes come after the second stories in the HTML too, so reading and keyboard order match what is seen; from 900px they are placed in column 4 of row 1.
- **Score plate:** label, bar and value in three tracks (11.5rem, flexible, 1.25rem; 9.5rem, flexible, 1rem on the small plate); from 640px the overall score sits to the left of the bars.
- **Paper page:** a 52rem feature column; from 900px a 12rem score column beside the text.
- **Onboarding steps:** two columns on a phone, four from 640px.

Narrow reading columns: 38rem for forms, notices and the welcome page; 44rem for onboarding and calibration forms; 52rem for index listings and the paper page; 60rem for the admin desk.

Rhythm is set in rem and follows a short ladder: 0.5 to 0.75rem inside rows, 1rem to 1.25rem for row and cell padding, 1rem between grid columns, 1.5rem between blocks and below the section strip, 1.75rem between the masthead and the page body, 2rem to 2.5rem between major sections.

### Named Rules
**The Ruled Cell Rule.** On the front page, each cell is closed by a 1px `rule-mid` on its right and bottom, like Tablet's section fronts. No vertical side rail, no main-column-plus-rail split, no rule on a cell's left.

**The 900 Rule.** One column below 900px, the four-column grid from 900px. Nothing is hidden on a phone.

**The 44 Rule.** Every link, button, toggle, summary, select and checkbox row is at least 44px tall (`tap`), including the wordmark, the section strip, the edition switch, box links and the skip link. No horizontal scroll at 375px.

## Elevation & Depth

Flat. The system has no elevation shadows. Depth comes from rules: a 1px strong rule for frames and control borders, a 1px cell rule around front-page cells, a 1px hairline for divisions, a 3px double rule above the edition line, a 2px vermilion rule above a pull line. Two flat fills sit at rest, both on the front page: the score plate in deep newsprint and the inverted ink box. Otherwise deep newsprint appears only on hover and selection. `box-shadow` appears only as a drawn mark: an inset 3px paper ring that turns a filled checkbox into a printed tick box, and an inset 2px vermilion underline on the current onboarding step.

### Named Rules
**The Ruled, Not Raised Rule.** Separate things with a rule, never with a shadow or a floating card. The score plate (standing where Tablet runs a photograph) and the inverted ink box are the only resting fills, and both lie flat on the page.

## Shapes

Square corners everywhere (`rounded.none`): buttons, inputs, selects, textareas, checkboxes, range thumbs, boxes, score plates, score bars, the stamp, progress bars. Frames are 1px. Score bars are flat ink rectangles (0.6rem tall, 0.45rem on the small plate) drawn to `score × 20%` of their track over a 1px cell-rule baseline. Text inputs are open at the top and sides, a single strong underline like a printed form blank; textareas and selects are fully framed. The range control is a 1px track with a square ink thumb (1rem by 1.25rem) that turns vermilion while in use. The favicon is the TMK mark drawn from Playfair's outlines on a newsprint square over a vermilion bar.

## Components

### Buttons
Print-style, square and hairline-framed: they look like boxed type, not pills.
- **Shape:** square (0px), 1px strong-rule border, at least 44px tall.
- **Default:** transparent on paper, ink label in Libre Franklin 600 capitals, 0.75rem, 0.14em tracking, 0 1.1rem padding.
- **Primary:** filled ink with a paper label ("Read the paper", confirm pages, form submits). Hover keeps the fill and underlines the label.
- **Small:** 0.6875rem label, 0 0.8rem padding; used for the like, mark read and not-for-me row and the weight suggestion. A pressed toggle (`aria-pressed="true"`, e.g. "Liked") fills with ink like a primary.
- **Hover / Focus:** hover fills with deep newsprint; focus is a 2px vermilion outline offset 2px. Background and colour transition over 120ms ease-out only when the reader allows motion. Disabled is 55% opacity.
- **Link-like:** a form button set as an underlined inline link, for actions that sit in running text.

### Stamp
"Open access" in the meta line: Libre Franklin 600 capitals in vermilion text inside a 1px vermilion frame, square, never wrapped onto two lines.

### Boxes
Framed boxes in the front page's fourth column, centred, with a tracked-capital heading over a 1px rule and list items divided by rules.
- **Red-text box** ("Your beat"): a 1px vermilion frame on paper; heading, topics and the "Edit topics" link all in vermilion text, the dividers in vermilion.
- **Inverted box** ("This edition"): filled ink with paper text; the heading rule, the three figures (found, screened, graded), their labels and the source line all in paper.

### Score plate
The front page's picture. A flat deep-newsprint panel holding the weighted score (Playfair numeral with "for you") and the five criteria as rows of label, ink bar and value. The lead carries the full plate (4.5rem numeral); second stories carry the small plate (2.75rem numeral, 0.625rem labels tracked 0.08em). On the paper page the overall numeral instead stands alone in a strong-rule frame and the five criteria become numbered reasons: a 2.6rem numeral beside the criterion label, its one-line reason, and a "Disagree?" disclosure that opens a small dispute form.

### Front-page cells
One anatomy at four pitches: a score (plate or numeral), a headline (linked, no underline until hover), a dek (lead, second and short stories, clamped to four lines), and a meta line in soft-ink capitals with dot separators.
- **Lead:** full plate, then headline, dek and meta (centred, max 40rem, from 900px), the pull line, "Read the paper" and "Scores and reasons" buttons, and the action row.
- **Second:** small plate, centred headline, dek and meta, the action row.
- **Short story:** numeral on top, left-set headline, dek and meta.
- **Brief:** centred numeral, headline and meta.
- **Big-numeral cell:** the edition's paper count as a centred 4.5rem numeral over a soft-ink Libre Franklin caption ("picked for you from <n> papers graded this week").

### Inputs / Fields
- **Style:** transparent, square; text inputs have a single 1px strong underline, textareas and selects a full 1px frame. Body serif at 1.0625rem; labels above in Libre Franklin capitals.
- **Focus:** 2px vermilion outline, offset 2px.
- **Checkbox:** a square 1.25rem box with a 1px strong rule; checked fills ink inside a 3px paper inset.
- **Radio:** native, tinted vermilion.
- **Error:** vermilion-text, semibold; a notice or error block sits between two vermilion rules.

### Navigation
- **Masthead:** the wordmark line, then the section word; on the front page, the edition rule (No., week of, paper count) in Libre Franklin capitals under a 3px double rule, separated by vermilion dots.
- **Section strip:** Front page, Library, History, Profile, Settings, Calibration and Admin where allowed, and Sign out, centred between strong rules in Libre Franklin capitals at 0.10em, soft ink at rest, ink on hover. The current section is bold ink with a 2px vermilion underline offset 0.55em. It wraps on a phone; every item is 44px tall.
- **Edition switch:** in the footer colophon of every page, "Edition" then Auto · Morning · Evening as borderless buttons in the colophon's soft-ink capitals, each 44px tall. The current choice is bold ink with the same 2px vermilion underline as the current section. It is a plain form posting to `/theme`; the choice is kept in a `theme` cookie and rendered as `data-theme` on `<html>`, and Auto clears it so the page follows the device.
- **Onboarding steps:** a ruled four-cell strip (two cells on a phone) of numeral and label; the current step is ink, bold, with a vermilion numeral and a 2px vermilion underline.

### Printed forms
Onboarding reads as a numbered printed form: each row is a 2rem vermilion Playfair row number beside the field, rows divided by hairlines, the first row under a strong rule. Weight sliders pair the square range control with a Playfair numeral readout.

## Do's and Don'ts

### Do:
- **Do** open every page with the small wordmark, and give each section its own section word in Libre Franklin 900 capitals.
- **Do** draw every division with a rule: 1px `rule` between items, 1px `rule-mid` on the right and bottom of front-page cells, 1px `rule-strong` for frames and controls, 2px `accent` above a pull line.
- **Do** keep every corner square (0px), including form controls, plates and boxes.
- **Do** set every score as a Playfair 400 numeral with lining tabular figures, next to the label, reason or bar that explains it.
- **Do** use `accent-text` for any small vermilion text and keep `accent` for rules, frames and large type.
- **Do** define colours only as `:root` custom properties with morning and evening values, and keep AA contrast in both editions.
- **Do** keep labels, metadata, navigation and buttons in Libre Franklin capitals at 0.6875rem to 0.75rem, tracked 0.10em to 0.14em.
- **Do** make every interactive element at least 44px tall and keep one column below 900px.
- **Do** self-host every font and asset; the page makes no external requests.

### Don't:
- **Don't** add JavaScript; plain forms that POST and redirect carry every action, including the edition switch.
- **Don't** round a corner or add an elevation shadow, and don't fill a resting surface other than the score plate and the inverted ink box.
- **Don't** add a vertical side rail or split the front page into a main column and a rail; it is a grid of ruled cells.
- **Don't** put a score in a pill, badge or coloured chip.
- **Don't** introduce a second accent hue or fill a button or surface with vermilion.
- **Don't** set small text in `accent` (#d9472b is 3.5:1 on paper).
- **Don't** add a kicker or eyebrow line that carries no data; a label above a headline must state a field of the paper, as the study design and sample size line does on the paper page.
- **Don't** swap the type roles: no Libre Franklin story headlines (the section word is the one Libre Franklin display line), no Playfair labels, no serif buttons.
