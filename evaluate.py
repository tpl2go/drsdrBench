#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_routing_config import MODEL_ROUTING
from config_taskstorun import MODELS_TO_RUN, TASK_FOLDERS

PASSING_SCORE = 0.9
TASKS_DIR_NAME = "TASKS"


@dataclass(frozen=True)
class FolderResult:
    model: str
    complete: bool
    score: float
    total_tokens: int | None


def is_experiment_complete(folder: Path) -> bool:
    return (folder / "opencode_session.json").is_file()


def is_decodeimg_task(task_dir: Path) -> bool:
    return task_dir.name.startswith("decodeimg")


def resolve_repo_task_directory(task_name: str, repo_root: Path) -> Path:
    task_path = Path(task_name).expanduser()
    if task_path.is_absolute():
        return task_path.resolve()

    repo_relative = (repo_root / task_path).resolve()
    if repo_relative.is_dir():
        return repo_relative

    tasks_relative = (repo_root / TASKS_DIR_NAME / task_path).resolve()
    if tasks_relative.is_dir():
        return tasks_relative

    return repo_relative


def resolve_cli_target_directory(targetdir: Path, repo_root: Path) -> Path:
    task_path = targetdir.expanduser()
    if task_path.is_absolute():
        return task_path.resolve()

    cwd_relative = (Path.cwd() / task_path).resolve()
    if cwd_relative.is_dir():
        return cwd_relative

    return resolve_repo_task_directory(str(task_path), repo_root)


def read_decoded_message(folder: Path) -> bytes:
    decoded_path = folder / "decoded_msg.bin"
    if not decoded_path.is_file():
        return b""
    return decoded_path.read_bytes()


def read_decoded_image(folder: Path) -> Any:
    np = require_numpy()
    decoded_path = folder / "decoded_img.npy"
    if not decoded_path.is_file():
        return None
    try:
        return np.load(decoded_path, allow_pickle=False)
    except (OSError, ValueError):
        return None


