/*---------------------------------------------------------------------------------
    Ultima VI SNES Port - Walkable Britannia with Objects
    Milestone 4: object layer (LZOBJBLK) - trees, buildings, furniture, NPCs.
    - Terrain subtiles (750) resident in VRAM at boot
    - Object/composite subtiles (4971) streamed into a 704-slot VRAM cache (LRU)
    - Per-superchunk object overlay (objmap): composite lookup + collision
    - Objects baked over terrain at convert time (SNES BG has no transparency),
      so each visible position renders either its terrain tile or a composite
---------------------------------------------------------------------------------*/

#include <snes.h>

extern char patterns, patterns_end;            // 750 terrain subtiles (24KB)
extern char obj_pic_0, obj_pic_0_end;          // object subtile banks (5 x <=32KB)
extern char obj_pic_1, obj_pic_1_end;
extern char obj_pic_2, obj_pic_2_end;
extern char obj_pic_3, obj_pic_3_end;
extern char obj_pic_4, obj_pic_4_end;
extern char palette, palette_end;
extern char tilemap, tilemap_end;              // 2048 x [pal + 4 subtile ids]
extern char comptab, comptab_end;              // 2541 x [pal + 4 subtile ids]
extern char objmap_a, objmap_a_end;            // overlay data (split 32KB)
extern char objmap_b, objmap_b_end;
extern char objmap_idx, objmap_idx_end;        // 64 x u32 offsets
extern char map_data, map_data_end;
extern char chunk_data_a, chunk_data_a_end;    // CHUNKS bytes 0..32767
extern char chunk_data_b, chunk_data_b_end;    // CHUNKS bytes 32768..65535
extern char tileflag, tileflag_end;            // 2048 collision flags
extern char avatar_gfx, avatar_gfx_end;
extern char avatar_pal, avatar_pal_end;

#define WORLD_W 1024
#define WORLD_H 1024

#define VIEW_W 16      // U6 tiles visible horizontally (16 * 16px = 256px)
#define VIEW_H 14      // U6 tiles visible vertically (14 * 16px = 224px)

#define N_TERRAIN_SUBTILES 750
#define N_OBJ_SUBTILES 4971
#define COMP_OFFSET 2048

// VRAM layout: 0x0000 avatar sprite, 0x4000 terrain patterns, 0xA000 map,
// 0xA800..0xFFFF object cache (704 slots x 32B = 22528B)
#define OBJ_CACHE_SLOTS 704
#define OBJ_CACHE_BASE 0xA800
#define OBJ_CACHE_TILE (OBJ_CACHE_BASE / 32)

// Viewport map buffer: 2 SNES tiles per U6 tile, SC_32x32 layout
static u16 viewport[32 * 28];

/*-----------------------------------------------------------------------------
    VRAM streaming cache.
    Hardware-critical rules (learned the hard way - see M4 bugfix):
    1. NEVER dmaCopyVram outside VBlank: the PPU reads VRAM during active
       scanout; concurrent writes corrupt the displayed tile data. All cache
       uploads are QUEUED during render and flushed inside the VBlank window.
    2. NEVER evict a slot referenced by the current viewport map: the stale
       map entry would show the wrong tile until the next render. Eviction
       victims are chosen only among slots NOT marked in-use this frame.
    3. Keep the reverse map slot_id[] so an evicted slot can release its
       obj_slot entry (otherwise the old id keeps pointing at the recycled
       slot and renders garbage).
-----------------------------------------------------------------------------*/
#define CACHE_MAX_PENDING 1024

static u16 obj_slot[N_OBJ_SUBTILES];        // obj subtile id -> cache slot (0xFFFF absent)
static u16 slot_id[OBJ_CACHE_SLOTS];        // slot -> obj subtile id (0xFFFF free)
static u16 slot_tick[OBJ_CACHE_SLOTS];      // last-use counter for LRU eviction
static u8  slot_inuse[OBJ_CACHE_SLOTS];     // referenced by current frame's map

static u16 pending_id[CACHE_MAX_PENDING];   // queued uploads (obj subtile ids)
static u16 pending_slot[CACHE_MAX_PENDING];
static u16 n_pending = 0;
static u16 tick = 1;

