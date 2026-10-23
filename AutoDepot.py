import os
import json
import shutil
import hashlib
import requests
import re
import struct
import zlib
import zipfile
import subprocess
import sys
from pathlib import Path
 
# --- CONFIGURATION ---
API_BASE_URL = "https://hubcapmanifest.com/api/v1"
SETTINGS_FILE = "settings.json"
TEMP_DIR = Path("temp_depot_data")
KEYS_FILE = "keys.txt"
EXE_NAME = "DepotDownloaderMod.exe"  # Change this if your file name is different
REDIST_DEPOT_RANGE = (228980, 229100)  # Steamworks Common Redistributables depots
 
# Headers (User-Agent is important)
HEADERS = {
    "User-Agent": "GreenLumaManager/1.0"
}
 
def clean_exit(msg):
    print(f"\n[!] {msg}")
    input("Press Enter to exit...")
    sys.exit()
 
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}
 
def save_setting(key, value):
    data = load_settings()
    data[key] = value
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f)
 
def get_api_key():
    """API Key check and retrieval process."""
    data = load_settings()
    api_key = data.get("api_key", "")
 
    if not api_key:
        print("\n⚠️ API Key not found (Morrenus API).")
        while True:
            new_key = input("Please enter API Key: ").strip()
            if len(new_key) > 5:
                save_setting("api_key", new_key)
                return new_key
            print("❌ Invalid key.")
    return api_key
 
def get_install_dir(app_id):
    """Install folder per AppID. Reusing the same folder lets DepotDownloader
    only fetch changed chunks instead of the whole game.
    Returns None to use the default DepotDownloader folder (full download)."""
    data = load_settings()
    install_dirs = data.get("install_dirs", {})
    saved = install_dirs.get(str(app_id))

    if saved:
        print(f"[*] Install folder: {saved}")
        answer = input("    Enter to keep, type a new path, or 'none' for default folder: ").strip().strip('"')
        if not answer:
            return saved
        if answer.lower() == "none":
            install_dirs.pop(str(app_id), None)
            save_setting("install_dirs", install_dirs)
            return None
    else:
        print("\n📁 Existing game folder (to only download changed files)?")
        answer = input("   Path (Enter to skip and use default folder): ").strip().strip('"')
        if not answer:
            return None

    install_dirs[str(app_id)] = answer
    save_setting("install_dirs", install_dirs)
    return answer
 
def is_redist_depot(depot_id):
    """Steamworks Common Redistributables (_CommonRedist: VC++, DirectX, .NET...)."""
    return REDIST_DEPOT_RANGE[0] <= int(depot_id) <= REDIST_DEPOT_RANGE[1]

def filter_redist(manifest_files):
    redist = [m for m in manifest_files
              if re.match(r"^\d+_", m) and is_redist_depot(m.split("_")[0])]
    if not redist:
        return manifest_files

    print(f"\n[*] Found {len(redist)} common redist depot(s) (_CommonRedist folder):")
    for m in redist:
        print(f"    - {m}")
    answer = input("    Skip them? [Y/n]: ").strip().lower()
    if answer in ("n", "no"):
        return manifest_files
    return [m for m in manifest_files if m not in redist]

def check_exe():
    if not os.path.exists(EXE_NAME):
        clean_exit(f"Error: {EXE_NAME} not found in this folder!")
 
