#!/bin/sh
# One-time: use repo git hooks (strips Cursor co-author trailers on commit).
cd "$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
git config core.hooksPath .githooks
echo "core.hooksPath set to .githooks"