static void tick_bump(u16 slot)
{
    slot_tick[slot] = tick;
    if (tick < 0xFFFE)          // saturate so it never hits the 0xFFFF marker
        tick++;
}

// Camera position in world U6-tile coordinates (wraps at 1024); top-left corner
static u16 cam_x = 320;
static u16 cam_y = 380;

// Avatar state
static u16 av_x = 319;    // world tile coords (Britain, tile 1 = walkable)
static u16 av_y = 380;
static u8  av_dir = 2;    // 0=N 1=E 2=S 3=W (NuVIE order)
static u8  av_walk = 0;   // walk frame 0..3
static u8  av_step_timer = 0;
static u8  av_anim_timer = 0;

/*-----------------------------------------------------------------------------
    chunk_data(chunk): pointer to a 64-byte chunk (0..1023), crossing the
    two 32KB CHUNKS sections.
-----------------------------------------------------------------------------*/
static const u8 *chunk_data(u16 chunk)
{
    if (chunk < 512)
        return (const u8 *)&chunk_data_a + chunk * 64;
    return (const u8 *)&chunk_data_b + (chunk - 512) * 64;
}

/*-----------------------------------------------------------------------------
    world_tile(wx, wy): resolve a world tile index (0..255) from MAP + CHUNKS.
    Port of NuVIE Map::insertSurfaceSuperChunk / insertSurfaceChunk.
-----------------------------------------------------------------------------*/
static u8 world_tile(u16 wx, u16 wy)
{
    u16 schunk = ((wy >> 7) & 7) * 8 + ((wx >> 7) & 7);
    const u8 *sc = (const u8 *)&map_data + schunk * 384;

    u8 i = (wy >> 3) & 0x0F;   // chunk row
    u8 j = (wx >> 3) & 0x0F;   // chunk col

    const u8 *g = sc + ((i * 8) + (j >> 1)) * 3;
    u16 c1 = ((g[1] & 0x0F) << 8) | g[0];
    u16 c2 = (g[2] << 4) | (g[1] >> 4);
    u16 chunk = (j & 1) ? c2 : c1;

    const u8 *ch = chunk_data(chunk);
    return ch[((wy & 7) << 3) + (wx & 7)];
}

/*-----------------------------------------------------------------------------
    obj_at(wx, wy): binary search the superchunk's overlay for a position.
    Returns the composite id + COMP_OFFSET (>= 2048) plus collision flags,
    or 0xFFFF if no object covers this position.
-----------------------------------------------------------------------------*/
static u16 obj_at(u16 wx, u16 wy)
{
    u8 sx = (wx >> 7) & 7;
    u8 sy = (wy >> 7) & 7;
    const u8 *idx = (const u8 *)&objmap_idx + (sy * 8 + sx) * 4;
    u32 off = idx[0] | (idx[1] << 8) | (idx[2] << 16) | (idx[3] << 24);
    if (off == 0)
        return 0xFFFF;

    const u8 *base = (off < 32768) ? (const u8 *)&objmap_a : (const u8 *)&objmap_b;
    u16 loff = (off < 32768) ? off : off - 32768;

    u16 n = base[loff] | (base[loff + 1] << 8);
    u16 key = ((wy & 127) << 7) | (wx & 127);
    u16 lo = 0, hi = n - 1;
    loff += 2;
    while (lo <= hi) {
        u16 mid = (lo + hi) >> 1;
        const u8 *e = base + loff + mid * 5;
        u16 ek = (e[1] << 7) | e[0];
        if (ek < key)
            lo = mid + 1;
        else if (ek > key)
            hi = mid - 1;
        else
            return e[2] | (e[3] << 8);   // composite id + COMP_OFFSET
    }
    return 0xFFFF;
}

