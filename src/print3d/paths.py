"""Where the pinned profiles, the skill and the jobs live."""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
JOBS_ENV = "PRINT3D_JOBS"
SLICER_ENV = "PRINT3D_SLICER"
SLICERS = ("bambu", "prusa")
NAME_RE = re.compile(r"[a-z0-9_-]{1,64}")


def repo_root() -> Path:
    return PACKAGE.parents[1]


def slicer() -> str:
    """`$PRINT3D_SLICER`: bambu (default) or prusa."""
    name = os.environ.get(SLICER_ENV, "").strip().lower() or "bambu"
    if name not in SLICERS:
        raise ValueError(f"{SLICER_ENV}={name!r}: use one of {', '.join(SLICERS)}")
    return name


def default_profiles_dir() -> Path:
    return PACKAGE / "profiles" / "x2d-0.4"


def prusa_profiles_dir() -> Path:
    return PACKAGE / "profiles" / "coreone-hf0.4"


def coupon_script() -> Path:
    return PACKAGE / "coupons" / "fit_coupon.py"


def skill_dir() -> Path:
    return PACKAGE / "skill"


def default_jobs_dir() -> Path:
    """`$PRINT3D_JOBS`, else `jobs/` in a source checkout, else `~/print3d/jobs`."""
    if env := os.environ.get(JOBS_ENV, "").strip():
        return Path(env).expanduser()
    if (repo_root() / "pyproject.toml").is_file():
        return repo_root() / "jobs"
    return Path.home() / "print3d" / "jobs"


def safe_name(name: str, what: str = "name") -> str:
    """A job slug or view name, kept to the alphabet slugify writes so it can't leave the jobs folder."""
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"{what} {name!r}: use 1 to 64 of a-z, 0-9, _ and -")
    return name


def job_path(slug: str) -> Path:
    """jobs/<slug>, refused if it would land outside the jobs folder."""
    root = default_jobs_dir().resolve()
    path = (root / safe_name(slug, "slug")).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"slug {slug!r} leaves the jobs folder")
    return path
