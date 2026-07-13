"""Run ``python -m intelliqx_llm`` to invoke the smoke CLI.

Equivalent to ``intelliqx-llm-smoke`` on the command line. Useful
when the entry point script is not on ``PATH`` (e.g. inside a
constrained CI container) but the Python module is.
"""

from intelliqx_llm._smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