/*-----------------------------------------------------------------------------
    obj_coll(wx, wy): collision flags (bit0 water, bit1 impassable) of the
    object covering a position, or 0 if none.
-----------------------------------------------------------------------------*/
static u8 obj_coll(u16 wx, u16 wy)
{
    u8 sx = (wx >> 7) & 7;
    u8 sy = (wy >> 7) & 7;
    const u8 *idx = (const u8 *)&objmap_idx + (sy * 8 + sx) * 4;
    u32 off = idx[0] | (idx[1] << 8) | (idx[2] << 16) | (idx[3] << 24);
    if (off == 0)
        return 0;

    const u8 *base = (off < 32768) ? (const u8 *)&objmap_a : (const u8 *)&objmap_b;
    u16 loff = (off < 32768) ? off : off - 32768;

    u16 n = base[loff] | (base[loff + 1] << 8);
    u16 key = ((wy & 127) << 7) | (wx & 127);
    u16 lo = 0, hi = n - 1;
    loff += 2;
    while (lo <= hi) {
        u16 mid = (lo + hi) >> 1;
        const u8 *e = base + loff + mid * 5;
        u16 ek = (e[1] << 7) | e[0];
        if (ek < key)
            lo = mid + 1;
        else if (ek > key)
            hi = mid - 1;
        else
            return e[4];
    }
    return 0;
}

/*-----------------------------------------------------------------------------
    passable(wx, wy): true when the avatar may enter this tile.
    Terrain TILEFLAG (bit0 water, bit1 impassable) AND object collision.
-----------------------------------------------------------------------------*/
static u8 passable(u16 wx, u16 wy)
{
    u8 f = ((const u8 *)&tileflag)[world_tile(wx, wy)];
    if (f & 0x03)
        return 0;
    return (obj_coll(wx, wy) & 0x03) == 0;
}

/*-----------------------------------------------------------------------------
    subtile_ptr(id): pointer to subtile data in ROM (terrain resident banks +
    object banks). id is a global subtile id 0..5720.
-----------------------------------------------------------------------------*/
static const u8 *subtile_ptr(u16 id)
{
    if (id < N_TERRAIN_SUBTILES)
        return (const u8 *)&patterns + id * 32;
    id -= N_TERRAIN_SUBTILES;
    switch (id >> 10) {
        case 0:  return (const u8 *)&obj_pic_0 + (id & 1023) * 32;
        case 1:  return (const u8 *)&obj_pic_1 + (id & 1023) * 32;
        case 2:  return (const u8 *)&obj_pic_2 + (id & 1023) * 32;
        case 3:  return (const u8 *)&obj_pic_3 + (id & 1023) * 32;
        default: return (const u8 *)&obj_pic_4 + (id & 1023) * 32;
    }
}

/*-----------------------------------------------------------------------------
    cache_get(id): ensure subtile id is in the VRAM cache; return its VRAM
    tile number. On a miss, a slot is assigned and the upload QUEUED (the DMA
    itself happens in flush_cache() inside VBlank - never touch VRAM outside
    VBlank). Eviction picks a free slot, else the LRU slot that is NOT marked
    in-use by the current frame's viewport map.
-----------------------------------------------------------------------------*/
static u16 cache_get(u16 id)
{
    if (id < N_TERRAIN_SUBTILES)
        return 512 + id;                     // resident at 0x4000 (tile 512+)

    u16 oid = id - N_TERRAIN_SUBTILES;
    if (obj_slot[oid] != 0xFFFF) {
        u16 s = obj_slot[oid];
        slot_inuse[s] = 1;
        tick_bump(s);
        return OBJ_CACHE_TILE + s;
    }

    // find a slot: any free slot, else LRU among slots NOT in use this frame
    u16 slot = 0xFFFF;
    u16 min_tick = 0xFFFF;
    u16 i;
    for (i = 0; i < OBJ_CACHE_SLOTS; i++) {
        if (slot_id[i] == 0xFFFF) { slot = i; break; }
    }
    if (slot == 0xFFFF) {
        for (i = 0; i < OBJ_CACHE_SLOTS; i++) {
            if (!slot_inuse[i] && slot_tick[i] < min_tick) {
                min_tick = slot_tick[i];
                slot = i;
            }
        }
    }
    // defensive: if ALL slots are in use, evict LRU anyway (avoid stall)
    if (slot == 0xFFFF) {
        for (i = 0; i < OBJ_CACHE_SLOTS; i++) {
            if (slot_tick[i] < min_tick) { min_tick = slot_tick[i]; slot = i; }
        }
    }

    // release the previous occupant of this slot
    if (slot_id[slot] != 0xFFFF)
        obj_slot[slot_id[slot]] = 0xFFFF;

    obj_slot[oid] = slot;
    slot_id[slot] = oid;
    slot_inuse[slot] = 1;
    tick_bump(slot);
    pending_id[n_pending] = oid;
    pending_slot[n_pending] = slot;
    n_pending++;
    return OBJ_CACHE_TILE + slot;
}

