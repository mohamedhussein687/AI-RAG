# Fine-Tuning

This project supports real supervised adapter fine-tuning for the
database-aware agent. Fine-tuning teaches routing, Arabic business vocabulary,
schema-aware structured planning, safe refusal, and final Arabic answer style.
It does not memorize changing operational rows; live facts still come from
MySQL through validated read-only parameterized queries.

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
