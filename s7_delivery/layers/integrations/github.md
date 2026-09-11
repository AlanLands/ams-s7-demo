---
id: github
layer: integration
title: GitHub integration
stage: cross_cutting
summary: How S7 is allowed to talk to the tenant's git hosting. Which host and owners a run may connect or create repositories under, whether local paths are accepted, whether new-application repos may be created, which branch names publication must refuse, and which gh login is expected. Credentials never live here — the gh CLI's own login is used and only its status is shown.
---
{
  "host": "github.com",
  "allowed_owners": [],
  "allow_local_paths": true,
  "allow_repo_creation": true,
  "refuse_branch_names": ["main", "master"],
  "expected_gh_login": "",
  "note": "allowed_owners empty means any owner on the host; a non-empty list is an allowlist of GitHub owners (users or organisations). expected_gh_login empty means any authenticated gh login."
}
