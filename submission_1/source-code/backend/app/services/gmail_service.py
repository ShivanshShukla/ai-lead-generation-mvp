import base64
import html
import json
import os
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from urllib.parse import parse_qs, urlparse

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import EmailDraft, GmailOAuthState, GmailToken
from app.utils.time_utils import utc_now

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_SEND_SCOPE, GMAIL_READONLY_SCOPE]
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailConfigurationError(Exception):
    pass


class GmailConnectionError(Exception):
    pass


class GmailPermissionError(GmailConnectionError):
    pass


def _load_flow_class():
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise GmailConfigurationError(
            "Gmail API dependencies are not installed. Run pip install -r requirements.txt."
        ) from exc

    return Flow


def _load_credentials_class():
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GmailConfigurationError(
            "Gmail API dependencies are not installed. Run pip install -r requirements.txt."
        ) from exc

    return Credentials


def _load_google_request_class():
    try:
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise GmailConfigurationError(
            "Gmail API dependencies are not installed. Run pip install -r requirements.txt."
        ) from exc

    return Request


def _load_gmail_build():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailConfigurationError(
            "Gmail API dependencies are not installed. Run pip install -r requirements.txt."
        ) from exc

    return build


def _get_gmail_client_config():
    missing_settings = []

    if not settings.GMAIL_CLIENT_ID:
        missing_settings.append("GMAIL_CLIENT_ID")
    if not settings.GMAIL_CLIENT_SECRET:
        missing_settings.append("GMAIL_CLIENT_SECRET")
    if not settings.GMAIL_REDIRECT_URI:
        missing_settings.append("GMAIL_REDIRECT_URI")

    if missing_settings:
        raise GmailConfigurationError(
            f"Missing Gmail configuration: {', '.join(missing_settings)}."
        )

    return {
        "web": {
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [settings.GMAIL_REDIRECT_URI],
        }
    }


def _allow_local_oauth_redirects():
    if settings.GMAIL_REDIRECT_URI.startswith(("http://localhost", "http://127.0.0.1")):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _build_oauth_flow(code_verifier=None, autogenerate_code_verifier=True):
    _allow_local_oauth_redirects()
    Flow = _load_flow_class()

    return Flow.from_client_config(
        _get_gmail_client_config(),
        scopes=GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
        code_verifier=code_verifier,
        autogenerate_code_verifier=autogenerate_code_verifier,
    )


def build_gmail_oauth_url(db: Session) -> str:
    flow = _build_oauth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    query_params = parse_qs(urlparse(auth_url).query)
    has_code_challenge = "code_challenge" in query_params
    code_verifier = getattr(flow, "code_verifier", None)

    print(f"Gmail OAuth start: auth_url_contains_code_challenge={has_code_challenge}")

    if not state:
        raise GmailConnectionError("Gmail OAuth state could not be generated.")

    oauth_state = GmailOAuthState(
        state=state,
        code_verifier=code_verifier,
    )

    try:
        db.add(oauth_state)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise GmailConnectionError("Gmail OAuth state could not be saved.") from exc

    return auth_url


def get_connected_gmail_token(db: Session):
    return (
        db.query(GmailToken)
        .order_by(
            GmailToken.updated_at.desc(),
            GmailToken.created_at.desc(),
            GmailToken.id.desc(),
        )
        .first()
    )


def _normalize_scope_values(scope_value):
    if not scope_value:
        return []

    if isinstance(scope_value, str):
        return [scope for scope in scope_value.split() if scope]

    if isinstance(scope_value, (list, tuple, set)):
        return [str(scope) for scope in scope_value if scope]

    return []


def _get_scopes_from_token_info(token_info: dict):
    return _normalize_scope_values(
        token_info.get("scopes") or token_info.get("scope")
    )


def get_connected_gmail_scopes(db: Session):
    token_record = get_connected_gmail_token(db)

    if not token_record or not token_record.token_json:
        return []

    try:
        token_info = json.loads(token_record.token_json)
    except json.JSONDecodeError:
        return []

    return _get_scopes_from_token_info(token_info)


def ensure_gmail_readonly_permission(db: Session):
    token_record = get_connected_gmail_token(db)

    if not token_record or not token_record.token_json:
        raise GmailConnectionError("Gmail is not connected. Please connect Gmail first.")

    try:
        token_info = json.loads(token_record.token_json)
    except json.JSONDecodeError as exc:
        raise GmailConnectionError("Stored Gmail token is invalid. Please reconnect Gmail.") from exc

    scopes = _get_scopes_from_token_info(token_info)

    if GMAIL_READONLY_SCOPE not in scopes:
        raise GmailPermissionError(
            "Gmail readonly permission is required. Please reconnect Gmail."
        )


