from tspotify.editorial import Cell, CellGrid, char_width, dissolve_image, fit_text, text_width, wrap_text
from tspotify.cli import parser


def test_text_fitting_uses_terminal_cells_and_keeps_combining_marks():
    assert char_width("界") == 2
    assert text_width("e\u0301界") == 3
    assert fit_text("e\u0301cho long", 6) == "e\u0301cho…"
    assert text_width(fit_text("長いタイトル", 5)) <= 5


def test_wrapping_caps_long_labels_without_exceeding_requested_width():
    lines = wrap_text("A very long title from an album", 12, 2)
    assert lines == ["A very long", "title from…"]
    assert all(text_width(line) <= 12 for line in lines)
    assert wrap_text("too-long-word", 4, 1) == ["too…"]


def test_cell_grid_wide_glyphs_clear_both_terminal_cells():
    grid = CellGrid(1, 5)
    grid.write(0, 1, "界", color=2, bold=True)
    assert grid.cells[0][1] == Cell("界", 2, True)
    assert grid.cells[0][2] == Cell("", 2, True)

    grid.write(0, 2, "x", color=3)
    assert grid.cells[0][1] == Cell()
    assert grid.cells[0][2] == Cell("x", 3, False)


def test_cell_grid_dither_has_exact_source_and_target_endpoints():
    old = CellGrid(8, 8)
    new = CellGrid(8, 8)
    old.write(0, 0, "OLD", 2)
    new.write(0, 0, "NEW", 3)
    assert old.compose(new, 0).cells == old.cells
    assert old.compose(new, 1).cells == new.cells
    assert old.compose(new, 0.5).cells != old.cells
    assert old.compose(new, 0.5).cells != new.cells


def test_cover_dither_is_deterministic_and_reaches_both_images():
    old = [["o"] * 8 for _ in range(8)]
    new = [["n"] * 8 for _ in range(8)]
    assert dissolve_image(old, new, 0) == old
    assert dissolve_image(old, new, 1) == new
    assert dissolve_image(old, new, 0.5) == dissolve_image(old, new, 0.5)
    assert set(sum(dissolve_image(old, new, 0.5), [])) == {"o", "n"}


def test_demo_reduced_motion_and_low_power_options_are_combined():
    args = parser().parse_args(["--demo", "--no-motion", "--low-power"])
    assert args.demo and args.no_motion and args.low_power
