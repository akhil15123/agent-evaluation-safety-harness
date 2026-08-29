# Contributing

1. Create a focused branch and add or update an evaluation case for behavioral changes.
2. Install development dependencies with `pip install -e . pytest`.
3. Run `pytest -q` and the demo production gate before opening a pull request.
4. Never commit API keys, customer data, or unredacted production traces.

Small, explainable evaluators are preferred. A new metric should document what it measures, what it misses, and how its threshold affects the final release decision.
