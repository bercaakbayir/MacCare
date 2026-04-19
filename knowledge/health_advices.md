# macOS Health Advices — Policy Document

## Storage Health
- **Threshold:** Warn if disk usage exceeds 80% of total capacity.
- **Critical:** Alert if disk usage exceeds 90% — this will severely impact performance and Time Machine backups.
- **Tip:** macOS needs at least 10–15 GB of free space for virtual memory swap files and system operations.
- **Action:** Run `sudo periodic daily weekly monthly` periodically to clean up system caches.
- **Downloads Folder:** Frequently the largest consumer of unnecessary space. Recommend reviewing files older than 30 days.
- **Trash:** Remind users to empty Trash if it contains more than 1 GB of data.

## Cache Files
- **Application Caches** (`~/Library/Caches`): Generally safe to delete on a per-app basis, but use caution. Apps will re-generate them.
- **System Caches** (`/Library/Caches`): Some are critical — only remove if you know the app.
- **Browser Caches:** Chrome, Safari, Firefox all maintain large caches (200 MB–2 GB). Safe to clear via the browser's settings.
- **Xcode Derived Data** (`~/Library/Developer/Xcode/DerivedData`): Can grow to tens of GBs. Completely safe to delete.
- **CocoaPods cache** (`~/Library/Caches/CocoaPods`): Safe to delete.
- **Homebrew cache** (`~/Library/Caches/Homebrew`): Safe to delete with `brew cleanup`.

## Memory (RAM) Health
- **Threshold:** Warn if memory pressure is "red" or if less than 500 MB of free memory exists for extended periods.
- **Swap Usage:** If swap exceeds 2 GB, this is a strong sign the Mac needs more RAM or has runaway processes.
- **Tip:** macOS uses "memory compression" — "used" memory shown by tools is not the same as "exhausted" memory.
- **Action:** Use Activity Monitor to identify and quit processes consuming more than 500 MB unexpectedly.
- **Browsers:** Chrome and Electron apps are notorious RAM consumers. Closing unused tabs helps significantly.

## Battery Health
- **Optimal Charge:** Keep battery between 20%–80% for longest longevity.
- **Cycle Count:** MacBook batteries are rated for ~1000 charge cycles. Above 800 cycles, consider replacement.
- **Health:** If battery health drops below 80%, macOS shows "Service Recommended". Take seriously.
- **Power Hogs:** GPU-intensive apps, display brightness, and external USB devices drain battery fastest.
- **Tip:** Use "Low Power Mode" in System Settings when on battery and not doing intensive tasks.
- **Thermal:** If the Mac is hot, the fan runs harder and battery drains faster. Ensure vents are unobstructed.

## CPU & Performance
- **Threshold:** Sustained CPU usage above 80% for more than 5 minutes indicates a problem.
- **Tip:** `kernel_task` high CPU usage is macOS intentionally throttling the CPU to cool the system.
- **Spotlight:** `mds_stores` high CPU after a new macOS install or migration is normal — it's indexing. Give it time.
- **Malware Check:** Unexpected high CPU from unknown processes warrants investigation.

## General Maintenance
- Keep macOS updated to the latest patch version for security and performance fixes.
- Restart your Mac at least once a week to clear memory and apply pending updates.
- Review Login Items (`System Settings > General > Login Items`) — remove unnecessary startup apps.
- Run Disk Utility's "First Aid" quarterly to check disk integrity.
