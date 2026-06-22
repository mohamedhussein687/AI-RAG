from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


FORBIDDEN_SUFFIXES = {
    ".sql",
    ".dump",
    ".backup",
    ".tar",
    ".gz",
}
FORBIDDEN_PARTS = {
    "models",
    "checkpoints",
    "outputs",
    "lora_adapters",
    "wandb",
    "runs",
}
ALLOWED_TRACKED_FILES = {
    "construction-ai-rag-module/ai_module/data/training/sample_fake.jsonl",
}


def test_gitignore_contains_required_secret_and_artifact_patterns() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    for pattern in [
        "*.sql",
        "*.dump",
        "*.backup",
        "*.tar",
        "*.gz",
        ".env",
        ".env.*",
        "!.env.example",
        "models/",
        "checkpoints/",
        "outputs/",
        "lora_adapters/",
        "wandb/",
        "runs/",
        "data/training/*.jsonl",
        "!data/training/sample_fake.jsonl",
    ]:
        assert pattern in gitignore


def test_no_forbidden_backup_model_or_real_dataset_artifacts_are_tracked() -> None:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    tracked = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    forbidden = []
    for path in tracked:
        if path in ALLOWED_TRACKED_FILES:
            continue
        p = Path(path)
        if p.name == ".env.example" or path.endswith(".env.example"):
            continue
        if p.suffix in FORBIDDEN_SUFFIXES:
            forbidden.append(path)
            continue
        if p.name == ".env" or ".env." in path:
            forbidden.append(path)
            continue
        if "data/training/" in path and p.suffix == ".jsonl":
            forbidden.append(path)
            continue
        if any(part in FORBIDDEN_PARTS for part in p.parts):
            forbidden.append(path)
    assert forbidden == []
