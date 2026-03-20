# Offline Helper

`OfflineHelper.py` is an interactive CLI tool for restricted/offline network environments.

It helps you quickly switch to documented local DNS/mirrors and apply related system settings.

## Features

- DNS provider selection with filters (network type, official, sanctions-friendly)
- Linux repository mirror change (auto-detect distro/release from `/etc/os-release`)
- Docker registry mirror selection
- Development package mirror selection (Node, Python, Go, Java, .NET, PHP)
- Automatic backup of edited system files before writing
- Automatic package index refresh after Linux repo changes
- Graceful `Ctrl+C` exit without traceback

## File

- Script: `OfflineHelper.py`

## Requirements

- Python 3.9+ (recommended)
- Linux for Linux/Docker repo apply operations
- Root privileges (`sudo`/root) for system file changes
- Related tools installed for selected mode (`apt`, `dnf`, `pacman`, `apk`, `zypper`, `docker`, etc.)

## Usage

Run in apply mode (default, executes commands):

```bash
python3 OfflineHelper.py
```

Run in dry-run mode (prints commands only, no changes):

```bash
python3 OfflineHelper.py --dry-run
```

## Main Modes

1. `DNS restriction mode`
   - Select provider and apply via:
     - Linux `/etc/resolv.conf`
     - Linux `nmcli`
     - Linux `systemd-resolved`
     - Windows `netsh`

2. `Linux OS repository mirror mode`
   - Auto-detects distro + release
   - Lets you choose mirror provider for detected distro
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