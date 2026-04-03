from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import logging
import os
import re
import textwrap
import time
import sys
import tokenize
from dataclasses import dataclass, field
from functools import wraps
from io import StringIO
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from error_correction.config import github_token, hf_token
except ModuleNotFoundError:
    ERROR_CORRECTION_DIR = Path(__file__).resolve().parents[1]
    if str(ERROR_CORRECTION_DIR) not in sys.path:
        sys.path.insert(0, str(ERROR_CORRECTION_DIR))
    from config import github_token, hf_token

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except ModuleNotFoundError:
    class _RetryIfExceptionType:
        def __init__(self, exceptions: tuple[type[BaseException], ...]):
            self.exceptions = exceptions

    class _StopAfterAttempt:
        def __init__(self, attempts: int):
            self.attempts = attempts

    class _WaitExponential:
        def __init__(self, multiplier: int = 1, min: int = 1, max: int = 60):
            self.multiplier = multiplier
            self.min = min
            self.max = max

        def compute(self, attempt: int) -> float:
            return max(self.min, min(self.multiplier * (2 ** max(attempt - 1, 0)), self.max))

    def retry_if_exception_type(
        exceptions: tuple[type[BaseException], ...] | type[BaseException],
    ) -> _RetryIfExceptionType:
        if not isinstance(exceptions, tuple):
            exceptions = (exceptions,)
        return _RetryIfExceptionType(exceptions)

    def stop_after_attempt(attempts: int) -> _StopAfterAttempt:
        return _StopAfterAttempt(attempts)

    def wait_exponential(multiplier: int = 1, min: int = 1, max: int = 60) -> _WaitExponential:
        return _WaitExponential(multiplier=multiplier, min=min, max=max)

    def retry(
        retry: _RetryIfExceptionType | None = None,
        stop: _StopAfterAttempt | None = None,
        wait: _WaitExponential | None = None,
        reraise: bool = False,
    ):
        exceptions = retry.exceptions if retry is not None else (Exception,)
        attempts = stop.attempts if stop is not None else 1

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                current_attempt = 0
                while True:
                    try:
                        return func(*args, **kwargs)
                    except exceptions:
                        current_attempt += 1
                        if current_attempt >= attempts:
                            if reraise:
                                raise
                            return None
                        if wait is not None:
                            time.sleep(wait.compute(current_attempt))

            return wrapper

        return decorator

DEFAULT_REPO_SEARCH_TERMS = [
    "PyRTL",
    "pyrtl.Input",
    "pyrtl.Output",
    "pyrtl.Register",
    "pyrtl.MemBlock",
    "RTL tutorial",
    "arithmetic circuit",
    "memory module",
]

DEFAULT_CODE_SEARCH_TERMS = [
    "PyRTL",
    "pyrtl.Input",
    "pyrtl.Output",
    "pyrtl.Register",
    "pyrtl.MemBlock",
]

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "knowledge_base" / "pyrtl_github"
GENERIC_FILE_STEMS = {
    "__init__",
    "example",
    "examples",
    "main",
    "demo",
    "test",
    "tests",
    "tutorial",
    "run",
    "lab",
}
EXCLUDED_PATH_FRAGMENTS = (
    "/.github/",
    "/docs/",
    "/doc/",
    "/dist/",
    "/build/",
    "/venv/",
    "/site-packages/",
    "/vendor/",
    "/vendors/",
    "/third_party/",
    "/third-party/",
    "/external/",
    "__pycache__",
)
LICENSE_HINTS = ("copyright", "license", "apache", "mit", "bsd", "gnu", "solderpad")
PYRTL_DECLARATION_CALLS = {
    "Input": "input",
    "Output": "output",
    "Register": "register",
    "WireVector": "wire",
    "MemBlock": "memory",
    "RomBlock": "memory",
}
PYRTL_LIST_HELPERS = {
    "input_list": "input",
    "output_list": "output",
    "register_list": "register",
    "wirevector_list": "wire",
}
ARITHMETIC_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.MatMult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
)


class RetryableGitHubError(RuntimeError):
    """Raised when a GitHub request should be retried."""


@dataclass(frozen=True)
class RepoRecord:
    full_name: str
    html_url: str
    stars: int
    default_branch: str
    description: str = ""
    topics: tuple[str, ...] = ()

    @property
    def slug(self) -> str:
        return self.full_name.replace("/", "_")


@dataclass
class CodeSearchRecord:
    repo: RepoRecord
    path: str
    sha: str
    html_url: str
    matched_terms: set[str] = field(default_factory=set)


@dataclass
class SignalInfo:
    name: str
    kind: str
    bitwidth: str | None = None
    addrwidth: str | None = None

    @property
    def width_label(self) -> str:
        parts = []
        if self.bitwidth:
            parts.append(f"{self.bitwidth}-bit")
        if self.addrwidth and self.kind == "memory":
            parts.append(f"addrwidth {self.addrwidth}")
        return ", ".join(parts)


