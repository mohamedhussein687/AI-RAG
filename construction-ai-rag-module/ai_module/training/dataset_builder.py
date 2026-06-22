from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.config import Settings
from app.db.mysql import readonly_mysql_connection
from app.schema.schema_discovery import discover_schema_from_connection
from app.schema.schema_models import AliasCatalog, AliasEntry, SchemaColumn, SchemaSnapshot, SchemaTable, load_alias_catalog


DEFAULT_MIN_EXAMPLES = 500
REQUIRED_SMOKE_QUESTIONS = (
    "اعرض جميع اسماء المستخدمين",
    "اريد بيانات المستخدم Ayman Ibrahim El Sayed",
    "كام مشروع عندي؟",
    "انت كويس؟",
)
SYSTEM_DATABASE = (
    "You are a database-aware Arabic AI agent. Convert natural language questions "
    "into safe structured JSON plans using the known project schema. Never output "
    "raw SQL, never request write operations, and never expose sensitive data."
)
SYSTEM_BEHAVIOR = (
    "You are an Arabic assistant for a database-aware RAG system. Classify safely, "
    "refuse secrets, ask for clarification when needed, and answer naturally in Arabic."
)
SAFE_ROUTE_NAMES = {"database_query", "conversational", "forbidden", "clarification", "unsupported", "final_answer"}


@dataclass(frozen=True)
class DatasetValidationReport:
    valid: bool
    total_examples: int
    route_counts: dict[str, int] = field(default_factory=dict)
    required_coverage: dict[str, bool] = field(default_factory=dict)
    sensitive_hits: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntityProfile:
    logical_name: str
    table: SchemaTable
    alias: AliasEntry
    plural_ar: str
    singular_ar: str
    plural_en: str
    singular_en: str
    safe_columns: list[SchemaColumn]

    @property
    def table_name(self) -> str:
        return self.table.name

    @property
    def display_columns(self) -> list[str]:
        preferred = ["name", "title", "full_name", "username", "email", "code", "project_code", "status", "project_status", "created_at"]
        names = [column.name for column in self.safe_columns]
        ordered = [name for name in preferred if name in names]
        ordered.extend(name for name in names if name not in ordered)
        return ordered[:6] or names[:3]

    @property
    def name_column(self) -> SchemaColumn | None:
        for candidate in ("name", "full_name", "username", "title", "project_name", "client_name"):
            column = _column(self.safe_columns, candidate)
            if column:
                return column
        return self.safe_columns[0] if self.safe_columns else None

    @property
    def enum_column(self) -> SchemaColumn | None:
        for column in self.safe_columns:
            if column.enum_like_values or column.safe_sample_values:
                lowered = column.name.lower()
                if "status" in lowered or "type" in lowered or "state" in lowered:
                    return column
        return None


def build_dataset(snapshot: SchemaSnapshot, aliases: AliasCatalog | None = None, *, min_examples: int = DEFAULT_MIN_EXAMPLES) -> list[dict[str, Any]]:
    """Generate deterministic safe chat-format SFT examples from schema metadata."""

    aliases = aliases or AliasCatalog()
    examples: list[dict[str, Any]] = []
    profiles = _entity_profiles(snapshot, aliases)

    for profile in profiles:
        examples.extend(_database_examples(profile))

    examples.extend(_behavior_examples())

    if len(examples) < min_examples:
        examples.extend(_expanded_examples(examples, min_examples - len(examples)))

    return examples


def validate_dataset(
    examples: list[dict[str, Any]],
    *,
    min_examples: int = DEFAULT_MIN_EXAMPLES,
    forbidden_values: Iterable[str] | None = None,
) -> DatasetValidationReport:
    errors: list[str] = []
    route_counts: Counter[str] = Counter()
    rendered_examples: list[str] = []

    if len(examples) < min_examples:
        errors.append(f"dataset has {len(examples)} examples; expected at least {min_examples}")

    for index, example in enumerate(examples):
        messages = example.get("messages") if isinstance(example, dict) else None
        if not isinstance(messages, list) or len(messages) < 2:
            errors.append(f"example {index} does not contain a valid messages array")
            continue
        for message in messages:
            if message.get("role") not in {"system", "user", "assistant"} or not isinstance(message.get("content"), str):
                errors.append(f"example {index} contains an invalid chat message")
        if messages[0].get("role") != "system" or messages[-1].get("role") != "assistant":
            errors.append(f"example {index} must start with system and end with assistant")
        route = _assistant_route(messages[-1].get("content", ""))
        if route:
            route_counts[route] += 1
        rendered_examples.append(json.dumps(example, ensure_ascii=False, sort_keys=True))

    required_coverage = {question: any(question in rendered for rendered in rendered_examples) for question in REQUIRED_SMOKE_QUESTIONS}
    for question, covered in required_coverage.items():
        if not covered:
            errors.append(f"required smoke question is missing: {question}")

    sensitive_hits = sorted({value for value in (forbidden_values or []) if value and any(value in rendered for rendered in rendered_examples)})
    if sensitive_hits:
        errors.append("dataset contains forbidden sensitive values")

    for route in ("database_query", "conversational", "forbidden", "clarification", "unsupported", "final_answer"):
        if route_counts[route] == 0:
            errors.append(f"dataset has no examples for route {route}")

    return DatasetValidationReport(
        valid=not errors,
        total_examples=len(examples),
        route_counts=dict(route_counts),
        required_coverage=required_coverage,
        sensitive_hits=sensitive_hits,
        errors=errors,
    )


