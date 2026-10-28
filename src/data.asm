.include "../hdr.asm"

.section ".rodata1" superfree

patterns:
.incbin "ultima_tiles.pic"
patterns_end:

.ends

.section ".rodata2" superfree

palette:
.incbin "ultima_tiles.pal"
palette_end:

.ends

.section ".rodata3" superfree

tilemap:
.incbin "ultima_tilemap.bin"
tilemap_end:

.ends

.section ".rodata4" superfree

map_data:
.incbin "../U6/MAP"
map_data_end:

.ends

; CHUNKS is 65536 bytes: split into two 32KB sections (LoROM bank window is 32KB)
.section ".rodata5" superfree

chunk_data_a:
.incbin "chunks_a.bin"
chunk_data_a_end:

.ends

.section ".rodata6" superfree

chunk_data_b:
.incbin "chunks_b.bin"
chunk_data_b_end:

.ends

; Collision flags: 2048 tiles x 1 byte (flags1: bit0=water, bit1=impassable)
.section ".rodata7" superfree

tileflag:
.incbin "tileflag.bin"
tileflag_end:

.ends

; Avatar sprite: 16 frames (4 dirs x 4 walk frames), 16x16 = 4 SNES 8x8 tiles each.
; OAM layout: frame f at tile (f&7)*2 + (f>>3)*32, tiles n,n+1,n+16,n+17.
.section ".rodata8" superfree

avatar_gfx:
.incbin "avatar.pic"
avatar_gfx_end:

.ends

.section ".rodata9" superfree

avatar_pal:
.incbin "avatar.pal"
avatar_pal_end:

.ends