"""Test helpers for loading the extensionless runtime module."""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys


def load_odindeps():
    script = Path(__file__).resolve().parents[2] / "odindeps"
    loader = SourceFileLoader("odindeps_test_module", str(script))
    specification = spec_from_loader(loader.name, loader)
    assert specification is not None
    module = module_from_spec(specification)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module
