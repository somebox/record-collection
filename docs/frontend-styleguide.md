---
title: "Frontend styleguide"
last_updated: 2026-08-22
status: aging
scope: design
audience: developer
tags: [design, styleguide, css, frontend]
---

# Frontend styleguide

The web app is server-rendered Jinja with one stylesheet (`lib/static/style.css`)
and one script (`lib/static/app.js`). No build step, no frameworks. This document
records the conventions; the stylesheet is organized in the same order.

## Design language

Minimalist black & white. Strong 1px black borders for structure, light grey for
secondary surfaces, **dotted lines as separators** (table rows, section breaks),
*italics for descriptive text* (style, summary, notes), bold for titles and
primary emphasis. Pastel folder colors are the only color in the UI, always with
black text. Sans-serif throughout (Helvetica stack on screen, Liberation Sans on
printed labels — the screen and the labels should feel like the same system).

## Tokens

All colors come from `:root` variables — no hex values in rules:

| token | use |
|---|---|
| `--ink` | text, strong borders |
| `--paper` | background |
| `--faint` | secondary text (keep ≥ AA contrast on paper) |
| `--hair` | light solid borders (form fields) |
| `--dot` | all dotted separators — one grey everywhere |
| `--tint` / `--tint-strong` | subtle row/hover tints |
| `--swatch-border` | borders on data-colored swatches and chips |

Folder pastels are data, not theme: they come from the database (or the
deterministic fallback in `web.py`) and are set as inline `style="background: …"`.
That is the one sanctioned use of inline styles.

## Conventions

- **Visibility**: the `hidden` attribute is the single mechanism for
  showing/hiding. `[hidden] { display: none !important }` guarantees it beats any
  component `display`. Never write per-component `.x[hidden]` rules and never
  toggle `style.display` from JS.
- **Naming**: components are lowercase nouns (`topbar`, `bulkbar`, `palette`);
  parts get the component prefix when the name is generic (`modal-body`,
  `palette-swatch`). States are bare adjectives applied next to the component
  class (`active`, `selected`, `dirty`, `dragging`). Utilities are a closed set:
  `.dim` (faint text), `.desc` (italic descriptive text), `.num` (right-aligned
  tabular numbers).
- **IDs are JavaScript hooks, not style targets.** CSS selects classes and
  attributes only. `app.js` uses delegated listeners on ids (`#save-fields`)
  and data attributes (`data-instance`, `data-folder`) — partials injected into
  the modal must not duplicate ids that exist on the page behind it.
- **Buttons**: default buttons invert on hover (black fill). Quiet buttons
  (modal close/nav, palette swatches) take `.btn-plain`, which opts out of the
  invert. Disabled buttons never invert.
- **Icons**: inline SVG only, from the `icon()` macro in `_icons.html` —
  16px grid, 1.8px stroke, `currentColor`. No emoji, no icon fonts. New icons
  join the macro, matching that style.
- **Type**: uppercase 11px letterspaced micro-labels for all headings-of-things
  (table headers, field labels, sidebar section, stat names) — one shared rule.
  Body 14px; h1 18px (topbar), h2 20px.
- **The eyebrow rule of thumb**: if text labels a value rather than being one,
  it's a micro-label; if it describes content, it's `.desc` italic; if it's
  secondary, it's `.dim`.

## Accessibility baseline

- `:focus-visible` shows a 2px dashed outline everywhere (matches the drag-over
  affordance); don't remove focus outlines.
- Every icon-only or ambiguous control carries `aria-label`. Status spans that
  JS writes into (`.save-status` etc.) carry `aria-live="polite"`.
- The modal is `role="dialog" aria-modal="true"`; Esc closes it. (Focus trapping
  is not implemented; known gap.)
- `--faint` must stay AA-compliant on white for the small text it's used at.

## Layout notes

- The page is a flex column (`body`) so the status bar sits at the bottom
  without hardcoded viewport math.
- The detail panel (`.detail`) is a two-column grid — info + label preview on
  the left, form on the right — collapsing to one column under 900px. It renders
  both as modal content and as the standalone item page; changes must work in
  both contexts.
- The items table lives in `.table-scroll` (horizontal overflow guard). Full
  responsive/mobile layout is a known gap; the app targets desktop.

## Known gaps (accepted for now)

- No focus trap in the modal; keyboard users can tab behind it.
- Table rows are click-to-open but not keyboard-focusable; the title link is
  the keyboard path.
- Link underline policy is ad-hoc (`text-decoration: none` set per component).
- No print stylesheet (printing goes through the server-rendered labels).
