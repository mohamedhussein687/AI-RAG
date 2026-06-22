import re
from typing import Any

from .normalization import ArabicNormalizer


class SchemaAwarePlanner:
    PROJECT_TERMS = ("مشروع", "مشاريع", "مشروعات", "project", "projects")
    CLIENT_TERMS = ("عميل", "عملاء", "العملاء", "client", "clients", "customer", "customers")
    USER_TERMS = ("مستخدم", "مستخدمين", "المستخدمين", "حساب", "حسابات", "account", "accounts", "users", "user", "system users")
    ADMIN_TERMS = ("ادمن", "الأدمن", "الادمن", "مسؤول", "المسؤول", "المسؤولين", "مدير النظام", "مديري النظام", "admin", "admins", "administrator", "super admin", "owner")
    LIST_TERMS = ("اعرض", "عرض", "هات", "وريني", "اظهر", "show", "list", "display")
    NAME_TERMS = ("اسم", "اسماء", "الاسماء", "name", "names")
    COUNT_TERMS = ("كم", "عدد", "how many", "count", "total")
    LATEST_TERMS = ("اخر", "آخر", "latest", "last", "newest")
    ADDED_TERMS = ("اضافته", "مضاف", "added", "created")
    DETAIL_TERMS = ("معلومات", "تفاصيل", "بيانات", "details", "detail", "info", "information", "data")
    CODE_TERMS = ("صاحب الكود", "بالكود", "كود المشروع", "رقم المشروع", "project code")
    DELAY_TERMS = ("متاخر", "متاخرين", "متاخره", "تاخير", "delayed", "late")
    DELIVERY_TERMS = ("تسليم", "delivery", "deadline", "end date")
    ACTIVE_TERMS = ("نشط", "نشطه", "نشطة", "نشطين", "active")
    STOPPED_TERMS = ("متوقف", "متوقفه", "متوقفة", "stopped", "paused")
    FINISHED_TERMS = ("منتهي", "منتهيه", "منتهية", "completed", "delivered", "finished")
    ADMIN_TABLE_CANDIDATES = ("admins", "users", "app_users", "organization_employees", "employees", "roles", "user_roles", "model_has_roles", "role_user")
    ADMIN_FLAG_COLUMNS = ("is_admin", "is_super_admin", "admin", "owner", "is_owner", "super_admin")
    ADMIN_ROLE_COLUMNS = ("role", "role_id", "type", "account_type", "user_type", "guard_name", "name")
    ADMIN_DISPLAY_COLUMNS = ("name", "full_name", "username", "email", "role", "type", "account_type", "user_type", "is_admin", "is_super_admin", "admin", "created_at", "updated_at")

    def plan(self, message: str, catalog: dict[str, Any], max_rows: int) -> dict[str, Any] | None:
        text = ArabicNormalizer.normalize(message)
        if self._is_admin_question(text):
            return self._admin_plan(catalog, max_rows)
        if self._is_client_question(text):
            return self._client_plan(text, catalog, max_rows)
        if self._is_user_question(text):
            return self._user_plan(text, catalog, max_rows)
        if not self._is_project_question(text):
            return None
        project = self._project_entity(catalog)
        if not project or project.get("table") != "projects":
            return None
        if self._is_delayed(text):
            return self._delayed_plan(text, project, max_rows)
        if self._is_latest(text):
            return self._latest_plan(project)
        if self._is_details(text):
            return self._details_plan(message, text, project)
        if self._is_count(text):
            return self._count_plan(text, project, max_rows)
        status = self._status_filter_value(text)
        if status:
            return self._status_list_plan(status, project, max_rows)
        return None

    def _client_plan(self, text: str, catalog: dict[str, Any], max_rows: int) -> dict[str, Any] | None:
        table = self._table(catalog, "clients")
        if not table:
            return None
        if self._is_count(text):
            return self._tool_plan("count_clients", "count", "clients", limit=min(max_rows, 20))
        if self._is_list(text) or any(ArabicNormalizer.contains_term(text, term) for term in self.NAME_TERMS):
            name_column = self._first_column(table, ("name", "client_name", "title", "full_name"))
            columns = [name_column] if name_column else []
            return self._tool_plan("list_clients", "list", "clients", columns=columns, limit=min(max_rows, 20), extra={"entities": ["clients"], "fields": columns})
        return None

    def _user_plan(self, text: str, catalog: dict[str, Any], max_rows: int) -> dict[str, Any] | None:
        table = self._table(catalog, "users")
        if not table:
            return None
        if self._is_count(text):
            return self._tool_plan("count_users", "count", "users", limit=min(max_rows, 20), extra={"entities": ["users"]})
        if self._is_details(text):
            lookup_value = self._user_lookup_value(text)
            if lookup_value:
                name_column = self._first_column(table, ("name", "full_name", "username", "email"))
                if not name_column:
                    return self._configuration_error("لا يوجد حقل اسم للمستخدمين في خريطة البيانات الحالية.", ["users.name"])
                columns = [
                    column for column in [
                        self._first_column(table, ("name", "full_name", "username", "email")),
                        self._first_column(table, ("email",)),
                        self._first_column(table, ("type", "user_type", "account_type")),
                        self._first_column(table, ("status", "is_active")),
                        self._first_column(table, ("created_at",)),
                        self._first_column(table, ("updated_at",)),
                    ] if column
                ]
                columns = list(dict.fromkeys(columns))
                return self._tool_plan(
                    "user_details",
                    "select",
                    "users",
                    columns=columns,
                    filters=[{"column": name_column, "operator": "contains", "value": lookup_value}],
                    limit=1,
                    extra={"entities": ["users"], "fields": columns, "lookup_value": lookup_value},
                )
        if self._is_list(text) or any(ArabicNormalizer.contains_term(text, term) for term in self.NAME_TERMS):
            name_column = self._first_column(table, ("name", "full_name", "username", "email"))
            columns = [name_column] if name_column else []
            return self._tool_plan("list_users", "list", "users", columns=columns, limit=min(max_rows, 20), extra={"entities": ["users"], "fields": columns})
        return None

    def _admin_plan(self, catalog: dict[str, Any], max_rows: int) -> dict[str, Any] | None:
        table_name, table = self._first_existing_table(catalog, self.ADMIN_TABLE_CANDIDATES)
        if not table_name or not table:
            return None
        columns = self._available_columns(table, self.ADMIN_DISPLAY_COLUMNS) or self._first_safe_columns(table, limit=6)
        filters = self._admin_filters(table, table_name)
        if not filters and table_name not in {"admins", "roles"}:
            return self._configuration_error(
                "لا أستطيع تحديد الأدمن لأن خريطة البيانات لا تحتوي على حقل دور أو صلاحية واضح.",
                [f"{table_name}.role", f"{table_name}.type", f"{table_name}.is_admin"],
            )
        return self._tool_plan(
            "find_admin_users",
            "select",
            table_name,
            columns=columns,
            filters=filters,
            limit=min(max_rows, 20),
            extra={"entities": ["admins", "users"], "fields": columns},
        )

    def _count_plan(self, text: str, project: dict[str, Any], max_rows: int) -> dict[str, Any]:
        filters = []
        status = self._status_filter_value(text)
        status_field = self._status_field(project)
        if status and status_field:
            filters.append({"column": status_field, "operator": "eq", "value": status})
        return self._tool_plan("project_count", "count", project["table"], filters=filters, limit=min(max_rows, 20))

    def _latest_plan(self, project: dict[str, Any]) -> dict[str, Any]:
        latest = self._report(project, "latest_project")
        if not latest or not latest.get("enabled"):
            missing = latest.get("missing_fields", ["created_at_or_sequential_id"]) if isinstance(latest, dict) else ["latest_project"]
            return self._configuration_error("لا يوجد حقل مناسب لتحديد آخر مشروع تم إضافته.", missing)
        return self._tool_plan(
            "latest_project",
            "select",
            latest["table"],
            columns=latest.get("display_fields", []),
            order_by={"column": latest["order_field"], "direction": "desc"},
            limit=1,
        )

    def _details_plan(self, message: str, text: str, project: dict[str, Any]) -> dict[str, Any] | None:
        details = self._report(project, "project_details")
        if not details or not details.get("enabled"):
            missing = details.get("missing_fields", ["project_details"]) if isinstance(details, dict) else ["project_details"]
            return self._configuration_error("لا أستطيع جلب تفاصيل المشروع لأن خريطة البيانات ناقصة.", missing)
        code = self._project_code(message)
        if code:
            code_fields = [field for field in details.get("code_fields", []) if isinstance(field, str)]
            if not code_fields:
                return self._configuration_error("لا يوجد حقل كود للمشاريع في الـ schema الحالية.", ["project_code"])
            return self._tool_plan(
                "project_details",
                "details",
                details["table"],
                columns=details.get("display_fields", []),
                filters=[{"column": code_fields[0], "operator": "code_equals_normalized", "value": code}],
                limit=1,
            )
        value = self._project_lookup_value(message)
        if not value:
            return None
        return self._tool_plan(
            "project_details",
            "details",
            details["table"],
            columns=details.get("display_fields", []),
            limit=1,
            extra={"lookup_value": value, "lookup_fields": details.get("lookup_fields", [])},
        )

    def _delayed_plan(self, text: str, project: dict[str, Any], max_rows: int) -> dict[str, Any]:
        report = self._report(project, "delayed_projects_report")
        if not report or not report.get("enabled"):
            missing = report.get("missing_fields", ["delayed_projects_report"]) if isinstance(report, dict) else ["delayed_projects_report"]
            return self._configuration_error("لا أستطيع حساب المشاريع المتأخرة لأن حقول التأخير غير مكتملة في خريطة البيانات.", missing)
        operation = "count" if self._is_count(text) and not self._requested_limit(text) else "select"
        filters = [
            {"column": report["deadline_field"], "operator": "lt", "value": "today"},
            {"column": report["completion_field"], "operator": "not_completed", "value": False},
        ]
        if operation == "count":
            return self._tool_plan("delayed_projects_count", "count", report["table"], filters=filters, limit=min(max_rows, 20))
        return self._tool_plan(
            "delayed_projects_report",
            "select",
            report["table"],
            columns=list(dict.fromkeys([report.get("title_field"), report.get("status_field"), report.get("deadline_field"), report.get("completion_field"), "actual_delivery_date", report.get("order_field")])),
            filters=filters,
            order_by={"column": report["order_field"], "direction": "desc"},
            limit=self._requested_limit(text) or int(report.get("default_limit", 4)),
        )

    def _status_list_plan(self, status: str, project: dict[str, Any], max_rows: int) -> dict[str, Any] | None:
        status_field = self._status_field(project)
        details = self._report(project, "project_details") or {}
        if not status_field:
            return self._configuration_error("لا يوجد حقل حالة للمشاريع في خريطة البيانات الحالية.", ["status"])
        columns = details.get("display_fields", [])
        return self._tool_plan(
            "project_status_list",
            "select",
            project["table"],
            columns=columns,
            filters=[{"column": status_field, "operator": "eq", "value": status}],
            limit=min(max_rows, 20),
        )

    def _is_client_question(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.CLIENT_TERMS)

    def _is_user_question(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.USER_TERMS)

    def _is_admin_question(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.ADMIN_TERMS)

    def _is_list(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.LIST_TERMS)

    def _tool_plan(self, intent: str, operation: str, table: str, *, columns=None, filters=None, order_by=None, limit=20, extra=None) -> dict[str, Any]:
        plan = {
            "intent": intent,
            "operation": operation,
            "table": table,
            "columns": [c for c in (columns or []) if c],
            "filters": filters or [],
            "limit": min(max(int(limit), 1), 20),
        }
        if order_by:
            plan["order_by"] = order_by
        if extra:
            plan.update(extra)
        return {
            "type": "tool_calls",
            "intent": intent,
            "reason": "schema_aware_planner",
            "tool_calls": [{"id": "db_1", "tool": "database_query", "plan": plan}],
            "local_rag_results": [],
        }

    @staticmethod
    def _configuration_error(answer: str, missing: list[Any]) -> dict[str, Any]:
        return {
            "type": "unsupported",
            "route": "unsupported",
            "intent": "configuration_error",
            "reason": "missing_schema_mapping",
            "answer": answer + (" الحقول الناقصة: " + ", ".join(map(str, missing)) if missing else ""),
        }

    def _project_entity(self, catalog: dict[str, Any]) -> dict[str, Any] | None:
        for entity in catalog.get("domain_entities", []):
            if entity.get("entity") == "projects" and entity.get("table") == "projects":
                return entity
        return None

    def _table(self, catalog: dict[str, Any], name: str) -> dict[str, Any] | None:
        for table in catalog.get("tables", []):
            if table.get("name") == name:
                return table
        for table in catalog.get("tables_index", []):
            if table.get("name") == name:
                return table
        return None

    def _first_existing_table(self, catalog: dict[str, Any], names: tuple[str, ...]) -> tuple[str | None, dict[str, Any] | None]:
        for name in names:
            table = self._table(catalog, name)
            if table:
                return name, table
        return None, None

    @staticmethod
    def _first_column(table: dict[str, Any], names: tuple[str, ...]) -> str | None:
        raw_columns = table.get("columns", [])
        columns = []
        for column in raw_columns:
            if isinstance(column, dict):
                columns.append(str(column.get("name", "")))
            else:
                columns.append(str(column))
        for name in names:
            if name in columns:
                return name
        return None

    def _available_columns(self, table: dict[str, Any], names: tuple[str, ...]) -> list[str]:
        return [name for name in names if self._first_column(table, (name,))]

    def _first_safe_columns(self, table: dict[str, Any], *, limit: int) -> list[str]:
        result: list[str] = []
        for column in table.get("columns", []):
            if isinstance(column, dict):
                name = str(column.get("name") or "")
                if column.get("sensitive") or column.get("is_sensitive"):
                    continue
            else:
                name = str(column)
            if name and name not in result:
                result.append(name)
            if len(result) >= limit:
                break
        return result

    def _admin_filters(self, table: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
        if table_name == "admins":
            return []
        for column in self.ADMIN_FLAG_COLUMNS:
            if self._first_column(table, (column,)):
                return [{"column": column, "operator": "eq", "value": 1}]
        for column in self.ADMIN_ROLE_COLUMNS:
            if self._first_column(table, (column,)):
                return [
                    {
                        "column": column,
                        "operator": "in",
                        "value": ["admin", "administrator", "super_admin", "super admin", "owner", 1],
                    }
                ]
        return []

    @staticmethod
    def _report(project: dict[str, Any], name: str) -> dict[str, Any] | None:
        value = project.get(name)
        return value if isinstance(value, dict) else None

    def _status_field(self, project: dict[str, Any]) -> str | None:
        report = self._report(project, "delayed_projects_report")
        if report and report.get("status_field"):
            return str(report["status_field"])
        return None

    def _status_filter_value(self, text: str) -> str | None:
        if any(ArabicNormalizer.contains_term(text, term) for term in self.ACTIVE_TERMS):
            return "active"
        if any(ArabicNormalizer.contains_term(text, term) for term in self.STOPPED_TERMS):
            return "stopped"
        if any(ArabicNormalizer.contains_term(text, term) for term in self.FINISHED_TERMS):
            return "completed"
        return None

    def _is_project_question(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.PROJECT_TERMS)

    def _is_count(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.COUNT_TERMS)

    def _is_latest(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.LATEST_TERMS) and (
            any(ArabicNormalizer.contains_term(text, term) for term in self.ADDED_TERMS) or "latest" in text or "last" in text
        )

    def _is_details(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.DETAIL_TERMS + self.CODE_TERMS)

    def _is_delayed(self, text: str) -> bool:
        return any(ArabicNormalizer.contains_term(text, term) for term in self.DELAY_TERMS) and (
            any(ArabicNormalizer.contains_term(text, term) for term in self.DELIVERY_TERMS) or self._is_count(text) or self._requested_limit(text)
        )

    def _requested_limit(self, text: str) -> int | None:
        match = re.search(r"\b([1-9][0-9]?)\b", text)
        if match:
            return min(int(match.group(1)), 20)
        if "اربع" in text or "اربعه" in text:
            return 4
        return None

    def _project_lookup_value(self, message: str) -> str | None:
        cleaned = re.sub(r"[؟?؛،,]", " ", message).strip()
        for pattern in (r"(?:المشروع|مشروع|project)\s+([A-Za-z0-9_-]{2,80})", r"([A-Za-z]+[0-9][A-Za-z0-9_-]{1,80})"):
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _user_lookup_value(self, text: str) -> str | None:
        cleaned = re.sub(r"[؟?؛،,]", " ", text).strip()
        patterns = (
            r"(?:المستخدم|مستخدم|user|account|الحساب|حساب)\s+(.{2,120})$",
            r"(?:بيانات|معلومات|تفاصيل)\s+(?:المستخدم|مستخدم|user|account|الحساب|حساب)\s+(.{2,120})$",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip()
            value = re.sub(r"\s+", " ", value)
            if value:
                return value
        return None

    def _project_code(self, message: str) -> str | None:
        text = ArabicNormalizer.normalize(message)
        if not any(ArabicNormalizer.contains_term(text, term) for term in self.CODE_TERMS):
            return None
        pattern = r"([A-Za-z][A-Za-z0-9]*(?:\s*[-–—]\s*[A-Za-z0-9]+){2,})"
        match = re.search(pattern, message, re.IGNORECASE)
        if not match:
            match = re.search(r"([A-Za-z0-9]{2,}(?:[\s_-]+[A-Za-z0-9]{2,}){1,})", message, re.IGNORECASE)
        if not match:
            return None
        raw = match.group(1).strip()
        code = re.sub(r"\s*[-–—]\s*", "-", raw)
        code = re.sub(r"\s+", "-", code).strip("-").lower()
        if not re.search(r"[a-z]", code) or not re.search(r"\d", code):
            return None
        return code
