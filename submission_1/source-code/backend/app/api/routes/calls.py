from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import CallLog, Campaign, Lead
from app.schemas.call_schema import (
    CallOutcomeUpdate,
    GenerateCallScriptRequest,
    ManualCallLogCreate,
    StartVapiCallRequest,
)
from app.services.vapi_service import (
    VapiConfigurationError,
    VapiServiceError,
    create_manual_call_log,
    generate_call_script,
    generate_call_followup_email,
    handle_tool_call,
    handle_vapi_webhook,
    is_vapi_configured,
    start_outbound_call,
    update_call_outcome,
    vapi_config_status,
)

router = APIRouter(
    prefix="/calls",
    tags=["Calls"],
)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def get_call_or_404(call_log_id: int, db: Session):
    call_log = (
        db.query(CallLog)
        .options(joinedload(CallLog.lead), joinedload(CallLog.campaign))
        .filter(CallLog.id == call_log_id)
        .first()
    )

    if not call_log:
        raise HTTPException(status_code=404, detail=f"Call log with id {call_log_id} was not found")

    return call_log


def get_lead_or_404(lead_id: int, db: Session):
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.id == lead_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead with id {lead_id} was not found")

    return lead


def serialize_call_log(call_log: CallLog, include_raw: bool = False):
    lead = call_log.lead
    campaign = call_log.campaign
    data = {
        "id": call_log.id,
        "lead_id": call_log.lead_id,
        "campaign_id": call_log.campaign_id,
        "provider": call_log.provider,
        "provider_call_id": call_log.provider_call_id,
        "provider_assistant_id": call_log.provider_assistant_id,
        "provider_phone_number_id": call_log.provider_phone_number_id,
        "direction": call_log.direction,
        "phone_number": call_log.phone_number,
        "called_number": call_log.called_number or call_log.phone_number,
        "call_mode": call_log.call_mode,
        "lead_phone_used": bool(call_log.lead_phone_used),
        "status": call_log.status,
        "outcome": call_log.outcome,
        "sentiment": call_log.sentiment,
        "priority": call_log.priority,
        "transcript": call_log.transcript,
        "summary": call_log.summary,
        "next_action": call_log.next_action,
        "call_script": call_log.call_script,
        "recording_url": call_log.recording_url,
        "duration_seconds": call_log.duration_seconds,
        "started_at": call_log.started_at,
        "ended_at": call_log.ended_at,
        "error_message": call_log.error_message,
        "created_at": call_log.created_at,
        "updated_at": call_log.updated_at,
        "lead_name": lead.contact_name if lead else None,
        "lead_company_name": lead.company_name if lead else None,
        "lead_contact_role": lead.contact_role if lead else None,
        "lead_phone": lead.phone if lead else None,
        "lead_do_not_call": lead.do_not_call if lead else None,
        "campaign_name": campaign.campaign_name if campaign else None,
    }

    if include_raw:
        data["raw_vapi_payload"] = call_log.raw_vapi_payload

    return data


def _verify_vapi_secret(
    x_vapi_secret: str | None,
    authorization: str | None,
):
    if not settings.VAPI_WEBHOOK_SECRET:
        return

    expected_bearer = f"Bearer {settings.VAPI_WEBHOOK_SECRET}"

    if x_vapi_secret == settings.VAPI_WEBHOOK_SECRET or authorization == expected_bearer:
        return

    raise HTTPException(status_code=401, detail="Invalid Vapi webhook secret.")


@router.get("/config/status")
def get_config_status():
    return {
        "status": "success",
        **vapi_config_status(),
    }


