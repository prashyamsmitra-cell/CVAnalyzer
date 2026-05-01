"""
Backend API for resume analysis and WhatsApp webhook handling.
"""
from typing import Any, Dict, Optional
import json
import logging
import os
import time

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .ai_engine import get_ai_engine
from .config import settings
from .database import DatabaseManager
from .parser import ResumeParser
from .storage import StorageManager
from .whatsapp import WhatsAppClient


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

whatsapp_client = WhatsAppClient()
db = DatabaseManager()
storage = StorageManager()
ai_engine = get_ai_engine()

GREETING_MESSAGES = {"hi", "hello", "hey", "hii", "start", "help"}
SUPPORTED_EXTENSIONS = {"pdf", "doc", "docx"}
MESSAGE_DEDUP_TTL_SECONDS = 900
processed_message_ids: Dict[str, float] = {}
DEFAULT_LANGUAGE_CODE = "en_US"


@app.get("/")
async def root() -> Dict[str, Any]:
    """Basic health check for Render and API consumers."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "whatsapp_configured": whatsapp_client.is_configured,
    }


@app.get("/api/health")
async def api_health() -> Dict[str, Any]:
    """Frontend-friendly health endpoint."""
    return {
        "status": "ok",
        "api": "resume-analyzer",
        "environment": settings.ENVIRONMENT,
    }


@app.post("/api/analyze")
async def analyze_resume_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Analyze a resume uploaded from the web frontend."""
    filename = file.filename or "resume.pdf"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOC, and DOCX files are supported.",
        )

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    analysis_result = await analyze_resume_bytes(
        file_content=file_content,
        filename=filename,
        user_id="web-user",
        persist=False,
    )
    return analysis_result


@app.get("/webhook")
async def webhook_verify(request: Request):
    """Verify the WhatsApp webhook with Meta."""
    if not whatsapp_client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp integration is not configured.",
        )

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    challenge_response = whatsapp_client.verify_webhook(
        mode=mode,
        token=token,
        challenge=challenge,
    )

    if challenge_response:
        return PlainTextResponse(challenge_response)

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
    """Receive incoming WhatsApp messages."""
    if not whatsapp_client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp integration is not configured.",
        )

    try:
        body = await request.json()
        logger.info("Received webhook payload: %s", json.dumps(body, indent=2))
        background_tasks.add_task(process_webhook_payload, body)
        return JSONResponse(content={"status": "ok"})

    except Exception as exc:
        logger.error("Webhook error: %s", exc, exc_info=True)
        return JSONResponse(content={"status": "error"}, status_code=500)


async def process_webhook_payload(body: dict):
    """Process webhook payload after the HTTP response has been returned."""
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    await process_message(message)
    except Exception as exc:
        logger.error("Background webhook processing error: %s", exc, exc_info=True)


