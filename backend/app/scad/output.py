from __future__ import annotations

import re


ECHO_RE = re.compile(r'(?:ECHO:\s*)?["\']?(INFO|WARNING|ERROR|DEBUG):\s*([^"\']*)', re.IGNORECASE)


def parse_openscad_output(stdout: str, stderr: str) -> dict:
    messages: list[dict[str, str]] = []
    for line in (stdout + "\n" + stderr).splitlines():
        match = ECHO_RE.search(line)
        if not match:
            continue
        level, message = match.groups()
        key = None
        value = None
        if "=" in message:
            key, value = (part.strip() for part in message.split("=", 1))
        messages.append({"level": level.upper(), "message": message.strip(), "key": key, "value": value})
    return {
        "messages": messages,
        "info": [item for item in messages if item["level"] == "INFO"],
        "warnings": [item for item in messages if item["level"] == "WARNING"],
        "errors": [item for item in messages if item["level"] == "ERROR"],
    }
