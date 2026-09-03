"""Role → permitted actions. Enforced in the engine, reflected in the UI.

The separation rules the spec names (spec §4) are the point, not the list:

- the development worker cannot approve its own output,
- the independent reviewer cannot modify development results,
- only the Business Owner signs the plan,
- only the Release Manager approves release.

`require` raises rather than returns so a missing check is loud.

`PERMISSIONS` and `ROLE_PROFILES` below are the committed *defaults*. Every
reader in this module consults the effective tables — defaults with the
operator's overrides from `s7_delivery/product/roles_config.py`
(`config/roles.json`) applied — on every call, so an admin change applies
to the next request with no restart. The overrides can never leave an
action with no holder; that module refuses it.
"""

from __future__ import annotations

from s7_delivery.factory.models import Role


class PermissionError_(Exception):
    """Named with a trailing underscore to avoid shadowing the builtin.

    Carries the structured facts alongside the message so a surface can
    offer the fix ("switch to Business Owner and retry") instead of only
    quoting the refusal. All three are ``None`` for an unknown action.
    """

    def __init__(self, message: str, *, action: str | None = None,
                 role: Role | None = None,
                 permitted: tuple[Role, ...] = ()) -> None:
        super().__init__(message)
        self.action = action
        self.role = role
        self.permitted = permitted


# Presenter-facing profile per role: the label the UI shows and one line on
# what the role owns. `signs` names the decisions only this role (or this
# role among a required set) records — the separation rules above, stated
# from the role's side so the picker can show them.
ROLE_PROFILES: dict[Role, dict[str, object]] = {
    Role.BUSINESS_OWNER: {
        "label": "Business Owner",
        "summary": "Owns the requirement: sources it, answers clarifications, "
                   "signs the intake gate and the plan, approves release.",
        "signs": ["G0 intake gate", "G1 plan sign-off", "release approval"],
    },
    Role.DELIVERY_LEAD: {
        "label": "Delivery Lead",
        "summary": "Runs the delivery: drives analysis, planning and the "
                   "downstream lane; owns dependency overrides.",
        "signs": ["dependency-gate override"],
    },
    Role.PRODUCT_ANALYST: {
        "label": "Product Analyst",
        "summary": "Shapes the epic: runs analysis, asks clarifications, "
                   "captures business rules, generates and edits the plan.",
        "signs": [],
    },
    Role.ENGINEERING_LEAD: {
        "label": "Engineering Lead",
        "summary": "Owns the technical blueprint: accepts architecture, "
                   "publishes delivery packs, assigns developers.",
        "signs": ["architecture acceptance", "release approval"],
    },
    Role.QA_LEAD: {
        "label": "QA Lead",
        "summary": "Owns test quality: approves and amends AC test plans, "
                   "decides the quality gate.",
        "signs": ["test-plan approval", "G3 quality gate", "release approval"],
    },
    Role.INDEPENDENT_REVIEWER: {
        "label": "Independent Reviewer",
        "summary": "Reviews development output it did not produce: executes "
                   "review, approves or returns to development.",
        "signs": ["G2 independent review"],
    },
    Role.RELEASE_MANAGER: {
        "label": "Release Manager",
        "summary": "Owns the release: requests approvals, holds the only "
                   "deploy permission, generates the release document.",
        "signs": ["G4 deploy decision", "release approval"],
    },
    Role.SUPPORT_LEAD: {
        "label": "Support Lead",
        "summary": "Receives the release: approves from the support side "
                   "and completes the handover.",
        "signs": ["release approval", "support handover"],
    },
}


def _effective_profiles() -> dict[Role, dict[str, object]]:
    """`ROLE_PROFILES` with the product layer's overrides applied. Imported
    lazily: `product.roles_config` imports this module's defaults."""
    from s7_delivery.product import roles_config

    return roles_config.effective_profiles()


def _effective_permissions() -> dict[str, set[Role]]:
    """`PERMISSIONS` with the product layer's overrides applied — read on
    every call so a saved override applies to the next request."""
    from s7_delivery.product import roles_config

    return roles_config.effective_permissions()


def profile(role: Role | str) -> dict[str, object]:
    """The effective presenter-facing profile of one role."""
    return dict(_effective_profiles()[Role(role)])


def profiles() -> dict[Role, dict[str, object]]:
    """Every role's effective profile, in the Role enum's declared order."""
    table = _effective_profiles()
    return {r: dict(table[r]) for r in Role}


def role_label(role: Role | str) -> str:
    try:
        return str(_effective_profiles()[Role(role)]["label"])
    except (KeyError, ValueError):
        return str(role).replace("_", " ").title()


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
    # The AI's clarification questions are directed at the business — the
    # Business Owner answers them (analysts may relay answers gathered
    # offline). Asking stays analyst work; answering is business input.
    "answer_clarification": {Role.BUSINESS_OWNER, Role.PRODUCT_ANALYST,
                             Role.DELIVERY_LEAD},
    # Business rules are business input, like clarification answers: the
    # Business Owner owns them, analysts may capture them. Human rules are
    # BR-H<n>; the AI's BR-<n> extractions stay immutable.
    "manage_business_rules": {Role.BUSINESS_OWNER, Role.PRODUCT_ANALYST,
                              Role.DELIVERY_LEAD},
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
    # The release/design document is a deterministic rendering of run state —
    # generated by the roles that own the release narrative.
    "generate_release_document": {Role.RELEASE_MANAGER, Role.DELIVERY_LEAD},
    "complete_handover": {Role.SUPPORT_LEAD, Role.RELEASE_MANAGER},
    # governance
    "create_amendment": {Role.DELIVERY_LEAD, Role.PRODUCT_ANALYST, Role.ENGINEERING_LEAD},
    "trigger_upstream_change": {Role.PRODUCT_ANALYST, Role.BUSINESS_OWNER},
    "run_self_correction": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
    # run lifecycle — anyone driving the demo
    "manage_run": set(Role),
}


def allowed(action: str, role: Role) -> bool:
    roles = _effective_permissions().get(action)
    return roles is not None and role in roles


def permitted_roles(action: str) -> tuple[Role, ...]:
    """Roles holding `action`, in the Role enum's declared order."""
    holders = _effective_permissions().get(action, set())
    return tuple(r for r in Role if r in holders)


def require(action: str, role: Role) -> None:
    table = _effective_permissions()
    if action not in table:
        raise PermissionError_(f"Unknown action: {action}", action=action, role=role)
    if role not in table[action]:
        permitted = tuple(r for r in Role if r in table[action])
        raise PermissionError_(
            f"Role '{role.value}' may not perform '{action}' "
            f"(permitted: {', '.join(r.value for r in permitted)})",
            action=action, role=role, permitted=permitted,
        )


def actions_for(role: Role) -> list[str]:
    return sorted(a for a, roles in _effective_permissions().items() if role in roles)
