"""ARVEN terminal text entry point (restores ``python app.py --text``).

``app.py`` (Day-1 GUI, frozen) imports ``run_text`` from this module; we only
provide the function it expects — no GUI code is touched. The REPL drives the
Day-3 terminal engine end to end (intent -> confirmation -> registry -> result
-> audit/memory/event), staying honest about capabilities, configuration and
offline providers.
"""

import sys


def run_text(argv=None):
    from cli import main as cli_main
    argv = list(argv) if argv is not None else ["--repl"]
    known = ("--repl", "--ask", "--mission", "--health", "--answer",
             "--orchestrate", "--features", "--feature", "--capabilities",
             "--resources", "--dependencies")
    if not any(flag in argv for flag in known):
        argv = argv + ["--repl"]
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(run_text())