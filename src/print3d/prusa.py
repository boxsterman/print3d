"""PrusaSlicer CLI wrapper. System presets by name, isolated --datadir."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PRUSA_ENV = "PRUSA_SLICER_BIN"
PRESET_KEYS = ("printer", "print", "filament")


class PrusaError(RuntimeError):
    """Raised for PrusaSlicer discovery or slice failures."""


@dataclass(frozen=True)
class PrusaRequest:
    input_mesh: Path
    output_gcode: Path
    output_project_3mf: Path
    presets: dict[str, str]
    datadir: Path


def find_prusa(search_path: str | None = None) -> Path:
    candidates: list[str] = []
    if env := os.environ.get(PRUSA_ENV, "").strip():
        candidates.append(env)
    if which := shutil.which("prusa-slicer", path=search_path):
        candidates.append(which)
    candidates.append("/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer")
    # Versioned app bundles, e.g. PrusaSlicer-3.0.0-alpha12.app; newest name last.
    candidates.extend(sorted(glob.glob("/Applications/PrusaSlicer*.app/Contents/MacOS/PrusaSlicer"), reverse=True))
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    raise PrusaError(f"PrusaSlicer not found. Install PrusaSlicer or set {PRUSA_ENV}.")


def load_presets(path: Path) -> dict[str, str]:
    presets = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in PRESET_KEYS if not presets.get(key)]
    if missing:
        raise PrusaError(f"{path} names no {', '.join(missing)} preset.")
    return {key: presets[key] for key in PRESET_KEYS}


def _common_prefix(binary: Path, request: PrusaRequest) -> list[str]:
    return [
        str(binary),
        "--datadir",
        str(request.datadir.resolve()),
        "--printer-profile",
        request.presets["printer"],
        "--print-profile",
        request.presets["print"],
        "--material-profile",
        request.presets["filament"],
    ]


def build_project_command(binary: Path, request: PrusaRequest) -> list[str]:
    """Export an unsliced PrusaSlicer project to open and print from."""
    return [
        *_common_prefix(binary, request),
        "--export-3mf",
        "--output",
        str(request.output_project_3mf.resolve()),
        str(request.input_mesh.resolve()),
    ]


def build_slice_command(binary: Path, request: PrusaRequest) -> list[str]:
    # Plain text gcode: the slice checks read its moves and footer.
    return [
        *_common_prefix(binary, request),
        "--export-gcode",
        "--no-binary-gcode",
        "--output",
        str(request.output_gcode.resolve()),
        str(request.input_mesh.resolve()),
    ]


def slice_plan(request: PrusaRequest, *, binary: Path | None = None) -> dict[str, Any]:
    if binary is None:
        # A plan is only a preview; name the binary even when it is not installed.
        try:
            binary = find_prusa()
        except PrusaError:
            binary = Path("prusa-slicer")
    return {
        "dry_run": True,
        "slicer": "prusa",
        "prusa_slicer": str(binary),
        "project_command": build_project_command(binary, request),
        "command": build_slice_command(binary, request),
        "presets": request.presets,
        "open_in_studio": str(request.output_project_3mf),
        "note": "Open the .3mf in PrusaSlicer File > Open Project. The .gcode is the sliced print job.",
    }


def _run(command: list[str], timeout_s: float, path: Path, label: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        raise PrusaError(
            f"PrusaSlicer {label} failed with exit {result.returncode}.\n"
            f"output tail:\n{(result.stderr + result.stdout)[-4000:]}"
        )
    if not path.is_file():
        raise PrusaError(f"PrusaSlicer {label} exited 0 but did not write {path}")
    return result


def run_slice(request: PrusaRequest, *, binary: Path | None = None, timeout_s: float = 180) -> dict[str, Any]:
    binary = binary or find_prusa()
    plan = slice_plan(request, binary=binary)
    plan["dry_run"] = False
    request.datadir.mkdir(parents=True, exist_ok=True)
    request.output_gcode.parent.mkdir(parents=True, exist_ok=True)
    request.output_project_3mf.parent.mkdir(parents=True, exist_ok=True)
    # Never report a stale output as this run's.
    request.output_gcode.unlink(missing_ok=True)
    request.output_project_3mf.unlink(missing_ok=True)

    _run(build_project_command(binary, request), timeout_s, request.output_project_3mf, "project export")
    result = _run(build_slice_command(binary, request), timeout_s, request.output_gcode, "slice")

    plan["returncode"] = result.returncode
    plan["stdout"] = result.stdout
    plan["stderr"] = result.stderr
    plan["output_3mf"] = str(request.output_gcode)
    plan["output_project_3mf"] = str(request.output_project_3mf)
    plan["output_size_bytes"] = request.output_gcode.stat().st_size
    plan["project_size_bytes"] = request.output_project_3mf.stat().st_size
    return plan
