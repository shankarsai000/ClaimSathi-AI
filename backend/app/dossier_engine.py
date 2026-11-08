"""
Claim Documentation Engine & Insurer Integration Gateway for ClaimSathi AI (Phases 5, 6 & 7).
Implements:
1. 9-Section Professional Insurance Claim Dossier (Pages 5–6 of PDF)
2. Layer 1 — ClaimSathi Canonical Schema JSON (Pages 6–7 of PDF)
3. Real Multi-Section PDF Report Generator (Valid PDF 1.4 binary document)
4. Layer 2 — Insurer-Specific Adapters & Mock Insurer Integration Gateway (Pages 7, 10–11 of PDF)
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .models import (
    ClaimRecord,
    UserProfile,
    EvidenceAssetRecord,
    ProfessionalClaimDossier,
    DossierSection01Customer,
    DossierSection02Policy,
    DossierSection03Incident,
    DossierSection04Statement,
    DossierEvidenceItem,
    DossierSection05EvidenceInventory,
    DossierSection06ValidationReview,
    DossierSupportingDoc,
    DossierSection07SupportingDocuments,
    DossierSection08PreparationSummary,
    DossierSection09Declaration,
    CanonicalClaimSchema,
    DuplicateStatus,
)
from .database import (
    get_claim,
    get_user_profile,
    get_claim_evidence,
    get_claim_reports,
    save_generated_report,
    save_insurer_submission,
    get_claim_insurer_submissions,
    add_timeline_event,
    log_audit_event,
    build_detailed_incident_statement,
)

REPORT_STORAGE_ROOT = Path("storage/reports")


def _pdf_escape(text: str) -> str:
    """Escape characters for PDF literal strings and normalize non-ASCII characters."""
    safe_ascii = (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("·", "-")
        .replace("•", "*")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .encode("ascii", errors="replace")
        .decode("ascii")
    )
    return safe_ascii.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_text(text: str, width: int = 88) -> List[str]:
    """Word-wrap text into lines of at most `width` characters."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for w in words[1:]:
        if len(current) + 1 + len(w) <= width:
            current += " " + w
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def render_dossier_pdf_bytes(dossier: ProfessionalClaimDossier) -> bytes:
    """
    Generate a real, standards-compliant multi-page PDF 1.4 document containing all 9 sections
    of the Professional Insurance Claim Dossier.
    """
    lines_with_style: List[tuple[str, str]] = []  # (style: 'title'|'h2'|'body'|'muted', text)

    lines_with_style.append(("title", "CLAIMSATHI AI - PROFESSIONAL INSURANCE CLAIM DOSSIER"))
    lines_with_style.append(("muted", f"Claim ID: {dossier.claim_id}   |   Report ID: {dossier.report_id}   |   Version: {dossier.report_version}"))
    lines_with_style.append(("muted", f"Category: {dossier.insurance_category}   |   Status: {dossier.status_badge}"))
    lines_with_style.append(("body", "-" * 92))

    # SECTION 01
    s1 = dossier.section_01_customer
    lines_with_style.append(("h2", "SECTION 01 - Customer Information"))
    lines_with_style.append(("body", f"Customer Name: {s1.name}   |   Unique Customer ID: {s1.customer_id}"))
    lines_with_style.append(("body", f"Contact: {s1.email} / {s1.phone}   |   Declared Insurer: {s1.declared_insurer}"))
    lines_with_style.append(("body", ""))

    # SECTION 02
    s2 = dossier.section_02_policy
    lines_with_style.append(("h2", "SECTION 02 - Policy Information"))
    lines_with_style.append(("body", f"Policy Number: {s2.policy_number}   |   Insurer: {s2.insurer_name}"))
    lines_with_style.append(("body", f"Policy Type: {s2.policy_type}   |   Status: {s2.verification_status}"))
    lines_with_style.append(("body", ""))

    # SECTION 03
    s3 = dossier.section_03_incident
    lines_with_style.append(("h2", "SECTION 03 - Incident Information"))
    lines_with_style.append(("body", f"Date & Time: {s3.incident_date_time}   |   Location: {s3.incident_location}"))
    lines_with_style.append(("body", f"Vehicle Details: {s3.vehicle_details}   |   People Involved: {s3.people_involved}"))
    for wline in _wrap_text(f"Reported Damage / Injuries: {s3.injuries_or_damage}", 88):
        lines_with_style.append(("body", wline))
    lines_with_style.append(("body", ""))

    # SECTION 04
    s4 = dossier.section_04_statement
    lines_with_style.append(("h2", "SECTION 04 - Detailed Incident Statement"))
    for wline in _wrap_text(s4.chronological_account, 88):
        lines_with_style.append(("body", wline))
    lines_with_style.append(("body", ""))

    # SECTION 05
    s5 = dossier.section_05_evidence_inventory
    lines_with_style.append(("h2", "SECTION 05 - Evidence Inventory & Screening Outcome"))
    if not s5.items:
        lines_with_style.append(("body", "No media evidence uploaded for this claim."))
    else:
        for item in s5.items:
            review_tag = " [HUMAN REVIEW]" if item.requires_human_review else ""
            lines_with_style.append(
                ("body", f"* {item.item_label} ({item.evidence_id}) [{item.capture_method}]: {item.screening_outcome}{review_tag}")
            )
    lines_with_style.append(("muted", f"Note: {s5.disclaimer}"))
    lines_with_style.append(("body", ""))

    # SECTION 06
    s6 = dossier.section_06_validation_review
    lines_with_style.append(("h2", "SECTION 06 - Validation & Review"))
    lines_with_style.append(("body", f"Missing Information: {', '.join(s6.missing_information) if s6.missing_information else 'None (All required fields captured)'}"))
    lines_with_style.append(("body", f"Inconsistencies: {', '.join(s6.inconsistent_answers) if s6.inconsistent_answers else 'None detected'}"))
    if s6.evidence_warnings:
        for warn in s6.evidence_warnings:
            for wline in _wrap_text(f"Warning: {warn}", 88):
                lines_with_style.append(("body", wline))
    else:
        lines_with_style.append(("body", "Evidence Warnings: None"))
    lines_with_style.append(("body", ""))

    # SECTION 07
    s7 = dossier.section_07_supporting_documents
    lines_with_style.append(("h2", "SECTION 07 - Supporting Documents & Cryptographic Fingerprints"))
    if not s7.documents:
        lines_with_style.append(("body", "No supporting file attachments recorded."))
    else:
        for doc in s7.documents:
            lines_with_style.append(
                ("body", f"* {doc.evidence_id} | {doc.filename} ({doc.file_size_bytes} bytes) | Session: {doc.capture_session_id or 'Standard Upload'}")
            )
            lines_with_style.append(
                ("muted", f"  SHA-256: {doc.sha256_hash[:48]}... | pHash: {doc.perceptual_hash or 'N/A'}")
            )
    lines_with_style.append(("body", ""))

    # SECTION 08
    s8 = dossier.section_08_preparation_summary
    lines_with_style.append(("h2", "SECTION 08 - Claim Preparation Summary"))
    for wline in _wrap_text(s8.incident_summary, 88):
        lines_with_style.append(("body", wline))
    lines_with_style.append(("body", f"Evidence Summary: {s8.available_evidence_summary}"))
    lines_with_style.append(("body", f"Next Steps: {'; '.join(s8.recommended_next_steps)}"))
    lines_with_style.append(("body", ""))

    # SECTION 09
    s9 = dossier.section_09_declaration
    lines_with_style.append(("h2", "SECTION 09 - Declaration & Confirmation"))
    lines_with_style.append(("body", f"Confirmed By: {s9.confirmed_by_name} ({s9.confirmed_by_id})   |   Confirmed: {s9.customer_confirmed}"))
    lines_with_style.append(("body", f"Generated At: {s9.report_generation_timestamp}   |   Report ID: {s9.report_id} (v{s9.report_version})"))
    for wline in _wrap_text(s9.regulatory_disclaimer, 88):
        lines_with_style.append(("muted", wline))

    # Paginate into chunks of 42 lines per page
    lines_per_page = 42
    pages_lines = [
        lines_with_style[i : i + lines_per_page]
        for i in range(0, len(lines_with_style), lines_per_page)
    ] or [[("title", "CLAIMSATHI AI REPORT")]]

    # Build PDF objects
    # Object 1: Catalog, Object 2: Pages, Object 3: Font Regular, Object 4: Font Bold
    # Then for each page: Page object + Content stream object
    objects: List[bytes] = []
    page_obj_ids: List[int] = []
    next_obj_id = 5

    page_streams: List[tuple[int, int, bytes]] = []
    for p_lines in pages_lines:
        p_id = next_obj_id
        c_id = next_obj_id + 1
        next_obj_id += 2
        page_obj_ids.append(p_id)

        stream_cmds = ["BT", "42 755 Td"]
        for style, txt in p_lines:
            esc = _pdf_escape(txt)
            if style == "title":
                stream_cmds.append("/F2 13 Tf")
                stream_cmds.append(f"({esc}) Tj")
                stream_cmds.append("0 -18 Td")
            elif style == "h2":
                stream_cmds.append("/F2 10.5 Tf")
                stream_cmds.append(f"({esc}) Tj")
                stream_cmds.append("0 -15 Td")
            elif style == "muted":
                stream_cmds.append("/F1 8.5 Tf")
                stream_cmds.append(f"({esc}) Tj")
                stream_cmds.append("0 -13 Td")
            else:
                stream_cmds.append("/F1 9.5 Tf")
                stream_cmds.append(f"({esc}) Tj")
                stream_cmds.append("0 -14 Td")
        stream_cmds.append("ET")
        stream_bytes = "\n".join(stream_cmds).encode("ascii")
        page_streams.append((p_id, c_id, stream_bytes))

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    for p_id, c_id, s_bytes in page_streams:
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {c_id} 0 R >>"
        ).encode("ascii")
        content_dict = (
            f"<< /Length {len(s_bytes)} >>\nstream\n".encode("ascii")
            + s_bytes
            + b"\nendstream"
        )
        objects.append(page_dict)
        objects.append(content_dict)

    # Assemble PDF with xref table
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = [0]
    for idx, obj_body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj_body)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


