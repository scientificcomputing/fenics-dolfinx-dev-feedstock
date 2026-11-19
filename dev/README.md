# Development builds of FEniCSx

This directory builds conda packages of the FEniCSx stack from the git `main`
branches of [ufl](https://github.com/FEniCS/ufl),
[basix](https://github.com/FEniCS/basix),
[ffcx](https://github.com/FEniCS/ffcx) and
[dolfinx](https://github.com/FEniCS/dolfinx) and uploads them to an
anaconda.org channel. It sits next to the regular conda-forge feedstock
files (`recipe/`, `.ci_support/`, ...), which are left untouched so upstream
feedstock changes can still be merged.

## Installing

```bash
conda create -n fenicsx-dev \
  -c <channel> -c conda-forge --strict-channel-priority \
  fenics-dolfinx mpich        # or openmpi
```

`--strict-channel-priority` makes sure all FEniCS packages come from the dev
channel and everything else from conda-forge.

## Versions

Each run builds a snapshot `<next release>.devN` of every component, e.g.
dolfinx `0.12.0.dev1`, `0.12.0.dev2`, ... and ufl `2026.3.0.dev1`, ...

* `<next release>` is read from `pyproject.toml` on the built commit
  (`0.12.0.dev0` -> `0.12.0`). When upstream releases 0.12.0 and `main` moves
  to `0.13.0.dev0`, the snapshots become `0.13.0.devN` automatically.
* `N` is one more than the highest `.devN` for that release already in the
  channel (starting at 1). Failed runs upload nothing, so they do not use up a
  number.
* `0.12.0.devN` sorts above `0.11.x` and below the final `0.12.0`, so dev
  builds never clash with conda-forge releases.
* The FEniCS packages from one snapshot pin each other exactly
  (`fenics-dolfinx 0.12.0.dev3` requires `fenics-basix ==0.12.0.dev3`, ...),
  because dev snapshots are not ABI compatible with each other.

## Build matrix

The variant files are the conda-smithy generated `.ci_support/*.yaml` files,
so pinnings follow conda-forge (rerender to update them). `dev/prepare.py`
skips Windows and complex builds (`SKIP_PATTERNS`), which leaves
linux-64, linux-aarch64, osx-64 and osx-arm64 x mpich/openmpi x
Python 3.12 in real mode. The 3.12 builds use the stable ABI (abi3), so they
also work on newer Pythons. basix is built once per platform; ufl and ffcx are
noarch and require Python >=3.12.

## The workflow

`.github/workflows/build-dev.yml` only runs when triggered manually
(Actions -> "Build dev packages" -> "Run workflow", or
`gh workflow run build-dev.yml`). Optional inputs choose other branches,
tags or commits of each repository, and can turn off the upload.

1. **prepare**: resolve the commits, compute versions, build the matrices.
2. **ufl** and **basix** (8 jobs) in parallel, then **ffcx**, then
   **dolfinx** (16 jobs). Each stage gets the earlier stages' packages
   through a local channel that takes priority over conda-forge.
3. **upload**: only after every build has succeeded.

### One-time setup

* Create an API token on anaconda.org with upload rights to the channel and
  store it as the repository secret `ANACONDA_API_TOKEN`.
* Optionally set the repository variable `ANACONDA_CHANNEL`. It defaults to
  the GitHub organisation or user that owns the repository.

## Building locally

Requires `rattler-build` and `rattler-index`. Without the `DEV_*` variables
the recipes build `main` as version `0.0.0.dev0`; to get real versions:

```bash
eval "$(python3 dev/prepare.py --channel <channel> | grep -v matrix \
  | sed -E 's/^([a-z]+)_(version|rev)=/export DEV_\U\1_\2=/')"
C=.ci_support/linux_64_mpimpichpython3.12.____cpythonscalarreal.yaml
dev/build.sh dev/recipes/fenics-ufl $C
```

For later stages, copy the `.conda` files from `output/<subdir>/` into
`local-channel/<subdir>/` first, as the workflow does.

## Updating the recipes

* `dev/recipes/fenics-dolfinx` is a copy of `recipe/` with git sources,
  env-based versions and exact pins. Port changes from `recipe/` by hand.
* `dev/recipes/fenics-{ufl,basix,ffcx}` are adapted from the conda-forge
  `fenics-*-feedstock` repositories in the same way.