async def analyze_resume_bytes(
    file_content: bytes,
    filename: str,
    user_id: str,
    persist: bool = True,
) -> Dict[str, Any]:
    """Parse, analyze, and optionally persist a resume analysis."""
    try:
        resume_text, metadata = await ResumeParser.parse(file_content, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resume_url: Optional[str] = None
    if persist:
        resume_url = await storage.upload_resume(file_content, filename, user_id)

    analysis = await ai_engine.analyze(resume_text)

    if persist:
        await db.save_analysis(
            whatsapp_number=user_id,
            resume_url=resume_url or "",
            ats_score=analysis.get("ats_score", 0),
            strengths=analysis.get("strengths", []),
            weaknesses=analysis.get("weaknesses", []),
            missing_sections=analysis.get("missing_sections", []),
            ai_insights=analysis.get("ai_insights", {}),
        )

    return {
        "filename": filename,
        "metadata": metadata,
        "analysis": analysis,
        "resume_url": resume_url,
    }


async def process_message(message: dict):
    """Process incoming WhatsApp messages."""
    from_id = message.get("from")
    message_type = message.get("type")
    message_id = message.get("id")

    if not should_process_message(message_id):
        logger.info("Skipping duplicate WhatsApp message: %s", message_id)
        return

    logger.info(
        "Processing message from %s, type: %s, id: %s",
        from_id,
        message_type,
        message_id,
    )

    user_session = await db.get_user_session(from_id)
    if not user_session:
        user_session = await db.create_user_session(from_id)

    if message_type == "text":
        text = message.get("text", {}).get("body", "").strip().lower()

        if text in GREETING_MESSAGES:
            await send_welcome_message(from_id)
        elif text == "status":
            await send_status_message(from_id, user_session)
        else:
            await whatsapp_client.send_message(
                from_id,
                (
                    "You are connected to CV Analyzer. "
                    "Send your resume in PDF or DOCX format and I will review it for ATS readiness, "
                    "keyword coverage, section completeness, and improvement opportunities."
                ),
            )

    elif message_type == "document":
        document = message.get("document", {})
        file_id = document.get("id")
        filename = document.get("filename", "resume.pdf")

        if message_id:
            await whatsapp_client.mark_as_read(message_id)

        await whatsapp_client.send_message(
            from_id,
            (
                "Your resume has been received. "
                "I am reviewing formatting, keyword alignment, experience signals, and section coverage now."
            ),
        )

        file_content = await download_whatsapp_file(file_id)
        if not file_content:
            await whatsapp_client.send_message(
                from_id,
                "Sorry, I could not download your CV. Please try again.",
            )
            return

        try:
            result = await analyze_resume_bytes(
                file_content=file_content,
                filename=filename,
                user_id=from_id,
                persist=True,
            )
        except HTTPException as exc:
            await whatsapp_client.send_message(
                from_id,
                f"Sorry, I could not parse your CV: {exc.detail}",
            )
            return

        await send_analysis_results(from_id, result["analysis"])

        await db.update_user_state(
            from_id,
            "analysis_complete",
            {
                "resume_url": result.get("resume_url"),
                "last_analysis": result["analysis"].get("ats_score"),
            },
        )

    else:
        await whatsapp_client.send_message(
            from_id,
            "Please send your CV in PDF or DOCX format so I can analyze it.",
        )


def should_process_message(message_id: Optional[str]) -> bool:
    """Deduplicate webhook retries from WhatsApp for a short time window."""
    if not message_id:
        return True

    now = time.time()
    expired = [
        existing_id
        for existing_id, seen_at in processed_message_ids.items()
        if now - seen_at > MESSAGE_DEDUP_TTL_SECONDS
    ]
    for existing_id in expired:
        processed_message_ids.pop(existing_id, None)

    if message_id in processed_message_ids:
        return False

    processed_message_ids[message_id] = now
    return True


async def download_whatsapp_file(file_id: str) -> Optional[bytes]:
    """Download a media file from the WhatsApp Cloud API."""
    try:
        url = f"https://graph.facebook.com/v18.0/{file_id}"
        headers = {"Authorization": f"Bearer {whatsapp_client.token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error("Failed to fetch media metadata: %s", response.text)
                return None

            file_data = response.json()
            download_url = file_data.get("url")
            if not download_url:
                logger.error("No download URL returned from WhatsApp API")
                return None

            download_response = await client.get(download_url, headers=headers)
            if download_response.status_code != 200:
                logger.error(
                    "Failed to download media file: %s",
                    download_response.text,
                )
                return None

            return download_response.content

    except Exception as exc:
        logger.error("File download error: %s", exc, exc_info=True)
        return None


async def send_welcome_message(to: str):
    """Send welcome instructions."""
    if settings.WHATSAPP_USE_TEMPLATES and settings.WHATSAPP_TEMPLATE_WELCOME:
        sent = await whatsapp_client.send_template_message(
            to=to,
            template_name=settings.WHATSAPP_TEMPLATE_WELCOME,
            language_code=DEFAULT_LANGUAGE_CODE,
        )
        if sent:
            return

    text = (
        "Welcome to CV Analyzer.\n\n"
        "I can review your resume for ATS readiness and share a concise scoring summary.\n\n"
        "Please send your CV in PDF or DOCX format and I will return:\n"
        "- an ATS score\n"
        "- strengths\n"
        "- improvement areas\n"
        "- missing sections"
    )
    await whatsapp_client.send_message(to, text)


async def send_status_message(to: str, user_session: dict):
    """Send the user's current status and last analysis."""
    last_score = user_session.get("last_analysis")

    if last_score:
        text = (
            f"Your latest ATS score is {last_score}/100.\n\n"
            "Send an updated PDF or DOCX resume any time if you want a fresh review."
        )
    else:
        text = (
            "No resume has been analyzed yet.\n\n"
            "Send your CV in PDF or DOCX format to begin your ATS review."
        )

    await whatsapp_client.send_message(to, text)


async def send_analysis_results(to: str, analysis: dict):
    """Send a text summary of the analysis result."""
    ats_score = analysis.get("ats_score", 0)
    strengths = analysis.get("strengths", [])
    weaknesses = analysis.get("weaknesses", [])
    recommendations = analysis.get("recommendations", [])
    missing_sections = analysis.get("missing_sections", [])

    score_label = (
        "Strong"
        if ats_score >= 70
        else "Moderate"
        if ats_score >= 50
        else "Needs Improvement"
    )

    if settings.WHATSAPP_USE_TEMPLATES and settings.WHATSAPP_TEMPLATE_ANALYSIS_READY:
        await whatsapp_client.send_template_message(
            to=to,
            template_name=settings.WHATSAPP_TEMPLATE_ANALYSIS_READY,
            language_code=DEFAULT_LANGUAGE_CODE,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(ats_score)},
                        {"type": "text", "text": score_label},
                    ],
                }
            ],
        )

    message = (
        "ATS review complete.\n\n"
        f"ATS Score: {ats_score}/100\n"
        f"Overall: {score_label}\n\n"
        "Strengths:\n"
    )

    if strengths:
        for strength in strengths[:3]:
            message += f"- {strength}\n"
    else:
        message += "- Resume submitted successfully\n"

    message += "\nAreas to improve:\n"

    if weaknesses:
        for weakness in weaknesses[:3]:
            message += f"- {weakness}\n"
    else:
        message += "- No major issues detected\n"

    if recommendations:
        message += "\nTop recommendations:\n"
        for recommendation in recommendations[:2]:
            message += f"- {recommendation}\n"

    if missing_sections:
        message += "\nMissing or weak sections:\n"
        for section in missing_sections[:3]:
            message += f"- {section}\n"

    message += "\nSend another CV any time for a fresh ATS review."
    await whatsapp_client.send_message(to, message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
