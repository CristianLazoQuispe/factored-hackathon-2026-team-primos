#!/usr/bin/env bash
# Runs tests/history.test.mjs. The web project has no test framework and adding one would change its
# package.json and lockfile, so esbuild and jsdom are installed in a temporary folder, not in the project.
# Needs `npm ci` done in web/ (React and react-markdown are the project's own).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
web=$(dirname "$here")
[ -d "$web/node_modules/react" ] || { echo "run 'npm ci' in web/ first" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
(cd "$tmp" && echo '{"private":true,"type":"module"}' > package.json \
  && npm install --no-audit --no-fund --loglevel=error esbuild jsdom > /dev/null)
"$tmp/node_modules/.bin/esbuild" "$here/history.test.mjs" --bundle --platform=node --format=esm \
  --jsx=automatic --outfile="$tmp/history.test.mjs" --log-level=error --external:jsdom \
  "--alias:@=$web" "--alias:react=$web/node_modules/react" "--alias:react-dom=$web/node_modules/react-dom" \
  "--alias:react-markdown=$web/node_modules/react-markdown" \
  "--banner:js=import { createRequire } from 'module'; const require = createRequire(import.meta.url);"
node "$tmp/history.test.mjs"
