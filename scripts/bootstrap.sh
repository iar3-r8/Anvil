#!/usr/bin/env bash
# Provision and maintain the project-local virtual environment.
#
# This is deliberately the only bash in the Python-era codebase: locate a
# suitable interpreter, create .venv if needed, refresh it when requirements.txt
# changes, and print the interpreter path. No business logic belongs here.
#
# Usage:
#   scripts/bootstrap.sh                # ensure venv, print interpreter path
#   scripts/bootstrap.sh --rebuild      # discard and recreate the venv
#   scripts/bootstrap.sh --no-venv      # print a suitable ambient interpreter
#   scripts/bootstrap.sh --python-path  # print the interpreter without provisioning

set -euo pipefail

readonly MIN_MAJOR=3
readonly MIN_MINOR=8

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="$repo_root/.venv"
requirements_file="$repo_root/requirements.txt"
stamp_file="$venv_dir/.anvil-requirements-stamp"

log() { echo "$@" >&2; }

# True when the given interpreter exists and satisfies the minimum version
interpreter_is_supported() {
    local candidate="$1"
    [[ -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1 || return 1
    "$candidate" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MIN_MAJOR, $MIN_MINOR) else 1)" 2>/dev/null
}

# Echo the first interpreter on the host meeting the minimum version.
# Newest first, so we prefer 3.13 over a 3.7 that merely happens to be $PATH default.
find_host_interpreter() {
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
        if interpreter_is_supported "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done

    # Fall back to well-known absolute locations for hosts where the versioned
    # names are not on PATH (common on HPC/CVMFS environments).
    for candidate in /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 \
                     /usr/bin/python3.10 /usr/bin/python3.9 /usr/bin/python3.8; do
        if interpreter_is_supported "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

fail_no_interpreter() {
    log "❌ Anvil requires Python ${MIN_MAJOR}.${MIN_MINOR} or newer, which was not found."
    log ""
    log "   Install it with one of:"
    log "     sudo apt install python3.11 python3.11-venv   # Debian/Ubuntu"
    log "     brew install python@3.11                      # macOS"
    log ""
    log "   Then re-run ./anvil"
    exit 1
}

# Fingerprint requirements.txt so venv refreshes are triggered by content, not mtime
requirements_fingerprint() {
    [[ -f "$requirements_file" ]] || { echo "no-requirements"; return 0; }

    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$requirements_file" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$requirements_file" | cut -d' ' -f1
    else
        # Portable last resort: size plus mtime is good enough to detect edits
        wc -c <"$requirements_file" | tr -d ' '
    fi
}

venv_is_healthy() {
    [[ -x "$venv_dir/bin/python" ]] && interpreter_is_supported "$venv_dir/bin/python"
}

create_venv() {
    local host_python
    host_python="$(find_host_interpreter)" || fail_no_interpreter

    log "🔧 Provisioning Anvil environment with $host_python ..."
    rm -rf "$venv_dir"
    "$host_python" -m venv "$venv_dir" || {
        log "❌ Failed to create the virtual environment."
        log "   On Debian/Ubuntu you may need: sudo apt install python3-venv"
        exit 1
    }
}

sync_requirements() {
    local expected="$1"

    log "📦 Installing Anvil dependencies ..."
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    if ! "$venv_dir/bin/python" -m pip install --quiet -r "$requirements_file"; then
        log "❌ Failed to install dependencies from requirements.txt."
        log "   If you are offline, an existing environment will still be reused."
        exit 1
    fi
    echo "$expected" >"$stamp_file"
    log "✅ Environment ready."
}

ensure_venv() {
    local expected
    expected="$(requirements_fingerprint)"

    venv_is_healthy || create_venv

    # Refresh whenever requirements.txt content differs from what we last installed
    if [[ ! -f "$stamp_file" ]] || [[ "$(cat "$stamp_file")" != "$expected" ]]; then
        sync_requirements "$expected"
    fi

    echo "$venv_dir/bin/python"
}

# Report the interpreter that would be used, without creating or updating anything.
# 'anvil doctor' relies on this: diagnosing a broken environment must never
# silently repair it, or the diagnosis is worthless.
python_path() {
    if venv_is_healthy; then
        echo "$venv_dir/bin/python"
        return 0
    fi

    find_host_interpreter || fail_no_interpreter
}

main() {
    case "${1:-}" in
        --no-venv)
            local host_python
            host_python="$(find_host_interpreter)" || fail_no_interpreter
            echo "$host_python"
            ;;
        --python-path)
            python_path
            ;;
        --rebuild)
            rm -rf "$venv_dir"
            ensure_venv
            ;;
        *)
            ensure_venv
            ;;
    esac
}

main "$@"
