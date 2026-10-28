#!/usr/bin/env python3
"""
Ultima 6 SNES Tile & Palette Converter (Corrected Palette Scaling)
------------------------------------------------------------------
Converts Ultima 6 VGA tile graphics and U6PAL (VGA 0-63 RGB)
into SNES 4bpp planar tile graphics (.pic) and 15-bit color palettes (.pal).
"""

import os
import sys

def convert_palette(u6_dir):
    pal_path = os.path.join(u6_dir, "U6PAL")
    if not os.path.exists(pal_path):
        pal_path = os.path.join(u6_dir, "PALETTES.INT")
    
    if not os.path.exists(pal_path):
        print("Warning: Palette file not found, creating default 16-color SNES palette.")
        return bytearray(32)

    print(f"Reading palette from {pal_path}...")
    with open(pal_path, "rb") as f:
        raw_pal = f.read()

    snes_pal = bytearray(32) # 16 colors * 2 bytes
    
    # VGA palette stores RGB values from 0 to 63 (6 bits per channel).
    # SNES 15-bit color stores RGB values from 0 to 31.
    for i in range(min(16, len(raw_pal) // 3)):
        r6 = raw_pal[i * 3]
        g6 = raw_pal[i * 3 + 1]
        b6 = raw_pal[i * 3 + 2]

        # Scale 0-63 to 0-31 correctly: (val * 31) // 63
        r = (r6 * 31) // 63
        g = (g6 * 31) // 63
        b = (b6 * 31) // 63

        color15 = (b << 10) | (g << 5) | r
        snes_pal[i * 2] = color15 & 0xFF
        snes_pal[i * 2 + 1] = (color15 >> 8) & 0xFF

    return snes_pal

def convert_tiles(u6_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Convert Palette
    snes_pal = convert_palette(u6_dir)
    pal_out = os.path.join(output_dir, "ultima_tiles.pal")
    with open(pal_out, "wb") as f:
        f.write(snes_pal)
    print(f"Exported corrected SNES palette to {pal_out}")

    # 2. Process MAPTILES.VGA
    maptiles_path = os.path.join(u6_dir, "MAPTILES.VGA")
    if os.path.exists(maptiles_path):
        with open(maptiles_path, "rb") as f:
            vga_data = f.read()
        print(f"Loaded MAPTILES.VGA ({len(vga_data)} bytes)")

        num_tiles = len(vga_data) // 64
        snes_tiles = bytearray(num_tiles * 32)

        for t in range(num_tiles):
            tile_src = vga_data[t * 64 : (t + 1) * 64]
            tile_dst = bytearray(32)

            for row in range(8):
                bp0 = 0
                bp1 = 0
                bp2 = 0
                bp3 = 0

                for col in range(8):
                    pixel = tile_src[row * 8 + col] & 0x0F
                    bit = 7 - col

                    if pixel & 1:   bp0 |= (1 << bit)
                    if pixel & 2:   bp1 |= (1 << bit)
                    if pixel & 4:   bp2 |= (1 << bit)
                    if pixel & 8:   bp3 |= (1 << bit)

                row_offset = row * 2
                tile_dst[row_offset] = bp0
                tile_dst[row_offset + 1] = bp1
                tile_dst[16 + row_offset] = bp2
                tile_dst[16 + row_offset + 1] = bp3

            snes_tiles[t * 32 : (t + 1) * 32] = tile_dst

        pic_out = os.path.join(output_dir, "ultima_tiles.pic")
        with open(pic_out, "wb") as f:
            f.write(snes_tiles)
        print(f"Exported {num_tiles} SNES 4bpp tiles to {pic_out}")

def main():
    u6_dir = r"C:\Users\Admin\ultima6_snes\U6"
    output_dir = r"C:\Users\Admin\ultima6_snes\gfx"
    print("=== Ultima 6 SNES Tile & Palette Converter (VGA Corrected) ===")
    convert_tiles(u6_dir, output_dir)
    print("Conversion complete!")

if __name__ == "__main__":
    main()
