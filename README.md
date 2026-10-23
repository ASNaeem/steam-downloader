# Steam Depot Downloader

`AutoDepot.py` downloads Steam game files with `DepotDownloaderMod.exe`, using manifests and depot keys from the Morrenus API (hubcapmanifest.com).

It can also **update an existing install by downloading only the changed files**, and it can skip the common redistributable depots (`_CommonRedist`).

## Requirements

- Windows
- [Python 3](https://www.python.org/downloads/) with `requests`:
  ```
  pip install requests
  ```
- [.NET 9 Runtime](https://dotnet.microsoft.com/download/dotnet/9.0) (or newer), for `DepotDownloaderMod.exe`
- An API key from https://hubcapmanifest.com

Keep `AutoDepot.py` in the same folder as `DepotDownloaderMod.exe` and its `.dll` files.

## Usage

Run the script from this folder:

```
python AutoDepot.py
```

1. **API key:** on the first run you're asked for your API key. It's saved in `settings.json`. If the key becomes invalid, it's cleared and you're asked again on the next run.
2. **AppID:** enter the game's Steam AppID. You can find it in the store URL, for example `store.steampowered.com/app/570/` → `570`. Enter `q` to quit.
3. **Install folder** (see [Updating a game](#updating-a-game-changed-files-only)):
   - **Press Enter to skip:** this is a full download into the default `depots` folder.
   - **Type a folder path:** the files are downloaded into that folder, or an existing install there is updated. The path is remembered for this AppID.
4. **Common redist:** if the game includes Steamworks redistributable depots (VC++, DirectX, .NET…, which go into `_CommonRedist`), the script lists them and asks `Skip them? [Y/n]`. Press Enter to skip them, or type `n` to download them too. You don't need them if those runtimes are already installed on your PC.
5. The script then downloads each depot. When it finishes, it tells you where the files are.

## Updating a game (changed files only)

To update without downloading the whole game again, always use the **same install folder**:

Unchanged files are always left alone. For the files that changed, the script shows the free space on the drive and offers two methods, with the download size and free space needed for each:

```
    Free space on drive: 20.48 GB
    1) Patch       - download ~0.33 GB, needs up to 32.75 GB free  ⚠️ not enough free space
    2) Re-download - download ~14.57 GB, needs ~0.01 GB free
    Choose method [1/2] (Enter = 2):
```

| Method | What it does | Best when |
|---|---|---|
| **1) Patch** | Downloads only the changed parts of each file. While rebuilding a file, DepotDownloader keeps the old copy, so it needs free space equal to the changed files. | You have enough free space. The download is usually much smaller. |
| **2) Re-download** | Deletes the changed files, then downloads them in full. | You're short on disk space. |

Enter picks Patch if it fits in the free space, otherwise Re-download. Download sizes are compressed, which is what actually goes over the network.

- **First time:** enter the path of your existing game folder, for example `D:\Games\MyGame`.
  - The script doesn't yet know which version is installed. It first checks the older manifests saved in the project folder: each run saves the manifests it receives there as `<DepotID>_<ManifestID>.manifest`.
  - If the game files match one of them, that version is used as the installed version. Only the changed chunks are downloaded, as in a normal update.
  - If none match, it hashes every local file against the new version. Only files that don't match are downloaded, but a large file whose contents shifted (common for pak files) may be downloaded almost in full. The Patch size is then marked **(approximate)**.
  - **Tip:** if you got the game files from someone who uses this script, ask them for the matching `.manifest` file, or for the `.DepotDownloader` folder from their game folder. Put it in your project folder (or game folder) before your first update.
- **Later updates:** the saved folder is shown. Press Enter to keep it.
  - The script compares the installed manifest with the new one. It also catches files that are missing or the wrong size on disk.
  - Files that were removed from the game are deleted.
  - If the installed version is already the latest, the depot is skipped.
- **After a failed or stopped run:** the next run checks a sample of each changed file to see whether it's closer to the old or the new version.
  - Files that are already partly new are **resumed**: they're checked in place against the new version, and only the missing parts are downloaded. No extra space is needed.
  - Files that are still old are patched as usual.
  - If an old copy was left in `.DepotDownloader\staging`, Patch moves it back into place and Re-download deletes it.
  - The download size for resumed files is only an estimate from the sample, so the Patch size is marked **(approximate)** in the menu. The real download can be larger or smaller.

At the saved-folder prompt you can also type a new path to change the folder, or `none` to go back to the default full download for that game.

Don't delete the hidden `.DepotDownloader` folder inside the install folder. Its `autodepot` subfolder records the installed version of each depot. Without it, the next update has to check every file again.

> **Why the script does the comparing:** when given `-manifestfile`, DepotDownloaderMod treats the new manifest as the "previous" version too. On its own it would mark every existing file as up to date without reading it, and a patch could reuse only data that stayed at the same position in a file. For a large pak where content shifts, that means downloading nearly the whole file.
>
> For **Patch**, the script works around this. It copies the installed and new manifests into DepotDownloaderMod's own cache (`.DepotDownloader\<depot>_<manifest>.manifest` + `.sha`) and records the installed version in `depot.config`, then runs without `-manifestfile`. DepotDownloaderMod loads both manifests from disk and compares them chunk by chunk, so it downloads only the chunks that really changed.

## Files

| File | Purpose |
|---|---|
| `AutoDepot.py` | The script you run |
| `settings.json` | Your API key and the saved install folder for each AppID. **Don't share it.** |
| `keys.txt` | Depot keys, rewritten on every run |
| `*.manifest` | Manifests downloaded from the API (named `<DepotID>_<ManifestID>.manifest`) |
| `depots/` | Default download location |
| `temp_depot_data/` | Temporary files, removed after each run |

## Troubleshooting

- **`API Key invalid or expired`:** run the script again and enter a new key.
- **`This game was not found in the API database`:** the API has no data for that AppID.
- **Download fails or no keys found:** the API data for the game may be incomplete or out of date. Try again later.
- **A full download happened instead of an update:** check that you entered the folder that holds the game files themselves, for example the one containing the game's `.exe`, not a parent folder.
