# Night Tasks Queue — TTools Autonomous Development

## Task Format
| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |

---

## Active Tasks

| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |
|----|----------|-----------|----------|-----------------|--------|---------------------|-------------|-------------|
| T001 | P0 | TVPN | oc-local | integration/windows-preview (C:\Users\user\source\repos\ttools-integration) | IN_PROGRESS | Globe zoom/rotate/focus/spin works; reduced_motion restored; region selection works; Riseup gateways load; no white rectangles; version sync | Globe fixes in progress; region selection refactored; update.json version synced to 1.4.1; tests updated | Complete globe.py and riseup-panel.py fixes; run offline tests |
| T002 | P0 | Common VT Rendering | cloud-1 | New worktree | TODO | All components inherit terminal background/transparency/acrylic; no opaque gray; no forced backgrounds | Not started | Create worktree; investigate curses/Windows VT transparency root cause |
| T003 | P0 | TTelegram Windows | cloud-2 | New worktree | TODO | Exit code 0 on launch; tdjson works; manifests verified; auth preserved | Not started | Create worktree; reproduce exit code 1; get traceback |
| T004 | P1 | TSpotify | cloud-1 (after T002) | fix/tspotify-windows-runtime | TODO | Native background; audio spectrum where possible; adaptive layout; F7-F12 work; mouse stable | 397 passed, 2 skipped; Windows runtime fixed | Fix background transparency; implement real audio spectrum; fix adaptive layout; restore F7-F12 |
| T005 | P1 | tthings | oc-local (after T001) | fix/tthings-windows-runtime | TODO | Gallery windows transparent; no spontaneous exits; 67 tests pass | 67 tests pass; GalleryPreview works | Fix Gallery window transparency; debug spontaneous exit |
| T006 | P1 | TSoundCloud | cloud-2 (after T003) | New worktree | TODO | Windows runtime works or documented limitations | Not started | Audit Linux-specific deps; implement Windows compat |
| T007 | P0 | TTools Launcher | lead | Main ttools branch | TODO | Apps list populated; native background; no Python conflicts; diagnostic logging | Not started | Fix empty app list; fix background; improve diagnostics |
| T008 | P0 | One-Command Install | lead | Main ttools branch | TODO | Single PS command installs; SHA-256 verified; PATH updated; `ttools` works | Not started | Prepare Install-ttools.ps1; test in clean prefix |
| T009 | P0 | Auto Updates | lead | Main ttools branch | TODO | Stable/preview channels; atomic install; rollback; data preserved | Not started | Verify suite-update.json; test update flow in isolation |

---

## Completed Tasks

| ID | Priority | Component | Assignee | Result |
|----|----------|-----------|----------|--------|
| C001 | P0 | TVPN Windows Runtime | oc-local (previous) | Real VPN connection verified; OpenVPN Interactive Service + DCO working; offline tests pass |
| C002 | P1 | tthings Windows Runtime | Nemotron Ultra | 67 tests pass; VT input; GalleryPreview; UTF-8 subprocess; Windows-safe Python |
| C003 | P1 | TSpotify Windows Runtime | Previous agent | 397 tests pass; Windows runtime lock fixed; intro animation works |

---

## Blockers

| ID | Task | Blocker | Resolution Plan |
|----|------|---------|-----------------|
| B001 | T002 | Need to determine exact cause of opaque background in curses on Windows | Create minimal reproduction; compare VT vs curses; check windows-curses/PDCurses behavior |
| B002 | T003 | TTelegram Windows exit code 1 with no diagnostics | Run with embedded Python; capture stderr; check tdjson DLL loading |
| B003 | T008 | Need GitHub Release artifacts for one-command install | Build release packages via CI after integration verified |

---

## Coordination Notes

- **oc-local** (Strata swift-1.5-iq2_xs): Currently active in `ttools-integration` worktree on TVPN. Do not interrupt. After T001, assign T005 (tthings).
- **cloud-1** (DeepSeek V4.1 Flash Free): Available for T002 (VT rendering) then T004 (TSpotify).
- **cloud-2** (MiMo V2.6 Flash Free / Nemotron 3 Ultra): Available for T003 (TTelegram) then T006 (TSoundCloud).
- **Lead** (this session): Architecture, review, integration, launcher, install, updates.

## Next Steps

1. Create worktrees for cloud agents (T002, T003)
2. Delegate T002 and T003 with specific technical requirements
3. Monitor oc-local progress on TVPN via Git
4. Prepare installer and update validation after component fixes