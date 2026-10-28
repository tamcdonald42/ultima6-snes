#!/usr/bin/env python3
"""
Ultima 6 SNES Asset Conversion Tool
-------------------------------------------------------------------
Demonstrates how to process original PC graphic assets (PCX/PNG)
into SNES 4bpp tile formats suitable for PVSnesLib.
"""

import os
import sys

def main():
    print("=== Ultima 6 SNES Asset Converter ===")
    print("This script provides a framework for processing PC tiles into SNES format.")
    print("Usage: python convert_assets.py <input_dir> <output_dir>")
    
    if len(sys.argv) < 3:
        print("Using default placeholder paths...")
        input_dir = "../assets_pc"
        output_dir = "../gfx"
    else:
        input_dir = sys.argv[1]
        output_dir = sys.argv[2]

    print(f"Input assets: {os.path.abspath(input_dir)}")
    print(f"Output gfx:   {os.path.abspath(output_dir)}")
    print("Conversion pipeline ready. Implement tile quantization and 4bpp packing here.")

if __name__ == "__main__":
    main()
