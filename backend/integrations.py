"""Explicit adapters for optional external services; never used for active scoring by default."""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict[str, Any], token: str, timeout: float = 8) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class CreditBureauAdapter:
    @staticmethod
    def status() -> dict[str, Any]:
        return {"configured": bool(os.getenv("CREDIT_BUREAU_URL") and os.getenv("CREDIT_BUREAU_TOKEN")), "mode": "verification-only"}

    @staticmethod
    def verify(record: dict[str, Any]) -> dict[str, Any]:
        if not CreditBureauAdapter.status()["configured"]:
            return {"status": "NOT_CONFIGURED", "message": "Set CREDIT_BUREAU_URL and CREDIT_BUREAU_TOKEN to enable verified bureau inputs."}
        identifiers = {
            "pan": record.get("pan") or record.get("pan_number"),
            "applicant_name": record.get("applicant_name"),
        }
        response = _post_json(os.environ["CREDIT_BUREAU_URL"], identifiers, os.environ["CREDIT_BUREAU_TOKEN"])
        return {"status": "VERIFIED", "provider_response": response}


class NarrativeLLMAdapter:
    @staticmethod
    def status() -> dict[str, Any]:
        return {"configured": bool(os.getenv("NARRATIVE_LLM_URL") and os.getenv("NARRATIVE_LLM_TOKEN")), "scope": "narrative-only", "decision_authority": False}

    @staticmethod
    def summarize(grounded_report: dict[str, Any]) -> dict[str, Any]:
        if not NarrativeLLMAdapter.status()["configured"]:
            return {"status": "NOT_CONFIGURED", "message": "The optional narrative LLM is disabled; the deterministic grounded answer remains active."}
        payload = {
            "instruction": "Summarize the supplied verified report. Preserve citations. Do not change scores or recommendation.",
            "report": {
                "answer": grounded_report["answer"],
                "decision": grounded_report["decision"],
                "verification": grounded_report["verification"],
            },
        }
        response = _post_json(os.environ["NARRATIVE_LLM_URL"], payload, os.environ["NARRATIVE_LLM_TOKEN"])
        return {"status": "GENERATED", "label": "optional external narrative", "response": response, "used_for_scoring": False}
