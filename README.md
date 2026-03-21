# Offline Helper

`OfflineHelper.py` is an interactive CLI tool for restricted/offline network environments.

It helps you quickly switch to documented local DNS/mirrors and apply related system settings.

## Features

- DNS provider selection with filters (network type, official, sanctions-friendly)
- **Custom DNS servers** (enter your own IPs in the interactive flow)
- Linux repository mirror change (auto-detect distro/release from `/etc/os-release`)
- **Custom Linux mirror URLs** (per-distro prompts when you pick “Custom mirror”)
- **Optional APT keyring** (`--keyring-url`): download a signing key, `gpg --dearmor` into `/usr/share/keyrings`, and add `deb [signed-by=…]` to `sources.list` (Ubuntu / Debian / Kali)
- **APT component detection** for Ubuntu / Debian / Kali: reads `Components:` from the remote `dists/<suite>/Release` (or `InRelease`) so `deb` lines match what the mirror actually publishes (e.g. `main` only vs full Ubuntu sets)
- Docker registry mirror selection
- Development package mirror selection (Node, Python, Go, Java, .NET, PHP)
- **Non-interactive mode** via `run` subcommand (scriptable, no menus)
- Automatic backup of edited system files before writing
- Automatic package index refresh after Linux repo changes

## Files

- Script: `OfflineHelper.py`
- Data: `providers.json` (DNS providers, Linux/Docker mirrors, package providers)

## Requirements

- Python 3.9+ (recommended)
- Linux for Linux/Docker repo apply operations
- Root privileges (`sudo`/root) for system file changes
- Related tools installed for selected mode (`apt`, `dnf`, `pacman`, `apk`, `zypper`, `docker`, etc.)

## Usage

### Interactive menu (default)

Run in apply mode (default, executes commands):

```bash
python3 OfflineHelper.py
```

Run in dry-run mode (prints commands only, no changes):

```bash
python3 OfflineHelper.py --dry-run
```

### Non-interactive `run` (no prompts)

Use `run` when you want a single command (automation, scripts, CI, SSH one-liners). Combine with `--dry-run` on the parent command to preview only.

General form:

```bash
python3 OfflineHelper.py [--dry-run] run <action> [options]
```

**DNS examples**

Print sample commands for custom servers (no system changes):

```bash
python3 OfflineHelper.py run dns --servers "1.1.1.1,8.8.8.8" --action print
```

Apply DNS using the auto-detected backend on this machine:

```bash
python3 OfflineHelper.py run dns --servers "1.1.1.1,8.8.8.8" --action apply --method auto
```

Use a provider id from `providers.json` instead of raw IPs:

```bash
python3 OfflineHelper.py run dns --provider-id google --action apply --method auto
```

Force a specific backend (when you know what your OS uses):

```bash
python3 OfflineHelper.py run dns --servers "1.1.1.1" --action apply --method systemd_resolved
python3 OfflineHelper.py run dns --servers "1.1.1.1" --action apply --method nmcli --nmcli-connection "Wired connection 1"
python3 OfflineHelper.py run dns --servers "1.1.1.1" --action apply --method windows_netsh --windows-interface "Ethernet"
```

**Linux repository examples**

Apply a mirror provider by id (must support your detected distro; see `providers.json` → `linux_mirror_providers`):

```bash
sudo python3 OfflineHelper.py run repo --provider-id runflare
```

Custom mirror URL (meaning depends on distro; on Debian you can add security mirror):

```bash
sudo python3 OfflineHelper.py run repo --custom-url "https://mirror.example/debian" --custom-security-url "https://mirror.example/debian-security"
sudo python3 OfflineHelper.py run repo --custom-url "https://mirror.example/ubuntu"
```

Signed-by keyring (equivalent to `mkdir -p /usr/share/keyrings` and `curl … | gpg --dearmor -o /usr/share/keyrings/name.gpg`):

```bash
sudo python3 OfflineHelper.py run repo \
  --custom-url "https://example.com/ubuntu" \
  --keyring-url "https://example.com/ubuntu/example.gpg" \
  --keyring-name "example.gpg"
```

