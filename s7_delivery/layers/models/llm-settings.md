---
id: llm-settings
layer: model
title: Models per stage
stage: cross_cutting
summary: Provider and model per workflow stage and per lane role, plus an optional LLM mode pin. Empty entries fall through to the global admin setting and then to the environment. Both provider and model enter the recording cache key, so a re-pointed stage honestly misses old recordings.
---
{
  "default": {},
  "stages": {},
  "llm_mode": null
}
