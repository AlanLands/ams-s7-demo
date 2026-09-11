---
id: pricing
layer: model
title: Token pricing
stage: cross_cutting
summary: Provider token prices behind the cost-per-release KPI. Deliberately empty in the default profile — a cost is computed only from measured token usage times a rate an operator entered here; it is never invented.
---
{
  "currency": "USD",
  "unit": "per 1M tokens",
  "rates": {},
  "note": "rates are keyed provider/model, e.g. \"anthropic/claude-sonnet-5\": {\"input\": 3.0, \"output\": 15.0, \"cache_read\": 0.3, \"cache_write\": 3.75}"
}
