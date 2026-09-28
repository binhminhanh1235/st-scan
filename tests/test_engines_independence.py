"""
Test Architecture Contract Rule #1:
Ba engine độc lập tuyệt đối: Flow Engine, Structure Engine, Volume Engine
không import lẫn nhau, không chia sẻ trạng thái, có params_hash và test riêng.
"""

import ast
import os
import inspect
import pytest
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine
from wfe.data.pit_feed import MarketBar


def get_imported_modules(file_path: str):
    """Parses AST of a python file and returns set of imported module names."""
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_engines_do_not_import_each_other():
    """Verify strictly by AST that no engine imports any other engine."""
    engines_dir = "/Volumes/Data/invest/wfe/engines"
    flow_file = os.path.join(engines_dir, "flow_engine.py")
    struct_file = os.path.join(engines_dir, "structure_engine.py")
    vol_file = os.path.join(engines_dir, "volume_engine.py")

    flow_imports = get_imported_modules(flow_file)
    struct_imports = get_imported_modules(struct_file)
    vol_imports = get_imported_modules(vol_file)

    # Flow cannot import structure or volume
    for imp in flow_imports:
        assert "structure_engine" not in imp, f"FlowEngine illegally imports {imp}"
        assert "volume_engine" not in imp, f"FlowEngine illegally imports {imp}"

    # Structure cannot import flow or volume
    for imp in struct_imports:
        assert "flow_engine" not in imp, f"StructureEngine illegally imports {imp}"
        assert "volume_engine" not in imp, f"StructureEngine illegally imports {imp}"

    # Volume cannot import flow or structure
    for imp in vol_imports:
        assert "flow_engine" not in imp, f"VolumeEngine illegally imports {imp}"
        assert "structure_engine" not in imp, f"VolumeEngine illegally imports {imp}"


def test_engines_have_distinct_params_hash():
    """Verify that each engine has its own unique parameter hash."""
    flow = FlowEngine()
    struct = StructureEngine()
    vol = VolumeEngine()

    assert flow.params_hash
    assert struct.params_hash
    assert vol.params_hash
    assert flow.params_hash != struct.params_hash
    assert struct.params_hash != vol.params_hash
    assert flow.params_hash != vol.params_hash


def test_engines_standalone_execution():
    """Verify each engine can execute in isolation without other engines."""
    # Synthetic bars
    bars = [
        MarketBar(date=f"2026-01-{i+1:02d}", open=50.0 + i*0.1, high=51.0 + i*0.1,
                  low=49.5 + i*0.1, close=50.5 + i*0.1, volume=100000.0)
        for i in range(80)
    ]

    # Flow standalone
    flow_out = FlowEngine().calculate(bars)
    assert flow_out.data_ok is True
    assert flow_out.trend.value is not None

    # Structure standalone
    struct_out = StructureEngine().calculate(bars)
    assert struct_out.data_ok is True
    assert struct_out.box_id.startswith("BOX_")

    # Volume standalone
    vol_out = VolumeEngine().calculate(bars)
    assert vol_out.data_ok is True
    assert vol_out.rvol > 0
