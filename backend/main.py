"""
Backend API for resume analysis and WhatsApp webhook handling.
"""
from typing import Any, Dict, Optional
import json
import logging
import os
import time

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .ai_engine import get_ai_engine
from .config import settings
from .database import DatabaseManager
from .parser import ResumeParser
from .whatsapp import WhatsAppClient


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

whatsapp_client = WhatsAppClient()
db = DatabaseManager()
ai_engine = get_ai_engine()

GREETING_MESSAGES = {"hi", "hello", "hey", "hii", "start", "help"}
SUPPORTED_EXTENSIONS = {"pdf", "doc", "docx"}
MESSAGE_DEDUP_TTL_SECONDS = 900
processed_message_ids: Dict[str, float] = {}
DEFAULT_LANGUAGE_CODE = "en_US"
questionnaire_sessions: Dict[str, Dict[str, Any]] = {}


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "whatsapp_configured": whatsapp_client.is_configured,
    }


@app.get("/api/health")
async def api_health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "api": "resume-analyzer",
        "environment": settings.ENVIRONMENT,
    }


@app.post("/api/analyze")
async def analyze_resume_upload(
    file: UploadFile = File(...),
    target_job: str = Form("Software Engineer"),
    current_prep: str = Form("Some projects"),
) -> Dict[str, Any]:
    filename = file.filename or "resume.pdf"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOC, and DOCX files are supported.")

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return await analyze_resume_bytes(
        file_content=file_content,
        filename=filename,
        user_id="web-user",
        target_job=target_job,
        current_prep=current_prep,
        persist=False,
    )


@app.get("/webhook")
async def webhook_verify(request: Request):
    if not whatsapp_client.is_configured:
        raise HTTPException(status_code=503, detail="WhatsApp integration is not configured.")

    challenge_response = whatsapp_client.verify_webhook(
        mode=request.query_params.get("hub.mode"),
        token=request.query_params.get("hub.verify_token"),
        challenge=request.query_params.get("hub.challenge"),
    )

    if challenge_response:
        return PlainTextResponse(challenge_response)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
    if not whatsapp_client.is_configured:
        raise HTTPException(status_code=503, detail="WhatsApp integration is not configured.")

    try:
        body = await request.json()
        logger.info("Received webhook payload: %s", json.dumps(body, indent=2))
        background_tasks.add_task(process_webhook_payload, body)
        return JSONResponse(content={"status": "ok"})
    except Exception as exc:
        logger.error("Webhook error: %s", exc, exc_info=True)
        return JSONResponse(content={"status": "error"}, status_code=500)