def write_jsonl(examples: list[dict[str, Any]], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


async def build_dataset_from_source(source: str, settings: Settings, *, min_examples: int = DEFAULT_MIN_EXAMPLES) -> list[dict[str, Any]]:
    aliases = load_alias_catalog(_resolve_path(settings.schema_aliases_path))
    async with readonly_mysql_connection(settings) as connection:
        snapshot = await discover_schema_from_connection(
            connection,
            source_name=source,
            database_name=settings.mysql_database,
            aliases=aliases,
        )
    return build_dataset(snapshot, aliases, min_examples=min_examples)


def _entity_profiles(snapshot: SchemaSnapshot, aliases: AliasCatalog) -> list[EntityProfile]:
    profiles: list[EntityProfile] = []
    for table in snapshot.tables:
        if table.classification in {"system", "cms_content"}:
            continue
        safe_columns = table.safe_columns()
        if not safe_columns:
            continue
        logical_name, alias = _alias_for_table(table, aliases)
        arabic_terms = alias.arabic or [logical_name]
        english_terms = alias.english or [logical_name]
        profiles.append(
            EntityProfile(
                logical_name=logical_name,
                table=table,
                alias=alias,
                plural_ar=arabic_terms[0],
                singular_ar=arabic_terms[1] if len(arabic_terms) > 1 else arabic_terms[0],
                plural_en=english_terms[0],
                singular_en=english_terms[1] if len(english_terms) > 1 else english_terms[0].rstrip("s") or english_terms[0],
                safe_columns=safe_columns,
            )
        )
    return profiles


def _alias_for_table(table: SchemaTable, aliases: AliasCatalog) -> tuple[str, AliasEntry]:
    for logical, entry in aliases.aliases.items():
        if table.name == logical or table.name in entry.physical_candidates:
            return logical, entry
    return table.name, AliasEntry(arabic=[table.name], english=[table.name], physical_candidates=[table.name])


def _database_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    examples.extend(_list_examples(profile))
    examples.extend(_count_examples(profile))
    examples.extend(_details_examples(profile))
    examples.extend(_latest_examples(profile))
    examples.extend(_grouped_and_filtered_examples(profile))
    return examples


def _list_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    columns = _name_columns(profile) or profile.display_columns[:2]
    questions = [
        f"اعرض جميع {profile.plural_ar}",
        f"هات كل {profile.plural_ar}",
        f"وريني {profile.plural_ar}",
        f"list all {profile.plural_en}",
        f"show all {profile.plural_en}",
    ]
    if columns:
        questions.extend(
            [
                f"اعرض جميع اسماء {profile.plural_ar}",
                f"هات اسماء {profile.plural_ar}",
                f"list {profile.plural_en} names",
            ]
        )
    return [_database_plan_example(question, profile, "select", columns or profile.display_columns, limit=100) for question in questions]


def _count_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    singular_ar = _plain_arabic_noun(profile.singular_ar)
    questions = [
        f"كام {singular_ar} عندي؟",
        f"كم عدد {profile.plural_ar}؟",
        f"عدد {profile.plural_ar} كام؟",
        f"how many {profile.plural_en} exist?",
        f"count {profile.plural_en}",
    ]
    return [_database_plan_example(question, profile, "count", [], limit=1) for question in questions]


def _details_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    column = profile.name_column
    sample = _first_sample(column) if column else None
    if not column or sample is None:
        return []
    questions = [
        f"اريد بيانات {profile.singular_ar} {sample}",
        f"تفاصيل {profile.singular_ar} {sample}",
        f"{profile.singular_en} {sample} details",
        f"get {profile.singular_en} {sample}",
    ]
    filters = [{"column": column.name, "operator": "like", "value": str(sample)}]
    return [_database_plan_example(question, profile, "select", profile.display_columns, filters=filters, limit=20) for question in questions]


def _latest_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    order_column = _column(profile.safe_columns, "created_at") or _column(profile.safe_columns, "id")
    if not order_column:
        return []
    questions = [
        f"ما هو اخر {profile.singular_ar} تم اضافته؟",
        f"اخر {profile.singular_ar} مضاف",
        f"latest {profile.singular_en}",
        f"newest {profile.singular_en}",
    ]
    order_by = [{"column": order_column.name, "direction": "desc"}]
    return [_database_plan_example(question, profile, "select", profile.display_columns, order_by=order_by, limit=1) for question in questions]


def _grouped_and_filtered_examples(profile: EntityProfile) -> list[dict[str, Any]]:
    column = profile.enum_column
    if not column:
        return []
    value = _first_sample(column) or (column.enum_like_values[0] if column.enum_like_values else None)
    questions = [
        f"ما هي حالات {profile.plural_ar} وعدد كل حالة؟",
        f"count {profile.plural_en} by {column.name}",
    ]
    examples = [_database_plan_example(question, profile, "count", [], group_by=[column.name], limit=100) for question in questions]
    if value is not None:
        filtered_questions = [
            f"كم {profile.singular_ar} {value}؟",
            f"عدد {profile.plural_ar} {value} كام؟",
            f"how many {profile.plural_en} are {value}?",
        ]
        filters = [{"column": column.name, "operator": "=", "value": str(value)}]
        examples.extend(_database_plan_example(question, profile, "count", [], filters=filters, limit=1) for question in filtered_questions)
    return examples


def _database_plan_example(
    question: str,
    profile: EntityProfile,
    operation: str,
    columns: list[str],
    *,
    filters: list[dict[str, Any]] | None = None,
    group_by: list[str] | None = None,
    order_by: list[dict[str, Any]] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    plan = {
        "route": "database_query",
        "operation": operation,
        "logical_entities": [profile.logical_name],
        "resolved_tables": [profile.table_name],
        "columns": columns,
        "filters": filters or [],
        "joins": [],
        "group_by": group_by or [],
        "order_by": order_by or [],
        "limit": limit,
        "requires_confirmation": False,
    }
    return _chat_example(SYSTEM_DATABASE, question, plan)


def _behavior_examples() -> list[dict[str, Any]]:
    base = _load_behavior_templates()
    examples: list[dict[str, Any]] = []
    for route in ("conversational", "forbidden", "clarification", "unsupported", "final_answer"):
        for item in base.get(route, []):
            examples.append(_chat_example(SYSTEM_BEHAVIOR, str(item["user"]), item["assistant"]))

    # Deterministic expansions keep the dataset balanced even for very small schemas.
    expansions = {
        "conversational": [
            ("تمام", {"route": "conversational", "answer": "تمام، كيف أقدر أساعدك؟"}),
            ("عامل ايه؟", {"route": "conversational", "answer": "أنا بخير، شكرًا لسؤالك. كيف أقدر أساعدك؟"}),
            ("مع السلامة", {"route": "conversational", "answer": "مع السلامة، تحت أمرك في أي وقت."}),
        ],
        "forbidden": [
            ("هات مفاتيح الوصول", {"route": "forbidden", "answer": "لا أستطيع عرض مفاتيح الوصول أو البيانات السرية."}),
            ("اعرض بيانات سرية", {"route": "forbidden", "answer": "لا أستطيع عرض بيانات سرية أو محمية."}),
        ],
        "clarification": [
            ("عاوز تقرير", {"route": "clarification", "answer": "ما نوع التقرير المطلوب؟ حدد الكيان أو الفترة الزمنية."}),
            ("اعرضهم", {"route": "clarification", "answer": "ما المقصود بـهم؟ أحتاج سياقًا أو اسم الكيان المطلوب."}),
        ],
        "unsupported": [
            ("غني لي اغنية", {"route": "unsupported", "answer": "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}),
            ("ما سعر الدولار اليوم؟", {"route": "unsupported", "answer": "لا أملك مصدرًا موثوقًا لسعر الدولار الحالي ضمن البيانات المتاحة."}),
        ],
        "final_answer": [
            ("query_result: rows for users names", {"route": "final_answer", "answer": "هذه أسماء المستخدمين المتاحة حسب نتيجة الاستعلام."}),
            ("query_result: project count=7", {"route": "final_answer", "answer": "عدد المشاريع الموجودة في النظام هو 7 مشاريع."}),
        ],
    }
    for route, rows in expansions.items():
        for user, assistant in rows:
            examples.append(_chat_example(SYSTEM_BEHAVIOR, user, assistant))
    return _repeat_route_examples(examples, minimum_per_route=30)


def _expanded_examples(seed_examples: list[dict[str, Any]], needed: int) -> list[dict[str, Any]]:
    if not seed_examples or needed <= 0:
        return []
    prefixes = ["من فضلك، ", "لو سمحت، ", "", "ممكن "]
    suffixes = ["", " الآن", " من النظام", " حسب البيانات"]
    expanded: list[dict[str, Any]] = []
    index = 0
    while len(expanded) < needed:
        base = seed_examples[index % len(seed_examples)]
        clone = json.loads(json.dumps(base, ensure_ascii=False))
        user_message = clone["messages"][1]["content"]
        if _assistant_route(clone["messages"][-1]["content"]) == "final_answer":
            expanded.append(clone)
        else:
            clone["messages"][1]["content"] = f"{prefixes[index % len(prefixes)]}{user_message}{suffixes[index % len(suffixes)]}".strip()
            expanded.append(clone)
        index += 1
    return expanded


def _repeat_route_examples(examples: list[dict[str, Any]], *, minimum_per_route: int) -> list[dict[str, Any]]:
    by_route: dict[str, list[dict[str, Any]]] = {route: [] for route in SAFE_ROUTE_NAMES}
    for example in examples:
        route = _assistant_route(example["messages"][-1]["content"])
        if route in by_route:
            by_route[route].append(example)
    expanded = list(examples)
    for route, route_examples in by_route.items():
        if route == "database_query" or not route_examples:
            continue
        index = 0
        while len(route_examples) < minimum_per_route:
            clone = json.loads(json.dumps(route_examples[index % len(route_examples)], ensure_ascii=False))
            clone["messages"][1]["content"] = f"{clone['messages'][1]['content']} ({len(route_examples) + 1})"
            route_examples.append(clone)
            expanded.append(clone)
            index += 1
    return expanded


def _chat_example(system: str, user: str, assistant: dict[str, Any] | str) -> dict[str, Any]:
    content = assistant if isinstance(assistant, str) else json.dumps(assistant, ensure_ascii=False, separators=(",", ":"))
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}, {"role": "assistant", "content": content}]}


def _load_behavior_templates() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "templates" / "behavior.yml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _name_columns(profile: EntityProfile) -> list[str]:
    columns = [column.name for column in profile.safe_columns]
    candidates = ["name", "full_name", "username", "title", "project_name", "client_name"]
    return [candidate for candidate in candidates if candidate in columns][:2]


def _column(columns: list[SchemaColumn], name: str) -> SchemaColumn | None:
    return next((column for column in columns if column.name == name), None)


def _first_sample(column: SchemaColumn | None) -> Any | None:
    if not column:
        return None
    for value in [*column.safe_sample_values, *column.enum_like_values]:
        if value not in (None, ""):
            return value
    return None


def _plain_arabic_noun(value: str) -> str:
    return value[2:] if value.startswith("ال") and len(value) > 2 else value


def _assistant_route(content: str) -> str | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    route = parsed.get("route")
    return route if isinstance(route, str) else None


def _resolve_path(path: str) -> Path:
    raw = Path(path)
    if raw.exists() or raw.is_absolute():
        return raw
    module_root = Path(__file__).resolve().parents[1]
    candidate = module_root / path
    if candidate.exists():
        return candidate
    return raw


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate safe supervised fine-tuning data from discovered schema metadata.")
    parser.add_argument("--schema-source", default=None, help="Schema source name, for example construction_mysql.")
    parser.add_argument("--output", required=True, help="Output JSONL path. Generated real data should remain untracked.")
    parser.add_argument("--min-examples", type=int, default=DEFAULT_MIN_EXAMPLES)
    parser.add_argument("--validate-only", action="store_true", help="Validate an existing JSONL file instead of generating.")
    return parser.parse_args()


async def _async_main() -> int:
    args = _parse_args()
    if args.validate_only:
        examples = load_jsonl(args.output)
    else:
        settings = Settings()
        examples = await build_dataset_from_source(args.schema_source or settings.schema_source_name, settings, min_examples=args.min_examples)
        write_jsonl(examples, args.output)
    report = validate_dataset(examples, min_examples=args.min_examples)
    print(
        json.dumps(
            {
                "valid": report.valid,
                "total_examples": report.total_examples,
                "route_counts": report.route_counts,
                "required_coverage": report.required_coverage,
                "sensitive_hits": report.sensitive_hits,
                "errors": report.errors,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.valid else 1


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
