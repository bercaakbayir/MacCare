# Safe-to-Delete File Patterns — Policy Whitelist

The AI MUST only recommend deleting files/folders that match patterns in this list.
For anything else, the AI must respond: "I cannot confirm this is safe to delete."

## ✅ Confirmed Safe to Delete

### Caches
| Path Pattern | Description | Notes |
|---|---|---|
| `~/Library/Caches/` (per-app subdirs) | App-generated caches | Apps rebuild on next launch |
| `~/Library/Caches/Google/Chrome/` | Chrome cache | Clear via browser too |
| `~/Library/Caches/com.apple.Safari/` | Safari cache | Clear via Safari > Develop menu |
| `~/Library/Caches/Firefox/` | Firefox cache | Apps rebuild |
| `~/Library/Caches/CocoaPods/` | CocoaPods cache | Rebuild with `pod install` |
| `~/Library/Caches/pip/` | Python pip cache | No impact |
| `~/Library/Caches/Homebrew/` | Homebrew download cache | Use `brew cleanup` |

### Xcode / Developer Artifacts
| Path Pattern | Description | Notes |
|---|---|---|
| `~/Library/Developer/Xcode/DerivedData/` | Build artifacts | Rebuilt on next Xcode build |
| `~/Library/Developer/Xcode/Archives/ (old)` | Old app archives | Keep only current release archives |
| `~/Library/Developer/CoreSimulator/Caches/` | Simulator caches | Safe |
| `~/Library/Developer/CoreSimulator/Devices/ (dead simulators)` | Old simulator images | Use `xcrun simctl delete unavailable` |

### Logs
| Path Pattern | Description | Notes |
|---|---|---|
| `~/Library/Logs/` | App-generated log files | Not needed unless debugging |
| `/Library/Logs/DiagnosticReports/ (*.crash, *.ips)` | Crash reports older than 30 days | Safe after review |
| `~/Library/Logs/DiagnosticReports/` | User crash reports | Safe after review |

### Temporary Files
| Path Pattern | Description | Notes |
|---|---|---|
| `/tmp/*` | Temporary system files | macOS clears on reboot |
| `~/Downloads/ (files older than 90 days)` | User downloads | Review before deleting |

### Package Manager Caches
| Path Pattern | Description | Notes |
|---|---|---|
| `~/.npm/_cacache/` | Node/npm cache | Run `npm cache clean --force` |
| `~/.yarn/cache/` | Yarn cache | Run `yarn cache clean` |
| `~/.gradle/caches/` | Gradle build cache | Safe |
| `~/.m2/repository/` | Maven repository | Can re-download |
| `~/.cargo/registry/cache/` | Rust/Cargo cache | Safe |

### Mail
| Path Pattern | Description | Notes |
|---|---|---|
| `~/Library/Mail/V*/MailData/Envelope Index-shm` | Mail index temp | Rebuilt automatically |
| `~/Library/Mail/V*/MailData/Envelope Index-wal` | Mail WAL file | Rebuilt automatically |

## ❌ Never Delete (Protected Patterns)
- `/System/` — Core macOS system files
- `/Library/` root (non-Logs, non-Caches subdirs)
- `~/Library/Application Support/` — App data (settings, databases)
- `~/Library/Keychains/` — Passwords and certificates
- `~/Library/Preferences/` — App preference files (.plist)
- Any file not listed above
