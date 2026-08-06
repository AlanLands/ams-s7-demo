"""Structural tests for the SponsorConnect disability claim submission page.

The page is a single static file, so these tests read ``index.html`` as text and
assert that the markup and the inline script the acceptance criteria depend on
are actually present.  No browser, no server, no network.

Nothing here depends on the current date, time or environment: where the page
computes a value at runtime (the reference number, the submission timestamp) the
tests assert that the *generating code* exists, never the value it would produce
on any particular day.
"""

import re
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).parent / "index.html"


@pytest.fixture(scope="module")
def html():
    assert HTML_PATH.is_file(), "index.html not found next to the tests: %s" % HTML_PATH
    return HTML_PATH.read_text(encoding="utf-8")


def tag_with_id(markup, element, element_id):
    """Return the opening tag of ``element`` carrying ``element_id``, or None.

    Attribute quoting is accepted in either style so the assertions describe the
    page's structure rather than its formatting.
    """
    pattern = r"<%s\b[^>]*\bid=['\"]%s['\"][^>]*>" % (element, re.escape(element_id))
    match = re.search(pattern, markup)
    return match.group(0) if match else None


def has_id(markup, element_id):
    return re.search(r"\bid=['\"]%s['\"]" % re.escape(element_id), markup) is not None


def test_claim_form_and_member_identification_fields(html):
    """US-2-AC1: the guided journey starts from a form that identifies the member."""
    form = tag_with_id(html, "form", "claim-form")
    assert form is not None, "the submission form (id='claim-form') is missing"

    for field_id in ("policy-number", "member-id"):
        tag = tag_with_id(html, "input", field_id)
        assert tag is not None, "identification field '%s' is missing" % field_id
        assert "type='text'" in tag or 'type="text"' in tag, (
            "identification field '%s' should be a text input: %s" % (field_id, tag)
        )

    lookup = tag_with_id(html, "button", "lookup-btn")
    assert lookup is not None, "the 'Look up member' button (id='lookup-btn') is missing"
    assert has_id(html, "lookup-msg"), "no element to report the lookup result"

    # The submit handler refuses to proceed until a member has been identified.
    assert "if (!identified) { problems.push('look up the member'); }" in html


def test_member_lookup_prepopulates_and_attestation_gates_submission(html):
    """US-2-AC2: details are pre-populated, correctable, and attested before submit."""
    # Mock policy records the lookup resolves against.
    assert "'GRP-778120|MBR-40917'" in html, "first demo member record is missing"
    assert "'GRP-902355|MBR-11284'" in html, "second demo member record is missing"
    assert "Dana R. Whitfield" in html
    assert "Samuel O. Adeyemi" in html

    # Every pre-populated field exists and is written by the lookup handler.
    prepopulated = {
        "member-name": "found.name",
        "member-dob": "found.dob",
        "member-plan": "found.plan",
        "member-division": "found.division",
        "member-occupation": "found.occupation",
        "member-hire": "found.hire",
    }
    for field_id, source in prepopulated.items():
        tag = tag_with_id(html, "input", field_id)
        assert tag is not None, "pre-populated field '%s' is missing" % field_id
        assert "readonly" not in tag.lower(), (
            "'%s' must stay correctable by the sponsor: %s" % (field_id, tag)
        )
        assert "setValue('%s', %s)" % (field_id, source) in html, (
            "'%s' is never populated from the policy record" % field_id
        )

    assert has_id(html, "member-details"), "the member/plan details panel is missing"

    # The attestation covers the pre-populated *and* corrected details.
    attest = tag_with_id(html, "input", "attestation")
    assert attest is not None, "the attestation checkbox is missing"
    assert "type='checkbox'" in attest or 'type="checkbox"' in attest
    assert "pre-populated and corrected" in html, (
        "the attestation wording should name the pre-populated and corrected details"
    )
    assert "if (!document.getElementById('attestation').checked)" in html, (
        "submission is not gated on the attestation"
    )
    assert "problems.push('confirm the attestation')" in html