def exchange_code_for_token(code: str, state: str | None, db: Session) -> dict:
    print(f"Gmail OAuth callback: received_state={bool(state)}")

    if not state:
        raise GmailConnectionError("Gmail OAuth state is missing. Please start Gmail connection again.")

    oauth_state = (
        db.query(GmailOAuthState)
        .filter(GmailOAuthState.state == state)
        .first()
    )
    saved_code_verifier = oauth_state.code_verifier if oauth_state else None

    print(f"Gmail OAuth callback: saved_code_verifier_exists={bool(saved_code_verifier)}")

    if not oauth_state:
        raise GmailConnectionError("Gmail OAuth state is invalid or expired. Please start Gmail connection again.")

    flow = _build_oauth_flow(
        code_verifier=saved_code_verifier,
        autogenerate_code_verifier=False,
    )

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise GmailConnectionError(f"Gmail OAuth failed: {exc}") from exc

    credentials = flow.credentials
    sender_email = settings.GMAIL_SENDER_EMAIL.strip() or None
    token_record = get_connected_gmail_token(db)

    if token_record:
        token_record.email = sender_email
        token_record.token_json = credentials.to_json()
        token_record.updated_at = utc_now()
    else:
        token_record = GmailToken(
            email=sender_email,
            token_json=credentials.to_json(),
        )
        db.add(token_record)

    try:
        db.delete(oauth_state)
        db.commit()
        db.refresh(token_record)
    except SQLAlchemyError as exc:
        db.rollback()
        raise GmailConnectionError("Gmail token could not be saved.") from exc

    return {
        "email": token_record.email,
        "scopes": credentials.scopes or GMAIL_SCOPES,
    }


