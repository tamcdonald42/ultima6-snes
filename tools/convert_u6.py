#!/usr/bin/env python3
"""
Ultima 6 SNES Asset Converter (LZW-corrected)
=============================================
Ports NuVIE semantics exactly:
  1. LZW-decompress MAPTILES.VGA and MASKTYPE.VGA (U6Lzw)
  2. Index tiles via TILEINDX.VGA (offset x16 into maptiles+objtiles buffer)
  3. Decode PBLCK (pixel-block) tiles
  4. Quantize each used 16x16 8bpp tile to a 16-color palette (8 global palettes
     via median cut), split into 2x2 SNES 8x8 tiles, dedupe -> 4bpp planar .pic
  5. Emit: ultima_tiles.pic (4bpp), ultima_tiles.pal (8x16x2, 15-bit),
     ultima_tilemap.bin (2048 x [pal u8 + 4x subtile u16])
MAP and CHUNKS are included raw into the ROM (incbin) and decoded at runtime.
"""
import os
import struct
import sys
from collections import Counter

try:
    from u6lzw import U6Lzw
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from u6lzw import U6Lzw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # project root (ultima6_snes)
U6_DIR = os.path.join(ROOT, "U6")
OUT_DIR = os.path.join(ROOT, "src")

PLAIN, TRANS, PBLCK = 0x0, 0x5, 0xA


def load(name, base=None):
    with open(os.path.join(base or HERE, name), "rb") as f:
        return f.read()