/*-----------------------------------------------------------------------------
    flush_cache(): DMA queued uploads into VRAM, at most 1024 bytes per VBlank
    (a single VBlank can only absorb ~1-2KB of VRAM DMA; overrunning corrupts
    active scanout again). MUST run inside VBlank. Returns 1 when drained,
    0 when more uploads remain for the next VBlank.
-----------------------------------------------------------------------------*/
#define CACHE_VBLANK_BUDGET 1024

static u8 flush_cache(void)
{
    u16 budget = CACHE_VBLANK_BUDGET;
    while (n_pending > 0 && budget >= 32) {
        n_pending--;
        u16 oid = pending_id[n_pending];
        u16 slot = pending_slot[n_pending];
        u16 vram_addr = OBJ_CACHE_BASE + slot * 32;
        dmaCopyVram((u8 *)subtile_ptr(oid + N_TERRAIN_SUBTILES), vram_addr, 32);
        budget -= 32;
    }
    return n_pending == 0;
}

/*-----------------------------------------------------------------------------
    sync_cache(): WaitForVBlank + flush until drained, then the caller DMAs
    the viewport map. Blocks across a few frames on big loads (superchunk
    crossings) — acceptable; the alternative (overrunning VBlank) corrupts.
-----------------------------------------------------------------------------*/
static void sync_cache(void)
{
    while (!flush_cache())
        WaitForVBlank();
}

/*-----------------------------------------------------------------------------
    render_viewport(): fill the viewport map buffer from world position.
    Each U6 16x16 tile -> 2x2 SNES 8x8 tiles. Position with an object renders
    the composite tile (terrain baked in); else the terrain tile.
    Map entry = subtile VRAM tile | (palette << 10).
-----------------------------------------------------------------------------*/
static void render_viewport(void)
{
    u16 vx, vy;
    u16 i;
    for (i = 0; i < OBJ_CACHE_SLOTS; i++)
        slot_inuse[i] = 0;   // fresh frame: nothing in use yet

    for (vy = 0; vy < VIEW_H; vy++) {
        for (vx = 0; vx < VIEW_W; vx++) {
            u16 wx = (cam_x + vx) & 1023;
            u16 wy = (cam_y + vy) & 1023;
            u8 tile = world_tile(wx, wy);
            u16 oid = obj_at(wx, wy);

            const u8 *tm;
            if (oid != 0xFFFF)
                tm = (const u8 *)&comptab + (oid - COMP_OFFSET) * 9;
            else
                tm = (const u8 *)&tilemap + tile * 9;

            u8 pal = tm[0];
            u16 id0 = tm[1] | (tm[2] << 8);
            u16 id1 = tm[3] | (tm[4] << 8);
            u16 id2 = tm[5] | (tm[6] << 8);
            u16 id3 = tm[7] | (tm[8] << 8);

            u16 palbits = (u16)pal << 10;
            u32 base = (u32)(vy * 2) * 32 + vx * 2;

            viewport[base] = cache_get(id0) | palbits;
            viewport[base + 1] = cache_get(id1) | palbits;
            viewport[base + 32] = cache_get(id2) | palbits;
            viewport[base + 33] = cache_get(id3) | palbits;
        }
    }
}

/*-----------------------------------------------------------------------------
    update_avatar_sprite(): place the avatar sprite on screen.
    Camera centers the avatar at pixel (128, 112) = tile (8, 7).
    Frame = dir*4 + walk_frame_tbl[walk_frame], tbl = {0,1,2,1}.
    OAM gfxoffset = (f&7)*2 + (f>>3)*32  (16x16 sprite, 4 tiles n,n+1,n+16,n+17).
-----------------------------------------------------------------------------*/
static const u8 walk_tbl[4] = {0, 1, 2, 1};