def download_and_extract(app_id):
    url = f"{API_BASE_URL}/manifest/{app_id}"
 
    if TEMP_DIR.exists():
        try:
            shutil.rmtree(TEMP_DIR)
        except:
            pass
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
 
    print(f"[*] Downloading data from API... ({app_id})")
 
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=30)
 
        if r.status_code == 401 or r.status_code == 403:
            print("⛔ ERROR: API Key invalid or expired.")
            # Reset key
            save_setting("api_key", "")
            clean_exit("Please restart the script and enter a new key.")
        elif r.status_code == 404:
            clean_exit("❌ This game was not found in the API database.")
 
        r.raise_for_status()
 
        zip_path = TEMP_DIR / "data.zip"
        with open(zip_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
 
        print("[*] Extracting archive...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(TEMP_DIR)
 
        return True
    except Exception as e:
        clean_exit(f"Download/Extraction error: {e}")
 
def parse_keys_and_prepare():
    print("[*] Extracting Keys from Lua files...")
 
    keys = {}
    lua_files = list(TEMP_DIR.glob("*.lua"))
 
    if not lua_files:
        print("⚠️ Warning: No Lua files found, keys might be missing.")
    else:
        # Scan all lua files (otoas.py logic)
        for lua_file in lua_files:
            with open(lua_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Regex logic inside otoas.py
                matches = re.findall(r'addappid\((\d+),\s*\d+,\s*"([A-Za-z0-9]+)"\)', content)
                if not matches:
                    matches = re.findall(r'\[(\d+)\]\s*=\s*"([A-Za-z0-9]+)"', content)
 
                for depot_id, key in matches:
                    keys[depot_id] = key
 
    # Create Keys.txt
    if keys:
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            for depot_id, key in keys.items():
                f.write(f"{depot_id};{key}\n")
        print(f"✔ keys.txt created ({len(keys)} keys).")
    else:
        print("⚠️ No keys found. Download might fail.")
 
    # Move manifests to main directory
    manifests = list(TEMP_DIR.glob("*.manifest"))
    local_manifests = []
 
    for m in manifests:
        target = Path(m.name) # Copy to main directory
        shutil.copy(str(m), str(target))
        local_manifests.append(target.name)
 
    print(f"✔ {len(local_manifests)} manifest files prepared.")
    return local_manifests
 
# --- UPDATE SUPPORT ---
# DepotDownloaderMod treats the -manifestfile manifest as the "previous" version
# too, so on its own it skips every existing file without checking it. To update,
# we find the changed files ourselves (manifest diff, or hashing local files when
# the installed version is unknown) and pass only those via -filelist. Two methods:
#   patch      - -validate: downloads only changed chunks, but the downloader keeps
#                the old copy of each file while rebuilding it (needs extra space)
#   redownload - delete the changed files first, then download them in full

def _varint(b, i):
    result = shift = 0
    while True:
        x = b[i]
        i += 1
        result |= (x & 0x7F) << shift
        shift += 7
        if x < 0x80:
            return result, i

def _proto_fields(b):
    i = 0
    while i < len(b):
        tag, i = _varint(b, i)
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value, i = _varint(b, i)
        elif wire == 2:
            n, i = _varint(b, i)
            value = b[i:i + n]
            i += n
        elif wire == 5:
            value = b[i:i + 4]
            i += 4
        elif wire == 1:
            value = b[i:i + 8]
            i += 8
        else:
            raise ValueError("Unknown protobuf wire type")
        yield field, value

def read_manifest_files(path):
    """Returns {filename: {"sha", "size", "chunks", "layout"}} for a Steam .manifest,
    or None if it can't be read (e.g. encrypted filenames).
    chunks = {chunk_sha: compressed_size}, layout = [(chunk_sha, offset, length)]."""
    try:
        data = Path(path).read_bytes()
        files, encrypted, i = {}, False, 0
        while i + 8 <= len(data):
            magic, size = struct.unpack_from("<II", data, i)
            section = data[i + 8:i + 8 + size]
            i += 8 + size
            if magic == 0x71F617D0:  # Payload: file list
                for field, value in _proto_fields(section):
                    if field != 1:
                        continue
                    entry, chunks, layout = {}, {}, []
                    for f, v in _proto_fields(value):
                        if f == 6:
                            chunk = dict(_proto_fields(v))
                            sha = chunk.get(1, b"").hex()
                            chunks[sha] = chunk.get(5, 0)
                            layout.append((sha, chunk.get(3, 0), chunk.get(4, 0)))
                        else:
                            entry[f] = v
                    if entry.get(3, 0) & 0x40:  # Directory
                        continue
                    name = entry[1].decode("utf-8").replace("\\", "/")
                    files[name] = {"sha": entry.get(5, b"").hex(), "size": entry.get(2, 0),
                                   "chunks": chunks, "layout": layout}
            elif magic == 0x1F4812BE:  # Metadata
                encrypted = bool(dict(_proto_fields(section)).get(4, 0))
            else:
                break
        return None if encrypted else files
    except Exception:
        return None

def state_dir(install_dir):
    return Path(install_dir) / ".DepotDownloader" / "autodepot"

def load_installed(install_dir):
    try:
        with open(state_dir(install_dir) / "installed.json", "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_installed(install_dir, depot_id, manifest_file):
    folder = state_dir(install_dir)
    folder.mkdir(parents=True, exist_ok=True)
    installed = load_installed(install_dir)
    old = installed.get(depot_id)
    shutil.copy(manifest_file, folder / Path(manifest_file).name)
    if old and old != Path(manifest_file).name:
        (folder / old).unlink(missing_ok=True)
    installed[depot_id] = Path(manifest_file).name
    with open(folder / "installed.json", "w") as f:
        json.dump(installed, f, indent=2)

def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def differs(path, info, check_hash):
    if not path.is_file() or path.stat().st_size != info["size"]:
        return True
    return check_hash and file_sha1(path) != info["sha"]

def same_file(a, b):
    return a is not None and (a["sha"], a["size"]) == (b["sha"], b["size"])

def chunk_match(path, info, samples=64):
    """Fraction of a sample of the file's chunks that are already on disk at their offset."""
    if info is None or not info["layout"] or not path.is_file():
        return 0.0
    layout = info["layout"]
    picked = layout[::max(1, len(layout) // samples)]
    matched = 0
    with open(path, "rb") as f:
        for sha, offset, length in picked:
            f.seek(offset)
            matched += hashlib.sha1(f.read(length)).hexdigest() == sha
    return matched / len(picked)

def plan_update(install_dir, depot_id, manifest_file):
    """Returns None if already up to date, else a dict with the changed/removed
    files (both None if the manifest can't be read). Changed files are split into:
      patch  - still the old version: diff against the installed manifest
      resume - (partly) new already, or no old version: check in place against the
               new manifest (e.g. after an interrupted update)"""
    installed = load_installed(install_dir).get(depot_id)
    if installed == Path(manifest_file).name:
        return None

    plan = {"changed": None, "removed": None, "old": None, "installed": installed,
            "new": read_manifest_files(manifest_file), "patch": set(), "resume": {}}
    if plan["new"] is None:
        return plan

    plan["old"] = read_manifest_files(state_dir(install_dir) / installed) if installed else None
    root = Path(install_dir)
    staging = root / ".DepotDownloader" / "staging"
    new, old = plan["new"], plan["old"]

    if old is not None:
        # Known installed version: changed in the manifest, or missing/wrong size locally
        plan["changed"] = [f for f, info in new.items()
                           if not same_file(old.get(f), info) or differs(root / f, info, False)]
        plan["removed"] = [f for f in old if f not in new]
        for f in plan["changed"]:
            # Old copy left in staging by an interrupted patch counts as the old version
            old_match = max(chunk_match(p, old.get(f)) for p in (root / f, staging / f))
            new_match = chunk_match(root / f, new[f])
            if old_match > new_match:
                plan["patch"].add(f)
            else:
                plan["resume"][f] = new_match
        return plan

    # Unknown installed version: compare every local file with the new manifest
    print("[*] No record of the installed version: checking every file (slow once)...")
    plan["changed"] = []
    for n, (f, info) in enumerate(new.items(), 1):
        print(f"    [{n}/{len(new)}] {f}", end="\r")
        if differs(root / f, info, True):
            plan["changed"].append(f)
            plan["resume"][f] = chunk_match(root / f, info)
    print()
    plan["removed"] = []
    return plan

def gb(n):
    return f"{n / 1024 ** 3:.2f} GB"

def local_size(install_dir, f):
    root = Path(install_dir)
    staging = root / ".DepotDownloader" / "staging"
    return sum(p.stat().st_size for p in (root / f, staging / f) if p.is_file())

def choose_method(install_dir, plan):
    """Shows download size and space needed for both methods. Returns "patch" or "redownload"."""
    new, old = plan["new"], plan["old"]

    full_download = sum(sum(new[f]["chunks"].values()) for f in plan["changed"])
    patch_download = 0
    for f in plan["patch"]:
        patch_download += sum(size for sha, size in new[f]["chunks"].items() if sha not in old[f]["chunks"])
    for f, matched in plan["resume"].items():
        patch_download += (1 - matched) * sum(new[f]["chunks"].values())
    # Patching keeps the old copy next to the new one; resuming fills the file in place
    patch_space = sum(new[f]["size"] for f in plan["patch"])
    patch_space += sum(max(0, new[f]["size"] - local_size(install_dir, f)) for f in plan["resume"])
    redownload_space = max(0, sum(new[f]["size"] for f in plan["changed"])
                           - sum(local_size(install_dir, f) for f in plan["changed"]))
    free = shutil.disk_usage(install_dir).free

    def fits(space):
        return "" if space <= free else "  ⚠️ not enough free space"

    if plan["resume"] and old is not None:
        print(f"    ({len(plan['resume'])} file(s) already partly updated, will resume them)")
    print(f"\n    Free space on drive: {gb(free)}")
    # Resumed files are estimated from a sample of chunks, so the real size can differ
    approx = " (approximate)" if plan["resume"] else ""
    print(f"    1) Patch       - download ~{gb(patch_download)}{approx}, needs up to {gb(patch_space)} free{fits(patch_space)}")
    print(f"    2) Re-download - download ~{gb(full_download)}, needs ~{gb(redownload_space)} free{fits(redownload_space)}")
    default = "1" if patch_space <= free else "2"
    if approx:
        print("    (approximate) = estimated from a sample of the files, the actual download may be larger or smaller")
    while True:
        answer = input(f"    Choose method [1/2] (Enter = {default}): ").strip() or default
        if answer in ("1", "2"):
            return "patch" if answer == "1" else "redownload"

def _encode_varint(n):
    out = bytearray()
    while True:
        out.append((n & 0x7F) | (0x80 if n > 0x7F else 0))
        n >>= 7
        if not n:
            return bytes(out)

def seed_patch_cache(install_dir, depot_id, manifest_file, plan, use_old):
    """Puts the manifests in DepotDownloader's own cache and sets depot.config.
    Run without -manifestfile, the downloader then loads them from disk:
      use_old=True  - installed version recorded: diffs old vs new by chunk ID
      use_old=False - no installed version: checks each file in place
    (with -manifestfile it only reuses chunks at unchanged offsets)."""
    config_dir = Path(install_dir) / ".DepotDownloader"
    sources = [Path(manifest_file)]
    if use_old:
        sources.append(state_dir(install_dir) / plan["installed"])
    for src in sources:
        shutil.copy(src, config_dir / src.name)
        (config_dir / (src.name + ".sha")).write_bytes(hashlib.sha1(src.read_bytes()).digest())

    config_file = config_dir / "depot.config"
    installed = {}
    try:
        for _, entry in _proto_fields(zlib.decompress(config_file.read_bytes(), -15)):
            fields = dict(_proto_fields(entry))
            installed[fields.get(1, 0)] = fields.get(2, 0)
    except Exception:
        pass
    if use_old:
        installed[int(depot_id)] = int(plan["installed"].split("_")[1].split(".")[0])
    else:
        installed.pop(int(depot_id), None)
    data = b""
    for depot, manifest in installed.items():
        entry = b"\x08" + _encode_varint(depot) + b"\x10" + _encode_varint(manifest)
        data += b"\x0a" + _encode_varint(len(entry)) + entry
    compressor = zlib.compressobj(wbits=-15)
    config_file.write_bytes(compressor.compress(data) + compressor.flush())

def clean_patch_cache(install_dir, keep_manifest):
    config_dir = Path(install_dir) / ".DepotDownloader"
    for f in config_dir.glob("*.manifest*"):
        if not f.name.startswith(Path(keep_manifest).name):
            f.unlink(missing_ok=True)

def prepare_files(install_dir, plan, method):
    """Deletes removed files; for redownload also deletes the changed files.
    Leftovers of an interrupted patch (old copy in staging) are restored or removed."""
    root = Path(install_dir)
    staging = root / ".DepotDownloader" / "staging"
    for f in plan["removed"]:
        (staging / f).unlink(missing_ok=True)
        if (root / f).is_file():
            (root / f).unlink()
            print(f"    Deleted {f}")
    for f in plan["changed"]:
        leftover = staging / f
        if method == "patch" and f in plan["patch"]:
            if leftover.is_file():
                os.replace(leftover, root / f)  # Old full copy is a better base than a partial file
                print(f"    Restored old copy of {f}")
        else:
            leftover.unlink(missing_ok=True)
            if method == "redownload" and (root / f).is_file():
                (root / f).unlink()
                print(f"    Deleted {f}")

def run_cmd(cmd):
    try:
        # Run exe with subprocess
        exe = Path(cmd[0]).resolve()  # Full path: not every shell searches the current folder
        return subprocess.run([str(exe)] + cmd[1:], check=False).returncode
    except Exception as e:
        print(f"❌ Execution error: {e}")
        return -1

def run_depot_downloader(app_id, manifest_files, install_dir):
    print("\n🚀 Starting DepotDownloaderMod...")

    # Decode DepotID and ManifestID from manifest filename:
    # Format usually: DepotID_ManifestID.manifest

    for manifest_file in manifest_files:
        match = re.match(r"^(\d+)_(\d+)\.manifest$", manifest_file)
        if not match:
            print(f"⚠️ Filename format unrecognized, skipping: {manifest_file}")
            continue

        depot_id = match.group(1)
        manifest_id = match.group(2)

        print(f"\n>>> Downloading: Depot {depot_id} (Manifest: {manifest_id})")

        base_cmd = [
            EXE_NAME,
            "-app", str(app_id),
            "-depot", str(depot_id),
            "-manifest", str(manifest_id),
            "-depotkeys", KEYS_FILE,
            "-max-downloads", "16" # For speed
        ]
        manifest_args = ["-manifestfile", manifest_file]

        if not install_dir:
            run_cmd(base_cmd + manifest_args)
            continue

        base_cmd += ["-dir", install_dir]  # Same folder every time = delta update
        plan = plan_update(install_dir, depot_id, manifest_file)

        if plan is None:
            print("✔ Already up to date, skipping.")
            continue

        # Each run: (files, use old manifest?) - None = plain -manifestfile run
        runs = []
        if plan["changed"] is None:
            print("[*] Can't read manifest file names, letting DepotDownloader validate every file.")
            runs.append((None, ["-validate"]))
        else:
            print(f"[*] Update: {len(plan['changed'])} changed/new file(s), {len(plan['removed'])} removed.")
            method = choose_method(install_dir, plan) if plan["changed"] else "redownload"
            prepare_files(install_dir, plan, method)
            if method == "redownload":
                runs.append((plan["changed"], None))
            else:
                runs.append((sorted(plan["patch"]), True))
                runs.append((sorted(plan["resume"]), False))

        ok = True
        for n, (files, mode) in enumerate(runs):
            if files is not None and not files:
                continue
            cmd = list(base_cmd)
            if files is None:
                cmd += manifest_args + mode
            else:
                filelist = TEMP_DIR / f"filelist_{depot_id}_{n}.txt"
                filelist.write_text("\n".join(files), encoding="utf-8")
                cmd += ["-filelist", str(filelist)]
                if mode is None:
                    cmd += manifest_args  # Files were deleted: plain download
                else:
                    seed_patch_cache(install_dir, depot_id, manifest_file, plan, use_old=mode)
                    cmd += ["-validate"]  # Manifests come from the cache, check chunk by chunk
                print(f"\n[*] {'Patching' if mode else 'Resuming' if mode is False else 'Downloading'} "
                      f"{len(files)} file(s)...")
            code = run_cmd(cmd)
            if code != 0:
                ok = False
                print(f"❌ Depot {depot_id} failed (exit code {code}). Run again to retry.")
                break

        if ok:
            save_installed(install_dir, depot_id, manifest_file)
            clean_patch_cache(install_dir, manifest_file)
            if plan["changed"] == []:
                print("✔ No file changes to download.")

def main():
    print(f"### {EXE_NAME} Automation Script (Morrenus API) ###")
    check_exe()
 
    # API Key Management
    api_key = get_api_key()
    HEADERS["X-API-Key"] = api_key
 
    while True:
        app_id_input = input("\nAppID of the game you want to download (Exit: q): ").strip()
        if app_id_input.lower() == 'q':
            break
 
        if not app_id_input.isdigit():
            print("Enter a valid number.")
            continue
 
        install_dir = get_install_dir(app_id_input)
 
        # 1. Download and Extract
        download_and_extract(app_id_input)
 
        # 2. Prepare Keys and Manifests
        manifest_list = filter_redist(parse_keys_and_prepare())

        if not manifest_list:
            print("❌ No manifest file found to download.")
            continue
 
        # 3. Start Downloader
        run_depot_downloader(app_id_input, manifest_list, install_dir)
 
        print(f"\n✅ Operations completed for {app_id_input}.")
        print(f"📁 Game files are in '{install_dir or 'depots'}'.")
 
        # Cleanup
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR)
 
if __name__ == "__main__":
    main()