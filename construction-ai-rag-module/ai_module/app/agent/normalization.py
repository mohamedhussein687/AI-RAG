import re


class ArabicNormalizer:
    TYPO_FIXES = {
        "اضافتة": "اضافته",
        "إضافتة": "اضافته",
        "أضافتة": "اضافته",
        "صاخب": "صاحب",
    }

    @classmethod
    def normalize(cls, value: str) -> str:
        text = value.strip()
        for wrong, right in cls.TYPO_FIXES.items():
            text = text.replace(wrong, right)
        text = text.lower()
        text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        text = text.replace("ى", "ي")
        text = text.replace("ة", "ه")
        text = re.sub(r"[؟?؛،,!.:]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def contains_term(cls, text: str, term: str) -> bool:
        normalized = cls.normalize(term)
        if not normalized:
            return False
        if len(normalized) <= 2 or " " not in normalized:
            arabic = re.search(r"[\u0600-\u06ff]", normalized) is not None
            prefix = r"(?:ال)?" if arabic and not normalized.startswith("ال") else ""
            return re.search(rf"(?<!\w){prefix}{re.escape(normalized)}(?!\w)", text) is not None
        return normalized in text
