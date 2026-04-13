#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any, Sequence

from model_routing_config import MODEL_ROUTING

REPO_ROOT = Path(__file__).resolve().parent
TASKS_ROOT = REPO_ROOT / "TASKS"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config_taskstorun.json"
STANDARD_SHARED_FILES = [
    "README.md",
    "prompt.txt",
]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SERVER_STARTUP_TIMEOUT_SECONDS = 60.0
DOCKER_IMAGE_NAME = "drsdrbench-opencode-runner:py3.14"
CONTAINER_WORKSPACE = "/workspace"
CONTAINER_HOME = "/tmp/opencode-home"
DEFAULT_CONTAINER_LABEL_KEY = "drsdrbench.run_id"
FORBIDDEN_FORWARD_PREFIXES = (
    "--targetdir",
    "--models",
    "--nworkers",
    "--skip-docker-build",
    "--docker-image",
    "--container-label",
)


@dataclass(frozen=True)
class BatchConfig:
    task_folders: list[str]
    models_to_run: list[str] | None
    launch_task_args: list[str]
    docker_image: str
    build_docker_image: bool
    continue_on_error: bool
    container_label: str | None = None


@dataclass(frozen=True)
class JobSpec:
    task: str
    model: str


@dataclass(frozen=True)
class JobResult:
    task: str
    model: str
    returncode: int
    elapsed_seconds: float


@dataclass(frozen=True)
class LaunchRuntimeOptions:
    openrouter_auth_file: Path
    opencode_host: str
    poll_interval_seconds: float
    server_startup_timeout_seconds: float


def parse_positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be >= 1")
    return parsed


def make_container_label(run_id: str, *, key: str = DEFAULT_CONTAINER_LABEL_KEY) -> str:
    if not run_id.strip():
        raise RuntimeError("Run id used for container labels must be non-empty")
    return f"{key}={run_id.strip()}"


def cleanup_docker_containers(container_label: str) -> None:
    query = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={container_label}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if query.returncode != 0:
        message = (query.stderr or "").strip()
        if message:
            print(
                f"Warning: failed to query containers for label {container_label}: {message}",
                file=sys.stderr,
            )
        return

    container_ids = [line.strip() for line in query.stdout.splitlines() if line.strip()]
    if not container_ids:
        return

    print(
        f"Cleaning up {len(container_ids)} Docker container(s) with label {container_label}",
        file=sys.stderr,
    )
    removal = subprocess.run(
        ["docker", "rm", "-f", *container_ids],
        check=False,
        capture_output=True,
        text=True,
    )
    if removal.returncode != 0:
        message = (removal.stderr or "").strip()
        if message:
            print(
                f"Warning: failed to remove labeled containers ({container_label}): {message}",
                file=sys.stderr,
            )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Unified launcher for full benchmark batches or one-off task/model runs."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to JSON task run config (default: {DEFAULT_CONFIG_PATH.name}).",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help=(
            "Single task folder override. Repeatable. "
            "When provided, overrides TASK_FOLDERS from config."
        ),
    )
    parser.add_argument(
        "--tasks",
        action="append",
        default=[],
        help=(
            "Comma-separated task folder override. Repeatable. "
            "When provided, overrides TASK_FOLDERS from config."
        ),
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help=(
            "Single model override. Repeatable. "
            "When provided, overrides MODELS_TO_RUN from config."
        ),
    )
    parser.add_argument(
        "--models",
        action="append",
        default=[],
        help=(
            "Comma-separated model override. Repeatable. "
            "When provided, overrides MODELS_TO_RUN from config."
        ),
    )
    parser.add_argument(
        "--launch-task-arg",
        action="append",
        default=[],
        help=(
            "Extra per-job runner arg forwarded by main.py for every job. "
            "Repeatable (for example: --launch-task-arg=--openrouter-auth-file=/path/auth.json)."
        ),
    )
    parser.add_argument(
        "--write-default-config",
        type=Path,
        default=None,
        help=(
            "Write a default JSON config template to this path and exit."
        ),
    )
    parser.add_argument(
        "--nworkers",
        type=parse_positive_int,
        default=1,
        help=(
            "Number of workers for the global task+model job pool "
            "(default: 1)."
        ),
    )
    return parser.parse_args(argv)


