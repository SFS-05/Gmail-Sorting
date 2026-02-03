from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime, timedelta
from models import EmailScope
from config import get_settings
import logging
import base64
import time

settings = get_settings()
logger = logging.getLogger(__name__)


class GmailService:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        self.user_id = "me"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(HttpError),
    )
    def get_messages(self, scope: EmailScope, max_results: int = None) -> List[str]:
        max_results = max_results or settings.GMAIL_MAX_RESULTS
        query = self._build_query(scope)

        try:
            message_ids = []
            page_token = None

            while len(message_ids) < max_results:
                results = (
                    self.service.users()
                    .messages()
                    .list(
                        userId=self.user_id,
                        q=query,
                        maxResults=min(500, max_results - len(message_ids)),
                        pageToken=page_token,
                    )
                    .execute()
                )

                messages = results.get("messages", [])
                message_ids.extend([msg["id"] for msg in messages])

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

                time.sleep(0.1)  # Rate limiting

            logger.info(f"Retrieved {len(message_ids)} message IDs with scope {scope}")
            return message_ids[:max_results]

        except HttpError as e:
            logger.error(f"Gmail API error fetching messages: {e}")
            raise

    def _build_query(self, scope: EmailScope) -> str:
        if scope == EmailScope.UNREAD:
            return "is:unread"
        elif scope == EmailScope.INBOX:
            return "in:inbox"
        elif scope == EmailScope.RECENT:
            days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
            return f"after:{days_ago}"
        elif scope == EmailScope.ALL:
            return ""
        return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def get_message_detail(self, message_id: str) -> Optional[Dict]:
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format="full")
                .execute()
            )

            headers = {
                h["name"]: h["value"]
                for h in message["payload"].get("headers", [])
            }

            subject = headers.get("Subject", "")
            sender = headers.get("From", "")
            body = self._extract_body(message["payload"])

            return {
                "id": message_id,
                "subject": subject,
                "from": sender,
                "body": body,
                "snippet": message.get("snippet", ""),
                "labels": message.get("labelIds", []),
            }

        except HttpError as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            return None

    def _extract_body(self, payload: Dict) -> str:
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if part["body"].get("data"):
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                elif "parts" in part:
                    body = self._extract_body(part)
                    if body:
                        return body

        return ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_label(self, label_name: str) -> str:
        try:
            existing_labels = self.service.users().labels().list(userId=self.user_id).execute()
            for label in existing_labels.get("labels", []):
                if label["name"].lower() == label_name.lower():
                    logger.info(f"Label '{label_name}' already exists: {label['id']}")
                    return label["id"]

            label_object = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }

            created_label = (
                self.service.users()
                .labels()
                .create(userId=self.user_id, body=label_object)
                .execute()
            )

            logger.info(f"Created label '{label_name}': {created_label['id']}")
            return created_label["id"]

        except HttpError as e:
            logger.error(f"Error creating label '{label_name}': {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def apply_label(self, message_id: str, label_id: str) -> bool:
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()

            time.sleep(1.0 / settings.GMAIL_RATE_LIMIT_PER_SECOND)
            return True

        except HttpError as e:
            logger.error(f"Error applying label to message {message_id}: {e}")
            return False

    def batch_apply_labels(self, message_label_pairs: List[tuple]) -> int:
        success_count = 0
        for message_id, label_id in message_label_pairs:
            if self.apply_label(message_id, label_id):
                success_count += 1
        return success_count