.include "../hdr.asm"

; Terrain subtiles (750) - resident in VRAM at boot
.section ".rodata1" superfree

patterns:
.incbin "tiles_terrain.bin"
patterns_end:

.ends

; Object subtiles (4971) - streamed into a VRAM cache. 4 x 32KB banks + tail.
.section ".rodata2" superfree

obj_pic_0:
.incbin "tiles_obj_0.bin"
obj_pic_0_end:

.ends

.section ".rodata3" superfree

obj_pic_1:
.incbin "tiles_obj_1.bin"
obj_pic_1_end:

.ends

.section ".rodata4" superfree

obj_pic_2:
.incbin "tiles_obj_2.bin"
obj_pic_2_end:

.ends

.section ".rodata5" superfree

obj_pic_3:
.incbin "tiles_obj_3.bin"
obj_pic_3_end:

.ends

.section ".rodata6" superfree

obj_pic_4:
.incbin "tiles_obj_4.bin"
obj_pic_4_end:

.ends

.section ".rodata7" superfree

palette:
.incbin "ultima_tiles.pal"
palette_end:

.ends

.section ".rodata8" superfree

tilemap:
.incbin "ultima_tilemap.bin"
tilemap_end:

.ends

; Composite table: 2541 x [pal u8 + 4x u16 subtile ids]
.section ".rodata9" superfree

comptab:
.incbin "comptab.bin"
comptab_end:

.ends

; Object map: 36735B -> split at 32KB
.section ".rodata10" superfree

objmap_a:
.incbin "objmap_a.bin"
objmap_a_end:

.ends

.section ".rodata11" superfree

objmap_b:
.incbin "objmap_b.bin"
objmap_b_end:

.ends

.section ".rodata12" superfree

objmap_idx:
.incbin "objmap_idx.bin"
objmap_idx_end:

.ends

.section ".rodata13" superfree

map_data:
.incbin "../U6/MAP"
map_data_end:

.ends

; CHUNKS is 65536 bytes: split into two 32KB sections (LoROM bank window is 32KB)
.section ".rodata14" superfree

chunk_data_a:
.incbin "chunks_a.bin"
chunk_data_a_end:

.ends

.section ".rodata15" superfree

chunk_data_b:
.incbin "chunks_b.bin"
chunk_data_b_end:

.ends

; Collision flags: 2048 tiles x 1 byte (flags1: bit0=water, bit1=impassable)
.section ".rodata16" superfree

tileflag:
.incbin "tileflag.bin"
tileflag_end:

.ends

; Avatar sprite: 16 frames (4 dirs x 4 walk frames), 16x16 = 4 SNES 8x8 tiles each.
; OAM layout: frame f at tile (f&7)*2 + (f>>3)*32, tiles n,n+1,n+16,n+17.
.section ".rodata17" superfree

avatar_gfx:
.incbin "avatar.pic"
avatar_gfx_end:

.ends

.section ".rodata18" superfree

avatar_pal:
.incbin "avatar.pal"
avatar_pal_end:

.ends