---
id: ui-starter-css
layer: standard
title: UI starter stylesheet
stage: build_review
summary: The complete starter stylesheet a team pack publishes to .s7/shared/ui/app.css — the identity token block, base and focus styles, the brand bar, the focused-page card, forms, banners, table stripes and the 600px responsive rule from the UI guidelines. The engine supplies the token declarations from the identity file; the :root block is locked because every other rule reads its variables.
variables: css_tokens
locked: :root, {{css_tokens}}
---
/* Application stylesheet — the one stylesheet every page shares (ui-guidelines.md §1).
   Tokens come from the delivery identity; everything below reads them. No colour
   literals outside :root, no inline styles, nothing fetched from a CDN. */

:root {
{{css_tokens}}
}

/* Base */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--ms-bg); color: var(--ms-ink); font: 16px/1.5 var(--ms-font); }
:focus-visible { outline: 2px solid var(--ms-red); outline-offset: 2px; }
a { color: var(--ms-red-dark); }
h1, h2, h3 { line-height: 1.25; margin: 0 0 calc(var(--ms-space) * 2); }
h1 { font-size: 1.75rem; }
h2 { font-size: 1.25rem; }
p { margin: 0 0 calc(var(--ms-space) * 2); }

/* Skip link — visible only when focused */
.skip-link { position: absolute; left: -999px; top: var(--ms-space); background: var(--ms-surface); color: var(--ms-ink); padding: var(--ms-space) calc(var(--ms-space) * 2); border-radius: var(--ms-radius-sm); z-index: 10; }
.skip-link:focus { left: var(--ms-space); }

/* Brand bar */
.brand-bar { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--ms-space) * 2); padding: calc(var(--ms-space) * 1.5) calc(var(--ms-space) * 3); background: var(--ms-surface); border-bottom: 1px solid var(--ms-border); }
.brand { display: flex; align-items: center; gap: calc(var(--ms-space) * 1.5); text-decoration: none; color: var(--ms-ink); }
.brand-mark { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; background: var(--ms-red); color: #ffffff; font-family: Georgia, 'Times New Roman', serif; font-weight: 700; border-radius: var(--ms-radius-sm); }
.brand-name { font-weight: 600; }
.brand-bar .session { display: flex; align-items: center; gap: calc(var(--ms-space) * 2); color: var(--ms-muted); font-size: 0.9375rem; }

/* Page shells (ui-guidelines.md §2) */
main { display: block; }
.page-focused { max-width: 420px; margin: calc(var(--ms-space) * 6) auto; padding: 0 calc(var(--ms-space) * 2); }
.page-working { max-width: 1080px; margin: calc(var(--ms-space) * 4) auto; padding: 0 calc(var(--ms-space) * 3); }
.card { background: var(--ms-surface); border: 1px solid var(--ms-border); border-radius: var(--ms-radius-md); padding: calc(var(--ms-space) * 4); }
.page-title-row { display: flex; align-items: baseline; justify-content: space-between; gap: calc(var(--ms-space) * 2); margin-bottom: calc(var(--ms-space) * 3); }
.help-links { margin-top: calc(var(--ms-space) * 3); font-size: 0.9375rem; }
.help-links a + a { margin-left: calc(var(--ms-space) * 2); }

/* Forms (ui-guidelines.md §3) */
.field { margin-bottom: calc(var(--ms-space) * 3); }
label { display: block; font-weight: 600; margin-bottom: calc(var(--ms-space) / 2); }
.hint { display: block; color: var(--ms-muted); font-size: 0.9375rem; margin-bottom: var(--ms-space); }
input[type="text"], input[type="email"], input[type="password"], input[type="number"], input[type="date"], select, textarea { display: block; width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--ms-border); border-radius: var(--ms-radius-sm); background: var(--ms-surface); color: var(--ms-ink); font: inherit; }
textarea { min-height: 96px; padding: var(--ms-space) 12px; }
input:hover, select:hover, textarea:hover { border-color: var(--ms-border-strong); }
input[readonly] { background: var(--ms-surface-2); }
.field-error input, .field-error select, .field-error textarea { border-color: var(--ms-red); }
.field-error .error-message { color: var(--ms-red-dark); font-weight: 600; margin-top: calc(var(--ms-space) / 2); }
.button, button { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 0 calc(var(--ms-space) * 3); border: 1px solid transparent; border-radius: var(--ms-radius-sm); font: inherit; font-weight: 600; cursor: pointer; }
.button-primary { background: var(--ms-red); color: #ffffff; }
.button-primary:hover, .button-primary:active { background: var(--ms-red-dark); }
.button-primary[aria-busy="true"] { opacity: 0.85; cursor: progress; }
.page-focused .button-primary { width: 100%; }
.button-link { background: none; border: 0; color: var(--ms-red-dark); text-decoration: underline; padding: 0; min-height: 44px; }

/* Banners (ui-guidelines.md §4) */
.banner { border-radius: var(--ms-radius-md); padding: calc(var(--ms-space) * 2) calc(var(--ms-space) * 3); margin-bottom: calc(var(--ms-space) * 3); border: 1px solid transparent; }
.banner-error { background: var(--ms-red-pale); color: var(--ms-red-dark); border-color: var(--ms-red); }
.banner-success { background: var(--ms-green-pale); color: var(--ms-green); border-color: var(--ms-green); }
.banner-warning { background: var(--ms-amber-pale); color: var(--ms-amber-text); border-color: var(--ms-amber-text); }
.banner ul { margin: var(--ms-space) 0 0; padding-left: calc(var(--ms-space) * 3); }
.empty-state { color: var(--ms-muted); padding: calc(var(--ms-space) * 4); text-align: center; }

/* Tables — stripe, and scroll inside their own container */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: calc(var(--ms-space) * 1.5) calc(var(--ms-space) * 2); border-bottom: 1px solid var(--ms-border); }
th { font-weight: 600; }
tbody tr:nth-child(even) { background: var(--ms-surface-2); }

/* Footer */
.site-footer { margin-top: calc(var(--ms-space) * 6); padding: calc(var(--ms-space) * 3); color: var(--ms-muted); font-size: 0.875rem; border-top: 1px solid var(--ms-border); }

/* Responsive — single column at or below 600px */
@media (max-width: 600px) {
  .brand-bar { flex-direction: column; align-items: flex-start; }
  .page-title-row { flex-direction: column; align-items: flex-start; }
  .page-focused { margin-top: calc(var(--ms-space) * 3); }
  .card { padding: calc(var(--ms-space) * 3); }
  .button, button { width: 100%; }
}
