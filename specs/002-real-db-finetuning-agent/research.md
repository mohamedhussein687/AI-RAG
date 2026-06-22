# Research: Real Database Fine-Tuning Agent

## Decision: Use restored MySQL/MariaDB schema as the primary domain source

**Rationale**: The protected backup is the closest available representation of the real project database. Schema discovery from the restored database gives table names, column names, data types, relationships, comments, indexes, enum-like values, and safe samples without copying operational data into the model.

**Alternatives considered**:

- Rely only on Qdrant-ingested row documents: rejected because changing structured facts must be queried live and Qdrant should not become a full operational mirror.
- Manually maintain all table mappings: rejected because it causes brittle phrase-by-phrase patches and table allowlist mismatches.
- Fine-tune on all database rows: rejected because the goal is behavior and domain language, not memorizing changing rows.

## Decision: Keep backup files outside Git with path validation

**Rationale**: The SQL backup can contain production-sensitive data. The restore workflow must refuse paths inside the repository and only use approved external locations such as `/home/hussein/backups/backup.sql` locally and `/home/rag/backup.sql` on the server.

**Alternatives considered**:

- Commit a sanitized backup fixture: rejected for the real workflow because the user specifically supplied a protected backup location. Tiny fake fixtures can still be committed for tests.
- Copy the server backup into the repository for convenience: rejected because it violates the backup rules and creates accidental commit risk.

## Decision: Use schema intelligence plus aliases rather than hardcoded routing

**Rationale**: The current failure mode comes from business meaning being decided by brittle gateway/rule mappings. Schema intelligence gives the model current table and column context, while the alias file adds domain vocabulary and Arabic synonyms that are auditable and updateable.

**Alternatives considered**:

- Hardcode Arabic terms to tables in Spring Gateway: rejected because Spring must validate/execute, not infer business intent.
- Depend only on model prior knowledge: rejected because physical table names and project-specific aliases are not stable public knowledge.

## Decision: Store/search schema context separately from operational facts

**Rationale**: Qdrant is useful for schema descriptions, relationship explanations, table/column comments, aliases, and long text/document context. Current counts, rows, statuses, and user/project details must come from MySQL at runtime.

**Alternatives considered**:

- Index all operational rows into Qdrant and answer from vectors: rejected because structured facts change and exact counts/filters require live SQL.
- Use only live metadata queries per chat turn: rejected because it is slower and gives the model less semantic context than indexed schema chunks.

## Decision: Generate supervised fine-tuning data from schema intelligence

**Rationale**: Fine-tuning should teach the model route classification, Arabic business vocabulary, structured JSON planning, safe refusal, clarification behavior, and final Arabic answer style. Schema-driven generation creates many safe examples without leaking secrets.

**Alternatives considered**:

- Handwrite a tiny prompt-only example set: rejected because it will not cover enough entity/operation variations.
- Use raw user tickets or production logs: rejected unless separately sanitized, because they may contain sensitive information.

## Decision: Use Qwen-compatible LoRA/QLoRA training path

**Rationale**: The deployed system already uses Qwen-oriented local inference, Arabic support is important, and adapter fine-tuning is practical compared with full model training. QLoRA allows lower-memory training when available, while LoRA remains useful for non-quantized training environments.

**Alternatives considered**:

- Full fine-tuning of base model weights: rejected as too resource-heavy and unnecessary for the target behavior.
- Prompt engineering only: rejected because the user explicitly requires real fine-tuning and current behavior shows prompt/rule brittleness.
- Fine-tune a closed model: rejected because the target is local open-source serving.

## Decision: Validate structured plans before any SQL execution

**Rationale**: The model is the classifier/planner, but it is not trusted. It must output structured JSON only. The backend validates tables, columns, operations, filters, joins, limits, and sensitive fields against discovered schema before compiling parameterized read-only SQL.

**Alternatives considered**:

- Let the model generate SQL directly: rejected due to injection, destructive-operation, and table/column hallucination risk.
- Let Spring infer the intended table from aliases: rejected because it recreates gateway business routing.

## Decision: Add AI module database execution path for local smoke, preserve Gateway boundary for production

**Rationale**: The feature requires local smoke commands and AI module chat behavior, while the existing production architecture uses Spring Gateway as the public entry point and execution boundary. The plan supports safe database utilities in the AI module for local restore/discovery/evaluation and keeps Spring as the public validator/executor when serving Laravel.

**Alternatives considered**:

- Move all execution permanently into FastAPI: rejected because the existing gateway flow and security boundary already exist.
- Keep all database execution only in Spring: rejected for local training/evaluation smoke tests that need a self-contained AI module path.

## Decision: Use real local tests first, server tests only after GitHub push

**Rationale**: The user explicitly requires local source-of-truth work. The server must not become a development workspace or contain uncommitted hotfixes. Server validation must pull the pushed branch under `/home/rag/`.

**Alternatives considered**:

- Copy uncommitted local files to server: rejected by workflow rule.
- Edit `/home/rag/current` directly: rejected because it breaks reproducibility and rollback.

## Decision: Treat insufficient training hardware as a blocker, not a failure to implement

**Rationale**: The code and workflow can be implemented even if the current machine cannot complete full QLoRA training. The correct behavior is to run a tiny smoke test if possible and report the exact blocker and full training command.

**Alternatives considered**:

- Fake a successful training result: rejected as inaccurate and unsafe.
- Skip training code until GPU access is available: rejected because the user requires the pipeline now.
