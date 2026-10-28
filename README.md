# Ultima VI: The False Prophet - SNES Port (Milestone 3: Walkable Britannia)

This repository contains the development environment, asset conversion pipeline, and
prototype engine for porting **Ultima VI: The False Prophet** (PC/DOS) to the
Super Nintendo (SNES) using **PVSnesLib**.

## Milestone 3 Accomplishments

1. **Avatar sprite** - The Avatar's 16 tiles (OBJTILES 1776-1791, found via
   BASETILE obj 410 -> tile 1776) are converted to a 64-tile SNES 4bpp sprite
   sheet (`src/avatar.pic`, palette `src/avatar.pal`) with one 16-color palette
   (slot 0 transparent). 16 frames = 4 directions (N=0,E=1,S=2,W=3 per NuVIE) x
   4 walk frames; walk cycle uses NuVIE's walk_frame_tbl {0,1,2,1}.
   OAM layout: 16x16 sprite = 4 8x8 tiles at n,n+1,n+16,n+17; frames placed at
   (f&7)*2 + (f>>3)*32 (PVSnesLib sprite interleave: 8 frames per 16-tile row).

2. **Collision (TILEFLAG)** - `src/tileflag.bin` = raw flags1 bytes for all 2048
   tiles (bit0=water, bit1=impassable, per NuVIE loadTileFlag). Avatar is blocked
   by both; bump animates in place.

3. **Walkable world** - Avatar spawns at Britain (319,380) (tile 1 = walkable;
   the original spawn (320,380) is a building interior), camera follows the
   avatar (centered at pixel 128,112), D-pad moves 1 tile/step at ~4.3 steps/sec
   with walk animation. Sprite gfx at VRAM 0x0000, sprite palette at CGRAM 128
   (BG palettes own CGRAM 0-127; PVSnesLib oamInitGfxSet puts sprite palettes at
   128+tilePaletteNumber*16, confirmed from sprites.asm source).

4. **Verified** - ROM contains tileflag.bin/avatar.pic/avatar.pal byte-exact;
   Python simulator (sim_m3.py) renders the ROM's own bytes: avatar sprite
   matches the source frame pixel-for-pixel (102/102 px), collision stops the
   avatar at building walls and water, Britain area is 1163 passable / 437
   blocked tiles in a 40x40 patch.

## Milestone 2 Accomplishments

1. **Corrected Asset Pipeline (LZW)**:
   - Fixed `convert_tiles.py` (broken: it read LZW-compressed `MAPTILES.VGA` as raw pixels).
   - New `tools/convert_u6.py` ports NuVIE semantics exactly: LZW-decompresses
     `MAPTILES.VGA` + `MASKTYPE.VGA` (`tools/u6lzw.py`), indexes tiles via
     `TILEINDX.VGA` (offset x16 into the maptiles+objtiles buffer), decodes PBLCK
     pixel-block tiles, quantizes each used 16x16 8bpp tile into 8 global 16-color
     palettes (median cut + k-means refinement), splits into 2x2 SNES 8x8 tiles,
     dedupes, and emits SNES 4bpp planar graphics.
   - Outputs: `src/ultima_tiles.pic` (4bpp), `src/ultima_tiles.pal` (8x16x2 15-bit),
     `src/ultima_tilemap.bin` (2048 tiles x [palette u8 + 4 subtile u16]),
     `src/chunks_a.bin` + `src/chunks_b.bin` (CHUNKS split into two 32KB halves,
     because a single 64KB section cannot fit a LoROM 32KB bank window).

2. **Real Britannia Map Render**:
   - `src/main.c` decodes `MAP` + `CHUNKS` at runtime (ported from NuVIE
     `Map.cpp::insertSurfaceSuperChunk` / `insertSurfaceChunk`): 64 superchunks of
     128x128 tiles, packed 12-bit chunk indices, 8x8 tile chunks.
   - Full 1024x1024 surface world, wrapping at edges, camera spawns at Britain
     (320, 380). D-pad scrolls through the world; the 16x14-tile viewport is
     re-rendered and DMA'd to VRAM on camera move.
   - Data layout: tiles at VRAM 0x4000, map at 0xA000 (SC_32x32), mode 1.

3. **Verified**:
   - Tile decode cross-checked against a reference decoder at multiple world
     coordinates (byte-identical tile indices).
   - ROM data verified: MAP/CHUNKS/palette/tilemap/pic all present byte-exact.
   - Viewport render simulated from the actual ROM bytes — shows coherent Britannia
     terrain (grass, river, roads, Britain's buildings) matching the original.

## Project Structure
- `U6/` - Original PC game asset files (`MAP`, `CHUNKS`, `MAPTILES.VGA`, `U6PAL`, etc.)
- `nuvie/` - Nuvie engine source code (reference; ScummVM handoff commit)
- `src/` - Engine source (`main.c`, `data.asm`, `hdr.asm`) + converted assets
- `tools/` - `convert_u6.py` (LZW-corrected converter), `u6lzw.py` (LZW decoder),
  `extract_u6.py` (file scanner), `convert_assets.py` (framework stub)
- `build.py` - Python build script (path-independent: works from D:\ or C:\)
- `ultima6_snes.sfc` - Compiled SNES ROM (LoROM, 256KB) for Mesen-S / bsnes / FXPak Pro

## How to Rebuild
```bash
python build.py
```

## Next Milestones (suggested)
- Animated water / ANIMDATA overlay on the black river-base tiles
- Object layer (OBJBLK) for trees, buildings' interior objects, NPCs
- Avatar sprite + movement with collision (TILEFLAG)
- Dungeon levels (MAP dungeon superchunks, 256x256)
- Conversation system (CONVERSE.A/B), look/use via TILEFLAG + usecode