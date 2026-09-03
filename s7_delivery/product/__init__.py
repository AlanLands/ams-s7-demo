"""The product-configuration plane (added 2026-09-03).

Everything an operator can change *without editing code* lives here, as
plain JSON and markdown files under one configuration directory
(`S7_CONFIG_DIR`, default `<repo>/config/`, gitignored):

    config/
      prompt-sets/<name>/     a full copy of the layer files — rules/, skills/,
                              tasks/, playbooks/ — with its own history.jsonl
                              and versions/ snapshots; `default` is the
                              committed set under s7_delivery/layers/
      llm_settings.json       provider/model per stage, optional mode override
      roles.json              permission and profile overrides
      users.json              named users and the role each acts as
      audit.jsonl             append-only log of every admin change

Discipline, shared with the rest of the repo: every change is recorded
(prompt edits in the set's ledger, everything else in audit.jsonl); nothing
here ever presents an unrecorded value as recorded; and the committed default
prompt set stays byte-identical unless someone deliberately edits it — which
the recordings guard in `tests/test_layers.py` then reports.
"""
