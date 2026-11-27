# Night Tasks Queue — TTools Autonomous Development

## Task Format
| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |

---

## Active Tasks

| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |
|----|----------|-----------|----------|-----------------|--------|---------------------|-------------|-------------|
| T001 | P0 | TVPN | oc-local | integration/windows-preview (C:\Users\user\source\repos\ttools-integration) | DONE | Globe zoom/rotate/focus/spin works; reduced_motion restored; region selection works; Riseup gateways load; no white rectangles; version sync | 13 passed, 5 skipped (POSIX PTY); splash/demo/offline doctor OK; version 1.4.1 synced; Windows installer hardened; no bkgd | None; real VPN connect requires user |
| T002 | P0 | Common VT Rendering | lead + cloud-1 | integration/windows-preview | DONE (offline) | All components inherit terminal background/transparency/acrylic; no opaque gray; no forced backgrounds | PDCurses root cause documented (`docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md`); direct VT backend for launcher, TSpotify and TVPN; root suite 79 passed, 6 VT tests | Visual acceptance in Windows Terminal |
| T003 | P0 | TTelegram Windows | cloud-2 + lead | integration/windows-preview | DONE (offline) | Exit code 0 on launch; tdjson works; manifests verified; auth preserved | wt.exe app-alias discovery, actionable missing-pointer error, bundle auto-install, trampoline argv fix; 12 passed, 1 skipped; installed doctor ok | Real auth/playback requires user |
| T004 | P1 | TSpotify | lead | integration/windows-preview | DONE (offline) | Native background; audio spectrum where possible; adaptive layout; F7-F12 work; mouse stable | 397 passed, 2 skipped; `_vt` shim selects VT backend on Windows; verify-runtime OK in installed package | Real audio/login needs user; visual acceptance |
| T005 | P1 | tthings | oc-local (after T001) | fix/tthings-windows-runtime | DONE | Gallery windows transparent; no spontaneous exits; tests pass | Merged `origin/fix/tthings-windows-runtime`; 60 passed, 7 skipped, 4870 subtests | Visual transparency needs manual check |
| T006 | P1 | TSoundCloud | cloud-2 (after T003) | New worktree | DEFERRED (tests green) | Windows runtime works or documented limitations | Not in standard Windows install; 14 passed, 3 skipped after fixing cross-platform test fixture | Document limitation; do not ship in Windows installer |
| T007 | P0 | TTools Launcher | lead | integration/windows-preview | DONE | Apps list populated; native background; no Python conflicts; diagnostic logging | Dev `--list` shows 5; installed runner `--list` shows 4 supported apps; direct VT backend on interactive Windows consoles; 79 root tests passed | Visual acceptance in Windows Terminal |
| T008 | P0 | One-Command Install | lead | integration/windows-preview | DONE (isolated) | Single command installs; SHA-256 verified; PATH updated; `ttools` works | Final Windows ZIP 94,166,354 bytes; full one-command install of all 4 apps with `-DeferSystem` exit 0; runner/TVPN/TTelegram/TSpotify smoke checks pass; no user install/PATH change | Manual one-command install by user not performed; winget needed for full system setup |
| T009 | P0 | Auto Updates | lead | integration/windows-preview | DONE (offline E2E) | Stable/preview channels; atomic install; rollback; data preserved | Root suites: update E2E, complete-suite update, release gate, distribution all pass | Real GitHub release update not performed at night |

---

## Completed Tasks

| ID | Priority | Component | Assignee | Result |
|----|----------|-----------|----------|--------|
| C001 | P0 | TVPN Windows Runtime | oc-local (previous) | OpenVPN Interactive Service backend, Windows doctor, offline tests pass; real connect not attempted |
| C002 | P1 | tthings Windows Runtime | Nemotron Ultra | 60 tests pass; VT input; GalleryPreview; UTF-8 subprocess; Windows-safe Python |
| C003 | P1 | TSpotify Windows Runtime | Previous agent | 397 tests pass; Windows runtime lock fixed; intro animation works |
| C004 | P0 | Integration + test build | oc-local | All remote branches merged; Windows test package built and installed in isolated prefix; report in NIGHT_REPORT.md |

---

## Blockers

| ID | Task | Blocker | Resolution Plan |
|----|------|---------|-----------------|
| B001 | T002 | Visual transparency in Windows Terminal cannot be verified headlessly | Manual check by user; launcher/TSpotify/TVPN VT hooks landed, only visual acceptance remains |
| B002 | T003 | Real Telegram authorization not possible at night | User performs auth on their account |
| B003 | T008 | No user-facing release published (by design) | Night build only in temp prefix; user release after verification |

---

## Coordination Notes

- **oc-local** (Strata): Completed TVPN + integration + final test build in `ttools-integration`; sole owner; all agent work preserved and integrated.
- **cloud-1**: VT backend (`72469c1`) and TSpotify/TVPN shims (`67416f4`) committed and verified; diagnosis doc committed.
- **cloud-2**: TTelegram wt.exe alias (`8a0965d`) plus launch/prefix recovery fixes committed and verified; TSoundCloud deferred.
- **Lead**: Architecture, review, integration, launcher, install, updates.

## Next Steps

1. All agent work integrated, verified and pushed to `origin/integration/windows-preview` (`9724404..eddca75`); Draft PR #8 open.
2. Rebuilds and isolated installs were re-run from final commits; smoke checks pass.
3. User to verify real VPN connect, Telegram auth, Spotify login, visual transparency; no user-facing release published.
