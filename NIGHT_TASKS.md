# Night Tasks Queue — TTools Autonomous Development

## Task Format
| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |

---

## Active Tasks

| ID | Priority | Component | Assignee | Branch/Worktree | Status | Acceptance Criteria | Last Result | Next Action |
|----|----------|-----------|----------|-----------------|--------|---------------------|-------------|-------------|
| T001 | P0 | TVPN | oc-local | integration/windows-preview (C:\Users\user\source\repos\ttools-integration) | DONE | Globe zoom/rotate/focus/spin works; reduced_motion restored; region selection works; Riseup gateways load; no white rectangles; version sync | 13 passed, 5 skipped (POSIX PTY); splash/demo/offline doctor OK; version 1.4.1 synced; Windows installer hardened; no bkgd | None; real VPN connect requires user |
| T002 | P0 | Common VT Rendering | cloud-1 | integration/windows-preview | IN_PROGRESS (cloud) | All components inherit terminal background/transparency/acrylic; no opaque gray; no forced backgrounds | Launcher migrated to direct VT backend (`72469c1`, 5 tests); root suite 78 passed; diagnosis doc untracked; component entry-point hooks pending | Wait for agent completion; do not edit its files |
| T003 | P0 | TTelegram Windows | cloud-2 | integration/windows-preview | DONE (offline) | Exit code 0 on launch; tdjson works; manifests verified; auth preserved | Windows payload downloaded + SHA-256 verified; modernization merged; manifests fixed for CRLF; native doctor OK; 9 passed, 1 skipped | Real auth/playback requires user |
| T004 | P1 | TSpotify | cloud-1 (after T002) | fix/tspotify-windows-runtime | PARTIAL | Native background; audio spectrum where possible; adaptive layout; F7-F12 work; mouse stable | 397 passed, 2 skipped; no bkgd; verify-runtime OK in installed package | Real audio/login needs user; VT agent work pending |
| T005 | P1 | tthings | oc-local (after T001) | fix/tthings-windows-runtime | DONE | Gallery windows transparent; no spontaneous exits; tests pass | Merged `origin/fix/tthings-windows-runtime`; 60 passed, 7 skipped, 4870 subtests | Visual transparency needs manual check |
| T006 | P1 | TSoundCloud | cloud-2 (after T003) | New worktree | DEFERRED (tests green) | Windows runtime works or documented limitations | Not in standard Windows install; 14 passed, 3 skipped after fixing cross-platform test fixture | Document limitation; do not ship in Windows installer |
| T007 | P0 | TTools Launcher | lead | integration/windows-preview | DONE | Apps list populated; native background; no Python conflicts; diagnostic logging | Dev `--list` shows 5; installed runner `--list` shows 4 supported apps; no bkgd; direct VT backend on interactive Windows consoles; 78 root tests passed | Visual acceptance in Windows Terminal |
| T008 | P0 | One-Command Install | lead | integration/windows-preview | DONE (isolated) | Single command installs; SHA-256 verified; PATH updated; `ttools` works | Built Windows ZIP (159 MB); installed to isolated prefix; `--no-shortcuts --defer-system`; runner works; no user install/PATH change | Manual one-command install by user not performed |
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
| B001 | T002 | Visual transparency in Windows Terminal cannot be verified headlessly | Manual check by user; launcher VT backend landed, component hooks pending from cloud agent |
| B002 | T003 | Real Telegram authorization not possible at night | User performs auth on their account |
| B003 | T008 | No user-facing release published (by design) | Night build only in temp prefix; user release after verification |

---

## Coordination Notes

- **oc-local** (Strata): Completed TVPN + integration + test build in `ttools-integration`. Sole owner of that worktree; preserving untracked VT work from cloud-1.
- **cloud-1**: VT backend for launcher is committed (`72469c1`); agent still editing TTelegram files and holds the untracked VT diagnosis doc in this worktree; do not touch its in-flight files.
- **cloud-2**: TTelegram wt.exe alias fix committed locally (`8a0965d`); additional launcher/prefix recovery fixes in flight; TSoundCloud deferred.
- **Lead**: Architecture, review, integration, launcher, install, updates.

## Next Steps

1. Wait for cloud agents to finish in-flight TTelegram/VT work, then review and commit only after verification.
2. Rebuild the Windows test package from final commits; re-run isolated install + smoke checks.
3. Push final verified commits to `origin/integration/windows-preview`; update Draft PR.
4. User to verify real VPN connect, Telegram auth, Spotify login, visual transparency.
