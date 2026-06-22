# Data Model: Real Database Fine-Tuning Agent

## SQL Backup

Represents the protected database dump used for local and server validation.

**Fields**

- `file_path`: Absolute path outside the Git repository.
- `environment`: `local` or `server`.
- `database_name`: Target restore database.
- `size_bytes`: Optional file-size metadata for operator reporting.
- `checksum`: Optional integrity value for local verification.
- `restored_at`: Timestamp of last successful restore.
- `restore_status`: `not_started`, `running`, `succeeded`, `failed`, `refused`.
- `error_message`: Redacted restore error summary.

**Validation Rules**

- Path must exist before restore.
- Path must not be inside the repository.
- Restore must not modify `/home/rag/backup.sql`.
- Restore output must not print secrets.

## Restored Project Database

Represents a local or server-side database restored from the protected backup.

**Fields**

- `host`, `port`, `database_name`: Non-secret connection metadata.
- `user`: Configured database username, redacted in reports when needed.
- `connect_timeout_seconds`
- `query_timeout_seconds`
- `max_rows`
- `created_at`
- `last_verified_at`

**Relationships**

- Has one or more `SchemaSnapshot` records.
- Supplies live rows for `QueryExecution`.

**Validation Rules**

- Credentials are environment-specific and never committed.
- Queries run read-only for chat and evaluation.
- Row limits and timeouts are enforced.

## SchemaSnapshot

Captures discovered schema intelligence for one source database at a point in time.

**Fields**

- `source_name`
- `database_name`
- `schema_hash`
- `alias_hash`
- `generated_at`
- `status`: `fresh`, `stale`, `failed`
- `table_count`
- `column_count`
- `relationship_count`
- `sensitive_field_count`
- `error_message`

**Relationships**

- Contains many `SchemaTable` records.
- Uses one `AliasCatalog` version.
- Produces many `SchemaChunk` records for search.

**Validation Rules**

- Hash changes when table/column/relationship/alias metadata changes.
- Sensitive field values are never included.
- Status becomes stale when schema or alias hash differs from the last ingested version.

## SchemaTable

Represents a discovered physical table.

**Fields**

- `name`
- `comment`
- `classification`: `business`, `cms_content`, `system`, `unknown`
- `approximate_row_count`
- `primary_key_columns`
- `indexes`
- `foreign_keys`
- `business_description`
- `safe_sample_summary`

**Relationships**

- Contains many `SchemaColumn` records.
- May relate to other tables through foreign keys or detected naming patterns.

**Validation Rules**

- CMS/content and system tables are not used for operational business answers unless explicitly requested and allowed.
- Table names used in plans must exist in the snapshot.

## SchemaColumn

Represents a discovered physical column.

**Fields**

- `table_name`
- `name`
- `data_type`
- `nullable`
- `default_value`
- `comment`
- `is_primary_key`
- `is_foreign_key`
- `is_indexed`
- `is_sensitive`
- `enum_like_values`
- `safe_sample_values`
- `semantic_description`

**Validation Rules**

- Sensitive columns include password, token, secret, API key, credential, OTP, reset, private key, and similar names.
- Sensitive values are never stored in samples, training examples, logs, or user responses.
- Query plans selecting sensitive columns are rejected.

## AliasCatalog

Human-editable vocabulary that enriches schema interpretation.

**Fields**

- `version`
- `file_path`
- `alias_hash`
- `logical_entity`
- `arabic_aliases`
- `english_aliases`
- `physical_candidates`
- `notes`

**Relationships**

- Enhances `SchemaSnapshot` and training data generation.

**Validation Rules**

- Aliases cannot force a nonexistent table to be valid.
- Ambiguous aliases must result in clarification or lower confidence, not unsafe guessing.

## SchemaChunk

Searchable schema intelligence stored for retrieval.

**Fields**

- `chunk_id`
- `source_name`
- `schema_hash`
- `table_name`
- `column_names`
- `content`
- `metadata`
- `indexed_at`

**Relationships**

- Derived from `SchemaSnapshot`.
- Retrieved for decision prompts.

**Validation Rules**

- Content includes schema meaning, aliases, relationships, and safe samples only.
- Does not include database credentials or sensitive sample values.

## TrainingExample

One supervised chat example for fine-tuning or evaluation.

**Fields**

- `example_id`
- `split`: `train`, `eval`, `smoke`
- `messages`
- `route`
- `operation`
- `logical_entities`
- `resolved_tables`
- `safety_labels`
- `source_schema_hash`
- `contains_real_sample`: boolean

**Validation Rules**

- Must be valid JSONL chat format.
- Assistant structured-plan examples must parse as JSON.
- Must not include sensitive values.
- Generated real-data examples are not committed.

## FineTuneRun

Tracks a real training attempt.

**Fields**

- `run_id`
- `base_model`
- `dataset_path`
- `output_path`
- `training_mode`: `lora`, `qlora`, `smoke`
- `started_at`
- `finished_at`
- `status`: `not_started`, `running`, `succeeded`, `failed`, `blocked`
- `resource_summary`
- `blocker`
- `metrics_summary`

**Validation Rules**

- Success requires a produced adapter/model artifact and evaluation result.
- Hardware/resource blockers are reported explicitly.
- Output artifacts are not committed.

## EvaluationResult

Represents model or pipeline evaluation.

**Fields**

- `run_id`
- `evaluated_artifact`
- `json_validity_rate`
- `route_accuracy`
- `table_resolution_accuracy`
- `sensitive_refusal_rate`
- `write_operation_rejection_rate`
- `arabic_answer_score`
- `smoke_prompt_results`
- `passed`

**Validation Rules**

- Required smoke prompts must be included.
- Unsafe output fails evaluation.

## StructuredQueryPlan

The model-produced plan for live data access.

**Fields**

- `route`
- `operation`: `select`, `count`, `aggregate`
- `logical_entities`
- `resolved_tables`
- `columns`
- `filters`
- `joins`
- `group_by`
- `order_by`
- `limit`
- `requires_confirmation`
- `reason`

**Validation Rules**

- Must not contain raw executable SQL.
- Must reference existing, allowed, non-sensitive tables and columns.
- Must be read-only and bounded.
- Invalid plans are rejected before execution.

## QueryExecution

Represents a validated read-only database query and its result summary.

**Fields**

- `request_id`
- `source_name`
- `schema_hash`
- `plan_summary`
- `query_summary`
- `bound_parameter_count`
- `row_count`
- `status`: `succeeded`, `rejected`, `failed`, `timed_out`
- `error_message`

**Validation Rules**

- Parameterized execution only.
- No secrets or raw credential values in logs.
- Returned rows are limited and safe for final answer composition.

## ChatResponse

Final user-facing response.

**Fields**

- `answer`
- `route`
- `display`
- `executed_query_summary`
- `safety_summary`
- `request_id`

**Validation Rules**

- Arabic questions receive natural Arabic answers.
- Operational facts come only from returned rows.
- Empty results explain what was searched.
- Forbidden requests refuse without exposing sensitive data.
