# Protected Processes — Blacklist

The AI MUST NEVER suggest killing, force-quitting, or disabling any process in this list.
Doing so can cause data loss, system instability, or security vulnerabilities.

## ✅ Absolutely Protected (System Critical)

| Process Name | Role |
|---|---|
| `kernel_task` | macOS kernel — thermal management, core OS |
| `launchd` | Root process manager — parent of all processes |
| `WindowServer` | Manages all graphical display output |
| `mds` / `mds_stores` | Spotlight indexing — metadata server |
| `coreaudiod` | Core Audio daemon |
| `bluetoothd` | Bluetooth daemon |
| `configd` | Network configuration daemon |
| `diskarbitrationd` | Disk mount/unmount daemon |
| `powerd` | Power management daemon |
| `securityd` | Keychain and security services |
| `trustd` | Certificate trust evaluation |
| `syspolicyd` | Gatekeeper / app security policy |
| `amfid` | App Mobile File Integrity daemon |
| `notifyd` | System-wide notification service |
| `opendirectoryd` | Directory services (users, groups) |
| `logd` | Unified logging system |
| `syslogd` | Legacy system log daemon |
| `fseventsd` | File system events daemon |
| `cfprefsd` | Preferences daemon |
| `lsd` | Launch Services daemon |
| `SpringBoard` | iOS/Simulator UI layer |
| `loginwindow` | Login screen manager |
| `ctkahp` | Credential provider |
| `endpointsecurityd` | Endpoint security framework |

## ⚠️ Use With Extreme Caution (User-Facing but Critical)

| Process Name | Role | Why Protected |
|---|---|---|
| `Finder` | File manager | Core user shell — restart, don't kill |
| `Dock` | Application dock | Can be restarted, not killed |
| `SystemUIServer` | Menu bar | Manages menu bar — restart safely |
| `ControlCenter` | Control Center | macOS 11+ menu bar manager |
| `NotificationCenter` | Notifications | User notification layer |

## ℹ️ Policy
- If a protected process has high CPU/RAM, report it and explain WHY macOS is doing it (e.g., `kernel_task` throttles CPU to cool the system).
- Never suggest `sudo killall -9 <protected_process>`.
- Instead, recommend: restarting the app, restarting the Mac, or investigating the root cause.