async def generate_claim_dossier_and_report(claim_id: str, requesting_user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Build the 9-Section Professional Insurance Claim Dossier, Layer 1 Canonical Schema JSON,
    and binary PDF report for a claim, incrementing report version (1.0, 1.1, etc.).
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise ValueError(f"Claim {claim_id} not found")

    user_id = claim.customer_id or requesting_user_id or "USR-100001"
    user = await get_user_profile(user_id)
    if not user:
        user = await get_user_profile("USR-100001")

    evidence_list = await get_claim_evidence(claim_id, requesting_user_id=user_id)
    existing_reports = await get_claim_reports(claim_id)
    version_num = len(existing_reports)
    version_str = f"1.{version_num}"
    report_id = f"RPT-{claim_id.replace('CS-', '').replace('DEMO-', '')}-V{version_num + 1}"
    now_iso = datetime.utcnow().isoformat()

    # Check missing fields & evidence warnings
    missing_fields: List[str] = []
    for attr, label in [
        ("policy_reference", "Policy Reference"),
        ("incident_location", "Incident Location"),
        ("incident_date", "Incident Date"),
        ("vehicle_type", "Vehicle Type"),
        ("damage_description", "Damage Description"),
    ]:
        val = getattr(claim, attr, None)
        if not val or not str(val).strip():
            missing_fields.append(label)

    evidence_warnings: List[str] = []
    human_review_needed = False
    dossier_ev_items: List[DossierEvidenceItem] = []
    supporting_docs: List[DossierSupportingDoc] = []

    for ev in evidence_list:
        sc = ev.screening
        if sc.requires_human_review:
            human_review_needed = True
        if sc.duplicate_status == DuplicateStatus.EXACT_DUPLICATE:
            evidence_warnings.append(
                f"{ev.label} ({ev.evidence_id}): Exact SHA-256 duplicate detected ({sc.matched_claim_reference or 'prior record'})."
            )
        elif sc.duplicate_status == DuplicateStatus.VISUAL_DUPLICATE:
            evidence_warnings.append(
                f"{ev.label} ({ev.evidence_id}): Visual similarity / possible reuse detected via pHash (Hamming distance={sc.hamming_distance}, {sc.matched_claim_reference or 'prior record'})."
            )
        if sc.c2pa_found or sc.synthid_found or "warning" in sc.provenance_system_response.lower():
            evidence_warnings.append(
                f"{ev.label} ({ev.evidence_id}): Provenance check reported '{sc.provenance_system_response}' ({sc.provenance_result})."
            )

        dossier_ev_items.append(
            DossierEvidenceItem(
                item_label=ev.label,
                evidence_id=ev.evidence_id,
                media_type=ev.media_type,
                capture_method=ev.capture_method,
                screening_outcome=sc.screening_outcome_label,
                provenance_response=sc.provenance_system_response,
                duplicate_status=sc.duplicate_status.value,
                requires_human_review=sc.requires_human_review,
            )
        )
        supporting_docs.append(
            DossierSupportingDoc(
                evidence_id=ev.evidence_id,
                filename=ev.original_filename,
                media_type=ev.media_type,
                file_size_bytes=ev.file_size_bytes,
                sha256_hash=sc.sha256_hash,
                perceptual_hash=sc.perceptual_hash,
                capture_session_id=ev.capture_session_id,
                upload_timestamp=ev.upload_timestamp.isoformat(),
            )
        )

    detailed_stmt = claim.detailed_statement or build_detailed_incident_statement(
        incident_date=claim.incident_date,
        incident_location=claim.incident_location,
        vehicle_type=claim.vehicle_type,
        policy_reference=claim.policy_reference,
        damage_description=claim.damage_description,
        people_involved=claim.people_involved,
        injuries_reported=claim.injuries_reported,
    )

    img_count = sum(1 for e in evidence_list if e.media_type == "image")
    vid_count = sum(1 for e in evidence_list if e.media_type == "video")

    outstanding_reqs: List[str] = []
    if not evidence_list:
        outstanding_reqs.append("Upload vehicle damage photographs or capture guided live video evidence.")
    if human_review_needed:
        outstanding_reqs.append("Flagged evidence items require insurer surveyor / human review.")

    next_steps = [
        "Download the official ClaimSathi PDF Dossier and Canonical JSON for your records.",
        "Submit the confirmed dossier through the Authorized Insurer Integration Gateway.",
        "Keep original vehicle parts and repair estimates available for surveyor inspection.",
    ]

    dossier = ProfessionalClaimDossier(
        claim_id=claim.id,
        report_id=report_id,
        report_version=version_str,
        insurance_category="Motor Insurance",
        status_badge="Customer confirmed" if claim.customer_confirmation else "Draft review",
        section_01_customer=DossierSection01Customer(
            customer_id=user.customer_id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            declared_insurer=claim.insurer_name or user.declared_insurer,
        ),
        section_02_policy=DossierSection02Policy(
            policy_number=claim.policy_reference,
            insurer_name=claim.insurer_name,
            policy_type=claim.policy_type,
            insurance_category="Motor Insurance",
            verification_status="Unverified (Customer-entered value — subject to insurer policy check)",
        ),
        section_03_incident=DossierSection03Incident(
            incident_date_time=claim.incident_date,
            incident_location=claim.incident_location,
            incident_description=f"Motor vehicle incident involving {claim.vehicle_type} at {claim.incident_location}",
            vehicle_details=claim.vehicle_type,
            people_involved=claim.people_involved,
            injuries_or_damage=f"Damage: {claim.damage_description} | Injuries: {claim.injuries_reported}",
        ),
        section_04_statement=DossierSection04Statement(
            chronological_account=detailed_stmt,
            source_language="Multilingual Voice/Text Intake (Gnani Prisma STT)",
            customer_confirmed=claim.customer_confirmation,
        ),
        section_05_evidence_inventory=DossierSection05EvidenceInventory(
            items=dossier_ev_items,
            disclaimer="Illustrative screening results, not actual verification.",
        ),
        section_06_validation_review=DossierSection06ValidationReview(
            missing_information=missing_fields,
            inconsistent_answers=[],
            evidence_warnings=evidence_warnings,
            unresolved_fields=missing_fields,
            human_review_recommended=human_review_needed,
        ),
        section_07_supporting_documents=DossierSection07SupportingDocuments(
            documents=supporting_docs,
        ),
        section_08_preparation_summary=DossierSection08PreparationSummary(
            incident_summary=(
                f"Motor claim dossier {claim.id} prepared for Policy {claim.policy_reference} "
                f"({claim.vehicle_type}) regarding incident on {claim.incident_date} at {claim.incident_location}."
            ),
            available_evidence_summary=f"{img_count} photograph(s) and {vid_count} video(s) screened and indexed.",
            outstanding_requirements=outstanding_reqs,
            recommended_next_steps=next_steps,
        ),
        section_09_declaration=DossierSection09Declaration(
            customer_confirmed=claim.customer_confirmation,
            confirmed_by_name=user.name,
            confirmed_by_id=user.customer_id,
            report_generation_timestamp=now_iso,
            report_id=report_id,
            report_version=version_str,
        ),
    )

    # Build Layer 1 — ClaimSathi Canonical Schema (Pages 6–7 of PDF)
    canonical = CanonicalClaimSchema(
        claim_id=claim.id,
        customer_id=user.customer_id,
        insurance_type="motor",
        policy={
            "policy_number": claim.policy_reference,
            "insurer_name": claim.insurer_name,
            "policy_type": claim.policy_type,
            "verified": False,
        },
        incident={
            "date": claim.incident_date,
            "location": claim.incident_location,
            "vehicle_type": claim.vehicle_type,
            "damage_description": claim.damage_description,
            "description": f"Customer-reported {claim.vehicle_type} accident: {claim.damage_description}",
            "detailed_statement": detailed_stmt,
        },
        evidence={
            "images": [
                {
                    "evidence_id": e.evidence_id,
                    "label": e.label,
                    "filename": e.original_filename,
                    "capture_method": e.capture_method,
                    "capture_session_id": e.capture_session_id,
                }
                for e in evidence_list
                if e.media_type == "image"
            ],
            "videos": [
                {
                    "evidence_id": e.evidence_id,
                    "label": e.label,
                    "filename": e.original_filename,
                    "capture_method": e.capture_method,
                    "capture_session_id": e.capture_session_id,
                }
                for e in evidence_list
                if e.media_type == "video"
            ],
            "integrity_checks": [
                {
                    "evidence_id": e.evidence_id,
                    "label": e.label,
                    "sha256_hash": e.screening.sha256_hash,
                    "perceptual_hash": e.screening.perceptual_hash,
                    "provenance_result": e.screening.provenance_result,
                    "provenance_system_response": e.screening.provenance_system_response,
                    "duplicate_status": e.screening.duplicate_status.value,
                    "requires_human_review": e.screening.requires_human_review,
                    "outcome": e.screening.screening_outcome_label,
                }
                for e in evidence_list
            ],
        },
        validation={
            "missing_fields": missing_fields,
            "inconsistencies": [],
            "evidence_warnings": evidence_warnings,
            "human_review_recommended": human_review_needed,
        },
        customer_confirmation=claim.customer_confirmation,
        report_status="generated",
        insurer_submission_status=claim.insurer_submission_status or "not_submitted",
    )

    # Render binary PDF report and save to disk
    REPORT_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    pdf_bytes = render_dossier_pdf_bytes(dossier)
    pdf_path = REPORT_STORAGE_ROOT / f"{report_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    saved = await save_generated_report(
        report_id=report_id,
        claim_id=claim.id,
        user_id=user.customer_id,
        version=version_str,
        dossier_dict=dossier.model_dump(),
        canonical_dict=canonical.model_dump(),
        pdf_storage_path=str(pdf_path),
    )

    await add_timeline_event(
        claim_id=claim.id,
        title=f"Professional Claim Dossier Generated (v{version_str})",
        description=f"9-Section Claim Dossier {report_id} generated with PDF and Canonical JSON export.",
        status="report_generated",
    )
    await log_audit_event(
        user_id=user.customer_id,
        claim_id=claim.id,
        action="DOSSIER_REPORT_GENERATED",
        details=f"Generated Dossier {report_id} (v{version_str}) with {len(evidence_list)} screened evidence items.",
    )

    return {
        **saved,
        "pdf_download_url": f"/api/claims/{claim.id}/report/pdf?version={version_str}",
        "json_download_url": f"/api/claims/{claim.id}/report/json?version={version_str}",
    }


