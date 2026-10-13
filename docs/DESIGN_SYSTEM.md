# Design system: how it should look and feel

> Keep this current. A change to `.streamlit/config.toml` `[theme]`, the `--jh-*` tokens or the
> CSS in `ui/components.py`, or a new UI pattern, updates this file in the same commit.
> Last reviewed: 2026-10-13. Palette chosen by Arpit on 2026-10-12: ink on warm paper with one
> indigo accent, Geist type. On 2026-10-13 Arpit gave the React app (`web/`) its own design
> system: warm paper with one slate-blue accent (`#2F4858`), described under "The React app".
> The Streamlit app keeps the indigo theme below until the owner moves it too.

## Feel

Calm, dense and readable, like a well-kept spreadsheet rather than a marketing page. The
user scans dozens of jobs a day, so information comes first and decoration last. The page is
a flat warm paper color with no gradients. Motion is limited to 160 ms ease-out
hover and color changes (cards lift, buttons gain a shadow, tabs shift), switched off under
`prefers-reduced-motion`. No web fonts from the internet (Geist is bundled in
`ui/static/fonts` and served with `server.enableStaticServing`), no images.

## Where the styles live

| Layer | File | Holds |
| --- | --- | --- |
| Streamlit theme | `.streamlit/config.toml` `[theme]` | Colors of Streamlit's own widgets, radius, font family |
| App tokens | `ui/components.py` `CSS` (`--jh-*` variables) | The same colors repeated for the app's own HTML (cards, chips, score) |
| Components | `ui/components.py` helpers | Job card, chips, score bar, empty state, panel title |
| Page frame | `c.page_setup(title)`, `c.legal_footer()` | Tab title, favicon (`ui/static/favicon.png`), styles, footer links on every page |
| Legal pages | `ui/pages/privacy.py`, `ui/pages/terms.py` | Privacy policy, terms and conditions (hidden from the sidebar; `client.showSidebarNavigation = false`) |
| React tokens | `web/src/theme.css` `:root` | The same palette and type for the React app, plus its own components |

The Streamlit theme and the `--jh-*` tokens must carry the same values. `web/src/theme.css`
has its own palette since 2026-10-13 (see "The React app").

The theme and the `--jh-*` tokens must carry the same values; change both together.

## Tokens (names are stable, values follow the theme)

| Token | Use |
| --- | --- |
| `--jh-ink`, `--jh-ink-2`, `--jh-muted` | Text: primary, secondary, captions |
| `--jh-line`, `--jh-line-2` | Borders and dividers |
| `--jh-paper`, `--jh-surface`, `--jh-wash` | Page background, cards and inputs, subtle fills |
| `--jh-accent`, `--jh-accent-ink`, `--jh-accent-wash` | The one accent: primary buttons, links, focus ring, selected state |
| `--jh-accent-line` | Border of accent-tinted elements |
| `--jh-ok`, `--jh-warn`, `--jh-bad` (+ `-wash`, `-line`) | Match bands and status: good, partial, problem |
| `--jh-r-sm`, `--jh-r`, `--jh-r-lg` | Corner radius: 5 px chips and tags, 8 px buttons and controls, 12 px cards and tiles |
| `--jh-shadow`, `--jh-shadow-hi` | Resting card shadow, hover shadow |
| `--jh-sans`, `--jh-mono` | Geist, Geist Mono |

Current palette (source of truth: `.streamlit/config.toml`; use the tokens, never copy hex
values into new code):

| Role | Value |
| --- | --- |
| Accent (primary, focus) | `#4F46E5` indigo; links `#4338CA` |
| Background | `#F7F6F2` warm paper; sidebar and fills `#EFEDE7` |
| Cards, panels, inputs (secondary background) | `#FFFFFF` |
| Text / secondary / muted | `#17171C` / `#3D3D47` / `#64646F` |
| Borders | `#DEDACD` |
| Good / warning / problem | `#15803D` / `#A34D08` / `#B42318` |
| Radius | 10 px (buttons 8 px) |

## Type

- One family: Geist for text and headings, Geist Mono for numbers that are compared
  (scores, years, counts). Headings in sentence case.