def load_json_config(config_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Failed to read JSON config at {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON config at {config_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON config must be an object at top level: {config_path}")
    return payload


def parse_bool_field(
    payload: dict[str, object], *, field_name: str, default: bool
) -> bool:
    value = payload.get(field_name, default)
    if not isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be a boolean")
    return value


def parse_str_list(value: object, *, field_name: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list of non-empty strings")

    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"{field_name} must contain only non-empty strings")
        parsed.append(item.strip())

    if not allow_empty and not parsed:
        raise RuntimeError(f"{field_name} must not be empty")

    return parsed


def validate_no_forbidden_forward_args(
    args: Sequence[str], *, source_name: str
) -> None:
    for arg in args:
        for prefix in FORBIDDEN_FORWARD_PREFIXES:
            if arg == prefix or arg.startswith(f"{prefix}="):
                raise RuntimeError(
                    f"Do not include {prefix} in {source_name}; it is controlled by main.py"
                )


def build_launch_task_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--openrouter-auth-file",
        default="~/.local/share/opencode/auth.json",
    )
    parser.add_argument(
        "--opencode-host",
        default=DEFAULT_HOST,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--server-startup-timeout-seconds",
        type=float,
        default=DEFAULT_SERVER_STARTUP_TIMEOUT_SECONDS,
    )
    return parser


def parse_launch_runtime_options(launch_task_args: list[str]) -> LaunchRuntimeOptions:
    validate_no_forbidden_forward_args(
        launch_task_args,
        source_name="launch-task args",
    )

    try:
        parsed = build_launch_task_arg_parser().parse_args(launch_task_args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        raise RuntimeError(f"Invalid LAUNCH_TASK_ARGS (launch parser exit {code})") from None

    if parsed.poll_interval_seconds <= 0:
        raise RuntimeError("--poll-interval-seconds must be > 0")
    if parsed.server_startup_timeout_seconds <= 0:
        raise RuntimeError("--server-startup-timeout-seconds must be > 0")

    auth_file = Path(parsed.openrouter_auth_file).expanduser().resolve()
    if not auth_file.is_file():
        raise RuntimeError(f"OpenRouter auth file does not exist: {auth_file}")

    return LaunchRuntimeOptions(
        openrouter_auth_file=auth_file,
        opencode_host=parsed.opencode_host,
        poll_interval_seconds=parsed.poll_interval_seconds,
        server_startup_timeout_seconds=parsed.server_startup_timeout_seconds,
    )


def parse_batch_config(config_payload: dict[str, object]) -> BatchConfig:
    task_folders = dedupe_keep_order(parse_str_list(
        config_payload.get("TASK_FOLDERS"),
        field_name="TASK_FOLDERS",
        allow_empty=False,
    ))

    models_value = config_payload.get("MODELS_TO_RUN")
    models_to_run: list[str] | None
    if models_value is None:
        models_to_run = None
    else:
        models_to_run = dedupe_keep_order(parse_str_list(
            models_value,
            field_name="MODELS_TO_RUN",
            allow_empty=False,
        ))

    launch_task_args = parse_str_list(
        config_payload.get("LAUNCH_TASK_ARGS", []),
        field_name="LAUNCH_TASK_ARGS",
        allow_empty=True,
    )
    validate_no_forbidden_forward_args(
        launch_task_args,
        source_name="LAUNCH_TASK_ARGS",
    )

    docker_image = config_payload.get("DOCKER_IMAGE", DOCKER_IMAGE_NAME)
    if not isinstance(docker_image, str) or not docker_image.strip():
        raise RuntimeError("DOCKER_IMAGE must be a non-empty string")

    return BatchConfig(
        task_folders=task_folders,
        models_to_run=models_to_run,
        launch_task_args=launch_task_args,
        docker_image=docker_image.strip(),
        build_docker_image=parse_bool_field(
            config_payload,
            field_name="BUILD_DOCKER_IMAGE",
            default=True,
        ),
        continue_on_error=parse_bool_field(
            config_payload,
            field_name="CONTINUE_ON_ERROR",
            default=True,
        ),
    )


def dedupe_keep_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def parse_cli_list_overrides(
    *,
    singular_values: list[str],
    csv_values: list[str],
    singular_flag: str,
    csv_flag: str,
) -> list[str] | None:
    if not singular_values and not csv_values:
        return None

    parsed: list[str] = []

    for value in singular_values:
        item = value.strip()
        if not item:
            raise RuntimeError(f"{singular_flag} must be a non-empty string")
        parsed.append(item)

    for value in csv_values:
        split_items = [item.strip() for item in value.split(",")]
        csv_items = [item for item in split_items if item]
        if not csv_items:
            raise RuntimeError(f"{csv_flag} was provided but no values were parsed")
        parsed.extend(csv_items)

    return dedupe_keep_order(parsed)


def apply_cli_overrides(config: BatchConfig, args: argparse.Namespace) -> BatchConfig:
    task_overrides = parse_cli_list_overrides(
        singular_values=args.task,
        csv_values=args.tasks,
        singular_flag="--task",
        csv_flag="--tasks",
    )
    model_overrides = parse_cli_list_overrides(
        singular_values=args.model,
        csv_values=args.models,
        singular_flag="--model",
        csv_flag="--models",
    )

    launch_task_args = list(config.launch_task_args)
    for value in args.launch_task_arg:
        arg = value.strip()
        if not arg:
            raise RuntimeError("--launch-task-arg must be a non-empty string")
        launch_task_args.append(arg)

    return replace(
        config,
        task_folders=task_overrides if task_overrides is not None else config.task_folders,
        models_to_run=model_overrides if model_overrides is not None else config.models_to_run,
        launch_task_args=launch_task_args,
    )


def write_default_config_template(output_path: Path, config: BatchConfig) -> Path:
    destination = output_path.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
    if destination.suffix.lower() != ".json":
        raise RuntimeError("--write-default-config path must end with .json")

    payload = {
        "TASK_FOLDERS": config.task_folders,
        "MODELS_TO_RUN": config.models_to_run,
        "LAUNCH_TASK_ARGS": config.launch_task_args,
        "DOCKER_IMAGE": config.docker_image,
        "BUILD_DOCKER_IMAGE": config.build_docker_image,
        "CONTINUE_ON_ERROR": config.continue_on_error,
    }
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return destination


def resolve_task_directory(task_folder: str) -> Path:
    task_path = Path(task_folder).expanduser()
    if task_path.is_absolute():
        return task_path

    repo_relative = REPO_ROOT / task_path
    if repo_relative.is_dir():
        return repo_relative

    tasks_relative = TASKS_ROOT / task_path
    if tasks_relative.is_dir():
        return tasks_relative

    return repo_relative


def validate_task_folders(task_folders: list[str]) -> None:
    resolved = [(folder, resolve_task_directory(folder)) for folder in task_folders]
    missing = [resolved_path for _, resolved_path in resolved if not resolved_path.is_dir()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Task folder(s) not found: {joined}")


def validate_launch_task_args(launch_task_args: list[str]) -> LaunchRuntimeOptions:
    return parse_launch_runtime_options(launch_task_args)


def build_docker_image_once(image_name: str) -> None:
    print(f"Building Docker image once: {image_name}")
    subprocess.run(
        ["docker", "build", "-t", image_name, "docker"],
        cwd=REPO_ROOT,
        check=True,
    )


def select_models(models_arg: str | None) -> list[tuple[str, dict[str, Any]]]:
    if models_arg is None:
        return list(MODEL_ROUTING.items())

    requested = [item.strip() for item in models_arg.split(",") if item.strip()]
    if not requested:
        raise RuntimeError("--models was provided but no model names were parsed")

    unknown_models = sorted({model for model in requested if model not in MODEL_ROUTING})
    if unknown_models:
        available = ", ".join(sorted(MODEL_ROUTING))
        unknown = ", ".join(unknown_models)
        raise RuntimeError(f"Unknown model(s): {unknown}. Available models: {available}")

    selected: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for model_name in requested:
        if model_name in seen:
            continue
        seen.add(model_name)
        selected.append((model_name, MODEL_ROUTING[model_name]))
    return selected


def discover_wav_file(target_dir: Path) -> Path:
    wav_files = sorted(
        path for path in target_dir.iterdir() if path.is_file() and path.suffix.lower() == ".wav"
    )
    if not wav_files:
        raise RuntimeError(f"No wav file found in target directory: {target_dir}")
    if len(wav_files) > 1:
        wav_names = ", ".join(path.name for path in wav_files)
        raise RuntimeError(f"Expected exactly one wav file in {target_dir}, found: {wav_names}")
    return wav_files[0]


def write_opencode_config(directory: Path, modelspecs: dict[str, Any]) -> Path:
    config_path = directory / "opencode.json"

    model_id_full = modelspecs.get("modelid")
    if not isinstance(model_id_full, str):
        raise RuntimeError(f"Model spec is missing a valid modelid: {modelspecs}")
    provider_id, _, model_id = model_id_full.partition("/")
    if not provider_id or not model_id:
        raise RuntimeError(f"Invalid model identifier: {model_id_full}")

    provider_block: dict[str, Any] = {}
    if "options" in modelspecs:
        provider_block = {
            provider_id: {
                "models": {
                    model_id: {
                        "options": modelspecs["options"],
                    },
                },
            },
        }

    payload: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "model": model_id_full,
    }

    if provider_block:
        payload["provider"] = provider_block

    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def prepare_model_directory(
    experiment_dir: Path,
    model_dir: Path,
    modelspecs: dict[str, Any],
    shared_files: list[str],
) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    config_path = write_opencode_config(model_dir, modelspecs)
    print(f"{model_dir.name}: wrote {config_path.name} for {model_dir.name}")

    for file_name in shared_files:
        source = experiment_dir / file_name
        destination = model_dir / file_name
        if destination.exists():
            print(f"Skipping existing file: {model_dir.name}/{file_name}")
            continue
        shutil.copy2(source, destination)


def _load_openrouter_auth_payload(auth_file: Path) -> dict[str, Any]:
    raw_text = auth_file.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise RuntimeError(f"OpenRouter auth file is empty: {auth_file}")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "openrouter": {
                "type": "api",
                "key": raw_text,
            }
        }

    if not isinstance(parsed, dict):
        raise RuntimeError(f"OpenRouter auth file must contain a JSON object: {auth_file}")
    return parsed


def _append_env_if_set(cmd: list[str], name: str) -> None:
    value = os.environ.get(name)
    if value is not None:
        cmd.extend(["--env", f"{name}={value}"])


def run_experiment_in_docker(
    image_name: str,
    target_dir: Path,
    runtime_options: LaunchRuntimeOptions,
    *,
    container_label: str,
) -> None:
    uid = os.getuid()
    gid = os.getgid()

    with tempfile.TemporaryDirectory(prefix="ofdm_opencode_home_") as home_dir_str:
        home_dir = Path(home_dir_str)
        auth_path = home_dir / ".local" / "share" / "opencode" / "auth.json"
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_payload = _load_openrouter_auth_payload(runtime_options.openrouter_auth_file)
        auth_path.write_text(
            json.dumps(auth_payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        cmd = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{uid}:{gid}",
            "--label",
            container_label,
            "--env",
            f"HOME={CONTAINER_HOME}",
            "--env",
            f"OPENCODE_HOST={runtime_options.opencode_host}",
            "--env",
            f"OPENCODE_POLL_INTERVAL_SECONDS={runtime_options.poll_interval_seconds}",
            "--env",
            f"OPENCODE_SERVER_STARTUP_TIMEOUT_SECONDS={runtime_options.server_startup_timeout_seconds}",
            "--mount",
            f"type=bind,src={str(home_dir.resolve())},dst={CONTAINER_HOME}",
            "--mount",
            f"type=bind,src={str(target_dir.resolve())},dst={CONTAINER_WORKSPACE}",
            "--workdir",
            CONTAINER_WORKSPACE,
        ]
        _append_env_if_set(cmd, "OPENCODE_SERVER_PASSWORD")
        _append_env_if_set(cmd, "OPENCODE_SERVER_USERNAME")
        cmd.append(image_name)
        subprocess.run(cmd, check=True)


def run_single_task_model_job(
    job: JobSpec,
    *,
    config: BatchConfig,
    runtime_options: LaunchRuntimeOptions,
) -> None:
    experiment_dir = resolve_task_directory(job.task).resolve()
    if not experiment_dir.is_dir():
        raise RuntimeError(f"Target directory does not exist or is not a directory: {experiment_dir}")

    if config.container_label is None:
        raise RuntimeError("container_label must be set before launching jobs")

    model_spec = MODEL_ROUTING.get(job.model)
    if model_spec is None:
        available = ", ".join(sorted(MODEL_ROUTING))
        raise RuntimeError(f"Unknown model '{job.model}'. Available models: {available}")

    wav_file = discover_wav_file(experiment_dir)
    shared_files = [*STANDARD_SHARED_FILES, wav_file.name]

    model_dir = experiment_dir / job.model
    if model_dir.exists():
        print(f"{job.task}/{job.model}: skipping existing model directory")
        return

    prepare_model_directory(experiment_dir, model_dir, model_spec, shared_files)
    print(f"{job.task}/{job.model}: launching Docker container")
    run_experiment_in_docker(
        config.docker_image,
        model_dir,
        runtime_options,
        container_label=config.container_label,
    )
    print(f"{job.task}/{job.model}: Docker container completed")


def resolve_models_to_run(models_to_run: list[str] | None) -> list[str]:
    models_arg = None if models_to_run is None else ",".join(models_to_run)
    selected_models = select_models(models_arg)
    return [model_name for model_name, _ in selected_models]


def build_job_specs(task_folders: list[str], models_to_run: list[str]) -> list[JobSpec]:
    return [
        JobSpec(task=task_folder, model=model_name)
        for task_folder in task_folders
        for model_name in models_to_run
    ]


def run_single_job(
    job: JobSpec,
    *,
    config: BatchConfig,
    runtime_options: LaunchRuntimeOptions,
) -> JobResult:
    start = time.monotonic()
    returncode = 0
    try:
        run_single_task_model_job(job, config=config, runtime_options=runtime_options)
    except Exception:
        traceback.print_exc()
        returncode = 1

    elapsed_seconds = time.monotonic() - start
    return JobResult(
        task=job.task,
        model=job.model,
        returncode=returncode,
        elapsed_seconds=elapsed_seconds,
    )


def print_summary(results: list[JobResult]) -> None:
    print("")
    print("Batch Summary")
    for result in sorted(results, key=lambda item: (item.task, item.model)):
        status = "ok" if result.returncode == 0 else f"failed({result.returncode})"
        print(f"- {result.task}/{result.model}: {status} in {result.elapsed_seconds:.1f}s")


def run_jobs_serial(
    job_specs: list[JobSpec],
    config: BatchConfig,
    runtime_options: LaunchRuntimeOptions,
) -> tuple[list[JobResult], list[JobResult]]:
    results: list[JobResult] = []
    failed_jobs: list[JobResult] = []
    total_jobs = len(job_specs)

    for index, job in enumerate(job_specs, start=1):
        print("")
        print(f"[{index}/{total_jobs}] Running {job.task}/{job.model}")
        result = run_single_job(job, config=config, runtime_options=runtime_options)
        results.append(result)

        if result.returncode == 0:
            print(f"Completed {job.task}/{job.model} in {result.elapsed_seconds:.1f}s")
            continue

        print(
            f"Failed {job.task}/{job.model} (exit {result.returncode}) after {result.elapsed_seconds:.1f}s",
            file=sys.stderr,
        )
        failed_jobs.append(result)
        if not config.continue_on_error:
            break

    return results, failed_jobs


def run_jobs_parallel(
    job_specs: list[JobSpec],
    config: BatchConfig,
    runtime_options: LaunchRuntimeOptions,
    *,
    nworkers: int,
) -> tuple[list[JobResult], list[JobResult]]:
    total_jobs = len(job_specs)
    worker_count = min(nworkers, total_jobs)
    print(f"Running {total_jobs} task/model jobs with {worker_count} workers")

    run_one = partial(run_single_job, config=config, runtime_options=runtime_options)
    results: list[JobResult] = []
    failed_jobs: list[JobResult] = []

    context = multiprocessing.get_context("spawn")
    with context.Pool(processes=worker_count) as pool:
        try:
            completed = 0
            for result in pool.imap_unordered(run_one, job_specs):
                completed += 1
                status = "ok" if result.returncode == 0 else f"failed({result.returncode})"
                print(
                    f"[{completed}/{total_jobs}] {result.task}/{result.model}: "
                    f"{status} in {result.elapsed_seconds:.1f}s"
                )
                results.append(result)

                if result.returncode != 0:
                    failed_jobs.append(result)
                    if not config.continue_on_error:
                        pool.terminate()
                        pool.join()
                        break
        except KeyboardInterrupt:
            print("Interrupted by user; terminating worker processes.", file=sys.stderr)
            pool.terminate()
            pool.join()
            raise
        except Exception:
            pool.terminate()
            pool.join()
            raise

    return results, failed_jobs


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config_path = args.config.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if config_path.suffix.lower() != ".json":
        raise RuntimeError(
            f"Only JSON config files are supported. Got: {config_path.name}"
        )

    config_payload = load_json_config(config_path)
    config = parse_batch_config(config_payload)
    config = apply_cli_overrides(config, args)

    if args.write_default_config is not None:
        written_path = write_default_config_template(args.write_default_config, config)
        print(f"Wrote default config template: {written_path}")
        return

    if shutil.which("docker") is None:
        raise RuntimeError("docker is not installed or not on PATH")

    config = replace(
        config,
        container_label=make_container_label(uuid.uuid4().hex, key="drsdrbench.batch"),
    )
    print(f"Using Docker cleanup label: {config.container_label}")

    validate_task_folders(config.task_folders)
    runtime_options = validate_launch_task_args(config.launch_task_args)

    if config.build_docker_image:
        build_docker_image_once(config.docker_image)
    else:
        print(f"Skipping Docker build. Expecting image to exist: {config.docker_image}")

    models_to_run = resolve_models_to_run(config.models_to_run)
    if not models_to_run:
        raise RuntimeError("No models resolved from MODELS_TO_RUN")

    job_specs = build_job_specs(config.task_folders, models_to_run)
    print(
        f"Prepared {len(job_specs)} task/model jobs "
        f"({len(config.task_folders)} tasks x {len(models_to_run)} models)"
    )

    try:
        if args.nworkers == 1:
            results, failed_jobs = run_jobs_serial(job_specs, config, runtime_options)
        else:
            results, failed_jobs = run_jobs_parallel(
                job_specs,
                config,
                runtime_options,
                nworkers=args.nworkers,
            )
    finally:
        if config.container_label is not None:
            cleanup_docker_containers(config.container_label)

    print_summary(results)

    if failed_jobs:
        failed_names = ", ".join(f"{result.task}/{result.model}" for result in failed_jobs)
        print(f"\nFailed jobs: {failed_names}", file=sys.stderr)
        sys.exit(1)

    print("\nAll tasks completed successfully.")


if __name__ == "__main__":
    main()