# ── Layer 2: Insurer-Specific Adapters & Mock Insurer Gateway ──────────
INSURER_ADAPTER_CATALOG = {
    "DEMO_INSURER_A": {
        "display_name": "Demo Insurer A — Bharat General Insurance (REST API v2)",
        "channel": "Official insurer API",
        "prefix": "DEMO-INS",
    },
    "DEMO_INSURER_B": {
        "display_name": "Demo Insurer B — Suraksha Motor Assurance (Partner API)",
        "channel": "Official insurer API",
        "prefix": "SRK-FNOL",
    },
    "DEMO_INSURER_C": {
        "display_name": "Demo Insurer C — National Motor Partner Portal",
        "channel": "Secure partner portal",
        "prefix": "NMP-CASE",
    },
}


def map_canonical_to_insurer_payload(canonical: Dict[str, Any], recipient: str) -> Dict[str, Any]:
    """
    Layer 2 — Insurer-Specific Adapter Layer (Page 7 of PDF).
    Transforms ClaimSathi Canonical Schema into partner-specific field mappings without
    hardcoding a single insurer format in the core database.
    """
    if recipient == "DEMO_INSURER_B":
        return {
            "schema_standard": "SURAKSHA_FNOL_MOTOR_V1",
            "external_case_ref": canonical["claim_id"],
            "policy_holder_ref": canonical["customer_id"],
            "policy_id": canonical["policy"]["policy_number"],
            "loss_event": {
                "loss_date": canonical["incident"]["date"],
                "loss_city": canonical["incident"]["location"],
                "vehicle_category": canonical["incident"]["vehicle_type"],
                "damage_narrative": canonical["incident"]["damage_description"],
                "chronological_statement": canonical["incident"]["detailed_statement"],
            },
            "screened_attachments_count": len(canonical["evidence"]["images"]) + len(canonical["evidence"]["videos"]),
            "human_review_flag": canonical["validation"]["human_review_recommended"],
        }
    elif recipient == "DEMO_INSURER_C":
        return {
            "portal_envelope": "PARTNER_PORTAL_PACKAGE",
            "dossier_reference": canonical["claim_id"],
            "insured_policy_no": canonical["policy"]["policy_number"],
            "incident_summary": canonical["incident"]["description"],
            "evidence_hashes": [
                chk["sha256_hash"] for chk in canonical["evidence"]["integrity_checks"]
            ],
            "customer_declaration_signed": canonical["customer_confirmation"],
        }
    else:
        # Default: DEMO_INSURER_A
        return {
            "adapter": "DEMO_INSURER_A_MOTOR_API",
            "claim_dossier_id": canonical["claim_id"],
            "customer_id": canonical["customer_id"],
            "insurance_line": canonical["insurance_type"].upper(),
            "policy_reference": canonical["policy"]["policy_number"],
            "incident_details": canonical["incident"],
            "evidence_manifest": canonical["evidence"]["integrity_checks"],
            "validation_summary": canonical["validation"],
            "customer_confirmed": canonical["customer_confirmation"],
        }


