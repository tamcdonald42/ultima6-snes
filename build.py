#!/usr/bin/env python3
"""
Ultima 6 SNES Build Script (Real Map Render)
---------------------------------------------
0. Runs tools/convert_u6.py (LZW-corrected tile/palette/tilemap conversion)
1. Compiles main.c -> main.ps (816-tcc)
2. Optimizes main.ps -> main.asm (816-opt)
3. Assembles main.asm -> main.obj (wla-65816)
4. Assembles data.asm -> data.obj (wla-65816)
5. Assembles hdr.asm -> hdr.obj (wla-65816)
6. Links objects -> ultima6_snes.sfc (wlalink)
"""

import os
import subprocess
import sys

def run_cmd(cmd):
    print(f">> {cmd}")
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"Error executing command: {cmd}", file=sys.stderr)
        sys.exit(res.returncode)

def main():
    # Project dir = this script's location (works whether on D:\ or C:\)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    pvsneslib_home = r"D:\pvsneslib"
    bin_dir = os.path.join(pvsneslib_home, "devkitsnes", "bin")
    tools_dir = os.path.join(pvsneslib_home, "devkitsnes", "tools")
    include_dir = os.path.join(pvsneslib_home, "pvsneslib", "include")
    dev_include = os.path.join(pvsneslib_home, "devkitsnes", "include")

    tcc = os.path.join(bin_dir, "816-tcc.exe")
    opt = os.path.join(tools_dir, "816-opt.exe")
    wla = os.path.join(bin_dir, "wla-65816.exe")
    wlalink = os.path.join(bin_dir, "wlalink.exe")

    main_c = os.path.join(project_dir, "src", "main.c")
    main_ps = os.path.join(project_dir, "src", "main.ps")
    main_asm = os.path.join(project_dir, "src", "main.asm")
    main_obj = os.path.join(project_dir, "src", "main.obj")

    data_asm = os.path.join(project_dir, "src", "data.asm")
    data_obj = os.path.join(project_dir, "src", "data.obj")

    hdr_asm = os.path.join(project_dir, "hdr.asm")
    hdr_obj = os.path.join(project_dir, "hdr.obj")

    linkfile = os.path.join(project_dir, "linkfile")
    output_rom = os.path.join(project_dir, "ultima6_snes.sfc")

    # 0. Convert tiles & palette (LZW-corrected)
    print("Step 0: Converting Ultima 6 tiles & palette (LZW)...")
    run_cmd(f'python "{os.path.join(project_dir, "tools", "convert_u6.py")}"')

    # 1. Compile main.c to main.ps
    print("Step 1: Compiling main.c -> main.ps")
    run_cmd(f'"{tcc}" -I"{include_dir}" -I"{dev_include}" -I"{project_dir}" -Wall -c "{main_c}" -o "{main_ps}"')

    # 2. Optimize main.ps to main.asm
    print("Step 2: Optimizing main.ps -> main.asm")
    run_cmd(f'"{opt}" -i "{main_ps}" -o "{main_asm}"')

    # 3. Assemble main.asm to main.obj
    print("Step 3: Assembling main.asm -> main.obj")
    run_cmd(f'"{wla}" -d -s -x -o "{main_obj}" "{main_asm}"')

    # 4. Assemble data.asm to data.obj
    print("Step 4: Assembling data.asm -> data.obj")
    os.chdir(os.path.join(project_dir, "src"))
    run_cmd(f'"{wla}" -d -s -x -o "data.obj" "data.asm"')
    os.chdir(project_dir)

    # 5. Assemble hdr.asm to hdr.obj
    print("Step 5: Assembling hdr.asm -> hdr.obj")
    run_cmd(f'"{wla}" -d -s -x -o "{hdr_obj}" "{hdr_asm}"')

    # 6. Link objects into ROM
    print("Step 6: Linking ROM...")
    run_cmd(f'"{wlalink}" -d -s -v -A -c -L D:/pvsneslib/pvsneslib/lib/LoROM_SlowROM "{linkfile}" "{output_rom}"')

    print(f"\nSUCCESS! Built Ultima 6 map render ROM: {output_rom}")

if __name__ == "__main__":
    main()