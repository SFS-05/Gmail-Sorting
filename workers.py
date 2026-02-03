from celery import Celery, Task
from sqlalchemy.orm import Session
from models import Job, User, JobStatus, ModelMode, EmailScope
from database import get_db_context
from auth import get_google_credentials, refresh_google_token
from gmail_service import GmailService
from classifier import EmailClassifier
from config import get_settings
import logging
import uuid
from datetime import datetime

settings = get_settings()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "gmail_sorter",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)


class DatabaseTask(Task):
    _db = None

    @property
    def db(self) -> Session:
        if self._db is None:
            raise RuntimeError("Database session not initialized")
        return self._db


@celery_app.task(bind=True, base=DatabaseTask, name="workers.classify_emails")
def classify_emails_task(
    self,
    job_id: str,
    user_id: str,
    mode: str,
    scope: str,
):
    with get_db_context() as db:
        self._db = db
        job = db.query(Job).filter(Job.id == job_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if not job or not user:
            logger.error(f"Job {job_id} or User {user_id} not found")
            return

        try:
            job.status = JobStatus.RUNNING
            job.celery_task_id = self.request.id
            db.commit()

            # Get Gmail credentials
            credentials = refresh_google_token(user, db)
            gmail = GmailService(credentials)

            # Initialize classifier
            classifier = EmailClassifier(mode=ModelMode(mode))

            # Get message IDs
            message_ids = gmail.get_messages(
                scope=EmailScope(scope), max_results=settings.GMAIL_MAX_RESULTS
            )
            job.total_emails = len(message_ids)
            db.commit()

            logger.info(f"Processing {len(message_ids)} emails for job {job_id}")

            # Create labels
            label_cache = {}
            for category in EmailClassifier.CATEGORIES.keys():
                label_id = gmail.create_label(f"Cloudidian/{category.capitalize()}")
                label_cache[category] = label_id

            # Process emails
            category_counts = {cat: 0 for cat in EmailClassifier.CATEGORIES.keys()}
            errors = []

            for idx, message_id in enumerate(message_ids):
                try:
                    message_detail = gmail.get_message_detail(message_id)
                    if not message_detail:
                        errors.append({"message_id": message_id, "error": "Failed to fetch"})
                        job.error_count += 1
                        continue

                    category = classifier.classify(
                        message_detail["subject"],
                        message_detail["body"],
                        message_detail["from"],
                    )

                    label_id = label_cache.get(category)
                    if label_id:
                        success = gmail.apply_label(message_id, label_id)
                        if success:
                            category_counts[category] += 1
                        else:
                            errors.append({"message_id": message_id, "error": "Failed to apply label"})
                            job.error_count += 1

                    job.processed_emails = idx + 1
                    job.category_counts = category_counts

                    if (idx + 1) % 10 == 0:
                        db.commit()
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "processed": idx + 1,
                                "total": len(message_ids),
                                "category_counts": category_counts,
                            },
                        )

                except Exception as e:
                    logger.error(f"Error processing message {message_id}: {e}")
                    errors.append({"message_id": message_id, "error": str(e)})
                    job.error_count += 1

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.errors = errors[:100]  # Store max 100 errors
            db.commit()

            logger.info(f"Job {job_id} completed. Processed: {job.processed_emails}, Errors: {job.error_count}")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            job.status = JobStatus.FAILED
            job.errors = [{"error": str(e)}]
            db.commit()
            raise