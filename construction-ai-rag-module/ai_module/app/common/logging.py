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


def route_log_fields(
    *,
    request_id: str | None = None,
    normalized_message: str | None = None,
    route: str | None = None,
    entity: str | None = None,
    operation: str | None = None,
    selected_table: str | None = None,
    selected_columns: list[str] | None = None,
    filters: object | None = None,
    sort: object | None = None,
    limit: int | None = None,
    validation_result: str | None = None,
    error_class: str | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "request_id": request_id or "none",
        "normalized_message": (normalized_message or "")[:300],
        "route": route or "none",
        "entity": entity or "none",
        "operation": operation or "none",
        "selected_table": selected_table or "none",
        "selected_columns": selected_columns or [],
        "filters": redact(filters or []),
        "sort": redact(sort or []),
        "limit": limit if limit is not None else "none",
        "validation_result": validation_result or "none",
        "error_class": error_class or "none",
    }
    return fields
