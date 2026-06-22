from __future__ import annotations

import json
from pathlib import Path

from training.dataset_builder import build_dataset, write_jsonl
from training.train_lora import (
    TrainingConfig,
    load_training_config,
    run_training,
    validate_training_dataset,
)

from tests.test_dataset_builder import _aliases, _snapshot


def test_training_config_loading_and_dataset_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "qwen_lora.yaml"
    config_path.write_text(
        """
base_model: Qwen/Qwen2.5-0.5B-Instruct
max_seq_length: 1024
epochs: 1
learning_rate: 0.0002
per_device_train_batch_size: 1
gradient_accumulation_steps: 2
lora_rank: 8
lora_alpha: 16
lora_dropout: 0.05
target_modules: [q_proj, v_proj]
fp16: false
bf16: false
use_4bit: false
""",
        encoding="utf-8",
    )
    dataset_path = tmp_path / "db_agent_sft.jsonl"
    write_jsonl(build_dataset(_snapshot(), _aliases(), min_examples=20), dataset_path)

    config = load_training_config(config_path)
    report = validate_training_dataset(dataset_path, min_examples=20)

    assert isinstance(config, TrainingConfig)
    assert config.base_model == "Qwen/Qwen2.5-0.5B-Instruct"
    assert config.lora_rank == 8
    assert report.valid is True
    assert report.total_examples >= 20


def test_tiny_smoke_training_dry_run_writes_redacted_report(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sample_fake.jsonl"
    write_jsonl(build_dataset(_snapshot(), _aliases(), min_examples=20), dataset_path)
    output_dir = tmp_path / "adapter"
    config = TrainingConfig(
        base_model="hf-internal-testing/tiny-random-gpt2",
        max_seq_length=128,
        epochs=1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        lora_rank=4,
        lora_alpha=8,
        lora_dropout=0.0,
        target_modules=["c_attn"],
        use_4bit=False,
    )

    report = run_training(config, dataset_path=dataset_path, output_dir=output_dir, dry_run=True, min_examples=20)

    assert report["status"] == "dry_run_passed"
    assert report["full_training_executed"] is False
    assert report["dataset"]["valid"] is True
    rendered = json.dumps(report, ensure_ascii=False)
    assert "secret" not in rendered.lower()
    assert (output_dir / "training_dry_run_report.json").exists()
