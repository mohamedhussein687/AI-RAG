# Fine-Tuning

This project supports real supervised adapter fine-tuning for the
database-aware agent. Fine-tuning teaches routing, Arabic business vocabulary,
schema-aware structured planning, safe refusal, and final Arabic answer style.
It does not memorize changing operational rows; live facts still come from
MySQL through validated read-only parameterized queries.

## Fine-Tuning vs RAG vs Live SQL

These three pieces have different jobs:

- Fine-tuning teaches behavior: route classification, Arabic business wording,
  safe JSON plan shape, refusal of sensitive requests, and answer tone.
- Schema RAG keeps current database structure available to the model: table
  names, column meanings, relationships, aliases, and enum-like values.
- Live SQL returns current facts: counts, lists, record details, and aggregates
  from the configured MySQL/MariaDB database.

Do not train the model to memorize changing rows. Do not put credentials or
secret values in training data. Do not treat a fine-tuned adapter as permission
to bypass schema search, validation, or parameterized SQL execution.

## What Is Trained

Training examples may include:

- schema-derived table and column descriptions;
- safe aliases and business vocabulary;
- synthetic and safe sample values;
- route decisions for conversational, database, RAG, clarification, forbidden,
  and unsupported messages;
- structured JSON plans;
- final Arabic answer style from provided rows.

Training examples must exclude:

- passwords, tokens, API keys, private keys, OTPs, reset tokens, and secrets;
- generated real datasets committed to Git;
- model weights, adapters, checkpoints, and training logs committed to Git;
- full operational data dumps.

## Generate Data

Generate a real local dataset from discovered schema metadata:

```bash
cd construction-ai-rag-module/ai_module
python -m training.dataset_builder \
  --schema-source construction_mysql \
  --output data/training/db_agent_sft.jsonl
```

The generated real dataset is ignored by Git. Commit only the tiny fake sample
at `data/training/sample_fake.jsonl`.

The builder validates JSONL chat format, route balance, required smoke-question
coverage, structured assistant JSON where expected, and absence of sensitive
values. If the schema is small, the target is at least 500 examples. Larger
schemas should produce 2,000 or more examples when enough safe entities exist.

## Validate and Smoke-Test Training

Validate config and dataset without loading model weights:

```bash
python -m training.train_lora \
  --config training/configs/qwen_qlora.yaml \
  --dataset data/training/db_agent_sft.jsonl \
  --output outputs/db-agent-qwen-lora \
  --dry-run
```

This produces `training_dry_run_report.json`; it is not a trained adapter.

## Run Real LoRA/QLoRA

Run QLoRA when a compatible GPU environment is available:

```bash
python -m training.train_lora \
  --config training/configs/qwen_qlora.yaml \
  --dataset data/training/db_agent_sft.jsonl \
  --output outputs/db-agent-qwen-lora
```

For non-quantized LoRA:

```bash
python -m training.train_lora \
  --config training/configs/qwen_lora.yaml \
  --dataset data/training/db_agent_sft.jsonl \
  --output outputs/db-agent-qwen-lora
```

If local hardware cannot complete training, do not claim success. Keep the dry
run report and record the GPU/VRAM blocker.

The full training command should create a real adapter under `outputs/` only
when compatible GPU/VRAM and dependencies are available. A dry run validates the
pipeline but is not a trained model.

## Evaluate

Evaluate JSON planning and safety behavior against an eval set:

```bash
python -m training.evaluate_agent \
  --adapter outputs/db-agent-qwen-lora \
  --eval data/training/eval.jsonl \
  --output outputs/db-agent-qwen-lora/evaluation_report.json
```

The evaluator reports valid JSON output rate, route accuracy, table resolution
accuracy, sensitive-data refusal accuracy, no-write-operation compliance, and
Arabic answer behavior.

## Serve Adapter or Merged Model

Serving depends on the inference backend:

- If vLLM supports the LoRA adapter for the chosen base model, serve the base
  model with the adapter and set `LLM_MODEL_NAME` to the served model alias.
- Otherwise merge the adapter into the base model in a controlled GPU
  environment and serve the merged model path.

Runtime configuration:

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL_NAME=<fine_tuned_model_or_adapter_served_name>
LLM_FINE_TUNED=true
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1200
LLM_ADAPTER_PATH=/absolute/path/to/adapter
LLM_MERGED_MODEL_PATH=
LLM_ADAPTER_SERVING_MODE=served_model
LLM_TRAINING_REPORT_PATH=/absolute/path/to/training_report.json
```

Do not commit adapters, merged model weights, generated datasets, checkpoints,
or training outputs.

## Acceptance Notes

An adapter is acceptable only after evaluation shows the required JSON validity,
route accuracy, table-resolution accuracy, sensitive-data refusal, no-write
compliance, and Arabic answer behavior. If the available machine cannot finish
full training, report the blocker honestly and deploy only the schema/search/chat
components that were actually validated.
