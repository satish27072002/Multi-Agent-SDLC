from __future__ import annotations

from src.evals.runner import EvalCase


DEFAULT_EVAL_CASES = [
    EvalCase(
        name="fastapi-health-endpoint",
        task="Create a FastAPI health endpoint with tests",
        required_files=["src/main.py", "tests/test_main.py"],
        required_substrings=["health", "pytest"],
    ),
    EvalCase(
        name="python-calculator-module",
        task="Create a Python calculator module with add and subtract tests",
        required_files=["calculator.py", "tests/test_calculator.py"],
        required_substrings=["def add", "def subtract"],
    ),
]
