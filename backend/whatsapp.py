"""
WhatsApp Cloud API client for messaging operations.
Handles webhook verification and message sending.
"""
from typing import Optional
import httpx
import logging

from .config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """
    Client for Meta WhatsApp Cloud API.
    Handles all messaging operations.
    """

    def __init__(self):
        self.token = settings.WHATSAPP_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = "v18.0"
        self.base_url = (
            f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        )

    @property
    def is_configured(self) -> bool:
        """Return True when WhatsApp credentials are available."""
        return bool(self.token and self.phone_number_id and settings.WHATSAPP_VERIFY_TOKEN)

    def verify_webhook(
        self,
        mode: str,
        token: str,
        challenge: str,
    ) -> Optional[str]:
        """
        Verify webhook subscription with Meta.
        Returns challenge on success, None on failure.
        """
        expected_token = settings.WHATSAPP_VERIFY_TOKEN.strip()

        logger.info(f"Webhook verify mode={mode}")
        logger.info(f"Token received='{token}'")
        logger.info(f"Token expected='{expected_token}'")

        if (
            mode == "subscribe"
            and token
            and token.strip() == expected_token
        ):
            logger.info("Webhook verified successfully")
            return challenge

        logger.warning("Webhook verification failed")
        return None

    async def send_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
    ) -> bool:
        """
        Send text message to WhatsApp user.
        Returns True on success.
        """
        if not self.is_configured:
            logger.warning("WhatsApp send skipped because credentials are not configured")
            return False

        url = f"{self.base_url}/messages"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    logger.info(f"Message sent to {to}")
                    return True

                logger.error(
                    f"Send failed: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def send_interactive_message(
        self,
        to: str,
        body_text: str,
        buttons: list,
    ) -> bool:
        """
        Send interactive button message.
        """
        if not self.is_configured:
            logger.warning("Interactive send skipped because credentials are not configured")
            return False

        url = f"{self.base_url}/messages"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn["id"],
                                "title": btn["title"],
                            },
                        }
                        for btn in buttons
                    ]
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Interactive message error: {e}")
            return False

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """
        Download media file from WhatsApp servers.
        Returns file content as bytes.
        """
        if not self.is_configured:
            logger.warning("Media download skipped because credentials are not configured")
            return None

        media_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"

        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(media_url, headers=headers)

                if response.status_code != 200:
                    logger.error(
                        f"Media metadata fetch failed: {response.text}"
                    )
                    return None

                media_data = response.json()
                download_url = media_data.get("url")

                if not download_url:
                    return None

                file_response = await client.get(
                    download_url,
                    headers=headers,
                )

                if file_response.status_code == 200:
                    return file_response.content

                return None

        except Exception as e:
            logger.error(f"Media download error: {e}")
            return None

    async def mark_as_read(self, message_id: str) -> bool:
        """
        Mark message as read.
        """
        if not self.is_configured:
            logger.warning("Mark as read skipped because credentials are not configured")
            return False

        url = f"{self.base_url}/messages"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Mark as read error: {e}")
            return False


# Singleton instance
whatsapp = WhatsAppClient()
