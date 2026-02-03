from typing import Dict, Optional
from models import ModelMode
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
import joblib
import re
import logging

logger = logging.getLogger(__name__)


class EmailClassifier:
    CATEGORIES = {
        "work": {"keywords": ["meeting", "project", "deadline", "report", "team", "office"], "color": "#4285f4"},
        "personal": {"keywords": ["family", "friend", "dinner", "party", "birthday"], "color": "#34a853"},
        "promotion": {"keywords": ["sale", "discount", "offer", "deal", "promo", "coupon"], "color": "#fbbc04"},
        "spam": {"keywords": ["lottery", "winner", "urgent", "verify", "click here", "congratulations"], "color": "#ea4335"},
        "finance": {"keywords": ["invoice", "payment", "transaction", "bank", "credit", "debit"], "color": "#ab47bc"},
        "security": {"keywords": ["password", "security", "alert", "verify", "authentication", "login"], "color": "#000000"},
    }

    def __init__(self, mode: ModelMode = ModelMode.FAST):
        self.mode = mode    
        self.model = None
        if mode in [ModelMode.BALANCED, ModelMode.ACCURATE]:
            self._load_or_train_model()

    def _load_or_train_model(self):
        try:
            self.model = joblib.load("email_classifier.pkl")
            logger.info("Loaded pre-trained classifier model")
        except FileNotFoundError:
            logger.warning("No pre-trained model found, using rule-based classification")
            self.model = None

    def classify(self, subject: str, body: str, sender: str) -> str:
        text = f"{subject} {body} {sender}".lower()

        # Rule-based classification first (fast and deterministic)
        category = self._rule_based_classify(text)
        if category:
            return category

        # ML fallback for balanced/accurate modes
        if self.mode != ModelMode.FAST and self.model:
            try:
                category = self._ml_classify(text)
                if category:
                    return category
            except Exception as e:
                logger.error(f"ML classification failed: {e}")

        # Default fallback
        return "personal"

    def _rule_based_classify(self, text: str) -> Optional[str]:
        # Spam detection (highest priority)
        spam_score = sum(
            1 for keyword in self.CATEGORIES["spam"]["keywords"] if keyword in text
        )
        if spam_score >= 2:
            return "spam"

        # Security alerts
        security_score = sum(
            1 for keyword in self.CATEGORIES["security"]["keywords"] if keyword in text
        )
        if security_score >= 2:
            return "security"

        # Finance
        if any(keyword in text for keyword in self.CATEGORIES["finance"]["keywords"]):
            return "finance"

        # Promotional
        promo_score = sum(
            1 for keyword in self.CATEGORIES["promotion"]["keywords"] if keyword in text
        )
        if promo_score >= 2:
            return "promotion"

        # Work-related
        work_score = sum(
            1 for keyword in self.CATEGORIES["work"]["keywords"] if keyword in text
        )
        if work_score >= 2:
            return "work"

        return None

    def _ml_classify(self, text: str) -> Optional[str]:
        if not self.model:
            return None

        try:
            prediction = self.model.predict([text])[0]
            return prediction
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
            return None

    @staticmethod
    def get_category_info(category: str) -> Dict:
        return EmailClassifier.CATEGORIES.get(
            category, {"keywords": [], "color": "#718096"}
        )