- Sizes: base 15 px; page title ~2.1rem (tracking -0.035em, with a small indigo square
  before it), section `h3` 1.3rem, panel titles and `h4` ~1rem, captions and chips ~0.8rem.
- Headings are tightened (negative letter-spacing); panel titles are sentence case, never
  uppercase labels.

## Patterns

- **One task per tab.** Order: title, one-line purpose, controls (in an `st.form` when they
  apply together), summary numbers, results, details in an `st.expander`.
- **Tabs**: a segmented bar on the wash color; the selected tab is a white raised tab with 8 px corners.
- **Multiselect choices**: accent-wash tags (5 px corners) with indigo text, not solid indigo blocks.
- **Captions**: muted ink at full opacity (Streamlit's default 60% fade fails contrast).
- **Headline numbers** (`.jh-stat`): white tiles in an auto-fit grid, value in Geist Mono.
- **Panels and cards**: a bordered container that holds a `.jh-panel-title` or a job card
  turns white with a soft shadow; job cards lift on hover.
- **Job card** (`c.job_card_html`): title, company, location, skill chips, age and source,
  "Open posting" link. Each card sits in `st.container(border=True)`.
- **Score**: a number plus a band word (strong 40+, possible 25 to 39, weak), never color
  alone. Breakdown (ATS, experience, semantic, freshness, location) in an expander.
- **Chips and badges**: small square-ish corners (`--jh-r-sm`, 5 px), never pill-shaped; a tick (✓) or cross (✕) carries the meaning, color
  only reinforces it.
- **Empty states** (`c.empty_state`): say why it is empty and the next step.
- **Feedback**: long work in `st.status` / `st.progress`; result in `st.success`, `st.info`,
  `st.warning`; never a traceback (`friendly_errors`).
- **Paging**: long lists show a page and a "Show more" button.

## Rules

- Owner's standing rules: no em dashes, no emoji icons, no purple gradients, no pill shapes
  (`tests/test_legal_pages.py` checks UI code for them). The same goes for docs.
### Owner's standing rules (Arpit, 2026-10-12)

- Nothing that looks like a "vibe-coded" product: no purple or indigo gradients, no
  pill-shaped buttons or chips, no glows.
- No fake reviews, fake metrics or fake customer counters. Every number shown comes from the
  user's own data.
- No vague hero text, no AI-sounding filler copy, no AI-generated stock photos.
- No emoji icons (the favicon is `ui/static/favicon.png`, an indigo square with a white tick)
  and no em dashes in UI text or docs.
- No cursor animation and no showy scroll animation; motion stays at the 160 ms hover
  changes described above.
- Nothing launches without a favicon, a privacy policy page (`ui/pages/privacy.py`) and a
  terms and conditions page (`ui/pages/terms.py`). Both are linked from every page's footer
  (`c.legal_footer()`) and must be updated in the same change when data handling changes.
- Check the work before calling it done: no mistakes.

### Working rules

- Keep existing controls (sliders, toggles, expanders, tabs) unless the user asks to change
  them; add a new control only where there was none.
- Every input has a visible label, a stable `key=` and a `help=` when the effect is not
  obvious.
- Text contrast meets WCAG AA (4.5:1). Status is never shown by color alone.
- Check every screen at desktop width and at about 400 px.
- UI work uses the `streamlit-ui-ux` skill.

## The React app (`web/`)

Arpit's design system of 2026-10-13: warm paper, one slate-blue accent, Geist type. Written as
plain CSS in `web/src/theme.css`. Nothing is loaded from the internet: Geist and Geist Mono are
copied into `web/public/fonts` (OFL) and the favicon is the square with a white tick.

### Colour tokens

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--paper` | `#F7F4EE` | `#141311` | App background |
| `--card` | `#FFFDF8` | `#1C1B18` | Panels, rows, inputs |
| `--sunk` | `#EFE9DE` | `#26241F` | Hover, selected row, notices |
| `--line` | `#E4DDD1` | `#34312B` | Borders, dividers |
| `--line-2` | `#D3CABB` | `#423E36` | Control and tag borders, a step stronger |
| `--ink` | `#1C1A17` | `#F2EDE3` | Headings, job titles |
| `--body` | `#44403A` | `#CFC8BB` | Paragraphs, descriptions |
| `--muted` | `#6E675D` | `#978F82` | Captions, meta, labels |
| `--accent` | `#2F4858` | `#8FB0CE` | Primary button, links, tab underline, score bars |
| `--on-accent` | `#FFFDF8` | `#141311` | Text on the primary button |

Dark mode is warm charcoal with a brown bias, never blue-black, and follows the OS
(`prefers-color-scheme`).

Score bands and status, each a text colour, a tint and a border (`--ok`, `--warn`, `--bad`,
`--applied`, `--hidden`, each with `-wash` and `-line`):

| Meaning | Light text / tint | Dark text / fill |
| --- | --- | --- |
| Strong fit (band `strong`) | `#2E5E45` / `#E3EDE6` | `#76B88D` / `#1C2A21` |
| Worth a look (band `possible`) | `#7A5A16` / `#F2EAD6` | `#D3A95C` / `#2B2518` |
| Reach and skill gaps (band `weak`, missing skills) | `#8C4A33` / `#F3E3DD` | `#DC8E78` / `#2E201B` |
| Applied, saved | `#33516B` / `#E2E8EE` | `#8FB0CE` / `#1C2430` |
| Hidden, rejected | `#6E675D` / `#EFE9DE` | `#978F82` / `#26241F` |

The band words themselves come from `api/catalog.py` ("Strong fit", "Worth a look", "Reach"), so they
stay the same as Streamlit's.

Older names (`--surface`, `--wash`, `--ink-2`, `--hover`) are aliases of `--card`, `--sunk`,
`--body` and `--sunk`, so every component reads the one palette.

### Type, spacing, shape

- Geist: 400 body, 500 UI (buttons, labels, tabs), 600 headings. 700 only for the score number.
- Geist Mono: scores, fractions, counts, dates and file names, and the uppercase section labels
  (`.label-mono`: SCORE BREAKDOWN, SKILLS, DESCRIPTION, the sidebar titles).
- Scale: display 40 px (`.display`, and the score in the job pane), h1 28 px (the job title in
  the pane), h2 20 px, title 16 px / 600 (job titles in the list, card titles). Body 15 px.
- Reading width (`--measure`) 680 px, about 60 to 75 characters: posting text and prose pages.
- Spacing steps `--s1` to `--s7`: 4, 8, 12, 16, 24, 32, 48 px. Cards pad 24 px.
- Corners: 6 px tags and chips (`--r-sm`), 8 px controls (`--r`), 10 px cards (`--r-lg`). Never
  pill-shaped.

### Components

- **Buttons**: 40 px tall, with an invisible 44 px tap area. Primary is filled slate blue with
  light text; secondary is bordered on the card colour ("Score stored jobs", "Save", "Mark
  applied"); tertiary is text only (`.quiet`, "Hide"); a link-styled action (`a.link`, "Open
  posting"). Disabled is the sunk fill with muted text, for work in progress ("Scoring...").
- **Inputs and selects**: 40 px, 8 px corners, label above in 500, help below in muted text.
  Every control in one row has the same height, so they line up.
- **Score**: the number in Geist Mono 700 (22 px in the list, 40 px in the pane) in the band's
  colour, and under it a 24 px chip with the band word: the band's tint with a border of the same
  hue. When a job's score was lowered because it is not open to you, a muted mono cap note sits
  under the chip ("capped: not open to you").
- **Skill tags**: always bordered, 24 px. A skill on your resume has a green tick; a gap is the
  reach tint with the word "missing" in small mono. The word and the tick carry the meaning.
- **Badges** (status, location, "1 skill short"): the same 24 px box as a tag, tinted by meaning.
- **Tabs**: underline only, never pills or segments. The tab in use is ink with a 2 px accent
  bar under it. The same style is used for the main tabs and the filters inside a tab
  (Applications, Documents).
- **Score bars**: label left, the fraction right in mono ("56 / 100"), a 6 px accent bar under
  them on the sunk track, and a muted line saying what the part measures.
- **Notices**: a tinted card with no border and body text inside (sunk, or the green, amber,
  reach or slate tint for success, warning, problem and information).
- **Empty states**: dashed frame, the icon on a small sunk tile, a title and the next step.
- **Loading**: skeletons shaped like the content (the Matches list gets rows with a title, a
  meta line, tags and a score), flat fills that breathe in opacity, no shimmer gradient; they
  appear only after 200 ms. A thin indeterminate bar (a sliding segment, moved by transform) for
  long work. No spinners.

### Page frame

- **Top bar**: the wordmark on the left, the five tabs in the centre, the resume file in use on
  the right in mono. Opaque paper with a bottom hairline. Below 900 px the tabs move to a second
  row that scrolls sideways, with the tab in use scrolled into view.
- **Sidebar** (every tab but Matches): resume in use, language model, storage, as plain sections
  split by hairlines under mono labels, not cards. Below 1000 px it moves under the main column.
- **Headline numbers** (`.stats`): one card split by hairlines, values in mono, then the "Next
  step" notice. Both are left out on Matches, which opens straight on its filters.
- **Footer**: "Data stays on this laptop, in SQLite." on the left, Privacy and Terms on the right.
- **Changing tab** scrolls to the top of the page and the new tab fades in.

### Matches

- **Filters** (one card): a row of four 40 px controls (Search, Your country, Status, Sort by),
  then the sliders (minimum score, years), Source and the two checkboxes. On a narrow screen the
  second group folds under "More filters". Under them, one line: the count and active filters on
  the left; "Reset filters", "What the scores mean" (opens the guide) and "Score stored jobs" on
  the right.
- **List and job**: the list on the left and the job you picked on the right (`.split`). On a
  wide screen (1120 px and up) the two columns sit in one screen-high frame and each scrolls on
  its own; below that the job opens as a full-screen sheet with a "Back to the list" button
  (Escape closes it too). The list is one bordered frame with rows split by hairlines. A row:
  title (16 / 600), company and place, a meta line (age, source, years, status), the
  score on the right, then badges and skill tags. The selected row has the sunk fill and a 2 px
  accent bar on its left edge, never colour alone. The same job posted for several cities (same
  company, title and score) is one row that says "N locations"; the job lists the cities.
- **Job pane** (one card): the title as h1, the facts, location and years badges, and the score
  on the right. Actions in one row: "Write cover letter" (primary), "Save", "Mark applied",
  "Hide" (tertiary), "Open posting" (link); the Status select on its own line under them. Then
  SCORE BREAKDOWN (the four parts in two groups, fit then reach, with the sentence from
  `api/catalog.py` and the guide behind a summary) beside SKILLS (must have, nice to have,
  keywords), and DESCRIPTION below (the snippet, or the whole posting on request).
- Charts ("The jobs shown at a glance") and "Skills worth adding" follow the list.
- The guide's numbers come from `matching/confidence_score.py` through `/api/catalog`, so they
  cannot drift from Streamlit's.
- **Job list keyboard**: `role="listbox"` with `role="option"` rows; arrow up and down move focus
  and selection.
- **Document title**: "Title - Company . Score | JobHunt AI" while a job is open.

### Behaviour kept from before

- **Header numbers** are read again on every tab change, so they agree with the list. Lists show
  20 jobs and a "Show more" button and start again at the top when a filter changes. Lists and
  cards set an explicit grid column (`minmax(0, 1fr)`), or a long title lays the card out wider
  than its column.
- **Facts under a title** (`c.Meta`): separated by a middle dot; a line breaks at a separator,
  never inside a fact.
- **Feedback**: a `.notice` under the control that caused it, which clears itself after a few
  seconds. Never a traceback: the API sends a sentence and the screen shows it.
- **Drafts**: the cover letter streams into the editor as the model writes it, with a Stop button.
- Tab data is cached per key, so switching tabs shows the last data at once while it refetches.

### Motion

160 ms colour changes on hover; buttons press down 1 px; the tab underline grows in. State
changes fade in with opacity and a 4 px rise in 200 ms (`.enter`): a new tab, another job, the
phone sheet. Score bars grow from the left once. Only transform and opacity animate, and
`.enter` uses fill mode `backwards` so no transform is left behind (a leftover transform would
trap the fixed-position sheet inside the tab). Everything is switched off under
`prefers-reduced-motion`. No scroll or cursor animation.
