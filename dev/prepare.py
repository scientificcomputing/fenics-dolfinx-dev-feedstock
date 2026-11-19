"""Prepare a development build of the FEniCSx stack.

For each FEniCS component (ufl, basix, ffcx, dolfinx) this script

1. resolves the requested git ref (default: ``main``) to a commit,
2. reads the upcoming release from ``pyproject.toml`` at that commit
   (e.g. ``0.12.0.dev0`` -> ``0.12.0``),
3. picks the next free ``<release>.devN`` version for the package in the
   target anaconda.org channel.

It also builds the CI matrices from the conda-smithy generated
``.ci_support/*.yaml`` variant files, skipping Windows and complex builds.

Results are written as ``key=value`` lines to ``$GITHUB_OUTPUT`` (or stdout),
and a summary table to ``$GITHUB_STEP_SUMMARY`` if set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Order matters: this is the build order.
COMPONENTS = {
    # name: (conda package, pyproject.toml path in the repository)
    "ufl": ("fenics-ufl", "pyproject.toml"),
    "basix": ("fenics-basix", "pyproject.toml"),
    "ffcx": ("fenics-ffcx", "pyproject.toml"),
    "dolfinx": ("fenics-dolfinx", "python/pyproject.toml"),
}

# .ci_support variants that are not built.
SKIP_PATTERNS = [r"^win_", r"scalarcomplex", r"python3\.11\."]

RUNNERS = {
    "linux_64": "ubuntu-latest",
    "linux_aarch64": "ubuntu-24.04-arm",
    "osx_64": "macos-15-intel",
    "osx_arm64": "macos-15",
}

USER_AGENT = "fenics-dev-build"


def http_get(url: str) -> bytes | None:
    """GET a URL, returning None on 404."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def resolve_rev(repo: str, ref: str) -> str:
    """Resolve a branch/tag/commit of github.com/FEniCS/<repo> to a commit sha."""
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    url = f"https://github.com/FEniCS/{repo}.git"
    out = subprocess.run(
        ["git", "ls-remote", url, ref, f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    lines = [line.split() for line in out.splitlines() if line.strip()]
    if not lines:
        raise SystemExit(f"Could not resolve ref {ref!r} in {url}")
    # prefer peeled tags (^{}), then branches, then whatever matched
    for suffix in ("^{}", f"refs/heads/{ref}"):
        for sha, name in lines:
            if name.endswith(suffix):
                return sha
    return lines[0][0]


def upstream_release(repo: str, rev: str, pyproject: str) -> str:
    """Return the release a commit is working towards, e.g. '0.12.0'."""
    url = f"https://raw.githubusercontent.com/FEniCS/{repo}/{rev}/{pyproject}"
    data = http_get(url)
    if data is None:
        raise SystemExit(f"{url} not found")
    version = tomllib.loads(data.decode())["project"]["version"]
    return release_of(version)


def release_of(version: str) -> str:
    """Strip pre/dev/post suffixes: '0.12.0.dev0' -> '0.12.0'."""
    m = re.match(r"\d+(\.\d+)*", version)
    if not m:
        raise ValueError(f"Cannot parse version {version!r}")
    return m.group(0)


def channel_versions(channel: str, package: str) -> list[str]:
    """All versions of a package in an anaconda.org channel."""
    data = http_get(f"https://api.anaconda.org/package/{channel}/{package}")
    if data is None:
        return []
    return list(json.loads(data).get("versions", []))


def next_dev_version(release: str, existing: list[str]) -> str:
    """Next '<release>.devN' that is not in ``existing`` (N starts at 1)."""
    pattern = re.compile(rf"^{re.escape(release)}\.dev(\d+)$")
    numbers = [int(m.group(1)) for v in existing if (m := pattern.match(v))]
    return f"{release}.dev{max(numbers, default=0) + 1}"


def build_matrices(ci_support: Path) -> tuple[list[dict], list[dict]]:
    """(basix matrix, dolfinx matrix) from .ci_support variant files.

    dolfinx is built for every non-skipped variant. basix does not depend on
    mpi/scalar, so it is built once per (platform, python) using the mpich
    variant files.
    """
    dolfinx, basix = [], []
    for path in sorted(ci_support.glob("*.yaml")):
        config = path.stem
        if any(re.search(p, config) for p in SKIP_PATTERNS):
            continue
        platform = next((p for p in RUNNERS if config.startswith(p + "_")), None)
        if platform is None:
            print(f"Skipping {config}: no runner for platform", file=sys.stderr)
            continue
        entry = {"config": config, "runner": RUNNERS[platform]}
        dolfinx.append(entry)
        if "mpimpich" in config:
            basix.append(entry)
    return basix, dolfinx


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channel", required=True, help="anaconda.org channel")
    for name in COMPONENTS:
        parser.add_argument(
            f"--{name}-ref", default="main", help=f"git ref of FEniCS/{name}"
        )
    parser.add_argument("--ci-support", type=Path, default=ROOT / ".ci_support")
    args = parser.parse_args(argv)

    outputs: dict[str, str] = {}
    rows = []
    for name, (package, pyproject) in COMPONENTS.items():
        ref = getattr(args, f"{name}_ref") or "main"
        rev = resolve_rev(name, ref)
        release = upstream_release(name, rev, pyproject)
        version = next_dev_version(release, channel_versions(args.channel, package))
        outputs[f"{name}_rev"] = rev
        outputs[f"{name}_version"] = version
        rows.append(f"| {package} | `{version}` | {ref} | FEniCS/{name}@{rev[:10]} |")

    basix, dolfinx = build_matrices(args.ci_support)
    outputs["basix_matrix"] = json.dumps({"include": basix})
    outputs["dolfinx_matrix"] = json.dumps({"include": dolfinx})

    lines = [f"{k}={v}" for k, v in outputs.items()]
    if gh_output := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_output, "a") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))

    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(
                f"## FEniCSx dev build for channel `{args.channel}`\n\n"
                "| package | version | ref | commit |\n|---|---|---|---|\n"
                + "\n".join(rows)
                + f"\n\n{len(basix)} basix builds, {len(dolfinx)} dolfinx builds\n"
            )


if __name__ == "__main__":
    main()