async def process_webhook_payload(body: dict):
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
    target_job: str,
    current_prep: str,
    persist: bool = True,
) -> Dict[str, Any]:
    try:
        logger.info("Starting resume parse for %s (%s)", user_id, filename)
        resume_text, metadata = await ResumeParser.parse(file_content, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Running ATS analysis for %s against %s", user_id, target_job)
    analysis = await ai_engine.analyze(
        resume_text,
        target_job=target_job,
        current_prep=current_prep,
    )
    processing_log = {
        "source": "whatsapp" if user_id != "web-user" else "web",
        "filename": filename,
        "metadata": metadata,
        "target_job": target_job,
        "current_prep": current_prep,
    }

    if persist:
        try:
            logger.info("Saving analysis record for %s", user_id)
            ai_insights = analysis.get("ai_insights", {})
            if not isinstance(ai_insights, dict):
                ai_insights = {"details": ai_insights}
            ai_insights["processing_log"] = processing_log

            await db.save_analysis(
                whatsapp_number=user_id,
                resume_url="",
                ats_score=analysis.get("ats_score", 0),
                strengths=analysis.get("strengths", []),
                weaknesses=analysis.get("weaknesses", []),
                missing_sections=analysis.get("missing_sections", []),
                ai_insights=ai_insights,
            )
        except Exception:
            logger.exception("Analysis save failed for %s", user_id)

    return {
        "filename": filename,
        "metadata": metadata,
        "analysis": analysis,
        "resume_url": None,
    }


async def process_message(message: dict):
    from_id = message.get("from")
    message_type = message.get("type")
    message_id = message.get("id")

    if not should_process_message(message_id):
        logger.info("Skipping duplicate WhatsApp message: %s", message_id)
        return

    logger.info("Processing message from %s, type: %s, id: %s", from_id, message_type, message_id)

    user_session = await db.get_user_session(from_id)
    if not user_session:
        user_session = await db.create_user_session(from_id)

    if message_type == "text":
        text = message.get("text", {}).get("body", "").strip()
        lower_text = text.lower()

        if lower_text in {"restart", "reset", "new", "start over"}:
            questionnaire_sessions.pop(from_id, None)
            await send_welcome_message(from_id)
            return

        if from_id in questionnaire_sessions:
            await handle_questionnaire_response(from_id, text)
            return

        if lower_text in GREETING_MESSAGES:
            await send_welcome_message(from_id)
        elif lower_text == "status":
            await send_status_message(from_id, user_session)
        else:
            await whatsapp_client.send_message(
                from_id,
                "Send your resume in PDF or DOCX format. After that I will ask which job you want and how ready you feel, then I will score the resume for that role.",
            )

    elif message_type == "document":
        document = message.get("document", {})
        file_id = document.get("id")
        filename = document.get("filename", "resume.pdf")

        if message_id:
            await whatsapp_client.mark_as_read(message_id)

        await whatsapp_client.send_message(
            from_id,
            "Your resume has been received. Before I score it, what job or internship role do you want this resume evaluated for?",
        )

        file_content = await download_whatsapp_file(file_id)
        if not file_content:
            await whatsapp_client.send_message(from_id, "Sorry, I could not download your CV. Please try again.")
            return

        questionnaire_sessions[from_id] = {
            "stage": "awaiting_target_job",
            "file_content": file_content,
            "filename": filename,
        }

    else:
        await whatsapp_client.send_message(from_id, "Please send your CV in PDF or DOCX format so I can analyze it.")


async def handle_questionnaire_response(from_id: str, text: str):
    session = questionnaire_sessions.get(from_id)
    if not session:
        return

    if session["stage"] == "awaiting_target_job":
        session["target_job"] = text.strip()
        session["stage"] = "awaiting_prep_level"
        await whatsapp_client.send_message(
            from_id,
            "What best describes your current prep? Reply with one option: Just starting, Learning basics, Some projects, Coursework and projects, Internship-ready, Interview-ready, or Already applying.",
        )
        return

    if session["stage"] == "awaiting_prep_level":
        session["current_prep"] = text.strip()
        await whatsapp_client.send_message(
            from_id,
            "Got it. I am now comparing your resume against the target role and your current prep level.",
        )

        try:
            result = await analyze_resume_bytes(
                file_content=session["file_content"],
                filename=session["filename"],
                user_id=from_id,
                target_job=session.get("target_job", "Software Engineer"),
                current_prep=session.get("current_prep", "Some projects"),
                persist=True,
            )
        except HTTPException as exc:
            logger.error("Resume processing validation failed for %s: %s", from_id, exc.detail, exc_info=True)
            await whatsapp_client.send_message(from_id, f"Sorry, I could not parse your CV: {exc.detail}")
            questionnaire_sessions.pop(from_id, None)
            return
        except Exception:
            logger.error("Unexpected resume processing failure for %s", from_id, exc_info=True)
            await whatsapp_client.send_message(
                from_id,
                "Sorry, I could not finish the ATS review for this file. Please try again in a moment, or resend the resume as PDF or DOCX.",
            )
            questionnaire_sessions.pop(from_id, None)
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
        questionnaire_sessions.pop(from_id, None)


def should_process_message(message_id: Optional[str]) -> bool:
    if not message_id:
        return True
    now = time.time()
    expired = [existing_id for existing_id, seen_at in processed_message_ids.items() if now - seen_at > MESSAGE_DEDUP_TTL_SECONDS]
    for existing_id in expired:
        processed_message_ids.pop(existing_id, None)
    if message_id in processed_message_ids:
        return False
    processed_message_ids[message_id] = now
    return True


async def download_whatsapp_file(file_id: str) -> Optional[bytes]:
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
                logger.error("Failed to download media file: %s", download_response.text)
                return None
            return download_response.content
    except Exception as exc:
        logger.error("File download error: %s", exc, exc_info=True)
        return None


async def send_welcome_message(to: str):
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
        "Send your CV in PDF or DOCX format. After that I will ask:\n"
        "- what role you want\n"
        "- how prepared you currently are\n\n"
        "Then I will return:\n"
        "- an ATS score\n"
        "- role fit score\n"
        "- likelihood of getting shortlisted\n"
        "- strengths, weaknesses, and missing skills"
    )
    await whatsapp_client.send_message(to, text)