That writes `/etc/apt/sources.list` with a line like:

`deb [signed-by=/usr/share/keyrings/example.gpg] https://example.com/ubuntu noble main`

The suite name (`noble`, etc.) comes from your OS. The component list (`main`, `main universe`, …) is **detected** by fetching `dists/<codename>/Release` from your mirror and parsing `Components:`. If that fetch fails (offline, wrong URL), Ubuntu/Debian main lines fall back to **`main` only**; Kali falls back to **`main contrib non-free non-free-firmware`**.

Override without probing the mirror:

```bash
sudo python3 OfflineHelper.py run repo --custom-url "https://example.com/ubuntu" --apt-components "main universe"
```

Optional fields on a `linux_mirror_providers` entry in `providers.json`: `aptComponents` (string, e.g. `"main"`), and for Debian with a security mirror, `aptComponentsSecurity` for the `-security` line.

Mirror providers in `providers.json` can also include optional top-level `keyringUrl` and `keyringName` next to `mirrors` for the same behavior when you pick that provider in the menu or use `--provider-id`.

`--dry-run` does not download `Release`; APT lines use the same fallbacks as when detection fails.

Alpine (explicit main + community lines):

```bash
sudo python3 OfflineHelper.py run repo --custom-alpine-main "https://mirror.example/alpine/v3.20/main" --custom-alpine-community "https://mirror.example/alpine/v3.20/community"
```

OpenSUSE (shell command with `<VERSION>` placeholder for detected release):

```bash
sudo python3 OfflineHelper.py run repo --custom-zypper-command 'sudo zypper addrepo -f "https://mirror.example/repo/oss/" my-oss'
```

**Docker example**

```bash
sudo python3 OfflineHelper.py run docker --mirror-id arvan --restart-docker
```

See all options:

```bash
python3 OfflineHelper.py run dns --help
python3 OfflineHelper.py run repo --help
python3 OfflineHelper.py run docker --help
```

## Main Modes

1. `DNS restriction mode`
   - Select a catalog provider **or** **Custom — enter DNS server addresses manually** (comma- or space-separated IPs)
   - Apply via:
     - Linux `/etc/resolv.conf`
     - Linux `nmcli`
     - Linux `systemd-resolved`
     - Windows `netsh`

2. `Linux OS repository mirror mode`
   - Auto-detects distro + release
   - Lets you choose mirror provider for detected distro, **or** **Custom mirror (enter URLs manually)** for your own bases/lines/commands
   - Optional **APT keyring URL** prompt (Ubuntu/Debian/Kali): downloads the key, stores it under `/usr/share/keyrings`, and adds `[signed-by=…]` to `deb` lines
   - **APT components** for Ubuntu/Debian/Kali are taken from the mirror’s `Release` file when possible (see examples above)
   - Updates mirror config files
   - Runs update/refresh automatically after change:
     - Ubuntu/Kali/Debian: `apt update`
     - Fedora/AlmaLinux: `dnf clean all && dnf makecache`
     - Arch/Manjaro: `pacman -Syy`
     - Alpine: `apk update`
     - OpenSUSE: `zypper refresh && zypper lr -u`

3. `Docker registry mirror mode`
   - Writes `/etc/docker/daemon.json`
   - Optional Docker daemon restart

4. `Development package server mode`
   - NodeJS: NVM mirror, npm registry, yarn registry
   - Python: pip index
   - Go: GOPROXY
   - Java: Maven/Gradle snippets
   - ASP/.NET: NuGet source
   - PHP: Composer Packagist mirror

## Safety Notes

- Backups are created before overwriting config files (when target file exists).
- Use `--dry-run` first to preview exact commands.
- Some operations are shelling out to distro tools; verify installed package manager commands on your host.

## Exit Behavior

- Pressing `Ctrl+C` exits cleanly with message:
  - `Interrupted by user. Exiting.`

## License
`OfflineHelper` is made with ♥  by [Wation](https://github.com/TheWation) and it's released under the `MIT` license.