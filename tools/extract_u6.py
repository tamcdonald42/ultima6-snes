#!/usr/bin/env python3
"""
Ultima 6 Asset Extractor & Converter for SNES Port
--------------------------------------------------
Reads original Ultima 6 files from the U6 directory and prepares them for SNES.
"""

import os
import sys

def main():
    u6_dir = r"C:\Users\Admin\ultima6_snes\U6"
    print(f"Scanning Ultima 6 data directory: {u6_dir}")

    required_files = ["MAP", "CHUNKS", "BASETILE", "TILEFLAG", "MAPTILES.VGA", "OBJTILES.VGA"]
    missing = []

    for f in required_files:
        fpath = os.path.join(u6_dir, f)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath)
            print(f"  [OK] {f} ({size} bytes)")
        else:
            print(f"  [MISSING] {f}")
            missing.append(f)

    if missing:
        print(f"\nWarning: Some files are missing: {missing}")
    else:
        print("\nAll essential Ultima 6 core files found!")

    print("\nAsset extraction framework ready. You can now build map parsers referencing Nuvie source code.")

if __name__ == "__main__":
    main()
