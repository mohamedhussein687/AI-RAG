import logging
from collections.abc import Mapping

SECRET_KEYS = {"authorization", "ai_module_token", "spring_gateway_token", "llm_api_key", "token", "api_key", "password"}


def redact(value):
    if isinstance(value, Mapping):
        return {k: ("[REDACTED]" if str(k).lower() in SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
