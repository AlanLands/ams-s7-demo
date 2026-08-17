# Business Requirement REQ-2026-121 — MapleSure Member Sign-In

**Requested by:** Group Benefits Digital Experience (Business Owner: P. Moreau)
**Date:** 2026-08-17
**Priority:** High
**Type:** New application — no existing system provides this capability

## Business objective

MapleSure members currently have no dedicated online entry point: every
digital journey begins with a phone call to the service desk for identity
verification. We need a standalone member sign-in application — the front
door for all future member-facing journeys — so that a member can
authenticate themselves online with their member ID and a password, and
downstream portals can trust that authentication.

## Background and current state

- There is no member-facing authentication capability today; portals under
  construction (claims, retirement) each assume "an authenticated member"
  and none provides authentication itself.
- The service desk performs manual identity verification by phone, which
  adds handling time to every member interaction and cannot scale to the
  online claim submission volumes forecast for next year.
- This is deliberately a new, separate application: authentication must be
  a shared front door, not a feature copied into each portal.

## Requirements

1. A member can sign in with their member ID and password on a single,
   clearly branded MapleSure sign-in page.
2. Credentials are validated against the member credential store; a
   successful sign-in shows a signed-in landing view confirming the
   member's display name and last sign-in time.
3. A failed sign-in shows one generic error message — it must not reveal
   whether the member ID or the password was wrong.
4. After five consecutive failed attempts for the same member ID, the
   account is temporarily locked for fifteen minutes and the page says so
   without revealing whether the credentials were otherwise correct.
5. A "Forgotten your password?" link is present and routes to a placeholder
   contact-the-service-desk page (self-serve reset is out of scope for this
   release).
6. Every sign-in attempt (success, failure, lockout) is recorded in an
   audit log with member ID, timestamp and outcome — never the password.
7. The sign-in form is keyboard-accessible, labels every field, and meets
   WCAG AA contrast on the MapleSure palette.
8. Passwords are never stored or logged in plain text; the credential store
   holds salted hashes only.

## Out of scope

- Self-serve password reset, multi-factor authentication, and federation
  with employer identity providers (future phases).
- Member registration/enrolment — credential records are provisioned by
  the existing membership back office.

## Success measures

- A member with valid credentials reaches the signed-in landing view in
  one attempt.
- Invalid attempts never disclose which credential was wrong.
- Lockout engages on the fifth consecutive failure and releases after
  fifteen minutes.
- Zero passwords in any log or audit record.

## Notes for delivery

Keep the application small and self-contained: one sign-in page, one
signed-in landing view, one placeholder help page, a credential store with
salted hashes, and the audit log. Synthetic member data only.