@dataclass
class SourceAnalysis:
    inputs: list[SignalInfo] = field(default_factory=list)
    outputs: list[SignalInfo] = field(default_factory=list)
    registers: list[SignalInfo] = field(default_factory=list)
    wires: list[SignalInfo] = field(default_factory=list)
    memories: list[SignalInfo] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    arithmetic_ops: int = 0
    comparison_ops: int = 0
    assignment_ops: int = 0
    conditional_blocks: int = 0
    select_calls: int = 0
    import_aliases: set[str] = field(default_factory=set)
    imported_symbols: dict[str, str] = field(default_factory=dict)

    @property
    def has_state(self) -> bool:
        return bool(self.registers or self.memories or self.conditional_blocks)

    @property
    def has_strong_logic(self) -> bool:
        interface_strength = bool(self.inputs and self.outputs)
        behavior_strength = bool(
            self.assignment_ops or self.arithmetic_ops or self.registers or self.memories
        )
        return interface_strength and behavior_strength


@dataclass
class CandidateSnippet:
    repo: RepoRecord
    path: str
    html_url: str
    matched_terms: set[str]
    snippet: str
    normalized_hash: str
    analysis: SourceAnalysis
    quality_score: float


@dataclass
class KBEntry:
    keyword: str
    category: str
    function_description: str
    input_descriptions: list[str]
    output_descriptions: list[str]
    code_snippet: str

    def render(self) -> str:
        input_block = "\n".join(self.input_descriptions)
        output_block = "\n".join(self.output_descriptions)
        return (
            f"[Keyword]: {self.keyword}\n\n"
            f"[Design Category]: {self.category}\n\n"
            "[Design Function Description]:\n"
            f"{self.function_description}\n\n"
            "[Input Signal Description]:\n"
            f"{input_block}\n\n"
            "[Output Signal Description]:\n"
            f"{output_block}\n\n"
            "[Design Detail]:\n"
            "```python\n"
            f"{self.code_snippet.rstrip()}\n"
            "```\n"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Search GitHub for PyRTL code, filter and deduplicate high-quality snippets, "
            "and emit knowledge-base entries that match the existing code_rag schema."
        )
    )
    # parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
    parser.add_argument(
    "--github-token",
    default=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or github_token,
)
    # parser.add_argument(
    #     "--hf-token",
    #     default=(
    #         os.getenv("HF_TOKEN")
    #         or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    #         or os.getenv("HUGGING_FACE_HUB_TOKEN")
    #     ),
    # )
    parser.add_argument(
    "--hf-token",
    default=(
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        or os.getenv("HUGGING_FACE_HUB_TOKEN")
        or hf_token
    ),
)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated .txt KB entries. Keep this under code_rag/knowledge_base.",
    )
    parser.add_argument("--min-stars", type=int, default=100, help="Minimum repo star count.")
    parser.add_argument("--top-n", type=int, default=25, help="Maximum number of KB entries to write.")
    parser.add_argument(
        "--max-repo-results-per-term",
        type=int,
        default=20,
        help="How many repositories to keep per repository search term.",
    )
    parser.add_argument(
        "--max-code-results-per-term",
        type=int,
        default=30,
        help="How many code search hits to inspect per file search term.",
    )
    parser.add_argument(
        "--repo-search-term",
        action="append",
        dest="repo_search_terms",
        help="Optional additional repository search term. Can be repeated.",
    )
    parser.add_argument(
        "--code-search-term",
        action="append",
        dest="code_search_terms",
        help="Optional additional code search term. Can be repeated.",
    )
    parser.add_argument(
        "--summary-backend",
        choices=("auto", "local", "hf_api", "heuristic"),
        default="auto",
        help="How to generate concise function descriptions.",
    )
    parser.add_argument(
        "--summary-model",
        default="google/flan-t5-small",
        help="Hugging Face model id used for local or inference-api summarization.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds for GitHub and Hugging Face requests.",
    )
    parser.add_argument(
        "--max-snippet-lines",
        type=int,
        default=120,
        help="Maximum lines kept in an extracted code snippet.",
    )
    parser.add_argument(
        "--max-full-file-lines",
        type=int,
        default=180,
        help="If a file is shorter than this, keep it whole after cleaning.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run the pipeline without writing files.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity.",
    )
    return parser


