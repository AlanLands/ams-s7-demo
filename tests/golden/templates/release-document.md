# Release & Design Document — Disability online claim submission <for> plan sponsors

Epic EPIC-S7-001 · Release REL-001 v1.0.0 · Run S7-00001

## Table of Contents

1. Overview
2. Plan Approval
3. Architecture
4. Development
5. Testing & Quality
6. Acceptance Criteria
7. Release Approvals
8. Deployment & Handover

## Overview

Plan sponsors submit disability claims online & track status.

## Plan Approval

- **P. Moreau** (business owner) — approved, 2026-09-01T09:00:00+00:00 — Scope agreed

## Architecture

Blueprint v1 accepted by **A. Osei** at 2026-09-01T10:00:00+00:00.

## Development

| Story | Title | Team | Developer | Independent Review |
|---|---|---|---|---|
| US-001 | Identify plan & member | portal-team | Priya Raman | passed |
| US-002 | Upload documents | services-team | — | pending |

**US-001 — changes:** Added lookup form

## Testing & Quality

| Story | Tested By (QA sign-off) |
|---|---|
| US-001 | R. Osei |
| US-002 | — |

- QC-01 All stories reviewed: **passed**
- QC-03 Every AC has a test: **failed**

## Acceptance Criteria

### US-001 — Identify plan & member

| Criterion | Description | Result |
|---|---|---|
| US-001-AC1 | Policy number is validated | passed |
| US-001-AC2 | Member id is pre-populated | failed |

### US-002 — Upload documents

| Criterion | Description | Result |
|---|---|---|
| US-002-AC1 | Multiple uploads accepted | not run |

## Release Approvals

- **M. Chen** (release manager) — approved, 2026-09-02T09:00:00+00:00

## Deployment & Handover

- Environment: production
- Window: 2026-09-05 22:00–23:00
- Feature flag: sponsor_claims
- Rollback: Disable flag
- Deployed: 2026-09-05T22:10:00+00:00 (blue-green, smoke tests passed)
- Handover accepted by S. Patel at 2026-09-05T23:00:00+00:00
