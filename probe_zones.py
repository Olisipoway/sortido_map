"""
probe_zones.py — Dispatcher: runs headless Bolt + Glovo sweeps together.

Called by launchd (com.sortido.bolt-sweep) at scheduled hours.
Each platform has its own file with the full algorithm:
  probe_bolt.py   — Bolt API (getSearchScreenContent)
  probe_glovo.py  — Glovo polygon check (--sweep) / browser (--browser)
  probe_ubereats.py — UberEats browser sweep (run manually)
"""

import argparse
import probe_bolt
import probe_glovo

PLATFORMS = {
    "bolt":  probe_bolt.sweep,
    "glovo": probe_glovo.sweep,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep",    action="store_true")
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--platform", nargs="+", choices=list(PLATFORMS.keys()),
                        default=list(PLATFORMS.keys()))
    args = parser.parse_args()

    if args.sweep:
        for platform in args.platform:
            PLATFORMS[platform]()
    elif args.schedule:
        probe_bolt.run_scheduler()
    else:
        parser.print_help()
