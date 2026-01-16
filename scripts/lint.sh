#!/bin/bash
# Wrapper for pre-commit hooks that shows fix commands on failure

set -e

case "$1" in
    check)
        shift
        uv run ruff check "$@" || {
            echo -e "\n\033[33mTo fix: uv run ruff check --fix .\033[0m"
            exit 1
        }
        ;;
    format)
        shift
        uv run ruff format --check "$@" || {
            echo -e "\n\033[33mTo fix: uv run ruff format .\033[0m"
            exit 1
        }
        ;;
    *)
        echo "Usage: lint.sh [check|format] [files...]"
        exit 1
        ;;
esac
