from dataclasses import dataclass

from .normalization import ArabicNormalizer


@dataclass(frozen=True)
class RouteDecision:
    route: str
    intent: str = ""
    answer: str = ""


class MessageRouter:
    THANKS = ("شكرا", "شكرًا", "متشكر", "تسلم", "thanks", "thank you")
    ACK = ("تمام", "حاضر", "اوكي", "أوكي", "ok", "okay")
    GREETING = ("السلام عليكم", "مرحبا", "اهلا", "أهلا", "hello", "hi")
    GOODBYE = ("مع السلامه", "مع السلامة", "باي", "bye", "goodbye")
    WELLBEING = ("انت كويس", "انت بخير", "هل انت بخير", "عامل ايه", "ازيك", "إزيك", "how are you")
    IDENTITY = ("انت مين", "مين انت", "ما اسمك", "اسمك ايه", "what are you", "who are you")
    DATABASE_ACTIONS = (
        "اعرض", "عرض", "هات", "وريني", "اظهر", "ابحث", "دور", "فلتر", "صدر", "تصدير",
        "كم", "عدد", "show", "list", "count", "search", "filter", "export",
    )
    DATABASE_ENTITIES = (
        "عميل", "عملاء", "العملاء", "client", "clients", "customer", "customers",
        "مشروع", "مشاريع", "المشاريع", "project", "projects",
        "فاتوره", "فواتير", "invoice", "invoices",
        "مستخدم", "مستخدمين", "users",
    )
    def route(self, message: str, has_database_catalog: bool = False) -> RouteDecision:
        text = ArabicNormalizer.normalize(message)
        conversation = self._conversation(text)
        if conversation:
            return conversation
        return RouteDecision("qwen", "needs_model_understanding")

    def _conversation(self, text: str) -> RouteDecision | None:
        if self._matches_only_conversation(text, self.THANKS):
            return RouteDecision("conversational", "thanks", "العفو، تحت أمرك.")
        if self._matches_only_conversation(text, self.ACK):
            return RouteDecision("conversational", "ack", "تمام، تحت أمرك.")
        if self._matches_only_conversation(text, self.GREETING):
            return RouteDecision("conversational", "greeting", "وعليكم السلام، أهلاً بك. كيف أقدر أساعدك؟")
        if self._matches_only_conversation(text, self.GOODBYE):
            return RouteDecision("conversational", "goodbye", "مع السلامة، تحت أمرك في أي وقت.")
        if self._matches_only_conversation(text, self.WELLBEING):
            return RouteDecision("conversational", "wellbeing", "أنا بخير، شكرًا لسؤالك. كيف أقدر أساعدك؟")
        if self._matches_only_conversation(text, self.IDENTITY):
            return RouteDecision("conversational", "identity", "أنا مساعد ORBIT AI، شغال على مشروع ORBIT، وأقدر أساعدك في قراءة وتحليل بيانات المشروع حسب الصلاحيات المتاحة.")
        return None

    def _matches_only_conversation(self, text: str, terms: tuple[str, ...]) -> bool:
        if not any(ArabicNormalizer.contains_term(text, term) for term in terms):
            return False
        if self.looks_like_database_request(text):
            return False
        return True

    def looks_like_database_request(self, message_or_normalized: str) -> bool:
        text = ArabicNormalizer.normalize(message_or_normalized)
        has_action = any(ArabicNormalizer.contains_term(text, term) for term in self.DATABASE_ACTIONS)
        has_entity = any(ArabicNormalizer.contains_term(text, term) for term in self.DATABASE_ENTITIES)
        return has_action and has_entity

    @staticmethod
    def _looks_too_short(text: str) -> bool:
        return len(text.split()) <= 1 and len(text) < 8
