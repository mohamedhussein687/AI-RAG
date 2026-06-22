from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from training.dataset_builder import DatasetValidationReport, load_jsonl, validate_dataset


@dataclass(frozen=True)
class TrainingConfig:
    base_model: str
    max_seq_length: int = 2048
    epochs: float = 1.0
    learning_rate: float = 2e-4
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    fp16: bool = False
    bf16: bool = True
    use_4bit: bool = False
    seed: int = 42
    warmup_ratio: float = 0.03
    logging_steps: int = 10
    save_steps: int = 100
    max_steps: int | None = None
    merge_adapter: bool = False


def load_training_config(path: str | Path) -> TrainingConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("training config must be a YAML mapping")
    config = TrainingConfig(**data)
    _validate_config(config)
    return config


def validate_training_dataset(path: str | Path, *, min_examples: int = 1) -> DatasetValidationReport:
    examples = load_jsonl(path)
    return validate_dataset(examples, min_examples=min_examples)


def run_training(
    config: TrainingConfig,
    *,
    dataset_path: str | Path,
    output_dir: str | Path,
    dry_run: bool = False,
    min_examples: int = 1,
) -> dict[str, Any]:
    _validate_config(config)
    dataset_report = validate_training_dataset(dataset_path, min_examples=min_examples)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not dataset_report.valid:
        report = _base_report("dataset_invalid", config, dataset_report, full_training_executed=False)
        _write_report(output / "training_error_report.json", report)
        raise ValueError("training dataset is invalid: " + "; ".join(dataset_report.errors))

    if dry_run:
        report = _base_report("dry_run_passed", config, dataset_report, full_training_executed=False)
        report["hardware_note"] = "Dry run validated config and dataset only; no model weights or adapters were produced."
        _write_report(output / "training_dry_run_report.json", report)
        return report

    return _run_real_training(config, dataset_path=Path(dataset_path), output_dir=output, dataset_report=dataset_report)


def _run_real_training(
    config: TrainingConfig,
    *,
    dataset_path: Path,
    output_dir: Path,
    dataset_report: DatasetValidationReport,
) -> dict[str, Any]:
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
        from trl import SFTTrainer
    except Exception as exc:  # pragma: no cover - depends on optional heavy deps
        report = _base_report("blocked_missing_training_dependency", config, dataset_report, full_training_executed=False)
        report["blocker"] = f"Training dependency unavailable: {exc.__class__.__name__}"
        _write_report(output_dir / "training_blocked_report.json", report)
        raise RuntimeError(report["blocker"]) from exc

    quantization_config = None
    if config.use_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16 if config.bf16 else torch.float16,
        )

    tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        trust_remote_code=True,
        quantization_config=quantization_config,
        device_map="auto",
    )
    if config.use_4bit:
        model = prepare_model_for_kbit_training(model)
    peft_config = LoraConfig(
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.target_modules,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, peft_config)
    dataset = load_dataset("json", data_files=str(dataset_path), split="train")

    def format_example(example: dict[str, Any]) -> str:
        messages = example["messages"]
        if hasattr(tokenizer, "apply_chat_template"):
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        return "\n".join(f"{message['role']}: {message['content']}" for message in messages)

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=config.epochs,
        max_steps=config.max_steps if config.max_steps is not None else -1,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        save_total_limit=2,
        fp16=config.fp16,
        bf16=config.bf16,
        report_to=[],
        seed=config.seed,
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=args,
        formatting_func=format_example,
        max_seq_length=config.max_seq_length,
        packing=False,
    )
    trainer.train()
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    report = _base_report("training_completed", config, dataset_report, full_training_executed=True)
    report["adapter_output_dir"] = str(output_dir)
    _write_report(output_dir / "training_report.json", report)
    return report


def _validate_config(config: TrainingConfig) -> None:
    if not config.base_model:
        raise ValueError("base_model is required")
    if config.max_seq_length < 128:
        raise ValueError("max_seq_length must be at least 128")
    if config.lora_rank <= 0 or config.lora_alpha <= 0:
        raise ValueError("LoRA rank and alpha must be positive")
    if not config.target_modules:
        raise ValueError("target_modules must not be empty")
    if config.fp16 and config.bf16:
        raise ValueError("fp16 and bf16 cannot both be enabled")


def _base_report(
    status: str,
    config: TrainingConfig,
    dataset_report: DatasetValidationReport,
    *,
    full_training_executed: bool,
) -> dict[str, Any]:
    redacted_config = asdict(config)
    return {
        "status": status,
        "full_training_executed": full_training_executed,
        "base_model": config.base_model,
        "config": redacted_config,
        "dataset": {
            "valid": dataset_report.valid,
            "total_examples": dataset_report.total_examples,
            "route_counts": dataset_report.route_counts,
            "required_coverage": dataset_report.required_coverage,
            "sensitive_hits": dataset_report.sensitive_hits,
            "errors": dataset_report.errors,
        },
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real LoRA/QLoRA supervised fine-tuning for the database-aware agent.")
    parser.add_argument("--config", required=True, help="YAML training config path.")
    parser.add_argument("--dataset", required=True, help="JSONL chat-format dataset path.")
    parser.add_argument("--output", required=True, help="Adapter output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and dataset without loading or training a model.")
    parser.add_argument("--min-examples", type=int, default=1, help="Minimum dataset size for this run.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_training_config(args.config)
    report = run_training(
        config,
        dataset_path=args.dataset,
        output_dir=args.output,
        dry_run=args.dry_run,
        min_examples=args.min_examples,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
