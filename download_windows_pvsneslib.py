#!/usr/bin/env python3
"""
Download correct Windows release of PVSnesLib.
"""

import os
import urllib.request
import json
import zipfile
import shutil

def main():
    repo = "alekmaul/pvsneslib"
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    
    print("Fetching release info from GitHub...")
    req = urllib.request.Request(api_url, headers={"User-Agent": "Python-Script"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    # Find Windows asset zip (ensuring it's not darwin/mac)
    target_asset = None
    for asset in data.get("assets", []):
        name = asset["name"].lower()
        if ("win" in name or "windows" in name) and "darwin" not in name and "mac" not in name and name.endswith(".zip"):
            target_asset = asset
            break

    if not target_asset:
        print("Error: Could not find Windows zip asset in release!")
        for asset in data.get("assets", []):
            print("  Available asset:", asset["name"])
        return

    download_url = target_asset["browser_download_url"]
    filename = target_asset["name"]
    temp_zip = os.path.join(os.environ["TEMP"], filename)

    print(f"Downloading {filename} from {download_url}...")
    urllib.request.urlretrieve(download_url, temp_zip)

    pvs_base = r"D:\pvsneslib"
    if os.path.exists(pvs_base):
        print(f"Cleaning existing {pvs_base}...")
        shutil.rmtree(pvs_base)
    os.makedirs(pvs_base, exist_ok=True)

    print(f"Extracting {filename} to {pvs_base}...")
    extract_temp = os.path.join(os.environ["TEMP"], "pvs_extract")
    if os.path.exists(extract_temp):
        shutil.rmtree(extract_temp)

    with zipfile.ZipFile(temp_zip, 'r') as zf:
        zf.extractall(extract_temp)

    items = os.listdir(extract_temp)
    if len(items) == 1 and os.path.isdir(os.path.join(extract_temp, items[0])):
        source_dir = os.path.join(extract_temp, items[0])
    else:
        source_dir = extract_temp

    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(pvs_base, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)

    print("Windows PVSnesLib successfully installed to D:\\pvsneslib!")

if __name__ == "__main__":
    main()
