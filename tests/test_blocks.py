# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""`let` variables and `def`/`use` reusable blocks (SPEC 2.1)."""
import pytest

from predictygraph.parser import PdgSyntaxError, parse

SERVER = """
let accent = "#3939D8"
def server gpus=2 {
  cpu "CPU"
  gpu "GPU x${gpus}" fill=$accent
  cpu -> gpu
}
"""


def test_use_makes_prefixed_copies():
    d = parse(SERVER + 'use server node1 "Node 1"\nuse server node2 gpus=8\nlb -> node1-cpu, node2-cpu\n')
    assert d.items["node1"].label == "Node 1"
    assert d.items["node1-gpu"].label == "GPU x2"
    assert d.items["node2-gpu"].label == "GPU x8"
    assert d.items["node2-gpu"].attrs["fill"] == "#3939D8"
    assert d.items["node1-cpu"].parent is d.items["node1"]
    assert {(e.src, e.dst) for e in d.edges} >= {("node1-cpu", "node1-gpu"), ("lb", "node2-cpu")}


def test_def_alone_draws_nothing():
    assert parse(SERVER).root.children == []


def test_variable_scope_and_quoting():
    d = parse('let t = "Two words"\ngroup g {\n  let t = inner\n  a $t\n}\nb $t\n')
    assert d.items["a"].label == "inner"
    assert d.items["b"].label == "Two words"


def test_id_and_label_inside_block():
    d = parse('def box {\n  x "${LABEL} (${ID})"\n}\nuse box b1 "First"\n')
    assert d.items["b1-x"].label == "First (b1)"


def test_nested_blocks():
    d = parse(SERVER + 'def rack {\n  use server s1\n}\nuse rack r1\n')
    assert "r1-s1-gpu" in d.items


@pytest.mark.parametrize("src, msg", [
    ("a $nope\n", "unknown variable"),
    ("use missing x\n", "unknown block"),
    ("def b need {\n  a\n}\nuse b x\n", "missing need"),
    ("def b {\n  use b y\n}\nuse b x\n", "uses itself"),
    ("def b {\n  a\n", "unclosed def"),
])
def test_errors(src, msg):
    with pytest.raises(PdgSyntaxError, match=msg):
        parse(src)