static void update_avatar_sprite(void)
{
    u16 sx = ((av_x - cam_x) & 1023) * 16;
    u16 sy = ((av_y - cam_y) & 1023) * 16;
    u8 f = av_dir * 4 + walk_tbl[av_walk];
    u16 gfx = (u16)((f & 7) * 2) + ((f >> 3) * 32);

    oamSet(0, sx, sy, 2, 0, 0, gfx, 0);
    oamSetEx(0, OBJ_SMALL, OBJ_SHOW);
}

/*-----------------------------------------------------------------------------
    main
-----------------------------------------------------------------------------*/
int main(void)
{
    u16 pad;
    u16 i;

    // Terrain patterns (750 subtiles) + 8x16-color palette into VRAM/CGRAM
    bgInitTileSet(0, &patterns, &palette, 0,
                  (&patterns_end - &patterns), (&palette_end - &palette),
                  BG_16COLORS, 0x4000);

    // Init background map on layer 0 at VRAM 0xA000
    bgInitMapSet(0, (u8 *)viewport, 2048, SC_32x32, 0xA000);

    // Avatar sprite: 2KB gfx at VRAM 0x0000, palette at CGRAM 128
    oamInitGfxSet(&avatar_gfx, (&avatar_gfx_end - &avatar_gfx),
                  &avatar_pal, (&avatar_pal_end - &avatar_pal),
                  0, 0x0000, OBJ_SIZE16_L32);

    // Object cache starts empty (0xFFFF = free slot / no mapping)
    for (i = 0; i < N_OBJ_SUBTILES; i++)
        obj_slot[i] = 0xFFFF;
    for (i = 0; i < OBJ_CACHE_SLOTS; i++) {
        slot_id[i] = 0xFFFF;
        slot_tick[i] = 0xFFFF;
        slot_inuse[i] = 0;
    }
    n_pending = 0;

    // Mode 1 (16 colors), only layer 0 active
    setMode(BG_MODE1, 0);
    bgSetDisable(1);
    bgSetDisable(2);
    setScreenOn();

    // Initial render: camera centered on the avatar
    cam_x = (av_x - 8) & 1023;
    cam_y = (av_y - 7) & 1023;
    render_viewport();
    sync_cache();                        // upload queued object tiles, in VBlank
    WaitForVBlank();
    dmaCopyVram((u8 *)viewport, 0xA000, 32 * 28 * 2);
    update_avatar_sprite();

    while (1) {
        pad = padsCurrent(0);

        // pick direction from held pad (priority: up/down over left/right)
        if (pad & KEY_UP)       av_dir = 0;
        else if (pad & KEY_RIGHT) av_dir = 1;
        else if (pad & KEY_DOWN)  av_dir = 2;
        else if (pad & KEY_LEFT)  av_dir = 3;

        if (pad & (KEY_UP | KEY_DOWN | KEY_LEFT | KEY_RIGHT)) {
            if (av_step_timer == 0) {
                u16 nx = av_x, ny = av_y;
                if (av_dir == 0) ny = (ny - 1) & 1023;
                if (av_dir == 1) nx = (nx + 1) & 1023;
                if (av_dir == 2) ny = (ny + 1) & 1023;
                if (av_dir == 3) nx = (nx - 1) & 1023;

                if (passable(nx, ny)) {
                    av_x = nx;
                    av_y = ny;
                    av_walk = (av_walk + 1) & 3;

                    // camera follows the avatar
                    cam_x = (av_x - 8) & 1023;
                    cam_y = (av_y - 7) & 1023;
                    render_viewport();
                    sync_cache();        // upload queued object tiles, in VBlank
                    WaitForVBlank();
                    dmaCopyVram((u8 *)viewport, 0xA000, 32 * 28 * 2);
                    update_avatar_sprite();
                } else {
                    // bump: face the blocked tile, animate a step anyway
                    av_walk = (av_walk + 1) & 3;
                    update_avatar_sprite();
                }
                av_step_timer = 14;   // ~4.3 steps/sec at 60fps
            } else {
                av_step_timer--;
            }
        } else {
            av_step_timer = 0;
            av_walk = 0;   // standing pose
            update_avatar_sprite();
        }

        WaitForVBlank();
    }

    return 0;
}