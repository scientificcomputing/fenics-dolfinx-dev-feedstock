#!/usr/bin/env bash
# Build one of the dev recipes with rattler-build.
#
# Usage: dev/build.sh <recipe-dir> <variant-config.yaml> [extra rattler-build args...]
#
# Packages built in earlier stages are read from $LOCAL_CHANNEL
# (default: ./local-channel), which takes priority over conda-forge.
# New packages are written to $OUTPUT_DIR (default: ./output).
# Versions and git revisions come from the DEV_* environment variables
# (see dev/prepare.py); without them, the recipes build main as 0.0.0.dev0.
set -euo pipefail

recipe=$1
config=$2
shift 2

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
local_channel=${LOCAL_CHANNEL:-$root/local-channel}
output_dir=${OUTPUT_DIR:-$root/output}

target_platform=$(sed -n '/^target_platform:/{n;s/^- *//p;}' "$config")
if [[ -z "$target_platform" ]]; then
  echo "No target_platform in $config" >&2
  exit 1
fi

# Index the local channel; make sure the subdirs we need exist, even if empty.
# --force: rebuild from scratch, so a rebuilt package that replaced a file of
# the same name is not listed with the old file's checksum.
mkdir -p "$local_channel/noarch" "$local_channel/$target_platform"
rattler-index fs --force "$local_channel"

env | grep '^DEV_' | sort || true

# The .ci_support files set `channel_sources: conda-forge`, and rattler-build
# rejects -c together with channel_sources, so override it with a variant
# file that puts the local channel first.
channels_config=$(mktemp "${TMPDIR:-/tmp}/channels.XXXXXX.yaml")
trap 'rm -f "$channels_config"' EXIT
printf 'channel_sources:\n  - %s,conda-forge\n' "$local_channel" > "$channels_config"

rattler-build build \
  --recipe "$recipe" \
  -m "$config" \
  --target-platform "$target_platform" \
  --output-dir "$output_dir" \
  "$@" \
  -m "$channels_config"
