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
    RAG = ("ازاي", "إزاي", "how to", "policy", "سياسه", "procedure", "اجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
    BUSINESS = (
        "مشروع", "مشاريع", "مشروعات", "project", "projects", "عميل", "عملاء", "client", "customer",
        "فاتوره", "فواتير", "invoice", "payment", "مدفوعات", "مستخدم", "users", "كم", "عدد",
        "اخر", "latest", "تفاصيل", "معلومات", "بيانات", "متاخر", "تاخير"
    )

    def route(self, message: str, has_database_catalog: bool) -> RouteDecision:
        text = ArabicNormalizer.normalize(message)
        conversation = self._conversation(text)
        if conversation:
            return conversation
        if any(ArabicNormalizer.contains_term(text, term) for term in self.RAG):
            return RouteDecision("rag_search", "document_or_policy")
        if has_database_catalog and any(ArabicNormalizer.contains_term(text, term) for term in self.BUSINESS):
            return RouteDecision("database_query", "business_data")
        if self._looks_too_short(text):
            return RouteDecision("clarification", "missing_information", "هل يمكنك توضيح البيانات أو المستندات المطلوبة؟")
        return RouteDecision("unsupported", "unknown", "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة.")

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
        return not any(ArabicNormalizer.contains_term(text, term) for term in self.BUSINESS + self.RAG)

    @staticmethod
    def _looks_too_short(text: str) -> bool:
        return len(text.split()) <= 1 and len(text) < 8
