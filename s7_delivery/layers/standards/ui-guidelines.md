---
id: ui-guidelines
layer: standard
title: UI guidelines
stage: build_review
summary: Developer-facing UI rules for every page a story adds or changes — one stylesheet with the tenant's tokens, page anatomy, forms, the five states, copy, WCAG AA and the screenshot evidence a pull request carries. Token values come from the identity file; the engine supplies the rendered token block and rows.
variables: team, scope_line, css_block, token_rows, organisation, short_mark, product_line, synthetic_domain
---
# UI guidelines — {{team}}

A page that passes its tests but looks like a framework default is not done. Every page a story adds or changes follows this file; the reviewer checks the pull request's screenshots against it.

{{scope_line}}

## 1. One stylesheet, these tokens

One application stylesheet (for example `static/css/app.css`), declared once in the shared layout. No inline `style=` attributes, no per-page stylesheets, no colour literals outside the token block, no fonts or CSS fetched from a CDN. Copy this block in unchanged:

```css
{{css_block}}
body { margin: 0; background: var(--ms-bg); color: var(--ms-ink); font: 16px/1.5 var(--ms-font); }
:focus-visible { outline: 2px solid var(--ms-red); outline-offset: 2px; }
```

| Token | Value | Use |
|---|---|---|
{{token_rows}}

## 2. Page anatomy

- **Shared layout.** One layout template or component (brand bar, `<main>`, footer) that every page extends. A story never builds its own page shell.
- **Brand bar.** Left: the `{{short_mark}}` mark (36px square, `--ms-red`, white serif initials) and the product name. Right, when signed in: the person's name, their organisation's plan number, and a *Sign out* link.
- **Focused pages** (sign-in, password reset, organisation choice, confirmations): one centred card, `max-width: 420px`, `--ms-surface` on `--ms-bg`, `--ms-radius-md`, 32px padding, a single `<h1>`, one primary action, help links underneath.
- **Working pages** (lists, forms, dashboards): `max-width: 1080px`, a page title row, then content in cards. Tables stripe with `--ms-surface-2` and scroll inside their own container — the page never scrolls horizontally.
- **Responsive.** Single column at or below 600px; touch targets at least 44px tall; nothing depends on hover.

## 3. Forms

- Label above every input, associated with `for`/`id`; help text under it in `--ms-muted`, linked with `aria-describedby`.
- Inputs: 44px tall, `--ms-border`, `--ms-radius-sm`, 12px horizontal padding; `--ms-red` focus ring from the token block.
- Primary button: `--ms-red` background, white text, full width on focused pages; secondary actions are text links in `--ms-red-dark`. One primary action per page.
- Never disable the submit button to enforce validation; validate on submit and show the errors. Show a busy state (text changes to *Signing in…*, button `aria-busy="true"`) while a request runs.
- Passwords: `autocomplete="current-password"` / `"new-password"`, no paste blocking, an optional show/hide toggle.

## 4. The five states every page renders

Before a page is done it renders, and the pull request shows, each of these that applies:

1. **Default** — first load.
2. **Validation error** — an error summary at the top of the form (`role="alert"`, `--ms-red-pale` on `--ms-red-dark` text, prefixed *Error:*) plus the inline message under each field. Focus moves to the summary.
3. **Server or auth failure** — the exact sentence the acceptance criterion specifies, and nothing that reveals more than it does.
4. **Success or confirmation** — `--ms-green-pale` banner or the next page; never a bare redirect with no acknowledgement.
5. **Loading / empty** — a busy state while waiting; an empty list says what would appear here and how to add it.

## 5. Copy

- Sentence case everywhere; plain words; no jargon, no codes shown to a person.
- Button labels are verbs (*Sign in*, *Send reset link*, *Choose organisation*).
- Error and confirmation sentences come from the acceptance criteria verbatim where one is given.
- Synthetic names, organisations and plan numbers only; the `{{synthetic_domain}}` domain for any address shown.

## 6. Accessibility — WCAG 2.1 AA, checked by a test

- `<html lang>`, a skip link to `<main>`, one `<h1>`, headings in order, landmarks (`header`, `main`, `nav`, `footer`).
- Every control reachable and operable by keyboard; visible focus ring; no keyboard trap; errors announced (`role="alert"`).
- Contrast: text 4.5:1, large text and UI borders 3:1. Pin the token pairings above in a test that reads the served stylesheet, so a colour change fails the suite rather than the audit.
- Images and icons carry `alt` text or `aria-hidden` when decorative.

## 7. Evidence in the pull request

For each page added or changed: screenshots at 1280px and 375px wide, one per state in section 4, captured from the running application — not mock-ups. Name them `<story-id>-<page>-<state>-<width>.png` and attach them under an *UI evidence* heading in the PR body, below the acceptance criteria table. The reviewer compares them against this file before approving.
