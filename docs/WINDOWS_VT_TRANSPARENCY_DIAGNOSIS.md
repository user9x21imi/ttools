# Windows VT transparency diagnosis — PDCurses vs. vtcurses

**Branch:** started on `fix/vt-console-mode-transparency`, integrated into
`integration/windows-preview`
**Status:** root cause confirmed by source inspection + reproducible local test; visual
acceptance in Windows Terminal still requires the user
**Scope:** TTools launcher, TSpotify, TVPN (PDCurses/`windows-curses`); reference: tthings, TTelegram Windows native (VT/ANSI)

## TL;DR

Removing `bkgd()` was necessary but **not sufficient**. On Windows, `windows-curses` is
PDCurses, and PDCurses turns `-1` (default/transparent background) into a **concrete
palette index inside `init_pair()`** — before any drawing happens. Every cell it writes
then carries an explicit, opaque background:

* Windows Terminal (`WT_SESSION` set): PDCurses writes `SGR 40..47` / `48;5;n` / `48;2;...`
  for the background. It never emits `SGR 49` (default background).
* Legacy path / no `WT_SESSION`: PDCurses uses `WriteConsoleOutput` with
  `Attributes = fore | (back << 4)`, i.e. a solid background bit field.

Windows Terminal renders those cells with an opaque palette color, so acrylic / background
images / transparency are covered. Enabling VT processing before curses starts **does not
change this** — the `-1` is already gone and PDCurses resets the console mode itself.

**Recommendation:** on Windows, use the existing VT backend (`ttools/vtbackend.py`, already
landed for the launcher) in place of `curses` for TSpotify, TVPN (and tsoundcloud). Keep
standard curses on POSIX.

Diagnostic artifacts (currently gitignored scratch tools, force-add if the team wants them
in the repo): `tools/test_vt_transparency.py`, `tools/diagnose_real_console.py`,
`tools/real_console_{vt,novt}.json`.

---

## Root cause (with source evidence)

### 1. `-1` is normalized away by PDCurses

`pdcurses/color.c` (PDCurses commit `5c62af0`, the submodule used by windows-curses 2.4.2):

```c
static void _normalize(short *fg, short *bg)
{
    if (*fg == -1) *fg = SP->orig_attr ? SP->orig_fore : COLOR_WHITE;
    if (*bg == -1) *bg = SP->orig_attr ? SP->orig_back : COLOR_BLACK;
}

static void _init_pair_core(short pair, short fg, short bg)
{
    PDC_PAIR *p = SP->atrtab + pair;
    _normalize(&fg, &bg);       /* <-- -1 is replaced HERE */
    p->f = fg;
    p->b = bg;
}
```

`use_default_colors()` only sets `first_col = -1` (so `-1` passes validation) and calls
`assume_default_colors(-1, -1)`, which still goes through `_normalize`. There is no code
path in PDCurses that retains "default background" for a cell.

`SP->orig_back` comes from the console at startup (`wincon/pdcscrn.c`, `PDC_scr_open()`):

```c
GetConsoleScreenBufferInfo(pdc_con_out, &csbi);
SP->orig_fore = csbi.wAttributes & 0x0f;
SP->orig_back = (csbi.wAttributes & 0xf0) >> 4;   /* legacy palette index 0..15 */
```

So `init_pair(1, WHITE, -1)` stores `(7, orig_back)`, not `(7, default)`.

### 2. Every PDCurses cell write carries a background

`wincon/pdcdisp.c`:

```c
pair_content(PAIR_NUMBER(attr), &fore, &back);   /* back is now concrete */
...
_set_ansi_color(fore, back, attr);              /* Windows Terminal path */
...
if (b != pdc_oldb) {
        /* b < 8 -> "4%d" (b+40), b < 16 -> bright bg, else 48;5;n / 48;2;r;g;b */
        p += sprintf(p, "%d", b + 40);  /* or 48;5;... / 48;2;... */
    }
```

(The actual source emits `b + 40`, `48;5;%d` or `48;2;...`; there is no `49` branch.)

Non-ANSI path:

```c
mapped_attr = fore | (back << 4);               /* background bits always set */
buffer[j].Attributes = mapped_attr;
WriteConsoleOutput(pdc_con_out, buffer, ...);
```

`writeConsoleOutput` has no "transparent cell" concept. Also `erase()`/`clear()` fill cells
with pair 0 (`use_default_colors()` normalizes that to `(orig_fore, orig_back)` too), so the
whole screen is painted with a solid background even if the app never calls `bkgd()`.

### 3. Pre-enabling VT processing cannot help

`wincon/pdcscrn.c` `PDC_scr_open()` overrides the output mode:

```c
SetConsoleMode(pdc_con_out, 0x0010);   /* ENABLE_LVB_GRID_WORLDWIDE only */
```

and `_set_ansi_color()` toggles `0x0015` (processed output + VT + LVB) around each ANSI
write, then restores `0x0010`. These calls act on PDCurses' own screen buffer; the app's
`SetConsoleMode()` on the std handle before `curses.wrapper()` is irrelevant to how
PDCurses renders colors. `WT_SESSION` merely selects the ANSI write path; it does not make
backgrounds transparent.

### 4. Why the gray specifically

