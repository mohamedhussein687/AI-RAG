from app.schemas import UserContext


def is_authorized_payload(payload: dict, user_context: UserContext) -> bool:
    if str(payload.get("tenant_id")) != user_context.tenant_id:
        return False
    project_id = payload.get("project_id")
    if project_id and str(project_id) not in set(user_context.project_ids):
        return False
    required = set(payload.get("permissions") or [])
    return required.issubset(set(user_context.permissions))
