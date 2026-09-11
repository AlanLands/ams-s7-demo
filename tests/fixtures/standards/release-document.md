# Release & Design Document — Online disability claim submission for plan sponsors

Epic EPIC-S7-001 · Release REL-2026R4-001 v1.0.0 · Run S7-00001

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

A plan sponsor can, unaided, submit a complete disability claim for a member they sponsor, receive a reference, see its status later, and intake receives a single associated packet rather than loose documents.

## Plan Approval

- **P. Moreau** (business owner) — approved, 2026-09-07T08:57:46+00:00 — Plan approved for build

## Architecture

Blueprint v1 accepted by **A. Osei** at 2026-09-07T08:57:46+00:00.

## Development

| Story | Title | Team | Developer | Independent Review |
|---|---|---|---|---|
| US-001 | Submission record with draft persistence and audit trail | Data Team | Elena Kovacs | passed |
| US-002 | Member and plan lookup with sponsor-organization isolation | Services Team | Marcus Chen | passed |
| US-003 | Guided claim journey with absence-date validation | Portal Team | Priya Raman | passed |
| US-004 | Multi-document upload under the existing file policy | Portal Team | Priya Raman | passed |
| US-005 | Intake handoff as a single associated packet | Intake Integration Team | Dev Patel | passed |
| US-006 | Automated regression and integration scenarios | QA Automation | Sofia Marino | passed |
| US-007 | Deployment, monitoring and support handover | Platform Team | Liam O'Rourke | passed |

**US-001 — changes:** Additive schema for the submission record, draft persistence and the append-only audit trail. No existing table altered; rollback is a reverse migration.

**US-002 — changes:** Sponsor-scoped lookup service resolving policy number and member id to pre-population data. Cross-organization requests return no data and write an audit event.

**US-003 — changes:** Guided claim journey collecting employment and absence facts, with absence-date validation before submission. Correction after independent review: the rejection boundary now includes the equal case (first day absent on or before last day worked), and the boundary test asserts it.

**US-004 — changes:** Multi-document upload attached to the submission record, enforcing the existing file type and size policy with a clear refusal reason.

**US-005 — changes:** Handoff of the completed submission to intake/indexing as one associated packet, with retry and surfacing on failure. Receiving contract agreed with the owning team.

**US-006 — changes:** Regression and integration scenarios: sponsor isolation, both absence-date boundaries, upload policy, end-to-end packet verification at intake.

**US-007 — changes:** Blue-green deployment behind the sponsor_claim_submission flag, monitoring alerts, runbook and support handover updates.

## Testing & Quality

| Story | Tested By (QA sign-off) |
|---|---|
| US-001 | R. Osei |
| US-002 | R. Osei |
| US-003 | R. Osei |
| US-004 | R. Osei |
| US-005 | R. Osei |
| US-006 | R. Osei |
| US-007 | R. Osei |

- QC-01 Requirement-to-story mapping: **passed**
- QC-02 AC-to-code mapping: **passed**
- QC-03 AC-to-test mapping: **passed**
- QC-04 Test execution: **passed**
- QC-05 Code coverage: **passed**
- QC-06 Security scan: **passed**
- QC-09 Dependency scan: **passed**
- QC-10 Standards check: **passed**
- QC-07 Independent-review gaps: **passed**
- QC-11 Regression & integration hand-off: **passed**
- QC-12 Performance test hand-off: **not_applicable**
- QC-08 Operational readiness: **passed**

## Acceptance Criteria

### US-001 — Submission record with draft persistence and audit trail

| Criterion | Description | Result |
|---|---|---|
| US-001-AC1 | A submission record persists across a dropped sponsor session. | passed |
| US-001-AC2 | Every submission carries an append-only audit trail of actor, action and time. | passed |
| US-001-AC3 | Documents are associated to the submission record, never stored loose. | passed |

### US-002 — Member and plan lookup with sponsor-organization isolation

| Criterion | Description | Result |
|---|---|---|
| US-002-AC1 | Lookup returns member and plan details for a member the sponsor sponsors. | passed |
| US-002-AC2 | Lookup for a member outside the sponsor organization returns no data and is audited. | passed |
| US-002-AC3 | Pre-populated fields are shown for confirmation and attested before submission. | passed |

### US-003 — Guided claim journey with absence-date validation

| Criterion | Description | Result |
|---|---|---|
| US-003-AC1 | The journey collects last day worked, first day absent, nature of absence and details. | passed |
| US-003-AC2 | A submission with first day absent after last day worked is accepted. | passed |
| US-003-AC3 | A submission where first day absent is on or before the last day worked is rejected. | passed |
| US-003-AC4 | Existing SponsorConnect session and authorization behaviour is unchanged. | passed |

### US-004 — Multi-document upload under the existing file policy

| Criterion | Description | Result |
|---|---|---|
| US-004-AC1 | Multiple documents can be uploaded and are listed against the submission. | passed |
| US-004-AC2 | Files outside the existing type and size policy are refused with a clear reason. | passed |

### US-005 — Intake handoff as a single associated packet

| Criterion | Description | Result |
|---|---|---|
| US-005-AC1 | A completed submission reaches intake as a single associated packet. | passed |
| US-005-AC2 | Handoff failures are retried and surfaced; a submission is never silently dropped. | passed |

### US-006 — Automated regression and integration scenarios

| Criterion | Description | Result |
|---|---|---|
| US-006-AC1 | Regression suite covers sponsor isolation and both absence-date boundaries. | passed |
| US-006-AC2 | Integration scenario submits end to end and verifies the packet at intake. | passed |

### US-007 — Deployment, monitoring and support handover

| Criterion | Description | Result |
|---|---|---|
| US-007-AC1 | Deployment runs behind the sponsor_claim_submission flag with a validated rollback. | passed |
| US-007-AC2 | Monitoring alerts, runbook and support handover are updated and accepted by Support. | passed |

## Release Approvals

- **P. Moreau** (business owner) — approved, 2026-09-07T08:57:59+00:00
- **A. Osei** (engineering lead) — approved, 2026-09-07T08:57:59+00:00
- **R. Tanaka** (qa lead) — approved, 2026-09-07T08:57:59+00:00
- **S. Lindqvist** (release manager) — approved, 2026-09-07T08:57:59+00:00
- **N. Whitfield** (support lead) — approved, 2026-09-07T08:57:59+00:00

## Deployment & Handover

- Environment: Production
- Window: 2026-08-21 20:00–23:00 ET
- Feature flag: sponsor_claim_submission (off at deploy)
- Rollback: Disable the feature flag and restore the previous journey entry point; database changes are additive with a reverse migration. Validated in staging.
- Deployed: 2026-09-07T08:57:59+00:00 (blue-green behind sponsor_claim_submission flag, smoke tests passed (8/8 checks))
- Handover accepted by support_lead at 2026-09-07T08:58:00+00:00
