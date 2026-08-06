"""Safe ``.env`` reading and writing.

Two properties this module guarantees:

* parsing is line-wise and nothing is ever exported into the process
  environment, so a value containing spaces or quotes cannot be word-split and
  no secret leaks into the environment of a child process;
* files are read, modified in memory and rewritten, so no value needs escaping
  and no metacharacter is special.
"""

from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

PathLike = Union[str, Path]


def read(path: PathLike) -> Dict[str, str]:
    """Parse ``path`` into a mapping of key to value.

    A missing file yields an empty mapping rather than an error, so commands that
    do not need configuration (``help``, ``doctor``) work before setup has run.
    Later duplicate keys win.
    """
    path = Path(path)

    if not path.is_file():
        return {}

    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(raw_line)
        if parsed is not None:
            key, value = parsed
            values[key] = value

    return values


def get(path: PathLike, key: str, default: Optional[str] = None) -> Optional[str]:
    return read(path).get(key, default)


def set_value(path: PathLike, key: str, value: str) -> None:
    """Set ``key`` to ``value`` in ``path``, replacing any existing entry.

    The key is matched exactly, so setting ``KEY`` never disturbs
    ``ANTHROPIC_API_KEY``. Surrounding lines, comments and ordering are
    preserved; a new key is appended.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    new_line = _format_line(key, value)

    replaced = False
    for index, line in enumerate(lines):
        parsed = _parse_line(line)
        if parsed is not None and parsed[0] == key:
            lines[index] = new_line
            replaced = True
            break

    if not replaced:
        lines.append(new_line)

    _write_lines(path, lines)


def write(
    path: PathLike,
    pairs: Sequence[Tuple[str, str]],
    sections: Optional[Mapping[str, str]] = None,
) -> None:
    """Write ``pairs`` to ``path``, replacing any existing content.

    ``sections`` optionally maps a key to a comment heading emitted just before
    it, which keeps the generated file readable.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sections = sections or {}
    lines = []

    for key, value in pairs:
        heading = sections.get(key)
        if heading:
            if lines:
                lines.append("")
            lines.append("# {}".format(heading))
        lines.append(_format_line(key, value))

    _write_lines(path, lines)


def _parse_line(raw_line: str) -> Optional[Tuple[str, str]]:
    line = raw_line.strip()

    if not line or line.startswith("#"):
        return None

    if line.startswith("export "):
        line = line[len("export ") :].strip()

    if "=" not in line:
        return None

    # Split once only: values legitimately contain '=' (base64, JWTs).
    key, _, value = line.partition("=")
    key = key.strip()

    if not key:
        return None

    return key, _unquote(value.strip())


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _format_line(key: str, value: str) -> str:
    return "{}={}".format(key, value)


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
