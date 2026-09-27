#!/bin/sh
# Runs the test suite on the production image's Python and SQLite (the host's are older:
# a word that is reserved only in newer SQLite once slipped past host-only tests).
set -eu
cd "$(dirname "$0")/.."
docker build -q -f deploy/Dockerfile -t cheabby-test-image . >/dev/null
name="cheabby-unit-$$"
docker create --name "$name" -w /app --user 0 --entrypoint python cheabby-test-image \
  -m unittest discover -s tests -t . >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT
docker cp tests "$name":/app/tests
docker start -a "$name"
