#!/usr/bin/env python3
"""
Generate a commit message mapping for git-filter-repo.
Reads the current commit history, applies conventional-commits transformation,
and outputs a mapping file: <SHA>===<new message>
"""

import subprocess
import re


def main():
    # Get all commit SHAs + messages
    result = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x00---END---"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )

    # Parse the output
    commits = []
    # Using split with ---END---\n to find blocks
    blocks = result.stdout.split("---END---\n")
    for block in blocks:
        if not block.strip():
            continue
        parts = block.split("\x00")
        if len(parts) < 2:
            continue
        sha = parts[0].strip()
        message = parts[1].strip()
        commits.append((sha, message))

    # Conventional commits transformation
    TYPE_MAP = {
        "add": "feat",
        "implement": "feat",
        "integrate": "feat",
        "unify": "feat",
        "fix": "fix",
        "resolve": "fix",
        "address": "fix",
        "refactor": "refactor",
        "standardize": "refactor",
        "align": "refactor",
        "segregate": "refactor",
        "update": "docs",
        "archive": "docs",
        "style": "style",
        "overhaul": "style",
        "build": "build",
        "remediate": "build",
    }

    def transform_message(message: str) -> str:
        """Transform a commit message to conventional commits format."""
        if not message:
            return "chore: initial commit"
        lines = message.splitlines()
        title = lines[0].strip()

        # If already conventional (e.g. feat: ..., docs: ...), normalize it
        m = re.match(r"^(\w+)(\([^)]+\))?: (.+)", title)
        if m:
            type_ = m.group(1).lower()
            scope = m.group(2) or ""
            desc = m.group(3).strip()
            desc = desc[0].lower() + desc[1:] if desc else desc
            desc = desc.rstrip(".")
            if len(desc) > 72:
                desc = desc[:69] + "..."
            return f"{type_}{scope}: {desc}"

        # Otherwise, look at the first word of the message
        words = title.split()
        if not words:
            return "chore: update"
        first_word = words[0].lower().rstrip(":,")
        type_ = TYPE_MAP.get(first_word, "chore")

        # Capitalize/lowercase normalization
        desc = title
        # strip first word if we match a keyword
        if first_word in TYPE_MAP:
            desc = " ".join(words[1:])

        if not desc:
            desc = title

        desc = desc[0].lower() + desc[1:] if desc else desc
        desc = desc.rstrip(".")

        if len(desc) > 72:
            desc = desc[:69] + "..."

        return f"{type_}: {desc}"

    # Output the mapping
    with open("commit-message-map.txt", "w", encoding="utf-8") as f:
        for sha, message in commits:
            new_message = transform_message(message)
            f.write(f"{sha}==={new_message}\n")


if __name__ == "__main__":
    main()