async def send_status_message(to: str, user_session: dict):
    last_score = user_session.get("last_analysis")
    active = questionnaire_sessions.get(to)

    if active:
        text = "I still have a resume in progress for you. Reply with the requested role or prep level, or send 'restart' to begin again."
    elif last_score:
        text = f"Your latest ATS score is {last_score}/100. Send a new PDF or DOCX resume any time if you want a fresh role-based review."
    else:
        text = "No resume has been analyzed yet. Send your CV in PDF or DOCX format to begin your ATS review."

    await whatsapp_client.send_message(to, text)


async def send_analysis_results(to: str, analysis: dict):
    ats_score = analysis.get("ats_score", 0)
    strengths = analysis.get("strengths", [])
    weaknesses = analysis.get("weaknesses", [])
    recommendations = analysis.get("recommendations", [])
    missing_sections = analysis.get("missing_sections", [])
    matched_job_skills = analysis.get("matched_job_skills", [])
    missing_job_skills = analysis.get("missing_job_skills", [])

    score_label = "Strong" if ats_score >= 70 else "Moderate" if ats_score >= 50 else "Needs Improvement"

    if settings.WHATSAPP_USE_TEMPLATES and settings.WHATSAPP_TEMPLATE_ANALYSIS_READY:
        await whatsapp_client.send_template_message(
            to=to,
            template_name=settings.WHATSAPP_TEMPLATE_ANALYSIS_READY,
            language_code=DEFAULT_LANGUAGE_CODE,
            components=[{"type": "body", "parameters": [{"type": "text", "text": str(ats_score)}, {"type": "text", "text": score_label}]}],
        )

    message = (
        "ATS review complete.\n\n"
        f"Target Role: {analysis.get('target_job', 'Software Engineer')}\n"
        f"Current Prep: {analysis.get('current_prep', 'Some Projects')}\n"
        f"ATS Score: {ats_score}/100\n"
        f"Role Fit: {analysis.get('job_fit_score', 0)}/100 ({analysis.get('job_fit_label', 'Moderate')})\n"
        f"Shortlist Likelihood: {analysis.get('likelihood_score', 0)}/100 - {analysis.get('likelihood_label', 'Moderate')}\n\n"
        f"Overall ATS Result: {score_label}\n\n"
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

    if matched_job_skills:
        message += "\nRelevant skills already shown:\n"
        for skill in matched_job_skills[:4]:
            message += f"- {skill}\n"

    if missing_job_skills:
        message += "\nImportant role skills still missing:\n"
        for skill in missing_job_skills[:4]:
            message += f"- {skill}\n"

    if recommendations:
        message += "\nTop recommendations:\n"
        for recommendation in recommendations[:3]:
            message += f"- {recommendation}\n"

    if missing_sections:
        message += "\nMissing or weak sections:\n"
        for section in missing_sections[:3]:
            message += f"- {section}\n"

    message += "\nSend another CV any time for a fresh role-based ATS review."
    await whatsapp_client.send_message(to, message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