def test_absence_details_are_collected(html):
    """US-2-AC1: the structured employment and absence information intake needs."""
    for field_id in ("last-day-worked", "first-day-absent"):
        tag = tag_with_id(html, "input", field_id)
        assert tag is not None, "absence field '%s' is missing" % field_id
        assert "type='date'" in tag or 'type="date"' in tag, (
            "'%s' should be a date input: %s" % (field_id, tag)
        )

    nature = tag_with_id(html, "select", "nature-of-absence")
    assert nature is not None, "the nature-of-absence selector is missing"
    for option in (
        "Illness",
        "Injury",
        "Surgery or hospitalization",
        "Mental health",
        "Workplace injury",
    ):
        assert option in html, "nature-of-absence option '%s' is missing" % option

    assert tag_with_id(html, "textarea", "claim-details") is not None, (
        "the additional-details textarea is missing"
    )

    # Each of these is required before the packet is accepted.
    assert "problems.push('enter the last day worked')" in html
    assert "problems.push('enter the first day absent')" in html
    assert "problems.push('choose the nature of the absence')" in html


def test_multiple_documents_attach_as_one_packet(html):
    """US-2-AC3: several documents attach to, and stay with, a single submission."""
    documents = tag_with_id(html, "input", "documents")
    assert documents is not None, "the document upload input is missing"
    assert "type='file'" in documents or 'type="file"' in documents
    assert re.search(r"\bmultiple\b", documents), (
        "the upload input must allow multiple files: %s" % documents
    )

    # Attachments accumulate in one list across successive selections: the input
    # is cleared after each change so a second selection adds rather than replaces.
    assert "var attachments = [];" in html, "no single list holding the packet"
    assert "attachments.push(file)" in html
    assert "docsInput.value = '';" in html, (
        "the file input is not reset, so a second selection would replace the first"
    )

    assert has_id(html, "file-list"), "the attached-documents list is missing"
    assert has_id(html, "no-files"), "the empty-state message for documents is missing"
    assert "problems.push('attach at least one supporting document')" in html

    # The confirmation reports the packet as a whole.
    assert (
        "document.getElementById('conf-docs').textContent = names.length + ' file(s): '"
        in html
    ), "the confirmation does not list the documents in the packet"


def test_upload_outside_policy_is_rejected_with_no_partial_file(html):
    """US-2-AC4: type/size violations are rejected clearly and nothing is retained."""
    assert "var ALLOWED = ['pdf', 'jpg', 'jpeg', 'png', 'docx'];" in html, (
        "the accepted file-type policy is missing"
    )
    assert "var MAX_BYTES = 10 * 1024 * 1024;" in html, "the size limit is missing"

    documents = tag_with_id(html, "input", "documents")
    assert "accept=" in documents, "the upload input declares no accept policy"
    for extension in ("pdf", "jpg", "png", "docx"):
        assert extension in documents, (
            "accepted type '%s' missing from the input's accept list: %s"
            % (extension, documents)
        )

    # Both checks bail out before the file can reach the attachment list.
    assert "if (ALLOWED.indexOf(extensionOf(file.name)) === -1) {" in html
    assert "rejected.push(file.name + ' (file type not accepted)');" in html
    assert "if (file.size > MAX_BYTES) {" in html
    assert "over the 10 MB limit" in html

    # The message is explicit that no partial file was kept, and is shown as an error.
    assert "Nothing from a rejected file has been kept." in html
    assert "setMsg(uploadMsg, 'Not attached: '" in html
    assert has_id(html, "upload-msg"), "no element to show the rejection message"


def test_confirmation_panel_carries_a_generated_reference_and_status(html):
    """US-2-AC6: submitting returns an immediate confirmation with a quotable reference."""
    confirmation = tag_with_id(html, "section", "confirmation")
    assert confirmation is not None, "the confirmation panel is missing"
    assert re.search(r"\bhidden\b", confirmation), (
        "the confirmation panel should start hidden: %s" % confirmation
    )

    assert has_id(html, "reference-number"), "the reference number element is missing"

    status = tag_with_id(html, "span", "status")
    assert status is not None, "the status badge is missing"
    assert "Status: Received" in html, "the submission status is not displayed"

    for summary_id in (
        "conf-member",
        "conf-policy",
        "conf-absence",
        "conf-docs",
        "conf-submitted",
    ):
        assert has_id(html, summary_id), "confirmation summary row '%s' is missing" % summary_id

    # The reference is built at submit time from the run's own clock — assert the
    # generating expression, never a produced value.
    assert "var now = new Date();" in html
    assert "'MS-' + now.getFullYear() + '-' + month + '-' + sequence" in html, (
        "the reference number is not generated at submit time"
    )
    assert "document.getElementById('reference-number').textContent = reference;" in html
    assert "document.getElementById('conf-submitted').textContent = now.toLocaleString();" in html

    # The confirmation replaces the form immediately, in-page.
    assert "form.hidden = true;" in html
    assert "confirmation.hidden = false;" in html