def iter_token_totals(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "tokens" and isinstance(value, dict):
                total = value.get("total")
                if isinstance(total, int):
                    yield total
            yield from iter_token_totals(value)
        return
    if isinstance(node, list):
        for value in node:
            yield from iter_token_totals(value)


def read_total_tokens(folder: Path) -> int | None:
    session_path = folder / "opencode_session.json"
    if not session_path.is_file():
        return None
    try:
        session_data = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    total_tokens = None
    for token_total in iter_token_totals(session_data):
        total_tokens = token_total
    return total_tokens


def normalized_levenshtein_score(expected: bytes, observed: bytes) -> float:
    """Return 1 - normalized Levenshtein distance."""

    if expected == observed:
        return 1.0

    len_a = len(expected)
    len_b = len(observed)

    previous_row = list(range(len_b + 1))
    for i, byte_a in enumerate(expected, start=1):
        current_row = [i]
        for j, byte_b in enumerate(observed, start=1):
            insertion_cost = current_row[j - 1] + 1
            deletion_cost = previous_row[j] + 1
            substitution_cost = previous_row[j - 1] + (byte_a != byte_b)
            current_row.append(min(insertion_cost, deletion_cost, substitution_cost))
        previous_row = current_row

    distance = previous_row[-1]
    normalized_distance = distance / max(len_a, len_b)
    return 1.0 - normalized_distance


def cosine_similarity_score(expected: Any, observed: Any) -> float:
    np = require_numpy()
    if observed is None:
        return 0.0

    expected_flat = np.asarray(expected).ravel()
    observed_flat = np.asarray(observed).ravel()
    if expected_flat.shape != observed_flat.shape:
        return 0.0
    if expected_flat.size == 0:
        return 1.0

    expected_flat = expected_flat - np.mean(expected_flat)
    observed_flat = observed_flat - np.mean(observed_flat)

    expected_norm = float(np.linalg.norm(expected_flat))
    observed_norm = float(np.linalg.norm(observed_flat))
    if expected_norm == 0.0 and observed_norm == 0.0:
        return 1.0
    if expected_norm == 0.0 or observed_norm == 0.0:
        return 0.0

    similarity = np.vdot(expected_flat, observed_flat) / (expected_norm * observed_norm)
    similarity = float(np.real(similarity))
    if not np.isfinite(similarity):
        return 0.0
    return float(np.abs(np.clip(similarity, -1.0, 1.0)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate decoded experiment outputs.")
    parser.add_argument(
        "--targetdir",
        type=Path,
        default=None,
        help=(
            "Task folder to evaluate. "
            "If omitted, evaluate all tasks listed in config_taskstorun.json."
        ),
    )
    parser.add_argument(
        "--groundtruth-file",
        type=Path,
        default=None,
        help=(
            "Path to the expected output file. "
            "Defaults to targetdir/groundtruth.bin for decodemsg tasks, "
            "or targetdir/groundtruth.npy for decodeimg tasks."
        ),
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help=(
            "Write collated score, token, and success tables to score.csv, "
            "tokens.csv, and success_count.csv in the current working directory."
        ),
    )
    return parser.parse_args()


def require_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "NumPy is required to evaluate decodeimg* tasks. "
            "Install it with `python3 -m pip install numpy`."
        ) from exc
    return np


def load_groundtruth_message(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    return path.read_bytes()


def load_groundtruth_image(path: Path) -> Any:
    np = require_numpy()
    if not path.is_file():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    try:
        return np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Failed to load ground truth array: {path}") from exc


def evaluate_task(task_dir: Path, groundtruth_file: Path | None = None) -> list[FolderResult]:
    decodeimg_task = is_decodeimg_task(task_dir)
    if groundtruth_file is None:
        groundtruth_file = task_dir / ("groundtruth.npy" if decodeimg_task else "groundtruth.bin")

    if decodeimg_task:
        groundtruth_image = load_groundtruth_image(groundtruth_file)
    else:
        groundtruth_message = load_groundtruth_message(groundtruth_file)

    model_names = list(MODELS_TO_RUN) if MODELS_TO_RUN is not None else list(MODEL_ROUTING.keys())

    results: list[FolderResult] = []
    for model_name in model_names:
        folder = task_dir / model_name
        if decodeimg_task:
            observed_image = read_decoded_image(folder)
            score = cosine_similarity_score(groundtruth_image, observed_image)
        else:
            observed_message = read_decoded_message(folder)
            score = normalized_levenshtein_score(groundtruth_message, observed_message)

        results.append(
            FolderResult(
                model=model_name,
                complete=is_experiment_complete(folder),
                score=score,
                total_tokens=read_total_tokens(folder),
            )
        )
    return results


def write_matrix_csv(
    csv_path: Path,
    tasks: list[str],
    models: list[str],
    matrix: dict[str, dict[str, object]],
    *,
    is_score: bool,
) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "average", *tasks])
        for model in models:
            task_cells: list[str] = []
            numeric_values: list[float] = []
            for task in tasks:
                value = matrix.get(model, {}).get(task)
                if value is None:
                    task_cells.append("")
                    continue

                numeric_values.append(float(value))
                if is_score:
                    task_cells.append(f"{float(value):.6f}")
                else:
                    task_cells.append(str(int(value)))
            average_cell = ""
            if numeric_values:
                average_cell = f"{sum(numeric_values) / len(numeric_values):.6f}"
            row = [model, average_cell, *task_cells]
            writer.writerow(row)


def write_collated_csv(
    task_names: list[str],
    scores_by_model: dict[str, dict[str, float]],
    tokens_by_model: dict[str, dict[str, int | None]],
) -> None:
    models = sorted(set(scores_by_model) | set(tokens_by_model))
    success_by_model: dict[str, dict[str, int]] = {}
    for model, task_scores in scores_by_model.items():
        model_successes = success_by_model.setdefault(model, {})
        for task_name, score in task_scores.items():
            model_successes[task_name] = 1 if score >= PASSING_SCORE else 0

    write_matrix_csv(Path("score.csv"), task_names, models, scores_by_model, is_score=True)
    write_matrix_csv(Path("tokens.csv"), task_names, models, tokens_by_model, is_score=False)
    write_matrix_csv(Path("success_count.csv"), task_names, models, success_by_model, is_score=False)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent

    if args.targetdir is not None:
        task_dir = resolve_cli_target_directory(args.targetdir, repo_root)
        if not task_dir.is_dir():
            raise FileNotFoundError(f"Task folder not found: {task_dir}")

        groundtruth_path = args.groundtruth_file.resolve() if args.groundtruth_file is not None else None
        results = evaluate_task(task_dir, groundtruth_path)
        for result in results:
            print(json.dumps(result.__dict__, ensure_ascii=True, sort_keys=True))

        if args.write_csv:
            task_name = task_dir.name
            scores_by_model: dict[str, dict[str, float]] = {}
            tokens_by_model: dict[str, dict[str, int | None]] = {}
            for result in results:
                scores_by_model.setdefault(result.model, {})[task_name] = result.score
                tokens_by_model.setdefault(result.model, {})[task_name] = result.total_tokens
            write_collated_csv([task_name], scores_by_model, tokens_by_model)
        return

    if args.groundtruth_file is not None:
        raise SystemExit("--groundtruth-file can only be used with --targetdir.")

    task_dirs: list[tuple[str, Path]] = []
    for task_name in TASK_FOLDERS:
        task_dir = resolve_repo_task_directory(task_name, repo_root)
        if not task_dir.is_dir():
            raise FileNotFoundError(f"Task folder not found: {task_dir}")
        task_dirs.append((task_name, task_dir))

    scores_by_model: dict[str, dict[str, float]] = {}
    tokens_by_model: dict[str, dict[str, int | None]] = {}
    evaluated_task_names: list[str] = []
    for task_name, task_dir in task_dirs:
        try:
            results = evaluate_task(task_dir)
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"Skipping task {task_name}: {exc}", file=sys.stderr)
            continue

        evaluated_task_names.append(task_name)
        for result in results:
            print(json.dumps({"task": task_name, **result.__dict__}, ensure_ascii=True, sort_keys=True))
            scores_by_model.setdefault(result.model, {})[task_name] = result.score
            tokens_by_model.setdefault(result.model, {})[task_name] = result.total_tokens

    total_tasks = len(evaluated_task_names)
    if total_tasks == 0:
        raise RuntimeError("No tasks were evaluated successfully.")

    for model in sorted(scores_by_model):
        task_scores = scores_by_model[model]
        avg_score = sum(task_scores.get(task_name, 0.0) for task_name in evaluated_task_names) / total_tasks
        print(
            json.dumps(
                {
                    "average_score": avg_score,
                    "model": model,
                    "tasks_total": total_tasks,
                    "tasks_with_results": len(task_scores),
                    "type": "model_average",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )

    if args.write_csv:
        write_collated_csv(evaluated_task_names, scores_by_model, tokens_by_model)


if __name__ == "__main__":
    main()
