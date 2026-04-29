"""
WhatsApp CV Analyzer - Main Application Entry Point
FastAPI server for WhatsApp webhook handling and resume analysis.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import logging
import json
import httpx

from config import settings
from whatsapp import WhatsAppClient
from database import DatabaseManager
from storage import StorageManager
from parser import ResumeParser
from ai_engine import get_ai_engine

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

# Initialize services
whatsapp_client = WhatsAppClient()
db = DatabaseManager()
storage = StorageManager()
ai_engine = get_ai_engine()

GREETING_MESSAGES = {"hi", "hello", "hey", "hii", "start", "help"}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    WhatsApp webhook verification endpoint.
    Meta calls this to verify webhook ownership.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(f"Webhook verification: mode={mode}, token={token}")

    challenge_response = whatsapp_client.verify_webhook(mode, token, challenge)
    if challenge_response:
        return challenge_response

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request):
    """
    Receive incoming WhatsApp messages.
    Handles resume uploads and user interactions.
    """
    try:
        body = await request.json()
        logger.info(f"Received webhook: {json.dumps(body, indent=2)}")

        entry = body.get("entry", [])
        if not entry:
            return JSONResponse(content={"status": "ok"})

        changes = entry[0].get("changes", [])
        if not changes:
            return JSONResponse(content={"status": "ok"})

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return JSONResponse(content={"status": "ok"})

        for message in messages:
            await process_message(message)

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)


async def process_message(message: dict):
    """
    Process incoming WhatsApp message.
    Handles greeting flow and resume attachments.
    """
    from_id = message.get("from")
    message_type = message.get("type")

    logger.info(f"Processing message from {from_id}, type: {message_type}")

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
                "Hi, welcome to CV Analyzer. We analyze resumes and provide great ATS feedback extremely fast. "
                "Please send your CV in PDF or DOCX format to get started.",
            )

    elif message_type == "document":
        document = message.get("document", {})
        file_id = document.get("id")
        filename = document.get("filename", "resume.pdf")

        await whatsapp_client.send_message(from_id, "Processing your CV. Please wait a moment.")

        file_content = await download_whatsapp_file(file_id)
        if not file_content:
            await whatsapp_client.send_message(
                from_id,
                "Sorry, I could not download your CV. Please try sending the file again.",
            )
            return

        try:
            resume_text, metadata = await ResumeParser.parse(file_content, filename)
            logger.info(
                "Parsed resume for %s with %s words from %s",
                from_id,
                metadata.get("word_count", 0),
                filename,
            )
        except Exception as e:
            logger.error(f"Parse error: {e}")
            await whatsapp_client.send_message(
                from_id,
                f"Sorry, I could not parse your CV: {str(e)}",
            )
            return

        resume_url = await storage.upload_resume(file_content, filename, from_id)
        analysis = await ai_engine.analyze(resume_text)

        await db.save_analysis(
            whatsapp_number=from_id,
            resume_url=resume_url or "",
            ats_score=analysis.get("ats_score", 0),
            strengths=analysis.get("strengths", []),
            weaknesses=analysis.get("weaknesses", []),
            missing_sections=analysis.get("missing_sections", []),
            ai_insights=analysis.get("ai_insights", {}),
        )

        await send_analysis_results(from_id, analysis)

        await db.update_user_state(
            from_id,
            "analysis_complete",
            {
                "resume_url": resume_url,
                "last_analysis": analysis.get("ats_score"),
            },
        )

    else:
        await whatsapp_client.send_message(
            from_id,
            "Please send your CV in PDF or DOCX format so I can analyze it.",
        )


async def download_whatsapp_file(file_id: str) -> bytes:
    """
    Download file from WhatsApp Cloud API.
    """
    try:
        url = f"https://graph.facebook.com/v18.0/{file_id}"
        headers = {"Authorization": f"Bearer {whatsapp_client.token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None

            file_data = response.json()
            download_url = file_data.get("url")
            if not download_url:
                return None

            download_response = await client.get(download_url, headers=headers)
            return download_response.content

    except Exception as e:
        logger.error(f"File download error: {e}")
        return None


async def send_welcome_message(to: str):
    """Send welcome message with instructions."""
    text = (
        "Hi, welcome to CV Analyzer.\n\n"
        "We analyze resumes and provide great ATS feedback extremely fast.\n\n"
        "Please send your CV in PDF or DOCX format, and I will reply with your ATS analysis."
    )

    await whatsapp_client.send_message(to, text)


async def send_status_message(to: str, user_session: dict):
    """Send user their current status and last analysis."""
    last_score = user_session.get("last_analysis")

    if last_score:
        text = (
            f"Your last ATS score is {last_score}/100.\n\n"
            "Send a new resume in PDF or DOCX format if you want a fresh analysis."
        )
    else:
        text = "You have not submitted a resume yet. Please send your CV in PDF or DOCX format to get started."

    await whatsapp_client.send_message(to, text)


async def send_analysis_results(to: str, analysis: dict):
    """Send comprehensive analysis results to user."""
    ats_score = analysis.get("ats_score", 0)
    strengths = analysis.get("strengths", [])
    weaknesses = analysis.get("weaknesses", [])
    recommendations = analysis.get("recommendations", [])

    score_label = "Strong" if ats_score >= 70 else "Moderate" if ats_score >= 50 else "Needs improvement"

    message = (
        "Resume analysis complete.\n\n"
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
        message += "- No major issues detected in the initial ATS check\n"

    if recommendations:
        message += "\nTop recommendations:\n"
        for rec in recommendations[:2]:
            message += f"- {rec}\n"

    message += "\nSend another CV anytime for a new ATS analysis."

    await whatsapp_client.send_message(to, message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
