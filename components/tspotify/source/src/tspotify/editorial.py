"""Small, deterministic primitives for the editorial terminal renderer."""

from dataclasses import dataclass
import unicodedata


BAYER_8 = (
    (0, 48, 12, 60, 3, 51, 15, 63),
    (32, 16, 44, 28, 35, 19, 47, 31),
    (8, 56, 4, 52, 11, 59, 7, 55),
    (40, 24, 36, 20, 43, 27, 39, 23),
    (2, 50, 14, 62, 1, 49, 13, 61),
    (34, 18, 46, 30, 33, 17, 45, 29),
    (10, 58, 6, 54, 9, 57, 5, 53),
    (42, 26, 38, 22, 41, 25, 37, 21),
)


def char_width(char):
    if not char or unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def text_width(value):
    return sum(char_width(char) for char in str(value))


def fit_text(value, width, marker="…"):
    """Fit a label to terminal cells while keeping combining characters intact."""
    value = " ".join(str(value).replace("\t", " ").splitlines())
    if width <= 0:
        return ""
    if text_width(value) <= width:
        return value
    marker_width = min(width, text_width(marker))
    target = width - marker_width
    output = []
    used = 0
    for char in value:
        cells = char_width(char)
        if used + cells > target:
            break
        output.append(char)
        used += cells
    return "".join(output).rstrip() + marker


def wrap_text(value, width, lines=2):
    """Wrap on word boundaries and cap the final line with an ellipsis."""
    value = " ".join(str(value).split())
    if width <= 0 or lines <= 0:
        return []
    output = []
    current = ""
    for word in value.split(" "):
        candidate = word if not current else current + " " + word
        if text_width(candidate) <= width:
            current = candidate
            continue
        if current:
            output.append(current)
            current = ""
        if text_width(word) > width:
            output.append(fit_text(word, width))
        else:
            current = word
        if len(output) == lines:
            break
    if current and len(output) < lines:
        output.append(current)
    if len(output) > lines:
        output = output[:lines]
    if output and (" ".join(output) != value):
        output[-1] = fit_text(output[-1] + "…", width)
    return output


@dataclass(frozen=True)
class Cell:
    glyph: str = " "
    color: int = 1
    bold: bool = False


class CellGrid:
    """A terminal-sized, styled frame used for short grid transitions."""

    def __init__(self, height, width, fill=None):
        self.height = max(0, height)
        self.width = max(0, width)
        fill = fill or Cell()
        self.cells = [[fill for _ in range(self.width)] for _ in range(self.height)]

    def clone(self):
        other = CellGrid(self.height, self.width)
        other.cells = [row.copy() for row in self.cells]
        return other

    def _clear(self, y, x):
        cell = self.cells[y][x]
        if cell.glyph == "" and x > 0:
            self.cells[y][x - 1] = Cell()
        elif char_width(cell.glyph) == 2 and x + 1 < self.width:
            self.cells[y][x + 1] = Cell()
        self.cells[y][x] = Cell()

    def write(self, y, x, value, color=1, bold=False):
        if not 0 <= y < self.height:
            return
        column = max(0, x)
        for char in str(value):
            cells = char_width(char)
            if cells == 0:
                if 0 < column <= self.width:
                    previous = min(column - 1, self.width - 1)
                    cell = self.cells[y][previous]
                    self.cells[y][previous] = Cell(cell.glyph + char, cell.color, cell.bold)
                continue
            if column + cells > self.width:
                break
            self._clear(y, column)
            self.cells[y][column] = Cell(char, color, bold)
            if cells == 2:
                self._clear(y, column + 1)
                self.cells[y][column + 1] = Cell("", color, bold)
            column += cells

    def compose(self, target, progress):
        if (self.height, self.width) != (target.height, target.width):
            return target.clone()
        progress = max(0.0, min(1.0, progress))
        output = CellGrid(self.height, self.width)
        previous_new = False
        for y in range(self.height):
            previous_new = False
            for x in range(self.width):
                old_cell = self.cells[y][x]
                new_cell = target.cells[y][x]
                threshold = BAYER_8[y % 8][x % 8] / 64
                use_new = threshold < progress
                if x and (old_cell.glyph == "" or new_cell.glyph == ""):
                    use_new = previous_new
                output.cells[y][x] = new_cell if use_new else old_cell
                previous_new = use_new
        return output


def dissolve_image(old, new, progress):
    """Reveal a cached cover through a stable 8×8 Bayer dither mask."""
    if not old or not new or (len(old), len(old[0])) != (len(new), len(new[0])):
        return new
    progress = max(0.0, min(1.0, progress))
    height, width = len(new), len(new[0])
    return [
        [
            new[y][x] if BAYER_8[y % 8][x % 8] / 64 < progress else old[y][x]
            for x in range(width)
        ]
        for y in range(height)
    ]


def ease_out(progress):
    progress = max(0.0, min(1.0, progress))
    return 1 - (1 - progress) ** 2
