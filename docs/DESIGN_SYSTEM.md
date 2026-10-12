# Design system: how it should look and feel

> Keep this current. A change to `.streamlit/config.toml` `[theme]`, the `--jh-*` tokens or the
> CSS in `ui/components.py`, or a new UI pattern, updates this file in the same commit.
> Last reviewed: 2026-10-12. Palette chosen by Arpit on 2026-10-12: ink on warm paper with one
> indigo accent, Geist type. A job list with a detail pane and score breakdown bars is coming
> soon; describe it here when it lands.

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
| Borders | `#E4E1D8` |
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
- **Score**: a number plus a band word (strong 50+, possible 35 to 49, weak), never color
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
