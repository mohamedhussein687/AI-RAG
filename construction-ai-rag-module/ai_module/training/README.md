# Fine-Tuning Dataset Generation

This directory contains the local tooling for generating supervised fine-tuning
examples from discovered database schema intelligence. The generated real
dataset teaches routing, Arabic business vocabulary, safe structured planning,
refusal behavior, clarification behavior, and final Arabic answer style.

It does not train the model to memorize changing operational rows. Live facts
must still come from MySQL at runtime through validated read-only queries.

## Inputs

- Discovered schema from `MYSQL_*` environment settings.
- `construction-ai-rag-module/config/schema_aliases.yml`.
- Safe sample values from non-sensitive, low-cardinality fields.

Sensitive fields are excluded from rendered examples, including names that look
like password, token, secret, API key, OTP, reset, private key, auth, or
credential fields.

## Generate

Run from `construction-ai-rag-module/ai_module`:

```bash
python -m training.dataset_builder \
  --schema-source construction_mysql \
  --output data/training/db_agent_sft.jsonl
```

The output path is intentionally ignored by Git. Do not commit generated real
training data.

## Validate Existing Dataset

```bash
python -m training.dataset_builder \
  --output data/training/db_agent_sft.jsonl \
  --validate-only
```

The validation report prints only counts, route coverage, required smoke prompt
coverage, and sensitive-hit names if any are found. It does not print secrets.

## Expected Coverage

For a small schema, the builder creates at least 500 examples. Larger schemas
produce more database-query variety through table, column, alias, enum, and safe
sample expansion.

The dataset includes examples for:

- `database_query`
- `conversational`
- `forbidden`
- `clarification`
- `unsupported`
- `final_answer`

Required smoke prompts covered by validation:

- `اعرض جميع اسماء المستخدمين`
- `اريد بيانات المستخدم Ayman Ibrahim El Sayed`
- `كام مشروع عندي؟`
- `انت كويس؟`

## Committed Sample

Only `data/training/sample_fake.jsonl` is committed. It uses fake schema and
fake values only, and exists to show the chat JSONL format.

