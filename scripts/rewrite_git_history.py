#!/usr/bin/env python3
import os
import sys

try:
    import git_filter_repo as fr
except ImportError:
    # Ensure git_filter_repo is importable
    sys.path.insert(
        0,
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "venv", "Lib", "site-packages"
            )
        ),
    )
    import git_filter_repo as fr


def main():
    # Setup RepoFilter arguments
    args = fr.FilteringOptions.default_options()
    args.force = True

    # We pass the body of the commit callback as a string
    args.commit_callback = """
# Read the commit mapping from file
mapping = {}
with open('commit-message-map.txt', 'r', encoding='utf-8') as f:
    for line in f:
        if '===' in line:
            sha, msg = line.strip().split('===', 1)
            mapping[sha.encode('utf-8')] = msg.encode('utf-8')

orig_sha = commit.original_id
if orig_sha in mapping:
    new_msg = mapping[orig_sha]
    if not new_msg.endswith(b'\\n'):
        new_msg += b'\\n'
    commit.message = new_msg
"""

    print("Starting history rewrite...")
    repo_filter = fr.RepoFilter(args)
    repo_filter.run()
    print("History rewrite completed successfully!")


if __name__ == "__main__":
    main()