def get_gmail_service(db: Session):
    token_record = get_connected_gmail_token(db)

    if not token_record or not token_record.token_json:
        raise GmailConnectionError("Gmail is not connected. Please connect Gmail first.")

    try:
        token_info = json.loads(token_record.token_json)
        Credentials = _load_credentials_class()
        token_scopes = _get_scopes_from_token_info(token_info)
        credentials = Credentials.from_authorized_user_info(
            token_info,
            token_scopes or GMAIL_SCOPES,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise GmailConnectionError("Stored Gmail token is invalid. Please reconnect Gmail.") from exc

    if credentials.expired:
        if not credentials.refresh_token:
            raise GmailConnectionError("Gmail token expired. Please reconnect Gmail.")

        try:
            Request = _load_google_request_class()
            credentials.refresh(Request())
            token_record.token_json = credentials.to_json()
            token_record.updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise GmailConnectionError("Refreshed Gmail token could not be saved.") from exc
        except Exception as exc:
            raise GmailConnectionError("Gmail token refresh failed. Please reconnect Gmail.") from exc

    if not credentials.valid:
        raise GmailConnectionError("Gmail token is invalid. Please reconnect Gmail.")

    build = _load_gmail_build()

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def create_message(to_email, subject, body, sender_email, thread_id=None):
    message = MIMEText(body or "", "plain", "utf-8")
    message["to"] = to_email
    message["subject"] = subject or ""

    if sender_email:
        message["from"] = sender_email

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    payload = {"raw": encoded_message}

    if thread_id:
        payload["threadId"] = thread_id

    return payload


def _format_gmail_api_error(exc: Exception) -> str:
    response = getattr(exc, "resp", None)
    status_code = getattr(response, "status", None)

    if status_code:
        return f"Gmail API error ({status_code}): {exc}"

    return f"Gmail API error: {exc}"


def _get_gmail_api_status_code(exc: Exception):
    response = getattr(exc, "resp", None)
    return getattr(response, "status", None)


def _build_reply_search_queries(lead_email: str, subject: str | None):
    base_query = f"from:{lead_email} newer_than:30d"
    subject_words = [
        word
        for word in re.findall(r"[A-Za-z0-9]{4,}", subject or "")
        if word.lower() not in {"re", "fwd", "with", "your", "from", "about"}
    ]
    queries = []

    if subject_words:
        subject_phrase = " ".join(subject_words[:3]).replace('"', '\\"')
        queries.append(f'{base_query} "{subject_phrase}"')

    queries.append(base_query)

    return list(dict.fromkeys(queries))


def _get_message_datetime(message: dict):
    internal_date = message.get("internalDate")

    if not internal_date:
        return None

    try:
        return datetime.fromtimestamp(int(internal_date) / 1000, timezone.utc)
    except (TypeError, ValueError):
        return None


def _to_utc_aware(value):
    if not value:
        return None

    if value.tzinfo:
        return value.astimezone(timezone.utc)

    return value.replace(tzinfo=timezone.utc)


def _message_is_after_sent_at(message_datetime, sent_at):
    normalized_message_datetime = _to_utc_aware(message_datetime)
    normalized_sent_at = _to_utc_aware(sent_at)

    if not normalized_sent_at or not normalized_message_datetime:
        return True

    return normalized_message_datetime > normalized_sent_at


def _handle_reply_gmail_api_error(exc: Exception):
    status_code = _get_gmail_api_status_code(exc)

    if status_code == 403:
        raise GmailPermissionError(
            "Gmail readonly permission is required. Please reconnect Gmail."
        ) from exc

    if status_code == 401:
        raise GmailConnectionError("Gmail authorization failed. Please reconnect Gmail.") from exc

    raise GmailConnectionError("Reply check failed. Please try again.") from exc


def get_gmail_message_thread_id(db: Session, gmail_message_id: str | None):
    if not gmail_message_id:
        return None

    try:
        service = get_gmail_service(db)
        message_detail = (
            service.users()
            .messages()
            .get(userId="me", id=gmail_message_id, format="metadata")
            .execute()
        )
        return message_detail.get("threadId")
    except Exception:
        return None


def _save_reply_check_result(db: Session, email_draft: EmailDraft):
    try:
        db.commit()
        db.refresh(email_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise GmailConnectionError("Reply check result could not be saved.") from exc


def _existing_reply_result(email_draft: EmailDraft):
    return {
        "replied": True,
        "reply_message_id": email_draft.reply_message_id,
        "reply_snippet": email_draft.reply_snippet,
    }


def _clean_reply_snippet(snippet: str | None):
    if not snippet:
        return None

    try:
        cleaned_snippet = html.unescape(str(snippet)).strip()
        quote_markers = [
            r"\bOn\b.{0,240}?\bwrote:",
            r"-----Original Message-----",
            r"\bFrom:",
            r"\bSent:",
            r"\bTo:",
            r"\bSubject:",
        ]
        marker_pattern = re.compile("|".join(quote_markers), re.IGNORECASE | re.DOTALL)
        marker_match = marker_pattern.search(cleaned_snippet)

        if marker_match:
            cleaned_snippet = cleaned_snippet[:marker_match.start()]

        cleaned_snippet = re.sub(r"\s+", " ", cleaned_snippet).strip()

        if cleaned_snippet:
            return cleaned_snippet

        return None if marker_match else str(snippet).strip()
    except Exception:
        return str(snippet).strip()


def check_reply_for_draft(db: Session, email_draft: EmailDraft) -> dict:
    if email_draft.status not in {"sent", "replied"}:
        raise ValueError("Only sent drafts can be checked for replies.")

    lead = email_draft.lead
    lead_email = ((lead.email if lead else "") or "").strip()
    now = utc_now()

    if not lead_email:
        email_draft.reply_checked_at = now
        _save_reply_check_result(db, email_draft)
        if email_draft.status == "replied":
            return _existing_reply_result(email_draft)
        return {"replied": False}

    ensure_gmail_readonly_permission(db)

    try:
        service = get_gmail_service(db)
    except (GmailConfigurationError, GmailConnectionError):
        raise

    seen_message_ids = set()

    for query in _build_reply_search_queries(lead_email, email_draft.subject):
        try:
            messages_response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=10)
                .execute()
            )
        except Exception as exc:
            _handle_reply_gmail_api_error(exc)

        for message in messages_response.get("messages", []):
            message_id = message.get("id")

            if not message_id or message_id in seen_message_ids:
                continue

            seen_message_ids.add(message_id)

            try:
                message_detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="metadata")
                    .execute()
                )
            except Exception as exc:
                _handle_reply_gmail_api_error(exc)

            message_datetime = _get_message_datetime(message_detail)

            if not _message_is_after_sent_at(message_datetime, email_draft.sent_at):
                continue

            original_reply_snippet = (message_detail.get("snippet") or "").strip()
            reply_snippet = _clean_reply_snippet(original_reply_snippet)
            email_draft.status = "replied"
            email_draft.reply_message_id = message_detail.get("id")
            email_draft.reply_snippet = reply_snippet[:500] if reply_snippet else None
            email_draft.replied_at = message_datetime or now
            email_draft.reply_checked_at = now
            _save_reply_check_result(db, email_draft)

            return {
                "replied": True,
                "reply_message_id": email_draft.reply_message_id,
                "reply_snippet": email_draft.reply_snippet,
            }

    email_draft.reply_checked_at = now
    _save_reply_check_result(db, email_draft)

    if email_draft.status == "replied":
        return _existing_reply_result(email_draft)

    return {"replied": False}


def send_email_via_gmail(db: Session, to_email, subject, body, thread_id=None) -> dict:
    cleaned_to_email = (to_email or "").strip()

    if not cleaned_to_email:
        return {
            "success": False,
            "error": "Lead email is missing.",
        }

    try:
        service = get_gmail_service(db)
    except (GmailConfigurationError, GmailConnectionError) as exc:
        return {
            "success": False,
            "error": str(exc),
        }

    token_record = get_connected_gmail_token(db)
    sender_email = (
        (token_record.email if token_record else None)
        or settings.GMAIL_SENDER_EMAIL
        or ""
    ).strip()

    if not sender_email:
        return {
            "success": False,
            "error": "Gmail sender email is not configured.",
        }

    message = create_message(cleaned_to_email, subject, body, sender_email, thread_id=thread_id)

    try:
        sent_message = (
            service.users()
            .messages()
            .send(userId="me", body=message)
            .execute()
        )
    except Exception as exc:
        return {
            "success": False,
            "error": _format_gmail_api_error(exc),
        }

    return {
        "success": True,
        "gmail_message_id": sent_message.get("id"),
        "gmail_thread_id": sent_message.get("threadId"),
    }
