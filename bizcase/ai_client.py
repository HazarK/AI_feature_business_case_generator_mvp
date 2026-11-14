"""The ONLY module that talks to an LLM.

It runs the authenticated Claude Code CLI in non-interactive ("print") mode:

    claude -p --output-format json [--allowedTools WebSearch WebFetch]

* No shell is involved (argument list + prompt on stdin), so user text cannot inject commands.
* User text is embedded as a JSON data block and the prompt tells the model to treat it as data.
* The reply must be one JSON object that validates against models.BusinessCase; on a validation
  failure the errors are sent back once for a corrected attempt.
* Hard timeout; every failure surfaces as AnalysisError with a readable message.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date

from pydantic import ValidationError

from .models import BusinessCase, UserInputs, apply_user_overrides
from .prompts import build_prompt, build_retry_prompt

DEFAULT_TIMEOUT_S = 420
CLI_NAME = os.environ.get("BIZCASE_CLAUDE_BIN", "claude")


class AnalysisError(RuntimeError):
    pass


def cli_available() -> bool:
    return shutil.which(CLI_NAME) is not None


def _run_cli(prompt: str, *, web_research: bool, timeout_s: int, model: str | None) -> str:
    exe = shutil.which(CLI_NAME)
    if exe is None:
        raise AnalysisError(
            "Claude Code CLI not found on PATH. Install it and log in (`claude` once, interactively), "
            "or use the manual workflow described in the README."
        )
    cmd = [exe, "-p", "--output-format", "json"]
    if web_research:
        cmd += ["--allowedTools", "WebSearch", "WebFetch"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout_s, cwd=os.path.expanduser("~")
        )
    except subprocess.TimeoutExpired as e:
        raise AnalysisError(f"Claude did not answer within {timeout_s}s. Try again or disable web research.") from e
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise AnalysisError(f"Claude CLI exited with code {proc.returncode}: {detail}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise AnalysisError("Claude CLI returned output that is not JSON.") from e
    if envelope.get("is_error"):
        raise AnalysisError(f"Claude reported an error: {str(envelope.get('result'))[:600]}")
    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise AnalysisError("Claude returned an empty answer.")
    return result


def extract_json(text: str) -> dict:
    """Pull the first complete top-level JSON object out of a model reply (tolerates code fences/prose)."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    raise AnalysisError("No JSON object found in Claude's answer.")


def parse_case(text: str) -> BusinessCase:
    data = extract_json(text)
    data.pop("synthetic_example", None)  # only our bundled examples may set this
    return BusinessCase.model_validate(data)


def analyze(
    inputs: UserInputs,
    *,
    web_research: bool = True,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    model: str | None = None,
    runner=_run_cli,
) -> tuple[BusinessCase, list[str]]:
    """Run the AI analysis. Returns (validated business case, notes about user-value overrides).

    `runner` is injectable so tests can exercise parsing/validation/retry without a live CLI.
    """
    prompt = build_prompt(inputs, today=date.today().isoformat(), web_research=web_research)
    reply = runner(prompt, web_research=web_research, timeout_s=timeout_s, model=model)
    try:
        case = parse_case(reply)
    except (ValidationError, AnalysisError) as first_error:
        retry = build_retry_prompt(prompt, reply, str(first_error))
        reply = runner(retry, web_research=False, timeout_s=timeout_s, model=model)
        try:
            case = parse_case(reply)
        except (ValidationError, AnalysisError) as e:
            raise AnalysisError(f"Claude's answer failed validation twice. Last error:\n{e}") from e
    return apply_user_overrides(case, inputs)