class GitHubClient:
    def __init__(self, token: str | None, timeout: int = 30):
        self.base_url = "https://api.github.com"
        self.token = token
        self.timeout = timeout
        self.repo_cache: dict[str, RepoRecord] = {}
        if not token:
            logging.warning(
                "No GitHub token detected. GitHub search endpoints are heavily rate-limited without one."
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PyRTL-KB-Builder/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _build_url(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        return url

    @retry(
        retry=retry_if_exception_type((RetryableGitHubError, URLError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )
    def get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        url = self._build_url(endpoint, params)
        request = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
                self._handle_rate_limit(response.headers)
                return json.loads(payload)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code in {403, 429}:
                self._sleep_until_rate_limit_reset(exc.headers)
                raise RetryableGitHubError(f"GitHub rate limit hit for {url}: {body}") from exc
            if exc.code in {500, 502, 503, 504}:
                raise RetryableGitHubError(f"Temporary GitHub failure for {url}: {body}") from exc
            if exc.code == 422:
                logging.warning("GitHub rejected query %s with 422: %s", url, body)
                return {"items": []}
            raise RuntimeError(f"GitHub request failed for {url}: {exc.code} {body}") from exc

    def _handle_rate_limit(self, headers: Any) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if remaining is None or reset is None:
            return
        try:
            remaining_int = int(remaining)
        except (TypeError, ValueError):
            return
        if remaining_int > 1:
            return
        self._sleep_until_rate_limit_reset(headers)

    def _sleep_until_rate_limit_reset(self, headers: Any) -> None:
        reset = headers.get("X-RateLimit-Reset")
        if not reset:
            time.sleep(5)
            return
        try:
            reset_ts = int(reset)
        except (TypeError, ValueError):
            time.sleep(5)
            return
        sleep_seconds = max(reset_ts - int(time.time()) + 1, 1)
        logging.warning("Sleeping %s seconds for GitHub rate-limit reset.", sleep_seconds)
        time.sleep(sleep_seconds)

    def search_repositories(self, term: str, min_stars: int, per_page: int) -> list[RepoRecord]:
        query = f'"{term}" language:Python stars:>={min_stars} archived:false'
        payload = self.get_json(
            "/search/repositories",
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(per_page, 100),
                "page": 1,
            },
        )
        repos: list[RepoRecord] = []
        for item in payload.get("items", []):
            if item.get("fork"):
                continue
            repo = self._repo_from_payload(item)
            self.repo_cache[repo.full_name] = repo
            repos.append(repo)
        return repos

    def search_code(self, term: str, per_page: int) -> list[CodeSearchRecord]:
        query = f'"{term}" language:Python extension:py'
        payload = self.get_json(
            "/search/code",
            {
                "q": query,
                "per_page": min(per_page, 100),
                "page": 1,
            },
        )
        results: list[CodeSearchRecord] = []
        for item in payload.get("items", []):
            repo_payload = item.get("repository", {})
            repo = self.repo_cache.get(repo_payload.get("full_name"))
            if repo is None:
                repo = self._repo_from_payload(repo_payload)
                self.repo_cache[repo.full_name] = repo
            results.append(
                CodeSearchRecord(
                    repo=repo,
                    path=item.get("path", ""),
                    sha=item.get("sha", ""),
                    html_url=item.get("html_url", ""),
                    matched_terms={term},
                )
            )
        return results

    def fetch_file_content(self, repo_full_name: str, path: str, ref: str | None = None) -> tuple[str, str]:
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        endpoint = f"/repos/{repo_full_name}/contents/{quote(path)}"
        payload = self.get_json(endpoint, params=params)
        encoded = payload.get("content", "")
        encoding = payload.get("encoding")
        if encoding != "base64":
            raise RuntimeError(f"Unsupported GitHub content encoding for {repo_full_name}:{path}: {encoding}")
        raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
        return raw, payload.get("html_url", "")

    @staticmethod
    def _repo_from_payload(payload: dict[str, Any]) -> RepoRecord:
        return RepoRecord(
            full_name=payload.get("full_name", ""),
            html_url=payload.get("html_url", ""),
            stars=int(payload.get("stargazers_count") or 0),
            default_branch=payload.get("default_branch", "main"),
            description=(payload.get("description") or "").strip(),
            topics=tuple(payload.get("topics") or ()),
        )


class DescriptionGenerator:
    def __init__(self, backend: str, model_name: str, hf_token: str | None, timeout: int):
        self.backend = backend
        self.model_name = model_name
        self.hf_token = hf_token
        self.timeout = timeout
        self._local_pipeline: Any | None = None
        self._local_init_attempted = False

    def refine(
        self,
        candidate: CandidateSnippet,
        category: str,
        heuristic_description: str,
    ) -> str:
        if self.backend == "heuristic":
            return heuristic_description

        prompt = build_summary_prompt(candidate, category)
        summary = None

        if self.backend in {"auto", "local"}:
            summary = self._run_local(prompt)
        if not summary and self.backend in {"auto", "hf_api"}:
            summary = self._run_hf_inference(prompt)

        return clean_summary_text(summary) if summary else heuristic_description

    def _run_local(self, prompt: str) -> str | None:
        pipeline_obj = self._ensure_local_pipeline()
        if pipeline_obj is None:
            return None
        try:
            result = pipeline_obj(
                prompt,
                max_new_tokens=96,
                do_sample=False,
                truncation=True,
            )
        except Exception as exc:  # pragma: no cover - depends on local model availability
            logging.warning("Local Hugging Face summarization failed: %s", exc)
            return None
        if not result:
            return None
        generated = result[0]
        if isinstance(generated, dict):
            return generated.get("generated_text") or generated.get("summary_text")
        return None

    def _ensure_local_pipeline(self) -> Any | None:
        if self._local_init_attempted:
            return self._local_pipeline
        self._local_init_attempted = True
        try:
            from transformers import pipeline
        except Exception as exc:  # pragma: no cover - import availability depends on env
            logging.info("transformers pipeline unavailable: %s", exc)
            return None
        try:
            self._local_pipeline = pipeline(
                "text2text-generation",
                model=self.model_name,
                tokenizer=self.model_name,
                device=-1,
            )
        except Exception as exc:  # pragma: no cover - local model availability depends on env
            logging.info("Could not initialize local summarization model %s: %s", self.model_name, exc)
            self._local_pipeline = None
        return self._local_pipeline

    @retry(
        retry=retry_if_exception_type((RetryableGitHubError, URLError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def _run_hf_inference(self, prompt: str) -> str | None:
        if not self.hf_token:
            return None
        body = json.dumps(
            {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 96,
                    "temperature": 0.1,
                    "return_full_text": False,
                },
                "options": {"wait_for_model": True},
            }
        ).encode("utf-8")
        request = Request(
            f"https://api-inference.huggingface.co/models/{self.model_name}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.hf_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="ignore")
            if exc.code in {429, 500, 502, 503, 504}:
                raise RetryableGitHubError(response_body) from exc
            logging.warning("HF inference request failed: %s %s", exc.code, response_body)
            return None
        if isinstance(payload, dict) and payload.get("error"):
            logging.warning("HF inference error: %s", payload["error"])
            return None
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                return first.get("generated_text") or first.get("summary_text")
        return None


def build_summary_prompt(candidate: CandidateSnippet, category: str) -> str:
    inputs = ", ".join(signal.name for signal in candidate.analysis.inputs[:6]) or "none detected"
    outputs = ", ".join(signal.name for signal in candidate.analysis.outputs[:6]) or "none detected"
    code_excerpt = truncate_text(candidate.snippet, limit=2200)
    return textwrap.dedent(
        f"""
        Summarize this PyRTL hardware design in 2 concise technical sentences.
        Mention the main behavior, whether it is combinational or sequential when clear,
        and avoid speculation or generic filler.

        Category: {category}
        Inputs: {inputs}
        Outputs: {outputs}
        Code:
        {code_excerpt}
        """
    ).strip()


def clean_summary_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return None
    return cleaned


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(levelname)s: %(message)s",
    )


def is_excluded_path(path: str) -> bool:
    lowered = f"/{path.lower().strip('/')}/"
    if not lowered.endswith(".py/"):
        return True
    if any(fragment in lowered for fragment in EXCLUDED_PATH_FRAGMENTS):
        return True
    filename = Path(path).name.lower()
    if filename in {"setup.py", "conftest.py"}:
        return True
    if filename.startswith("license"):
        return True
    return False


def strip_leading_boilerplate(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        if stripped.startswith("#"):
            start = idx
            block: list[str] = []
            while idx < len(lines) and (not lines[idx].strip() or lines[idx].lstrip().startswith("#")):
                block.append(lines[idx])
                idx += 1
            if any(hint in "\n".join(block).lower() for hint in LICENSE_HINTS):
                continue
            idx = start
            break
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote_marker = stripped[:3]
            start = idx
            block = [lines[idx]]
            if stripped.count(quote_marker) >= 2 and len(stripped) > 6:
                idx += 1
            else:
                idx += 1
                while idx < len(lines):
                    block.append(lines[idx])
                    if quote_marker in lines[idx]:
                        idx += 1
                        break
                    idx += 1
            if any(hint in "\n".join(block).lower() for hint in LICENSE_HINTS):
                continue
            idx = start
            break
        break
    return "\n".join(lines[idx:]).strip()


def parse_source_analysis(source: str) -> SourceAnalysis | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    analysis = SourceAnalysis()
    analysis.import_aliases, analysis.imported_symbols = collect_pyrtl_imports(tree)
    if not analysis.import_aliases and not analysis.imported_symbols:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            analysis.function_names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            analysis.class_names.append(node.name)
        elif isinstance(node, ast.Assign):
            record_assignment_declaration(node.targets, node.value, analysis)
        elif isinstance(node, ast.AnnAssign):
            record_assignment_declaration([node.target], node.value, analysis)
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.LShift, ast.BitOr)):
            analysis.assignment_ops += 1
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ARITHMETIC_BINOPS):
            analysis.arithmetic_ops += 1
        elif isinstance(node, ast.Compare):
            analysis.comparison_ops += 1
        elif isinstance(node, ast.With):
            if any(is_conditional_assignment(item.context_expr, analysis) for item in node.items):
                analysis.conditional_blocks += 1
        elif isinstance(node, ast.Call):
            call_name = resolve_pyrtl_call_name(node.func, analysis)
            if call_name in {"select", "mux"}:
                analysis.select_calls += 1

    dedupe_signals(analysis.inputs)
    dedupe_signals(analysis.outputs)
    dedupe_signals(analysis.registers)
    dedupe_signals(analysis.wires)
    dedupe_signals(analysis.memories)
    return analysis


def collect_pyrtl_imports(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    module_aliases: set[str] = set()
    imported_symbols: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pyrtl":
                    module_aliases.add(alias.asname or "pyrtl")
        elif isinstance(node, ast.ImportFrom) and node.module == "pyrtl":
            for alias in node.names:
                imported_symbols[alias.asname or alias.name] = alias.name
    return module_aliases, imported_symbols


def resolve_pyrtl_call_name(func: ast.expr, analysis: SourceAnalysis) -> str | None:
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id in analysis.import_aliases:
            return func.attr
    if isinstance(func, ast.Name) and func.id in analysis.imported_symbols:
        return analysis.imported_symbols[func.id]
    return None


def record_assignment_declaration(
    targets: list[ast.expr],
    value: ast.expr | None,
    analysis: SourceAnalysis,
) -> None:
    if not isinstance(value, ast.Call):
        return
    call_name = resolve_pyrtl_call_name(value.func, analysis)
    if call_name in PYRTL_DECLARATION_CALLS:
        assigned_names = flatten_target_names(targets)
        signal = parse_signal_from_call(call_name, value, assigned_names[0] if assigned_names else None)
        if signal:
            add_signal_to_analysis(signal, analysis)
    elif call_name in PYRTL_LIST_HELPERS:
        for signal in parse_signal_list_helper(call_name, value):
            add_signal_to_analysis(signal, analysis)


def flatten_target_names(targets: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                if isinstance(element, ast.Name):
                    names.append(element.id)
    return names


def parse_signal_from_call(call_name: str, call: ast.Call, assigned_name: str | None) -> SignalInfo | None:
    name_value = extract_string_arg(call, "name", positional_index=1) or assigned_name
    if not name_value:
        return None
    bitwidth = extract_expr_arg(call, "bitwidth", positional_index=0)
    addrwidth = extract_expr_arg(call, "addrwidth", positional_index=1 if call_name in {"MemBlock", "RomBlock"} else None)
    return SignalInfo(
        name=name_value,
        kind=PYRTL_DECLARATION_CALLS[call_name],
        bitwidth=bitwidth,
        addrwidth=addrwidth,
    )


def parse_signal_list_helper(call_name: str, call: ast.Call) -> list[SignalInfo]:
    if not call.args:
        return []
    spec = extract_constant_string(call.args[0])
    if not spec:
        return []
    signals: list[SignalInfo] = []
    for token in spec.split():
        if "/" in token:
            name, width = token.split("/", 1)
            signals.append(SignalInfo(name=name.strip(), kind=PYRTL_LIST_HELPERS[call_name], bitwidth=width.strip()))
        else:
            signals.append(SignalInfo(name=token.strip(), kind=PYRTL_LIST_HELPERS[call_name]))
    return signals


def extract_string_arg(call: ast.Call, keyword_name: str, positional_index: int | None) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return extract_constant_string(keyword.value)
    if positional_index is None:
        return None
    if positional_index < len(call.args):
        return extract_constant_string(call.args[positional_index])
    return None


def extract_expr_arg(call: ast.Call, keyword_name: str, positional_index: int | None) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return ast_expr_to_text(keyword.value)
    if positional_index is None:
        return None
    if positional_index < len(call.args):
        value = call.args[positional_index]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return None
        return ast_expr_to_text(value)
    return None


def extract_constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def ast_expr_to_text(node: ast.AST) -> str | None:
    try:
        text = ast.unparse(node)
    except Exception:
        return None
    return text.strip() or None


def add_signal_to_analysis(signal: SignalInfo, analysis: SourceAnalysis) -> None:
    target = {
        "input": analysis.inputs,
        "output": analysis.outputs,
        "register": analysis.registers,
        "wire": analysis.wires,
        "memory": analysis.memories,
    }[signal.kind]
    target.append(signal)


def dedupe_signals(signals: list[SignalInfo]) -> None:
    seen: set[tuple[str, str]] = set()
    deduped: list[SignalInfo] = []
    for signal in signals:
        key = (signal.name, signal.kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    signals[:] = deduped


def is_conditional_assignment(node: ast.AST, analysis: SourceAnalysis) -> bool:
    if isinstance(node, ast.Attribute):
        return resolve_pyrtl_call_name(node, analysis) == "conditional_assignment"
    if isinstance(node, ast.Call):
        return resolve_pyrtl_call_name(node.func, analysis) == "conditional_assignment"
    return False


def looks_like_pyrtl_logic(analysis: SourceAnalysis | None) -> bool:
    return analysis is not None and analysis.has_strong_logic


def extract_relevant_snippet(source: str, max_full_file_lines: int, max_snippet_lines: int) -> str:
    cleaned = strip_leading_boilerplate(source)
    lines = cleaned.splitlines()
    if len(lines) <= max_full_file_lines:
        return cleaned.strip()

    relevant_line_numbers: list[int] = []
    patterns = (
        r"\bimport\s+pyrtl\b",
        r"\bfrom\s+pyrtl\s+import\b",
        r"\bpyrtl\.(Input|Output|Register|WireVector|MemBlock|RomBlock)\b",
        r"\b(Input|Output|Register|WireVector|MemBlock|RomBlock)\(",
        r"<<=",
        r"\|=",
        r"\bconditional_assignment\b",
        r"\b(input_list|output_list|register_list|wirevector_list)\b",
    )
    compiled = [re.compile(pattern) for pattern in patterns]
    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in compiled):
            relevant_line_numbers.append(index)

    if not relevant_line_numbers:
        return "\n".join(lines[:max_snippet_lines]).strip()

    windows: list[tuple[int, int]] = []
    for line_number in relevant_line_numbers:
        windows.append((max(0, line_number - 2), min(len(lines), line_number + 3)))
    merged = merge_windows(windows)

    snippet_lines: list[str] = []
    for window_index, (start, end) in enumerate(merged):
        if window_index:
            snippet_lines.append("")
            snippet_lines.append("# ...")
            snippet_lines.append("")
        snippet_lines.extend(lines[start:end])
        if len(snippet_lines) >= max_snippet_lines:
            break

    return "\n".join(snippet_lines[:max_snippet_lines]).strip()


def merge_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not windows:
        return []
    windows = sorted(windows)
    merged = [windows[0]]
    for start, end in windows[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_normalized_hash(code: str) -> str:
    try:
        tokens = tokenize.generate_tokens(StringIO(code).readline)
        normalized = "".join(
            token.string
            for token in tokens
            if token.type
            not in {
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
            }
        )
    except tokenize.TokenError:
        normalized = re.sub(r"#.*", "", code)
        normalized = "".join(normalized.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def score_candidate(
    repo: RepoRecord,
    path: str,
    analysis: SourceAnalysis,
    snippet: str,
    matched_terms: Iterable[str],
) -> float:
    score = 0.0
    score += min(repo.stars / 25.0, 20.0)
    score += min(len(analysis.inputs), 5) * 2.5
    score += min(len(analysis.outputs), 5) * 3.0
    score += min(len(analysis.registers), 4) * 4.0
    score += min(len(analysis.memories), 2) * 6.0
    score += min(analysis.arithmetic_ops, 8) * 1.5
    score += min(analysis.assignment_ops, 10) * 1.5
    score += analysis.conditional_blocks * 3.0
    score += analysis.select_calls * 1.5
    score += min(len(list(matched_terms)), 4) * 2.0

    lowered_path = path.lower()
    if "/test" in lowered_path or "/tests" in lowered_path:
        score -= 6.0
    if "/example" in lowered_path or "/examples" in lowered_path:
        score -= 1.5
    if "/tutorial" in lowered_path or "/demo" in lowered_path:
        score -= 1.0

    line_count = len(snippet.splitlines())
    if line_count < 8:
        score -= 8.0
    elif line_count <= 120:
        score += 4.0
    else:
        score -= min((line_count - 120) / 10.0, 8.0)

    if not analysis.outputs:
        score -= 10.0
    if not analysis.inputs:
        score -= 10.0
    return score


def determine_design_category(analysis: SourceAnalysis, snippet: str) -> str:
    lowered = snippet.lower()
    signal_names = " ".join(signal.name.lower() for signal in analysis.inputs + analysis.outputs)
    if analysis.memories:
        return "Memory"
    if "valid" in signal_names or "ready" in signal_names or "handshake" in lowered:
        return "Interface"
    if analysis.registers and analysis.arithmetic_ops:
        return "Datapath"
    if analysis.registers or analysis.conditional_blocks:
        return "Sequential Logic"
    if analysis.arithmetic_ops:
        return "Arithmetic"
    if analysis.comparison_ops or "fsm" in lowered or "state" in lowered:
        return "Control"
    return "Combinational Logic"


def derive_keyword(candidate: CandidateSnippet) -> str:
    stem = Path(candidate.path).stem
    cleaned_stem = sanitize_keyword(stem)
    descriptive_functions = [name for name in candidate.analysis.function_names if is_descriptive_name(name)]
    if cleaned_stem and cleaned_stem.lower() not in GENERIC_FILE_STEMS and len(cleaned_stem) >= 3:
        base = cleaned_stem
    elif descriptive_functions:
        base = sanitize_keyword(descriptive_functions[0])
    elif candidate.analysis.outputs:
        base = sanitize_keyword(candidate.analysis.outputs[0].name)
    else:
        base = sanitize_keyword(f"{candidate.repo.slug}_{stem}") or "pyrtl_design"

    if base.lower() in GENERIC_FILE_STEMS:
        repo_name = sanitize_keyword(candidate.repo.full_name.split("/")[-1])
        base = f"{repo_name}_{base}"
    return base


def sanitize_keyword(value: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("._")
    return sanitized


def is_descriptive_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in GENERIC_FILE_STEMS:
        return False
    return len(lowered) >= 3 and not lowered.startswith("test")


def heuristic_function_description(candidate: CandidateSnippet, category: str) -> str:
    analysis = candidate.analysis
    input_names = format_signal_name_list(
        [signal.name for signal in analysis.inputs[:4]],
        fallback="the detected input signals",
    )
    output_names = format_signal_name_list(
        [signal.name for signal in analysis.outputs[:4]],
        fallback="the detected output signals",
    )
    sequential_text = "sequential" if analysis.has_state else "combinational"
    register_names = format_signal_name_list(
        [signal.name for signal in analysis.registers[:3]],
        fallback="the declared register signals",
    )
    memory_names = format_signal_name_list(
        [signal.name for signal in analysis.memories[:2]],
        fallback="the declared memory structures",
    )

    first_sentence = (
        f"This PyRTL snippet implements a {sequential_text} {category.lower()} block that consumes "
        f"{input_names} and drives {output_names}."
    )

    if analysis.memories:
        second_sentence = (
            f"It uses memory structure {memory_names} to store or retrieve stateful data within the datapath."
        )
    elif analysis.registers:
        second_sentence = (
            f"It keeps state in register signal {register_names} and updates outputs through PyRTL assignments."
        )
    elif analysis.arithmetic_ops:
        second_sentence = (
            "The logic is centered on arithmetic and bit-level operations expressed directly in PyRTL wire assignments."
        )
    elif analysis.comparison_ops or analysis.select_calls:
        second_sentence = (
            "The logic relies on comparisons and conditional selection to steer control or output behavior."
        )
    else:
        second_sentence = (
            "The implementation is expressed with explicit PyRTL signal declarations and hardware-style assignments."
        )

    return f"{first_sentence} {second_sentence}"


def format_signal_name_list(names: list[str], fallback: str) -> str:
    if not names:
        return fallback
    rendered = [f"`{name}`" for name in names]
    if len(rendered) == 1:
        return rendered[0]
    if len(rendered) == 2:
        return f"{rendered[0]} and {rendered[1]}"
    return ", ".join(rendered[:-1]) + f", and {rendered[-1]}"


def describe_input_signal(signal: SignalInfo) -> str:
    name = signal.name
    width = f"{signal.bitwidth}-bit " if signal.bitwidth else ""
    lowered = name.lower()
    if re.search(r"(clk|clock)$", lowered):
        detail = "clock input that advances sequential state in the PyRTL design."
    elif re.search(r"(^rst$|reset|rst_n|reset_n)", lowered):
        detail = "reset input used to initialize or clear design state."
    elif re.search(r"(we|write_en|write_enable|wr_en)", lowered):
        detail = "write-enable control input that gates state or memory updates."
    elif re.search(r"(re|read_en|read_enable|rd_en)", lowered):
        detail = "read-enable control input that qualifies data access."
    elif "addr" in lowered:
        detail = "address input used to select a register or memory location."
    elif re.search(r"(data|din|payload|value)", lowered):
        detail = "data input carried into the PyRTL datapath."
    elif re.search(r"(valid)", lowered):
        detail = "handshake-valid input indicating that the associated input data is meaningful."
    elif re.search(r"(ready)", lowered):
        detail = "handshake-ready input that coordinates transfer timing."
    elif re.search(r"(sel|select|mux|mode|opcode|op)", lowered):
        detail = "control input that selects between alternative operations or paths."
    elif re.search(r"(en|enable)$", lowered):
        detail = "enable input that gates activity or state updates."
    else:
        detail = "PyRTL input signal declared in the extracted hardware snippet."
    return f"- `{name}`: {width}{detail}"


def describe_output_signal(signal: SignalInfo) -> str:
    name = signal.name
    width = f"{signal.bitwidth}-bit " if signal.bitwidth else ""
    lowered = name.lower()
    if re.search(r"(data|dout|result|out|sum|value)", lowered):
        detail = "primary data output produced by the PyRTL logic."
    elif re.search(r"(valid)", lowered):
        detail = "handshake-valid output indicating when the output data is usable."
    elif re.search(r"(ready)", lowered):
        detail = "handshake-ready output used to coordinate downstream transfers."
    elif re.search(r"(carry|overflow)", lowered):
        detail = "status output that reports arithmetic carry or overflow conditions."
    elif re.search(r"(match|hit|eq|gt|lt|done)", lowered):
        detail = "status output that reports a comparison or completion condition."
    else:
        detail = "PyRTL output signal driven by the extracted hardware snippet."
    return f"- `{name}`: {width}{detail}"


def build_kb_entry(candidate: CandidateSnippet, generator: DescriptionGenerator) -> KBEntry:
    category = determine_design_category(candidate.analysis, candidate.snippet)
    heuristic_description = heuristic_function_description(candidate, category)
    function_description = generator.refine(candidate, category, heuristic_description)
    keyword = derive_keyword(candidate)
    input_descriptions = (
        [describe_input_signal(signal) for signal in candidate.analysis.inputs]
        or ["- `none_detected`: No direct PyRTL input declarations were recovered from the snippet."]
    )
    output_descriptions = (
        [describe_output_signal(signal) for signal in candidate.analysis.outputs]
        or ["- `none_detected`: No direct PyRTL output declarations were recovered from the snippet."]
    )
    return KBEntry(
        keyword=keyword,
        category=category,
        function_description=function_description,
        input_descriptions=input_descriptions,
        output_descriptions=output_descriptions,
        code_snippet=candidate.snippet,
    )


def build_output_path(output_dir: Path, entry: KBEntry, content_hash: str) -> Path:
    file_stem = sanitize_keyword(entry.keyword) or "pyrtl_design"
    return output_dir / f"{file_stem}__{content_hash[:10]}.txt"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def collect_repositories(
    client: GitHubClient,
    repo_search_terms: list[str],
    min_stars: int,
    max_repo_results_per_term: int,
) -> dict[str, RepoRecord]:
    repositories: dict[str, RepoRecord] = {}
    for term in repo_search_terms:
        logging.info("Searching repositories for term: %s", term)
        for repo in client.search_repositories(term, min_stars=min_stars, per_page=max_repo_results_per_term):
            existing = repositories.get(repo.full_name)
            if existing is None or repo.stars > existing.stars:
                repositories[repo.full_name] = repo
    logging.info("Collected %s unique repositories.", len(repositories))
    return repositories


def collect_code_hits(
    client: GitHubClient,
    repositories: dict[str, RepoRecord],
    code_search_terms: list[str],
    min_stars: int,
    max_code_results_per_term: int,
) -> dict[tuple[str, str], CodeSearchRecord]:
    code_hits: dict[tuple[str, str], CodeSearchRecord] = {}
    for term in code_search_terms:
        logging.info("Searching code for term: %s", term)
        for hit in client.search_code(term, per_page=max_code_results_per_term):
            if hit.repo.stars < min_stars:
                continue
            if not hit.repo.full_name:
                continue
            repositories.setdefault(hit.repo.full_name, hit.repo)
            key = (hit.repo.full_name, hit.path)
            existing = code_hits.get(key)
            if existing is None:
                code_hits[key] = hit
            else:
                existing.matched_terms.update(hit.matched_terms)
    logging.info("Collected %s unique Python file hits.", len(code_hits))
    return code_hits


def build_candidates(
    client: GitHubClient,
    code_hits: dict[tuple[str, str], CodeSearchRecord],
    max_full_file_lines: int,
    max_snippet_lines: int,
) -> list[CandidateSnippet]:
    candidates: list[CandidateSnippet] = []
    seen_hashes: set[str] = set()

    for hit in sorted(code_hits.values(), key=lambda item: (-item.repo.stars, item.path)):
        if is_excluded_path(hit.path):
            continue
        try:
            raw_source, html_url = client.fetch_file_content(
                repo_full_name=hit.repo.full_name,
                path=hit.path,
                ref=hit.repo.default_branch,
            )
        except Exception as exc:
            logging.warning("Skipping %s:%s due to fetch error: %s", hit.repo.full_name, hit.path, exc)
            continue

        cleaned_source = strip_leading_boilerplate(raw_source)
        analysis = parse_source_analysis(cleaned_source)
        if not looks_like_pyrtl_logic(analysis):
            continue

        snippet = extract_relevant_snippet(
            cleaned_source,
            max_full_file_lines=max_full_file_lines,
            max_snippet_lines=max_snippet_lines,
        )
        normalized_hash = compute_normalized_hash(snippet)
        if normalized_hash in seen_hashes:
            continue

        quality_score = score_candidate(
            repo=hit.repo,
            path=hit.path,
            analysis=analysis,
            snippet=snippet,
            matched_terms=hit.matched_terms,
        )
        if quality_score <= 0:
            continue

        seen_hashes.add(normalized_hash)
        candidates.append(
            CandidateSnippet(
                repo=hit.repo,
                path=hit.path,
                html_url=html_url or hit.html_url,
                matched_terms=set(hit.matched_terms),
                snippet=snippet,
                normalized_hash=normalized_hash,
                analysis=analysis,
                quality_score=quality_score,
            )
        )
    logging.info("Built %s candidate snippets after filtering and deduplication.", len(candidates))
    return sorted(candidates, key=lambda item: item.quality_score, reverse=True)


def write_entries(
    entries: list[tuple[KBEntry, CandidateSnippet]],
    output_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    written_paths: list[Path] = []
    for entry, candidate in entries:
        rendered = entry.render()
        output_path = build_output_path(output_dir, entry, candidate.normalized_hash)
        if dry_run:
            logging.info("Dry-run: would write %s", output_path)
        else:
            atomic_write_text(output_path, rendered)
            logging.info("Wrote KB entry: %s", output_path)
        written_paths.append(output_path)
    return written_paths


def ensure_term_list(custom_terms: list[str] | None, defaults: list[str]) -> list[str]:
    combined = list(defaults)
    if custom_terms:
        combined.extend(custom_terms)
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in combined:
        normalized = term.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_terms.append(normalized)
    return unique_terms


def validate_output_dir(path: Path) -> None:
    resolved = path.resolve()
    kb_root = (Path(__file__).resolve().parent / "knowledge_base").resolve()
    if kb_root not in resolved.parents and resolved != kb_root:
        logging.warning(
            "Output directory %s is outside the default knowledge_base tree. "
            "Your current indexer only walks ./code_rag/knowledge_base by default.",
            resolved,
        )


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    repo_search_terms = ensure_term_list(args.repo_search_terms, DEFAULT_REPO_SEARCH_TERMS)
    code_search_terms = ensure_term_list(args.code_search_terms, DEFAULT_CODE_SEARCH_TERMS)
    validate_output_dir(args.output_dir)

    client = GitHubClient(token=args.github_token, timeout=args.timeout)
    repositories = collect_repositories(
        client=client,
        repo_search_terms=repo_search_terms,
        min_stars=args.min_stars,
        max_repo_results_per_term=args.max_repo_results_per_term,
    )
    code_hits = collect_code_hits(
        client=client,
        repositories=repositories,
        code_search_terms=code_search_terms,
        min_stars=args.min_stars,
        max_code_results_per_term=args.max_code_results_per_term,
    )
    candidates = build_candidates(
        client=client,
        code_hits=code_hits,
        max_full_file_lines=args.max_full_file_lines,
        max_snippet_lines=args.max_snippet_lines,
    )

    if not candidates:
        logging.error("No PyRTL snippets survived filtering. Try lowering --min-stars or expanding search terms.")
        return 1

    generator = DescriptionGenerator(
        backend=args.summary_backend,
        model_name=args.summary_model,
        hf_token=args.hf_token,
        timeout=args.timeout,
    )

    selected = candidates[: args.top_n]
    logging.info("Selected top %s snippets by heuristic quality score.", len(selected))
    entries = [(build_kb_entry(candidate, generator), candidate) for candidate in selected]
    write_entries(entries, output_dir=args.output_dir, dry_run=args.dry_run)

    logging.info("Completed PyRTL KB generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
