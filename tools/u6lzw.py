#!/usr/bin/env python3
"""Port of NuVIE's U6Lzw decoder (from files/U6Lzw.cpp) — verifies MAPTILES.VGA format."""
import sys

class U6Lzw:
    def __init__(self):
        self.dict_root = [0] * 10000
        self.dict_codeword = [0] * 10000
        self.dict_contains = 0x102
        self.stack = [0] * 10000
        self.stack_contains = 0

    def reset_dict(self):
        self.dict_contains = 0x102

    def add_dict(self, root, codeword):
        self.dict_root[self.dict_contains] = root
        self.dict_codeword[self.dict_contains] = codeword
        self.dict_contains += 1

    def get_root(self, codeword):
        return self.dict_root[codeword]

    def get_codeword(self, codeword):
        return self.dict_codeword[codeword]

    def push(self, element):
        self.stack[self.stack_contains] = element
        self.stack_contains += 1

    def pop(self):
        self.stack_contains -= 1
        return self.stack[self.stack_contains]

    def gettop(self):
        return self.stack[self.stack_contains - 1]

    def get_string(self, codeword):
        self.stack_contains = 0
        while codeword > 0xff:
            root = self.get_root(codeword)
            codeword = self.get_codeword(codeword)
            self.push(root)
        self.push(codeword)

    def is_valid(self, buf):
        if len(buf) < 6:
            return False
        if buf[3] != 0:
            return False
        if buf[4] != 0 or (buf[5] & 1) != 1:
            return False
        return True

    def get_next_codeword(self, source, bits_read, codeword_size):
        br = bits_read[0]
        b0 = source[br // 8]
        b1 = source[br // 8 + 1]
        if codeword_size + (br % 8) > 16:
            b2 = source[br // 8 + 2]
        else:
            b2 = 0
        codeword = (b2 << 16) + (b1 << 8) + b0
        codeword = codeword >> (br % 8)
        masks = {9: 0x1ff, 10: 0x3ff, 11: 0x7ff, 12: 0xfff}
        codeword &= masks[codeword_size]
        bits_read[0] += codeword_size
        return codeword

    def decompress(self, source):
        if not self.is_valid(source):
            return None
        uncomp_size = source[0] + (source[1] << 8) + (source[2] << 16) + (source[3] << 24)
        dest = bytearray(uncomp_size)
        max_codeword_length = 12
        end_marker_reached = False
        codeword_size = 9
        bits_read = [0]
        next_free_codeword = 0x102
        dictionary_size = 0x200
        bytes_written = 0
        source = source[4:]  # skip filesize dword
        pW = 0
        while not end_marker_reached:
            cW = self.get_next_codeword(source, bits_read, codeword_size)
            if cW == 0x100:
                codeword_size = 9
                next_free_codeword = 0x102
                dictionary_size = 0x200
                self.dict_contains = 0x102
                cW = self.get_next_codeword(source, bits_read, codeword_size)
                dest[bytes_written] = cW & 0xff
                bytes_written += 1
            elif cW == 0x101:
                end_marker_reached = True
            else:
                if cW < next_free_codeword:
                    self.get_string(cW)
                    C = self.gettop()
                    while self.stack_contains > 0:
                        dest[bytes_written] = self.pop()
                        bytes_written += 1
                    self.add_dict(C, pW)
                    next_free_codeword += 1
                    if next_free_codeword >= dictionary_size:
                        if codeword_size < max_codeword_length:
                            codeword_size += 1
                            dictionary_size *= 2
                else:
                    self.get_string(pW)
                    C = self.gettop()
                    while self.stack_contains > 0:
                        dest[bytes_written] = self.pop()
                        bytes_written += 1
                    dest[bytes_written] = C
                    bytes_written += 1
                    if cW != next_free_codeword:
                        print("ERROR: cW != next_free_codeword")
                        return None
                    self.add_dict(C, pW)
                    next_free_codeword += 1
                    if next_free_codeword >= dictionary_size:
                        if codeword_size < max_codeword_length:
                            codeword_size += 1
                            dictionary_size *= 2
            pW = cW
        return bytes(dest[:bytes_written])


if __name__ == "__main__":
    with open("MAPTILES.VGA", "rb") as f:
        data = f.read()
    print(f"MAPTILES.VGA on-disk size: {len(data)}")
    print(f"Header (first 8 bytes): {' '.join(f'{b:02X}' for b in data[:8])}")
    print(f"  => LZW valid: {U6Lzw().is_valid(data)}")
    lzw = U6Lzw()
    out = lzw.decompress(data)
    if out is None:
        print("DECOMPRESSION FAILED")
        sys.exit(1)
    print(f"Decompressed size: {len(out)} bytes (header claims {data[0] + (data[1]<<8) + (data[2]<<16)})")
    print(f"  /256 per tile = {len(out)/256:.2f} tiles, /32 = {len(out)/32:.2f}, /64 = {len(out)/64:.2f}")
    # Tile 0 from TILEINDX
    with open("TILEINDX.VGA", "rb") as f:
        tind = f.read()
    print(f"\nTILEINDX.VGA size: {len(tind)} ({len(tind)//2} entries)")
    off0 = int.from_bytes(tind[0:2], "little") * 16
    off1 = int.from_bytes(tind[2:4], "little") * 16
    print(f"tile 0 offset: {off0}, tile 1 offset: {off1} (delta {off1-off0})")
    print(f"tile 0 first 32 bytes: {' '.join(f'{b:02X}' for b in out[off0:off0+32])}")
    print(f"tile 0 unique colors: {len(set(out[off0:off0+256]))}")
    # last tile referenced
    maxoff = max(int.from_bytes(tind[i:i+2], "little") * 16 for i in range(0, len(tind), 2))
    print(f"max tile offset: {maxoff} (decompressed size {len(out)}, {'OK' if maxoff+256 <= len(out) else 'OVERFLOW'})")