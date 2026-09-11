---
id: ui-layout-jinja
layer: standard
title: UI layout — Jinja2
stage: build_review
summary: The shared page layout for a Python (pytest) target — brand bar, skip link, main content block and footer as a Jinja2 base template every page extends, linking the starter stylesheet at /css/app.css. Published to .s7/shared/ui/layout.html when the repository's stack is pytest. The engine supplies the identity names. Jinja expressions in the body are written with spaces ({{ name }}) so they are not S7 placeholders; only the bare {{name}} form is substituted.
variables: organisation, short_mark, product_line
---
<!DOCTYPE html>
<!--
  Shared layout (ui-guidelines.md §2). Every page extends this base; a story never
  builds its own shell. Usage from a page template:

    {% extends "layout.html" %}
    {% block title %}Sign in{% endblock %}
    {% block content %}…page content…{% endblock %}

  Copy this file to templates/layout.html and the starter stylesheet to
  static/css/app.css.
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}{{product_line}}{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>
  <header class="brand-bar">
    <a class="brand" href="{{ url_for('index') }}">
      <span class="brand-mark" aria-hidden="true">{{short_mark}}</span>
      <span class="brand-name">{{product_line}}</span>
    </a>
    {% if current_user %}
    <div class="session">
      <span>{{ current_user.name }}</span>
      {% if current_user.plan_number %}<span>Plan {{ current_user.plan_number }}</span>{% endif %}
      <form action="{{ url_for('logout') }}" method="post"><button class="button-link" type="submit">Sign out</button></form>
    </div>
    {% endif %}
  </header>
  <main id="main">
    {% block content %}{% endblock %}
  </main>
  <footer class="site-footer">
    <p>{{organisation}} &middot; {{product_line}}. Synthetic data only &mdash; no real member, sponsor or claim information appears in this application.</p>
  </footer>
</body>
</html>