@router.get("/")
def list_call_logs(
    lead_id: int | None = Query(None),
    campaign_id: int | None = Query(None),
    status: str | None = Query(None),
    outcome: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(CallLog).options(joinedload(CallLog.lead), joinedload(CallLog.campaign))

    if lead_id is not None:
        query = query.filter(CallLog.lead_id == lead_id)
    if campaign_id is not None:
        query = query.filter(CallLog.campaign_id == campaign_id)
    if clean_text(status):
        query = query.filter(CallLog.status == clean_text(status))
    if clean_text(outcome):
        query = query.filter(CallLog.outcome == clean_text(outcome))

    call_logs = query.order_by(CallLog.created_at.desc(), CallLog.id.desc()).limit(100).all()

    return {
        "status": "success",
        "data": [serialize_call_log(call_log) for call_log in call_logs],
    }


@router.get("/{call_log_id}")
def get_call_log(call_log_id: int, db: Session = Depends(get_db)):
    call_log = get_call_or_404(call_log_id, db)

    return {
        "status": "success",
        "data": serialize_call_log(call_log, include_raw=False),
    }


@router.post("/generate-script")
def generate_script(payload: GenerateCallScriptRequest, db: Session = Depends(get_db)):
    get_lead_or_404(payload.lead_id, db)

    try:
        script = generate_call_script(db, payload.lead_id, payload.campaign_id)
    except VapiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Call script could not be generated.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Call script could not be generated.") from exc

    return {
        "status": "success",
        "message": "Call script generated successfully",
        **script,
    }


@router.post("/start-vapi")
def start_vapi_call(payload: StartVapiCallRequest, db: Session = Depends(get_db)):
    lead = get_lead_or_404(payload.lead_id, db)

    if lead.do_not_call:
        raise HTTPException(status_code=400, detail="This lead is marked do-not-call.")

    if not is_vapi_configured():
        raise HTTPException(status_code=400, detail="Vapi is not configured.")

    requested_call_mode = clean_text(payload.call_mode).lower()
    if requested_call_mode not in {"test", "actual"}:
        requested_call_mode = "test" if payload.use_test_number else "actual"

    use_test_call = payload.use_test_number or requested_call_mode == "test"
    if use_test_call:
        call_mode = "test"
        phone_number = clean_text(payload.test_phone_number) or settings.VAPI_DEFAULT_TEST_PHONE
        lead_phone_used = False
    else:
        call_mode = "actual"
        phone_number = clean_text(lead.phone)
        lead_phone_used = True

    if not phone_number:
        detail = "Phone number is required." if call_mode == "test" else "Lead does not have a phone number."
        raise HTTPException(status_code=400, detail=detail)

    try:
        call_log = start_outbound_call(
            db,
            lead_id=payload.lead_id,
            phone_number=phone_number,
            campaign_id=payload.campaign_id,
            call_mode=call_mode,
            lead_phone_used=lead_phone_used,
        )
    except VapiConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Vapi is not configured.") from exc
    except VapiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Vapi call could not be started.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Vapi call could not be started.") from exc

    return {
        "status": "success",
        "message": "Vapi call started",
        "call_log_id": call_log.id,
        "provider_call_id": call_log.provider_call_id,
        "data": serialize_call_log(call_log),
    }


@router.post("/manual-log")
def create_manual_log(payload: ManualCallLogCreate, db: Session = Depends(get_db)):
    get_lead_or_404(payload.lead_id, db)

    try:
        call_log = create_manual_call_log(
            db,
            lead_id=payload.lead_id,
            campaign_id=payload.campaign_id,
            phone_number=payload.phone_number,
            outcome=payload.outcome,
            notes=payload.notes,
            summary=payload.summary,
            next_action=payload.next_action,
            sentiment=payload.sentiment,
            priority=payload.priority,
        )
    except VapiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Manual call log could not be saved.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Manual call log could not be saved.") from exc

    return {
        "status": "success",
        "message": "Manual call log saved",
        "data": serialize_call_log(call_log),
    }


@router.patch("/{call_log_id}/outcome")
def patch_call_outcome(call_log_id: int, payload: CallOutcomeUpdate, db: Session = Depends(get_db)):
    call_log = get_call_or_404(call_log_id, db)

    try:
        updated = update_call_outcome(
            db,
            call_log,
            status=payload.status,
            outcome=payload.outcome,
            sentiment=payload.sentiment,
            priority=payload.priority,
            summary=payload.summary,
            next_action=payload.next_action,
            transcript=payload.transcript,
            do_not_call=payload.do_not_call,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Call outcome could not be updated.") from exc

    return {
        "status": "success",
        "message": "Call outcome updated",
        "data": serialize_call_log(updated),
    }


@router.post("/{call_log_id}/create-followup-email")
def create_followup_from_call(call_log_id: int, db: Session = Depends(get_db)):
    call_log = get_call_or_404(call_log_id, db)

    if not call_log.lead or not call_log.campaign:
        raise HTTPException(status_code=400, detail="Call log must be linked to a lead and campaign.")

    try:
        draft, created = generate_call_followup_email(db, call_log.id)
        db.commit()
        db.refresh(draft)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Follow-up email draft could not be created.") from exc

    return {
        "status": "success",
        "message": "Follow-up draft created. It was not sent." if created else "Follow-up draft already exists. It was not sent.",
        "email_draft_id": draft.id,
        "campaign_id": draft.campaign_id,
        "lead_id": draft.lead_id,
        "created": created,
    }


@router.post("/vapi/webhook")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str | None = Header(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    _verify_vapi_secret(x_vapi_secret, authorization)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    try:
        return handle_vapi_webhook(db, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Vapi webhook could not be processed.") from exc


@router.post("/vapi/tool")
async def vapi_tool(
    request: Request,
    x_vapi_secret: str | None = Header(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    _verify_vapi_secret(x_vapi_secret, authorization)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    try:
        return handle_tool_call(db, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Vapi tool call could not be processed.") from exc
