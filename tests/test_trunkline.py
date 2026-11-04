# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

from predictygraph import render


def test_draw_ring_grid():
    svg = render("graph theme=trunkline grid=40\na -> b flow=draw\nb -> c flow=forward\n")
    assert "pdg-grid" in svg and "pdg-draw" in svg and "pdg-flow-ring" in svg


def test_static_draw_is_complete():
    svg = render("graph\na -> b flow=draw\n", t=0)
    assert 'stroke-dashoffset="0"' in svg