def dist(c1, c2):
    return (c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2


def median_cut(cs, k):
    buckets = [sorted(set(cs))]
    while len(buckets) < k:
        cand = [b for b in buckets if len(b) > 1]
        if not cand:
            break
        widest = max(cand, key=lambda b: (max(c[0] for c in b)-min(c[0] for c in b)) +
                     (max(c[1] for c in b)-min(c[1] for c in b)) +
                     (max(c[2] for c in b)-min(c[2] for c in b)))
        axes = [max(c[a] for c in widest) - min(c[a] for c in widest) for a in range(3)]
        widest.sort(key=lambda c: c[axes.index(max(axes))])
        mid = len(widest) // 2
        i = buckets.index(widest)
        buckets[i:i+1] = [widest[:mid], widest[mid:]]
    return buckets


def to_4bpp_planar(sub):
    out = bytearray(32)
    for row in range(8):
        b0 = b1 = b2 = b3 = 0
        for col in range(8):
            px = sub[row*8+col]
            bit = 7-col
            if px & 1: b0 |= 1 << bit
            if px & 2: b1 |= 1 << bit
            if px & 4: b2 |= 1 << bit
            if px & 8: b3 |= 1 << bit
        out[row*2] = b0
        out[row*2+1] = b1
        out[16+row*2] = b2
        out[16+row*2+1] = b3
    return bytes(out)


def decode_tiles(combined, tileindx, masktype):
    tiles = []
    for i in range(2048):
        off = int.from_bytes(tileindx[i*2:i*2+2], "little") * 16
        mt = masktype[i] if i < len(masktype) else PLAIN
        buf = bytearray([0xff]) * 256
        if off + 256 <= len(combined):
            if mt == PBLCK:
                ptr = off + 1
                dptr = 0
                while True:
                    disp = combined[ptr] + (combined[ptr+1] << 8)
                    x = disp % 160 + (160 if disp >= 1760 else 0)
                    ln = combined[ptr+2]
                    if ln == 0:
                        break
                    dptr += x
                    buf[dptr:dptr+ln] = combined[ptr+3:ptr+3+ln]
                    dptr += ln
                    ptr += 3 + ln
            else:
                buf = bytearray(combined[off:off+256])
        tiles.append(buf)
    return tiles


def surface_used_tiles(mapdata, chunks):
    used = set()
    for s in range(64):
        sc = mapdata[s*384:(s+1)*384]
        for g in range(128):
            g3 = sc[g*3:g*3+3]
            c1 = ((g3[1] & 0xf) << 8) | g3[0]
            c2 = (g3[2] << 4) | (g3[1] >> 4)
            for c in (c1, c2):
                if c < 1024:
                    used.update(chunks[c*64:(c+1)*64])
    return used


def build_assets():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== Ultima 6 SNES converter (LZW-corrected) ===")

    lzw = U6Lzw()
    maptiles = lzw.decompress(load("MAPTILES.VGA", U6_DIR))
    masktype = lzw.decompress(load("MASKTYPE.VGA", U6_DIR))
    objtiles = load("OBJTILES.VGA", U6_DIR)
    tileindx = load("TILEINDX.VGA", U6_DIR)
    u6pal = load("U6PAL", U6_DIR)
    mapdata = load("MAP", U6_DIR)
    chunks = load("CHUNKS", U6_DIR)
    print(f"maptiles {len(maptiles)}B  masktype {len(masktype)}B  objtiles {len(objtiles)}B")

    pal256 = [((u6pal[i*3] << 2) | (u6pal[i*3] >> 4),
               (u6pal[i*3+1] << 2) | (u6pal[i*3+1] >> 4),
               (u6pal[i*3+2] << 2) | (u6pal[i*3+2] >> 4)) for i in range(256)]

    tiles = decode_tiles(maptiles + objtiles, tileindx, masktype)
    used = surface_used_tiles(mapdata, chunks)
    print(f"surface uses {len(used)} tile numbers (max {max(used)})")

    freq = Counter()
    for t in used:
        if t < 2048:
            freq.update(p for p in tiles[t] if p != 0xff)
    colors = [pal256[c] for c, _ in freq.most_common()]
    print(f"{len(colors)} distinct colors")

    clusters = median_cut(colors, 8)
    palettes = []
    # fill each palette with the most frequent colors in the cluster
    cl_sets = [set(cl) for cl in clusters]
    for ci_cl, cl in enumerate(clusters):
        cl_set = cl_sets[ci_cl]
        cl_freq = Counter()
        for t in used:
            if t >= 2048:
                continue
            for px in tiles[t]:
                if px != 0xff and pal256[px] in cl_set:
                    cl_freq[pal256[px]] += 1
        ranked = [c for c, _ in cl_freq.most_common()]
        p = [(0, 0, 0)] * 16
        for ci, c in enumerate(ranked[:16]):
            p[ci] = c
        palettes.append(p)

    # Per-tile palette assignment + k-means refinement of each palette
    tile_pal = {}
    for t in used:
        if t >= 2048:
            continue
        tile_pal[t] = min(range(8), key=lambda pi: sum(
            min(dist(pal256[px], c) for c in palettes[pi]) for px in tiles[t] if px != 0xff))

    # k-means refine each palette's 16 slots over the pixels mapped to it
    def nearest_slot(pix, pal):
        return min(range(1, 16), key=lambda ci: dist(pix, pal[ci]))  # slot 0 stays black

    for _ in range(16):
        sums = [[[0, 0, 0] for _ in range(16)] for _ in range(8)]
        cnts = [[0] * 16 for _ in range(8)]
        for t in used:
            if t >= 2048:
                continue
            pal = tile_pal[t]
            for px in tiles[t]:
                if px == 0xff:
                    continue
                ci = nearest_slot(pal256[px], palettes[pal])
                sums[pal][ci][0] += pal256[px][0]
                sums[pal][ci][1] += pal256[px][1]
                sums[pal][ci][2] += pal256[px][2]
                cnts[pal][ci] += 1
        for pi in range(8):
            for ci in range(1, 16):
                if cnts[pi][ci] > 0:
                    n = cnts[pi][ci]
                    palettes[pi][ci] = (sums[pi][ci][0] // n, sums[pi][ci][1] // n, sums[pi][ci][2] // n)

    # reassign tiles after refinement
    for t in used:
        if t >= 2048:
            continue
        tile_pal[t] = min(range(8), key=lambda pi: sum(
            min(dist(pal256[px], c) for c in palettes[pi]) for px in tiles[t] if px != 0xff))

    subtile_ids = {}
    pic = bytearray()
    tilemap = {}
    for t in sorted(used):
        if t >= 2048:
            continue
        pal = tile_pal[t]
        q = bytearray(256)
        for px_i, px in enumerate(tiles[t]):
            if px == 0xff:
                q[px_i] = 0
            else:
                q[px_i] = min(range(16), key=lambda ci: dist(pal256[px], palettes[pal][ci]))
        ids = []
        for sy in (0, 1):
            for sx in (0, 1):
                sub = bytearray(64)
                for r in range(8):
                    for c in range(8):
                        sub[r*8+c] = q[(sy*8+r)*16 + sx*8+c]
                key = bytes(sub)
                if key not in subtile_ids:
                    subtile_ids[key] = len(subtile_ids)
                    pic += to_4bpp_planar(sub)
                ids.append(subtile_ids[key])
        tilemap[t] = (pal, ids)
    print(f"{len(subtile_ids)} unique 8x8 subtiles -> pic {len(pic)}B")

    with open(os.path.join(OUT_DIR, "ultima_tiles.pic"), "wb") as f:
        f.write(pic)
    palbin = bytearray()
    for p in palettes:
        for (r, g, b) in p:
            palbin += struct.pack("<H", ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3))
    with open(os.path.join(OUT_DIR, "ultima_tiles.pal"), "wb") as f:
        f.write(palbin)
    tmb = bytearray()
    for t in range(2048):
        if t in tilemap:
            pal, ids = tilemap[t]
            tmb.append(pal)
            for i in ids:
                tmb += struct.pack("<H", i)
        else:
            tmb += b"\x00" + b"\x00\x00" * 4
    with open(os.path.join(OUT_DIR, "ultima_tilemap.bin"), "wb") as f:
        f.write(tmb)

    # CHUNKS split into two 32KB halves (LoROM bank window limit)
    with open(os.path.join(OUT_DIR, "chunks_a.bin"), "wb") as f:
        f.write(chunks[:32768])
    with open(os.path.join(OUT_DIR, "chunks_b.bin"), "wb") as f:
        f.write(chunks[32768:])

    # --- TILEFLAG collision: 2048 tiles x 1 byte (flags1) ---
    tileflag = load("TILEFLAG", U6_DIR)
    flags1 = tileflag[:2048]
    with open(os.path.join(OUT_DIR, "tileflag.bin"), "wb") as f:
        f.write(flags1)
    blocked = sum(1 for b in flags1 if b & 0x2)  # bit 1 = impassable
    water = sum(1 for b in flags1 if b & 0x1)
    print(f"tileflag: {blocked} impassable, {water} water tiles")

    # --- Avatar sprite: 16 tiles (1776-1791), 4 dirs x 4 frames ---
    # frame_n = direction*4 + walk_frame_tbl[walk_frame], tbl = {0,1,2,1}
    AV_BASE = 1776
    all_tiles = tiles
    av_colors = Counter()
    for t in range(AV_BASE, AV_BASE + 16):
        av_colors.update(p for p in all_tiles[t] if p != 0xff)
    av_rgbs = [pal256[c] for c, _ in av_colors.most_common()]
    # one 16-color palette for the whole avatar (slot 0 = transparent)
    av_clusters = median_cut(av_rgbs, 1)[0]
    av_ranked = [pal256[c] for c, _ in av_colors.most_common()]
    av_pal = [(0, 0, 0)] * 16
    for ci, c in enumerate(av_ranked[:15]):
        av_pal[ci + 1] = c
    # k-means refine avatar palette over avatar pixels
    def av_nearest(pix):
        return min(range(1, 16), key=lambda ci: dist(pix, av_pal[ci]))
    for _ in range(16):
        sums = [[0, 0, 0] for _ in range(16)]
        cnts = [0] * 16
        for t in range(AV_BASE, AV_BASE + 16):
            for px in all_tiles[t]:
                if px == 0xff:
                    continue
                ci = av_nearest(pal256[px])
                sums[ci][0] += pal256[px][0]; sums[ci][1] += pal256[px][1]; sums[ci][2] += pal256[px][2]
                cnts[ci] += 1
        for ci in range(1, 16):
            if cnts[ci] > 0:
                n = cnts[ci]
                av_pal[ci] = (sums[ci][0] // n, sums[ci][1] // n, sums[ci][2] // n)

    # 16x16 sprite = 4 SNES 8x8 tiles; OAM layout: TL,TR at n,n+1, BL,BR at n+16,n+17.
    # Frames 0-7 use tiles 0..30 (rows 0 and 16), frames 8-15 use 32..62 (rows 32 and 48).
    def av_frame_tiles(f):
        n = (f & 7) * 2 + (f >> 3) * 32
        return n, n + 1, n + 16, n + 17

    av_pic = bytearray(64 * 32)
    for f in range(16):
        t = AV_BASE + f
        q = bytearray(256)
        for px_i, px in enumerate(all_tiles[t]):
            q[px_i] = 0 if px == 0xff else av_nearest(pal256[px])
        n = (f & 7) * 2 + (f >> 3) * 32
        slots = av_frame_tiles(f)
        for sy in (0, 1):
            for sx in (0, 1):
                sub = bytearray(64)
                for r in range(8):
                    for c in range(8):
                        sub[r * 8 + c] = q[(sy * 8 + r) * 16 + sx * 8 + c]
                idx = slots[sy * 2 + sx]
                av_pic[idx * 32:(idx + 1) * 32] = to_4bpp_planar(sub)
    with open(os.path.join(OUT_DIR, "avatar.pic"), "wb") as f:
        f.write(av_pic)
    av_palbin = bytearray()
    for (r, g, b) in av_pal:
        av_palbin += struct.pack("<H", ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3))
    with open(os.path.join(OUT_DIR, "avatar.pal"), "wb") as f:
        f.write(av_palbin)
    print(f"avatar: {len(av_rgbs)} distinct colors -> 16, pic {len(av_pic)}B")

    print(f"Wrote {os.path.join(OUT_DIR, 'ultima_tiles.pic')}, .pal, ultima_tilemap.bin, chunks_a/b.bin, tileflag.bin, avatar.pic/.pal")
    return pic, palbin, tmb, tiles, pal256, palettes, tile_pal


if __name__ == "__main__":
    build_assets()