import sys

from cc_usage_reporter.cli import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        argv = ["gui"]
    raise SystemExit(main(argv))
