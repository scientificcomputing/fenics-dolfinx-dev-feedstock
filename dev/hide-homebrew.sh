#!/usr/bin/env bash
# Move /usr/local out of the way on GitHub macOS runners, so CMake and the
# compiler cannot pick up Homebrew headers/libraries (e.g. boost, hdf5)
# instead of the conda-forge ones. Same idea as conda-forge-ci-setup's
# mangle_homebrew. Only meant for throwaway CI machines.
set -euo pipefail

if [[ "$(uname)" != "Darwin" || -z "${CI:-}" ]]; then
  echo "Not on a macOS CI runner, doing nothing"
  exit 0
fi

mangled=/usr/local/conda_mangled
sudo mkdir -p "$mangled"
for path in /usr/local/*; do
  [[ "$path" == "$mangled" ]] && continue
  sudo mv "$path" "$mangled/"
  echo "moved $path -> $mangled/"
done