Your Windows Terminal profile uses `background: "#F6F9FD"`, `useAcrylic: true`,
`opacity: 68`, a light "One Half Light" scheme. The startup console attributes for such a
light scheme are typically mapped to a bright/gray palette index (e.g. 7/15), so
`orig_back` is a light gray. PDCurses writes that index as an explicit background on every
cell — Windows Terminal paints it opaque, producing the gray rectangle. A dark profile
would produce a black rectangle instead; either way transparency is lost.

---

## Tests performed

### `tools/test_vt_transparency.py` (new, deterministic, no GUI needed)

```
PDCurses pair_content(WHITE, -1) = (7, 0)
  -1 preserved?  False
vtcurses SGR with default bg: '\x1b[0;38;5;7m'          # fg only, no 48;...
vtcurses SGR with black bg:   '\x1b[0;38;5;6;48;5;0m'   # explicit bg when requested
DIAGNOSIS REPRODUCED
```

### Real console check — `tools/diagnose_real_console.py` under `conhost.exe`

| Run | stdout mode before | after `--vt` | inside curses | `pair_content(WHITE,-1)` |
|-----|-------------------|--------------|---------------|--------------------------|
| no `--vt` | `0x3` | — | `0x3` | `(7, 0)` |
| `--vt` | `0x3` | `0x7` | `0x7` | `(7, 0)` |

VT enablement worked (`0x3 -> 0x7`, i.e. `ENABLE_VIRTUAL_TERMINAL_PROCESSING` set), but the
normalized color pair was identical. This directly disproves the hypothesis that enabling
VT before curses fixes transparency.

Reference implementations:
* `components/ttelegram/windows-native/source/vtcurses.py:_sgr()` skips `fg/bg < 0`, so no
  background SGR is emitted for `-1`.
* `components/tthings/source/tthings/terminal.py:draw()` emits only `38;2;r;g;b` foreground
  sequences and `ESC[K` — no background writes. Both work with acrylic in Windows Terminal.

---

## Proposed fix

### Recommended: VT backend for Windows (reuse the proven vtcurses implementation)

This has **already landed for the launcher** in commit `72469c1`
(`ttools/vtbackend.py`, selected in `ttools/__main__.py` when `vtbackend.usable()`,
with PDCurses kept as a headless fallback). The same module should now be reused by
the remaining curses components.

1. `ttools/vtbackend.py` is a copy of the TTelegram Windows `vtcurses.py` plus the API
   surface the launcher/components need: `raw()`, `noraw()`, `flushinp()`,
   `def_prog_mode()`, `reset_prog_mode()`, `REPORT_MOUSE_POSITION`, `usable()` and
   `prepare_console_output()`. It preserves `-1` in `init_pair()` and `_sgr()` emits no
   background SGR for default pairs.
2. Select it before any curses import in each component entry point, mirroring
   `ttools/__main__.py` and TTelegram's `windows_bootstrap.py:8-11`:

```python
# at the top of a component entry module, before importing curses
if sys.platform == 'win32':
    from ttools import vtbackend
    curses = vtbackend if vtbackend.usable() else __import__('curses')
else:
    import curses
```

   Targets: `components/tspotify/source/src/tspotify/cli.py`,
   `components/tvpn/source/riseup-panel.py`,
   `components/tsoundcloud/source/tsound/__main__.py` (optional).
   Components installed standalone should vendor a copy of `vtbackend.py` (or add a
   small adapter with `sys.modules['curses'] = vtbackend`) because they may not have
   `ttools` on `sys.path`.
3. Keep `curses.use_default_colors()` + `init_pair(fg, -1)` in the apps: the VT backend
   preserves `-1` and emits no background SGR. Keep the existing "no `bkgd()`" rule —
   it is still correct on POSIX and harmless on Windows.
4. Note the launcher's fallback: when stdout is redirected/headless (`usable()` is
   false) PDCurses remains in use, which is fine for tests and `--list`; the
   transparency contract only matters in an interactive Windows Terminal.

### Not viable

* `SetConsoleMode` / `WT_SESSION` / `PDC_ORIGINAL_COLORS` / `PDC_PRESERVE_SCREEN`: none of
  these change `_normalize()` or the explicit background SGR/attribute.
* Making the palette entry transparent: Windows Terminal color-table entries are RGB
  (`COLORREF`), no alpha; acrylic applies to the terminal background layer, not to cells
  with explicit background colors.
* Patching/rebuilding windows-curses to emit `SGR 49`: possible in principle, but requires
  maintaining a custom PDCurses wheel for every Python version — much higher maintenance
  than reusing the VT backend already shipped and tested in this suite.

### Rollout / verification

1. Apply the shim, then run the existing test suites
   (`tests`, `components/tspotify/source/tests`, `components/tvpn/source/tests`,
   `components/ttelegram/windows-native/tests`).
2. Visual acceptance in Windows Terminal: enable acrylic and a background image, launch
   launcher → TSpotify → TVPN, confirm no gray/black rectangle and that colors/keys/mouse
   still work; confirm returning to the launcher after `def_prog_mode`-style launches works.
3. Keep `tools/test_vt_transparency.py` as a regression guard: it fails if a future backend
   reintroduces `-1` normalization or emits a background SGR for default backgrounds.

### Recommendation

**Convert the remaining PDCurses apps to the VT backend on Windows** rather than trying to
repair PDCurses. The shared module and launcher migration already exist (`72469c1`); what
remains is one selection hook per component entry point and visual acceptance. This is
the only approach in this codebase proven (tthings, TTelegram) to leave the cell
background unspecified, which is what Windows Terminal needs to composite acrylic /
background images. No UI rewrite is required.
