/*---------------------------------------------------------------------------------
    Ultima VI SNES Port - Walkable Britannia
    Milestone 3: avatar sprite + TILEFLAG collision on the real world map.
    - Decodes MAP + CHUNKS at runtime (NuVIE Map.cpp semantics)
    - Avatar walks 4 directions with walk animation, blocked by impassable/water
    - Camera follows the avatar, viewport re-renders + DMA'd on every step
---------------------------------------------------------------------------------*/

#include <snes.h>

extern char patterns, patterns_end;
extern char palette, palette_end;
extern char tilemap, tilemap_end;
extern char map_data, map_data_end;
extern char chunk_data_a, chunk_data_a_end;   // CHUNKS bytes 0..32767
extern char chunk_data_b, chunk_data_b_end;   // CHUNKS bytes 32768..65535
extern char tileflag, tileflag_end;           // 2048 collision flags
extern char avatar_gfx, avatar_gfx_end;       // 64 8x8 tiles (16 frames)
extern char avatar_pal, avatar_pal_end;       // 16 colors

#define WORLD_W 1024
#define WORLD_H 1024

#define VIEW_W 16      // U6 tiles visible horizontally (16 * 16px = 256px)
#define VIEW_H 14      // U6 tiles visible vertically (14 * 16px = 224px)

// Viewport map buffer: 2 SNES tiles per U6 tile, SC_32x32 layout
static u16 viewport[32 * 28];

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
    passable(wx, wy): true when the avatar may enter this tile.
    TILEFLAG flags1: bit0 = water, bit1 = impassable (NuVIE loadTileFlag).
-----------------------------------------------------------------------------*/
static u8 passable(u16 wx, u16 wy)
{
    u8 f = ((const u8 *)&tileflag)[world_tile(wx, wy)];
    return (f & 0x03) == 0;
}

/*-----------------------------------------------------------------------------
    render_viewport(): fill the viewport map buffer from world position.
    Each U6 16x16 tile -> 2x2 SNES 8x8 tiles via the tilemap table.
    Map entry = subtile id | (palette << 10).
-----------------------------------------------------------------------------*/
static void render_viewport(void)
{
    u16 vx, vy;

    for (vy = 0; vy < VIEW_H; vy++) {
        for (vx = 0; vx < VIEW_W; vx++) {
            u16 wx = (cam_x + vx) & 1023;
            u16 wy = (cam_y + vy) & 1023;
            u8 tile = world_tile(wx, wy);

            const u8 *tm = (const u8 *)&tilemap + tile * 9;
            u8 pal = tm[0];
            u16 e0 = tm[1] | (tm[2] << 8);
            u16 e1 = tm[3] | (tm[4] << 8);
            u16 e2 = tm[5] | (tm[6] << 8);
            u16 e3 = tm[7] | (tm[8] << 8);

            u16 palbits = (u16)pal << 10;
            u32 base = (u32)(vy * 2) * 32 + vx * 2;

            viewport[base] = e0 | palbits;
            viewport[base + 1] = e1 | palbits;
            viewport[base + 32] = e2 | palbits;
            viewport[base + 33] = e3 | palbits;
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

    // Load tile graphics (4bpp) + 8x16-color palette into VRAM/CGRAM
    bgInitTileSet(0, &patterns, &palette, 0,
                  (&patterns_end - &patterns), (&palette_end - &palette),
                  BG_16COLORS, 0x4000);

    // Init background map on layer 0 at VRAM 0xA000
    bgInitMapSet(0, (u8 *)viewport, 2048, SC_32x32, 0xA000);

    // Avatar sprite: 2KB gfx at VRAM 0x0000, palette at CGRAM 128
    oamInitGfxSet(&avatar_gfx, (&avatar_gfx_end - &avatar_gfx),
                  &avatar_pal, (&avatar_pal_end - &avatar_pal),
                  0, 0x0000, OBJ_SIZE16_L32);

    // Mode 1 (16 colors), only layer 0 active
    setMode(BG_MODE1, 0);
    bgSetDisable(1);
    bgSetDisable(2);
    setScreenOn();

    // Initial render: camera centered on the avatar
    cam_x = (av_x - 8) & 1023;
    cam_y = (av_y - 7) & 1023;
    render_viewport();
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