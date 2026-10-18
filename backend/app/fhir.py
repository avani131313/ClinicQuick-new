"""FHIR R4 export: turns an intake into a transaction Bundle any FHIR server can accept.

Resources: Patient, Encounter, QuestionnaireResponse (the full tagged Q&A),
RiskAssessment (one per score), Observation (vitals/trends), DocumentReference (the clinician note).
Synthetic data only — the public HAPI server is a shared test server.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

import httpx

from .config import FHIR_SERVER_URL


def _u() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def build_bundle(report: dict) -> dict:
    c = report["clinician"]
    p = c["patient"]
    pid, eid, qid = _u(), _u(), _u()
    now = datetime.now(timezone.utc).isoformat()
    first, *rest = p["name"].split()
    entries = [
        {"fullUrl": pid, "resource": {
            "resourceType": "Patient",
            "meta": {"tag": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActReason", "code": "HTEST", "display": "test health data"}]},
            "name": [{"given": [first], "family": " ".join(rest) or first}],
            "gender": {"female": "female", "male": "male"}.get(p["sex"], "other"),
            "birthDate": p["dob"]},
         "request": {"method": "POST", "url": "Patient"}},
        {"fullUrl": eid, "resource": {
            "resourceType": "Encounter", "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "VR", "display": "virtual"},
            "type": [{"text": "Pre-visit AI-assisted intake (ClinicQuick)"}],
            "subject": {"reference": pid}, "period": {"start": now, "end": now},
            "reasonCode": [{"text": c["chief_complaint"]}]},
         "request": {"method": "POST", "url": "Encounter"}},
        {"fullUrl": qid, "resource": {
            "resourceType": "QuestionnaireResponse", "status": "completed",
            "subject": {"reference": pid}, "encounter": {"reference": eid}, "authored": now,
            "item": [{
                "linkId": f"q{i + 1}",
                "text": t["question"],
                "extension": [{"url": "https://clinicquick.health/fhir/question-type", "valueCode": t["type"]},
                              {"url": "https://clinicquick.health/fhir/question-rationale", "valueString": t["rationale"] or ""}],
                "answer": [{"valueString": t["answer"]}] if t["answer"] else []}
                for i, t in enumerate(c["transcript"])]},
         "request": {"method": "POST", "url": "QuestionnaireResponse"}},
    ]
    for s in c["risk_scores"]:
        if not s["applicable"] or s["value"] is None:
            continue
        entries.append({"fullUrl": _u(), "resource": {
            "resourceType": "RiskAssessment", "status": "final",
            "subject": {"reference": pid}, "encounter": {"reference": eid}, "occurrenceDateTime": now,
            "method": {"text": f"{s['name']} ({s['version']}) — {s['citation']}"},
            "prediction": [{"outcome": {"text": s["band"]}, "qualitativeRisk": {"text": s["band"]}}],
            "note": [{"text": f"{s['summary']} Score: {s['value']}. Source: {s['citation_url']}"}]},
            "request": {"method": "POST", "url": "RiskAssessment"}})
    note_md = render_note_markdown(c)
    entries.append({"fullUrl": _u(), "resource": {
        "resourceType": "DocumentReference", "status": "current",
        "type": {"text": "Pre-visit intake note"}, "subject": {"reference": pid},
        "context": {"encounter": [{"reference": eid}]}, "date": now,
        "description": c["one_liner"],
        "content": [{"attachment": {"contentType": "text/markdown",
                                    "data": base64.b64encode(note_md.encode()).decode(),
                                    "title": "ClinicQuick clinician note"}}]},
        "request": {"method": "POST", "url": "DocumentReference"}})
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def render_note_markdown(c: dict) -> str:
    L = [f"# Pre-visit intake — {c['patient']['name']} ({c['patient']['age']}{c['patient']['sex'][0].upper()})",
         f"**{c['one_liner']}**", "", f"**Chief complaint:** {c['chief_complaint']}", "", "## HPI"]
    L += [f"- **{h['label']}:** {h['text']}" for h in c["hpi"]]
    L += ["", "**Associated:** " + "; ".join(c["associated"] or ["—"]),
          "**Relevant negatives:** " + "; ".join(c["relevant_negatives"] or ["—"]),
          f"**Red-flag screen:** {c['red_flag_screen']['result']} — {c['red_flag_screen']['detail']}", "",
          "## History", "**PMH:** " + ", ".join(c["pmh"] or ["none reported"]),
          "**Medications:** " + ", ".join(c["medications"] or ["none"]),
          "**Allergies:** " + ", ".join(c["allergies"] or ["NKDA"]), "", "## Risk scores"]
    L += [f"- {s['name']}: {s['band']} ({s['value']}) — {s['citation']}" for s in c["risk_scores"] if s["applicable"]]
    L += ["", "## Conditions to consider (clinician only)"]
    L += [f"- {x['name']} — {x['likelihood']}: {', '.join(x['because'])}" for x in c["considerations"]]
    L += ["", f"**ICE:** {c['ice']}", f"**Navigation:** {c['urgency']['label']}", "",
          "_Generated by ClinicQuick. Decision support only — not a diagnosis._"]
    return "\n".join(L)


def push(bundle: dict) -> dict:
    """POST the transaction bundle to the FHIR server and return what it created."""
    r = httpx.post(FHIR_SERVER_URL, content=json.dumps(bundle),
                   headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    created = [e.get("response", {}).get("location", "") for e in data.get("entry", [])]
    patient_loc = next((x for x in created if x.startswith("Patient/")), None)
    return {"server": FHIR_SERVER_URL, "created": created,
            "patient_url": f"{FHIR_SERVER_URL}/{patient_loc.split('/_history')[0]}" if patient_loc else None}
