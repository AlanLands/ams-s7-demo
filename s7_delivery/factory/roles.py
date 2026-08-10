"""Role → permitted actions. Enforced in the engine, reflected in the UI.

The separation rules the spec names (spec §4) are the point, not the list:

- the development worker cannot approve its own output,
- the independent reviewer cannot modify development results,
- only the Business Owner signs the plan,
- only the Release Manager approves release.

`require` raises rather than returns so a missing check is loud.
"""

from __future__ import annotations

from s7_delivery.factory.models import Role


class PermissionError_(Exception):
    """Named with a trailing underscore to avoid shadowing the builtin."""


# Action names are the engine's method names — one vocabulary end to end.
PERMISSIONS: dict[str, set[Role]] = {
    # intake
    # The requirement is the business's own artifact: only the Business Owner
    # uploads/pastes it (extraction of what they provided rides the same
    # permission), and only the Business Owner signs off the intake gate —
    # the same separation as `sign_off_plan`. Analysts run the deeper
    # analysis and shape the epic; they do not source or sign the requirement.
    "edit_requirement": {Role.BUSINESS_OWNER, Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "upload_intake_document": {Role.BUSINESS_OWNER},
    "run_intake_analysis": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "create_epic": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "connect_repository": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    "ask_clarification": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "route_requirement": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "setup_new_application": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "create_new_application_repo": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    "pass_intake_gate": {Role.BUSINESS_OWNER},
    # planning
    "generate_plan": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
    "edit_story": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD, Role.PRODUCT_ANALYST},
    "request_plan_revision": {Role.DELIVERY_LEAD, Role.PRODUCT_ANALYST},
    "sign_off_plan": {Role.BUSINESS_OWNER},
    "export_artifacts": {Role.DELIVERY_LEAD, Role.PRODUCT_ANALYST, Role.ENGINEERING_LEAD},
    "write_delivery_clone": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    "push_delivery_branch": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    # build & review — governed context generation and handoff
    # Generation is performed by the service/simulation actor; these roles may
    # trigger it. Acceptance is a *human* checkpoint held by the Engineering
    # Lead — the generator (the service) never accepts its own blueprint.
    "generate_architecture": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    "revise_architecture": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    "accept_architecture": {Role.ENGINEERING_LEAD},
    "generate_delivery_packs": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    # QA approves the AC test plan; the service that generated it never
    # approves its own tests — same separation as architecture acceptance.
    "approve_test_plan": {Role.QA_LEAD},
    # QA may amend the plan (an overlay of extra cases, refined by the
    # system), but every amendment resets the approval — the edit still
    # passes back through the checkpoint before publication.
    "amend_test_plan": {Role.QA_LEAD},
    "publish_delivery_pack": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    "assign_developer": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    # Unlocking a dependency-blocked story before its upstream evidence is a
    # recorded risk decision a lead owns — never automatic, never silent.
    "override_dependency_gate": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    "sync_git_evidence": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    # build & review — developer execution evidence
    "start_task": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    "run_development": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    "submit_for_review": {Role.ENGINEERING_LEAD, Role.DELIVERY_LEAD},
    "execute_review": {Role.INDEPENDENT_REVIEWER},
    "return_to_development": {Role.INDEPENDENT_REVIEWER},
    "approve_review": {Role.INDEPENDENT_REVIEWER},
    # quality
    "run_quality_checks": {Role.QA_LEAD, Role.DELIVERY_LEAD},
    "decide_quality_gate": {Role.QA_LEAD},
    # release
    "request_release_approval": {Role.RELEASE_MANAGER, Role.DELIVERY_LEAD},
    # Each required role records its own release approval; the final,
    # blocking decision is `deploy`, which only the Release Manager holds.
    "approve_release": {Role.BUSINESS_OWNER, Role.ENGINEERING_LEAD,
                        Role.QA_LEAD, Role.RELEASE_MANAGER, Role.SUPPORT_LEAD},
    "deploy": {Role.RELEASE_MANAGER},
    "complete_handover": {Role.SUPPORT_LEAD, Role.RELEASE_MANAGER},
    # governance
    "create_amendment": {Role.DELIVERY_LEAD, Role.PRODUCT_ANALYST, Role.ENGINEERING_LEAD},
    "trigger_upstream_change": {Role.PRODUCT_ANALYST, Role.BUSINESS_OWNER},
    "run_self_correction": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    # run lifecycle — anyone driving the demo
    "manage_run": set(Role),
}


def allowed(action: str, role: Role) -> bool:
    roles = PERMISSIONS.get(action)
    return roles is not None and role in roles


def require(action: str, role: Role) -> None:
    if action not in PERMISSIONS:
        raise PermissionError_(f"Unknown action: {action}")
    if role not in PERMISSIONS[action]:
        permitted = ", ".join(sorted(r.value for r in PERMISSIONS[action]))
        raise PermissionError_(
            f"Role '{role.value}' may not perform '{action}' (permitted: {permitted})"
        )


def actions_for(role: Role) -> list[str]:
    return sorted(a for a, roles in PERMISSIONS.items() if role in roles)