async def submit_to_mock_insurer_gateway(
    claim_id: str,
    recipient: str = "DEMO_INSURER_A",
    requesting_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulate the future insurer submission workflow (Pages 10–11 of PDF):
    ClaimSathi Report Generated -> Mock Insurer API -> Payload Received ->
    Mock Insurer Acknowledgement -> Demo Claim Reference Generated -> Mock Processing Status (received)
    """
    reports = await get_claim_reports(claim_id)
    if not reports:
        # Auto-generate report v1.0 if not yet generated
        latest_report = await generate_claim_dossier_and_report(claim_id, requesting_user_id=requesting_user_id)
    else:
        latest_report = reports[0]

    canonical_dict = latest_report["canonical_schema"]
    adapter_meta = INSURER_ADAPTER_CATALOG.get(recipient, INSURER_ADAPTER_CATALOG["DEMO_INSURER_A"])
    mapped_payload = map_canonical_to_insurer_payload(canonical_dict, recipient)

    existing_subs = await get_claim_insurer_submissions(claim_id)
    sub_idx = len(existing_subs) + 1
    submission_id = f"DEMO-SUB-{1000 + sub_idx}"
    insurer_ref = f"{adapter_meta['prefix']}-{sub_idx:03d}"
    now_iso = datetime.utcnow().isoformat()

    pipeline_steps = [
        {
            "step": "1. ClaimSathi Report Generated",
            "status": "completed",
            "detail": f"Dossier {latest_report['report_id']} (v{latest_report['version']}) packaged with Canonical Schema.",
            "timestamp": now_iso,
        },
        {
            "step": "2. Insurer Adapter Layer Mapping",
            "status": "completed",
            "detail": f"Canonical schema mapped to {adapter_meta['display_name']} format.",
            "timestamp": now_iso,
        },
        {
            "step": "3. Mock Insurer API — Payload Received",
            "status": "completed",
            "detail": f"Authenticated transmission via {adapter_meta['channel']} succeeded.",
            "timestamp": now_iso,
        },
        {
            "step": "4. Mock Insurer Acknowledgement",
            "status": "completed",
            "detail": f"Submission ID {submission_id} acknowledged by {recipient}.",
            "timestamp": now_iso,
        },
        {
            "step": "5. Demo Claim Reference & Processing Status",
            "status": "received",
            "detail": f"Generated insurer reference {insurer_ref} with status 'received' (Demo only).",
            "timestamp": now_iso,
        },
    ]

    saved_sub = await save_insurer_submission(
        submission_id=submission_id,
        claim_id=claim_id,
        recipient=recipient,
        recipient_display_name=adapter_meta["display_name"],
        adapter_payload=mapped_payload,
        delivery_status="simulated_success",
        insurer_claim_reference=insurer_ref,
        processing_status="received",
        pipeline_steps=pipeline_steps,
    )

    await add_timeline_event(
        claim_id=claim_id,
        title=f"Mock Insurer Gateway Submission ({submission_id})",
        description=(
            f"Simulated submission to {recipient} succeeded. "
            f"Insurer Claim Ref: {insurer_ref} | Status: received [DEMO ONLY]."
        ),
        status="submitted",
    )
    await log_audit_event(
        user_id=requesting_user_id or "USR-100001",
        claim_id=claim_id,
        action="MOCK_INSURER_SUBMISSION",
        details=f"Simulated submission {submission_id} to {recipient} -> ref {insurer_ref}.",
    )

    return saved_sub


DOSSIER_I18N: Dict[str, Dict[str, str]] = {
    "en": {
        "lang_name": "English (Insurer Standard)",
        "doc_title": "CLAIMSATHI AI — PROFESSIONAL INSURANCE CLAIM DOSSIER",
        "print_btn": "Print / Save as PDF",
        "s1": "SECTION 01 — Customer Identification & Profile",
        "s2": "SECTION 02 — Policy & Coverage Details",
        "s3": "SECTION 03 — Incident Details & Summary",
        "s4": "SECTION 04 — Detailed Chronological Incident Statement",
        "s5": "SECTION 05 — Evidence Inventory & Screening Summary",
        "s6": "SECTION 06 — Validation & Completeness Review",
        "s7": "SECTION 07 — Supporting Documents & Cryptographic Hashes",
        "s8": "SECTION 08 — Claim Preparation Summary & Next Steps",
        "s9": "SECTION 09 — Customer Confirmation & Regulatory Declaration",
        "name": "Customer Name",
        "cid": "Customer ID",
        "email": "Email / Phone",
        "insurer": "Insurer",
        "pol_no": "Policy / Vehicle Number",
        "pol_type": "Policy Type",
        "date_loc": "Incident Date & Location",
        "veh": "Vehicle Type",
        "damage": "Reported Damage (English for Insurer)",
        "confirmed": "Customer Confirmed",
    },
    "kn": {
        "lang_name": "ಕನ್ನಡ (Kannada)",
        "doc_title": "ಕ್ಲೈಮ್‌ಸಾಥಿ AI — ಅಧಿಕೃತ ವಿಮಾ ಕ್ಲೈಮ್ ವರದಿ (CLAIM DOSSIER)",
        "print_btn": "ಮುದ್ರಿಸಿ / PDF ಆಗಿ ಉಳಿಸಿ (Print / Save PDF)",
        "s1": "ವಿಭಾಗ 01 — ಗ್ರಾಹಕರ ವಿವರಗಳು (Customer Information)",
        "s2": "ವಿಭಾಗ 02 — ಪಾಲಿಸಿ ಮತ್ತು ವಾಹನದ ವಿವರಗಳು (Policy & Vehicle Details)",
        "s3": "ವಿಭಾಗ 03 — ಅಪಘಾತದ ವಿವರಗಳು (Incident Details)",
        "s4": "ವಿಭಾಗ 04 — ಸಂಪೂರ್ಣ ಘಟನೆಯ ಹೇಳಿಕೆ (Detailed Incident Statement)",
        "s5": "ವಿಭಾಗ 05 — ಸಾಕ್ಷ್ಯಾಧಾರಗಳ ಪರಿಶೀಲನೆ (Evidence Inventory & Screening)",
        "s6": "ವಿಭಾಗ 06 — ಪರಿಶೀಲನೆ ಮತ್ತು ಸಮಗ್ರತೆಯ ವರದಿ (Validation & Review)",
        "s7": "ವಿಭಾಗ 07 — ದಾಖಲೆಗಳು ಮತ್ತು ಕ್ರಿಪ್ಟೋಗ್ರಾಫಿಕ್ ಹ್ಯಾಶ್ (Supporting Documents)",
        "s8": "ವಿಭಾಗ 08 — ಕ್ಲೈಮ್ ಸಿದ್ಧತಾ ಸಾರಾಂಶ (Claim Preparation Summary)",
        "s9": "ವಿಭಾಗ 09 — ಗ್ರಾಹಕರ ದೃಢೀಕರಣ ಮತ್ತು ಘೋಷಣೆ (Customer Declaration)",
        "name": "ಗ್ರಾಹಕರ ಹೆಸರು (Name)",
        "cid": "ಗ್ರಾಹಕ ಐಡಿ (Customer ID)",
        "email": "ಇಮೇಲ್ / ಫೋನ್ (Contact)",
        "insurer": "ವಿಮಾ ಕಂಪನಿ (Insurer)",
        "pol_no": "ಪಾಲಿಸಿ / ವಾಹನ ಸಂಖ್ಯೆ (Policy / Vehicle No)",
        "pol_type": "ಪಾಲಿಸಿ ಪ್ರಕಾರ (Policy Type)",
        "date_loc": "ದಿನಾಂಕ ಮತ್ತು ಸ್ಥಳ (Date & Location)",
        "veh": "ವಾಹನದ ಪ್ರಕಾರ (Vehicle Type)",
        "damage": "ವರದಿಯಾದ ಹಾನಿ (Damage in English for Insurer)",
        "confirmed": "ಗ್ರಾಹಕರಿಂದ ದೃಢೀಕರಿಸಲ್ಪಟ್ಟಿದೆ (Confirmed)",
    },
    "te": {
        "lang_name": "తెలుగు (Telugu)",
        "doc_title": "క్లెయిమ్‌సాథీ AI — అధికారిక ఇన్సూరెన్స్ క్లెయిమ్ నివేదిక (CLAIM DOSSIER)",
        "print_btn": "ప్రింట్ / PDF గా సేవ్ చేయండి (Print / Save PDF)",
        "s1": "విభాగం 01 — కస్టమర్ వివరాలు (Customer Information)",
        "s2": "విభాగం 02 — పాలసీ & వాహన వివరాలు (Policy & Vehicle Details)",
        "s3": "విభాగం 03 — ప్రమాద వివరాలు (Incident Details)",
        "s4": "విభాగం 04 — పూర్తి సంఘటన వివరణ (Detailed Incident Statement)",
        "s5": "విభాగం 05 — సాక్ష్యాల పరిశీలన జాబితా (Evidence Inventory & Screening)",
        "s6": "విభాగం 06 — ధృవీకరణ & సమీక్ష (Validation & Review)",
        "s7": "విభాగం 07 — అనుబంధ పత్రాలు & క్రిప్టోగ్రాఫిక్ హ్యాష్ (Supporting Documents)",
        "s8": "విభాగం 08 — క్లెయిమ్ సారాంశం & తదుపరి చర్యలు (Preparation Summary)",
        "s9": "విభాగం 09 — కస్టమర్ నిర్ధారణ & డిక్లరేషన్ (Customer Declaration)",
        "name": "కస్టమర్ పేరు (Name)",
        "cid": "కస్టమర్ ఐడి (Customer ID)",
        "email": "ఇమెయిల్ / ఫోన్ (Contact)",
        "insurer": "ఇన్సూరెన్స్ కంపెనీ (Insurer)",
        "pol_no": "పాలసీ / వాహన నంబర్ (Policy / Vehicle No)",
        "pol_type": "పాలసీ రకం (Policy Type)",
        "date_loc": "తేదీ మరియు ప్రదేశం (Date & Location)",
        "veh": "వాహనం రకం (Vehicle Type)",
        "damage": "వాహన డ్యామేజ్ వివరాలు (Damage in English for Insurer)",
        "confirmed": "కస్టమర్ నిర్ధారించారు (Confirmed)",
    },
    "hi": {
        "lang_name": "हिन्दी (Hindi)",
        "doc_title": "क्लेमसाथी AI — आधिकारिक बीमा क्लेम रिपोर्ट (CLAIM DOSSIER)",
        "print_btn": "प्रिंट करें / PDF के रूप में सहेजें (Print / Save PDF)",
        "s1": "अनुभाग 01 — ग्राहक पहचान और प्रोफ़ाइल (Customer Information)",
        "s2": "अनुभाग 02 — पॉलिसी और वाहन विवरण (Policy & Vehicle Details)",
        "s3": "अनुभाग 03 — दुर्घटना का विवरण (Incident Details)",
        "s4": "अनुभाग 04 — विस्तृत घटना विवरण (Detailed Incident Statement)",
        "s5": "अनुभाग 05 — साक्ष्य सूची और जांच सारांश (Evidence Screening)",
        "s6": "अनुभाग 06 — सत्यापन और समीक्षा (Validation & Review)",
        "s7": "अनुभाग 07 — सहायक दस्तावेज़ और क्रिप्टोग्राफ़िक हैश (Supporting Documents)",
        "s8": "अनुभाग 08 — क्लेम तैयारी सारांश (Claim Preparation Summary)",
        "s9": "अनुभाग 09 — ग्राहक पुष्टि और घोषणा (Customer Declaration)",
        "name": "ग्राहक का नाम (Name)",
        "cid": "ग्राहक आईडी (Customer ID)",
        "email": "ईमेल / फ़ोन (Contact)",
        "insurer": "बीमा कंपनी (Insurer)",
        "pol_no": "पॉलिसी / वाहन नंबर (Policy / Vehicle No)",
        "pol_type": "पॉलिसी प्रकार (Policy Type)",
        "date_loc": "तारीख और स्थान (Date & Location)",
        "veh": "वाहन का प्रकार (Vehicle Type)",
        "damage": "क्षति का विवरण (Damage in English for Insurer)",
        "confirmed": "ग्राहक द्वारा सत्यापित (Confirmed)",
    },
    "ta": {
        "lang_name": "தமிழ் (Tamil)",
        "doc_title": "கிளைம்சாத்தி AI — அதிகாரப்பூர்வ காப்பீட்டு கோரிக்கை அறிக்கை (CLAIM DOSSIER)",
        "print_btn": "அச்சிடு / PDF ஆக சேமி (Print / Save PDF)",
        "s1": "பிரிவு 01 — வாடிக்கையாளர் விவரங்கள் (Customer Information)",
        "s2": "பிரிவு 02 — பாலிசி & வாகன விவரங்கள் (Policy & Vehicle Details)",
        "s3": "பிரிவு 03 — விபத்து விவரங்கள் (Incident Details)",
        "s4": "பிரிவு 04 — விரிவான சம்பவ அறிக்கை (Detailed Incident Statement)",
        "s5": "பிரிவு 05 — ஆதாரங்கள் மற்றும் சரிபார்ப்பு (Evidence Screening)",
        "s6": "பிரிவு 06 — சரிபார்ப்பு மற்றும் ஆய்வு (Validation & Review)",
        "s7": "பிரிவு 07 — துணை ஆவணங்கள் (Supporting Documents)",
        "s8": "பிரிவு 08 — கோரிக்கை சுருக்கம் (Claim Preparation Summary)",
        "s9": "பிரிவு 09 — வாடிக்கையாளர் உறுதிமொழி (Customer Declaration)",
        "name": "வாடிக்கையாளர் பெயர் (Name)",
        "cid": "வாடிக்கையாளர் எண் (Customer ID)",
        "email": "மின்னஞ்சல் / தொலைபேசி (Contact)",
        "insurer": "காப்பீட்டு நிறுவனம் (Insurer)",
        "pol_no": "பாலிசி / வாகன எண் (Policy / Vehicle No)",
        "pol_type": "பாலிசி வகை (Policy Type)",
        "date_loc": "தேதி மற்றும் இடம் (Date & Location)",
        "veh": "வாகன வகை (Vehicle Type)",
        "damage": "சேத விவரம் (Damage in English for Insurer)",
        "confirmed": "உறுதி செய்யப்பட்டது (Confirmed)",
    },
}


def render_localized_dossier_html(dossier: ProfessionalClaimDossier, lang: str = "en") -> str:
    """
    Render a printable, downloadable Unicode HTML dossier in the customer's preferred language
    (English, Kannada, Telugu, Hindi, or Tamil), keeping core structured values in English for insurers.
    """
    code = (lang or "en").split("-")[0].lower()
    tr = DOSSIER_I18N.get(code, DOSSIER_I18N["en"])

    s1 = dossier.section_01_customer
    s2 = dossier.section_02_policy
    s3 = dossier.section_03_incident
    s4 = dossier.section_04_statement
    s5 = dossier.section_05_evidence_inventory
    s6 = dossier.section_06_validation_review
    s7 = dossier.section_07_supporting_documents
    s8 = dossier.section_08_preparation_summary
    s9 = dossier.section_09_declaration

    ev_rows = "".join(
        f"<tr><td><b>{item.evidence_id}</b> ({item.item_label})</td><td>{item.capture_method}</td><td>{item.screening_outcome}</td></tr>"
        for item in s5.items
    ) or "<tr><td colspan='3'>No evidence uploaded yet.</td></tr>"

    doc_rows = "".join(
        f"<tr><td><b>{d.evidence_id}</b> — {d.filename}</td><td><code>{d.sha256_hash[:24]}...</code></td><td><code>{d.perceptual_hash or 'N/A'}</code></td></tr>"
        for d in s7.documents
    ) or "<tr><td colspan='3'>No supporting files attached.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="{code}">
<head>
<meta charset="utf-8" />
<title>{tr['doc_title']} - {dossier.claim_id}</title>
<style>
  body {{ font-family: 'Segoe UI', 'Nirmala UI', 'Gautami', 'Tunga', 'Mangal', sans-serif; margin: 32px; color: #111827; background: #f9fafb; }}
  .container {{ max-width: 900px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }}
  .top-bar {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1d4ed8; padding-bottom: 16px; margin-bottom: 24px; }}
  h1 {{ font-size: 20px; color: #1e3a8a; margin: 0 0 6px 0; }}
  h2 {{ font-size: 14px; color: #1d4ed8; background: #eff6ff; padding: 8px 12px; border-radius: 8px; margin-top: 20px; margin-bottom: 10px; border-left: 4px solid #2563eb; }}
  .meta {{ font-size: 12px; color: #4b5563; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px 20px; font-size: 13px; }}
  .field-box {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 12px; border-radius: 8px; }}
  .label {{ font-size: 11px; color: #64748b; font-weight: 600; display: block; margin-bottom: 2px; }}
  .val {{ font-size: 13px; color: #0f172a; font-weight: 700; }}
  p {{ font-size: 13px; line-height: 1.6; margin: 6px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }}
  th {{ background: #f1f5f9; color: #334155; }}
  .btn {{ background: #2563eb; color: #fff; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 13px; }}
  @media print {{ .no-print {{ display: none !important; }} body {{ margin: 0; background: #fff; }} .container {{ border: none; box-shadow: none; padding: 0; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="top-bar">
    <div>
      <h1>{tr['doc_title']}</h1>
      <div class="meta">Claim ID: <b>{dossier.claim_id}</b> &bull; Report ID: <b>{dossier.report_id} (v{dossier.report_version})</b> &bull; Language: <b>{tr['lang_name']}</b></div>
    </div>
    <button class="btn no-print" onclick="window.print()">{tr['print_btn']}</button>
  </div>

  <h2>{tr['s1']}</h2>
  <div class="grid">
    <div class="field-box"><span class="label">{tr['name']}</span><span class="val">{s1.name}</span></div>
    <div class="field-box"><span class="label">{tr['cid']}</span><span class="val">{s1.customer_id}</span></div>
    <div class="field-box"><span class="label">{tr['email']}</span><span class="val">{s1.email} / {s1.phone}</span></div>
    <div class="field-box"><span class="label">{tr['insurer']}</span><span class="val">{s1.declared_insurer}</span></div>
  </div>

  <h2>{tr['s2']}</h2>
  <div class="grid">
    <div class="field-box"><span class="label">{tr['pol_no']}</span><span class="val">{s2.policy_number}</span></div>
    <div class="field-box"><span class="label">{tr['pol_type']}</span><span class="val">{s2.policy_type} ({s2.verification_status})</span></div>
  </div>

  <h2>{tr['s3']}</h2>
  <div class="grid">
    <div class="field-box"><span class="label">{tr['date_loc']}</span><span class="val">{s3.incident_date_time} — {s3.incident_location}</span></div>
    <div class="field-box"><span class="label">{tr['veh']}</span><span class="val">{s3.vehicle_details}</span></div>
    <div class="field-box" style="grid-column: span 2;"><span class="label">{tr['damage']}</span><span class="val">{s3.injuries_or_damage}</span></div>
  </div>

  <h2>{tr['s4']}</h2>
  <div class="field-box"><p>{s4.chronological_account}</p></div>

  <h2>{tr['s5']}</h2>
  <table>
    <thead><tr><th>Evidence ID</th><th>Capture Method</th><th>Integrity Screening Outcome</th></tr></thead>
    <tbody>{ev_rows}</tbody>
  </table>

  <h2>{tr['s6']}</h2>
  <div class="field-box">
    <p><b>Missing Fields:</b> {', '.join(s6.missing_information) if s6.missing_information else 'None (All 5 Core Fields Captured in English)'}</p>
    <p><b>Warnings:</b> {', '.join(s6.evidence_warnings) if s6.evidence_warnings else 'None'}</p>
  </div>

  <h2>{tr['s7']}</h2>
  <table>
    <thead><tr><th>Document</th><th>SHA-256 Fingerprint</th><th>64-bit DCT pHash</th></tr></thead>
    <tbody>{doc_rows}</tbody>
  </table>

  <h2>{tr['s8']}</h2>
  <div class="field-box">
    <p>{s8.incident_summary}</p>
    <p><b>Evidence Summary:</b> {s8.available_evidence_summary}</p>
  </div>

  <h2>{tr['s9']}</h2>
  <div class="field-box">
    <p><b>{tr['confirmed']}:</b> {'YES' if s9.customer_confirmed else 'NO'} — {s9.confirmed_by_name} ({s9.confirmed_by_id}) at {s9.report_generation_timestamp}</p>
    <p style="font-size:11px;color:#64748b;">{s9.declaration_text}</p>
  </div>
</div>
</body>
</html>"""

