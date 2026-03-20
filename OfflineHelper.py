#!/usr/bin/env python3
"""
Offline network helper for restricted environments.

Modes:
1) DNS selection and apply
2) Linux repository mirror selection and apply
3) Docker registry mirror selection and apply
4) Development package server selection and apply

All mirror/provider values are extracted from local offline documentation.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def logo() -> str:
    """Return the logo/banner."""
    return r'''
____    __    ____  ___   .___________. __    ______   .__   __. 
\   \  /  \  /   / /   \  |           ||  |  /  __  \  |  \ |  | 
 \   \/    \/   / /  ^  \ `---|  |----`|  | |  |  |  | |   \|  | 
  \            / /  /_\  \    |  |     |  | |  |  |  | |  . `  | 
   \    /\    / /  _____  \   |  |     |  | |  `--'  | |  |\   | 
    \__/  \__/ /__/     \__\  |__|     |__|  \______/  |__| \__| 

                     Offline Helper v1.0                                       
'''

# -------------------- Data (from providers.json) --------------------

PROVIDERS_FILE = Path(__file__).with_name("providers.json")


def _load_provider_data() -> dict[str, Any]:
    if not PROVIDERS_FILE.exists():
        raise FileNotFoundError(f"providers.json not found at {PROVIDERS_FILE}")
    raw = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("providers.json root must be a JSON object")
    return raw


_PROVIDERS_DATA = _load_provider_data()
DNS_PROVIDERS: list[dict[str, Any]] = _PROVIDERS_DATA.get("dns_providers", [])
DOCKER_MIRRORS: list[dict[str, Any]] = _PROVIDERS_DATA.get("docker_mirrors", [])
LINUX_MIRROR_PROVIDERS: list[dict[str, Any]] = _PROVIDERS_DATA.get("linux_mirror_providers", [])
PKG_PROVIDERS: list[dict[str, Any]] = _PROVIDERS_DATA.get("pkg_providers", [])

UBUNTU_RELEASES = ["plucky", "oracular", "noble", "kinetic", "jammy", "focal"]
DEBIAN_RELEASES = ["trixie", "bookworm", "bullseye"]
ALPINE_RELEASES = ["v3.0", "v3.1", "v3.2", "v3.3", "v3.4", "v3.5", "v3.6", "v3.7", "v3.8", "v3.9", "v3.10", "v3.11", "v3.12", "v3.13", "v3.14", "v3.15", "v3.16", "v3.17", "v3.18", "v3.19", "v3.20", "v3.21"]
OPENSUSE_RELEASES = ["15.0", "15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "16.0", "42.3"]


# -------------------- Helpers --------------------


@dataclass
class Ctx:
    dry_run: bool = False


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def err(msg: str) -> None:
    print(f"[ERROR] {msg}")


def ask_choice(
    title: str,
    items: list[str],
    allow_back: bool = True,
    description: str = "",
) -> int:
    print()
    print(f"=== {title} ===")
    if description:
        print(description)
    for i, item in enumerate(items, start=1):
        print(f"{i}) {item}")
    if allow_back:
        print("0) Back")
    while True:
        raw = input("Select: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if allow_back and idx == 0:
                return -1
            if 1 <= idx <= len(items):
                return idx - 1
        print("Invalid selection, try again.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    raw = input(prompt + suffix).strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def run_command(cmd: str, ctx: Ctx, shell: bool = False) -> int:
    print(f"$ {cmd}")
    if ctx.dry_run:
        return 0
    if shell:
        return subprocess.call(cmd, shell=True)
    return subprocess.call(cmd.split())


def run_command_capture(cmd: str, shell: bool = False) -> tuple[int, str]:
    try:
        if shell:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        else:
            proc = subprocess.run(cmd.split(), capture_output=True, text=True, check=False)
        out = (proc.stdout or "").strip()
        if not out and proc.stderr:
            out = proc.stderr.strip()
        return proc.returncode, out
    except Exception:
        return 1, ""


def require_linux() -> bool:
    if platform.system().lower() != "linux":
        err("This apply mode is only supported on Linux.")
        return False
    return True


def require_root_for_file_writes() -> bool:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        err("Run with sudo/root for file write operations.")
        return False
    return True


def backup_file(path: Path, ctx: Ctx) -> Path | None:
    if not path.exists():
        return None
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak.{ts}")
    info(f"Backup: {path} -> {backup}")
    if not ctx.dry_run:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    return backup


def write_text_file(path: Path, content: str, ctx: Ctx) -> None:
    info(f"Write file: {path}")
    if ctx.dry_run:
        print("----- file content begin -----")
        print(content)
        print("----- file content end -----")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# -------------------- DNS mode --------------------


def filter_dns_providers(network: str, official: str, sanctions: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in DNS_PROVIDERS:
        network_ok = True
        official_ok = True
        sanctions_ok = True
        if network == "iran":
            network_ok = p["is_in_iran"] is True
        elif network == "international":
            network_ok = p["is_in_iran"] is False
        if official == "official":
            official_ok = p["is_official"] is True
        elif official == "unofficial":
            official_ok = p["is_official"] is False
        if sanctions == "has":
            sanctions_ok = p["is_sanctions_friendly"] is True
        elif sanctions == "does_not_have":
            sanctions_ok = p["is_sanctions_friendly"] is False
        if network_ok and official_ok and sanctions_ok:
            out.append(p)
    return out


def read_resolv_conf_servers() -> list[str]:
    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    servers: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[0].lower() == "nameserver":
            servers.append(parts[1])
    return servers


def read_systemd_resolved_servers() -> list[str]:
    path = Path("/etc/systemd/resolved.conf")
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("DNS="):
                value = stripped.split("=", 1)[1].strip()
                if value:
                    return value.split()
    code, out = run_command_capture("resolvectl dns")
    if code == 0 and out:
        servers: list[str] = []
        for raw in out.splitlines():
            line = raw.strip()
            if ":" in line:
                line = line.split(":", 1)[1].strip()
            for token in line.split():
                if "." in token or ":" in token:
                    servers.append(token)
        return servers
    return []


def read_networkmanager_servers() -> list[str]:
    code, out = run_command_capture("nmcli -t -f IP4.DNS,IP6.DNS device show")
    if code != 0 or not out:
        return []
    servers: list[str] = []
    for line in out.splitlines():
        if ":" not in line:
            continue
        _, value = line.split(":", 1)
        value = value.strip()
        if value:
            servers.append(value)
    return servers


def read_windows_dns_servers() -> list[str]:
    # Use PowerShell to query configured IPv4 DNS servers on Windows.
    cmd = (
        "powershell -NoProfile -Command "
        "\"Get-DnsClientServerAddress -AddressFamily IPv4 | "
        "ForEach-Object { $_.ServerAddresses }\""
    )
    code, out = run_command_capture(cmd, shell=True)
    if code != 0 or not out:
        return []
    servers: list[str] = []
    for line in out.splitlines():
        value = line.strip()
        if value:
            servers.append(value)
    return servers


def detect_dns_config() -> tuple[str, list[str]]:
    os_name = platform.system().lower()
    if os_name == "windows":
        return "windows-netsh", read_windows_dns_servers()
    if os_name != "linux":
        return "unsupported", []

    resolv_path = Path("/etc/resolv.conf")
    symlink_target = ""
    if resolv_path.exists() and resolv_path.is_symlink():
        try:
            symlink_target = str(resolv_path.resolve())
        except OSError:
            symlink_target = ""

    systemd_active = run_command_capture("systemctl is-active systemd-resolved")[0] == 0
    nm_active = run_command_capture("systemctl is-active NetworkManager")[0] == 0

    if "systemd/resolve" in symlink_target or systemd_active:
        return "systemd-resolved", read_systemd_resolved_servers() or read_resolv_conf_servers()
    if nm_active or Path("/etc/NetworkManager").exists():
        return "networkmanager", read_networkmanager_servers() or read_resolv_conf_servers()
    return "resolve.conf", read_resolv_conf_servers()


def dns_mode(ctx: Ctx) -> None:
    info(f"Detected OS: {platform.system().lower()}")
    manager_type, current_servers = detect_dns_config()
    if manager_type == "unsupported":
        warn("\nCurrent DNS manager detection is unsupported on this OS.")
    else:
        info(f"\nCurrent DNS manager type: {manager_type}")
        if current_servers:
            info("Current DNS servers on server: " + ", ".join(current_servers))
        else:
            warn("Could not detect current DNS server config on server.")

    network_opts = ["iran", "international", "all"]
    official_opts = ["all", "official", "unofficial"]
    sanctions_opts = ["all", "has", "does_not_have"]

    while True:
        n_idx = ask_choice(
            "DNS Network Type",
            network_opts,
            allow_back=True,
            description="Meaning: Filter providers by location scope (inside Iran, outside Iran, or all).",
        )
        if n_idx < 0:
            return

        while True:
            o_idx = ask_choice(
                "DNS Official Filter",
                official_opts,
                allow_back=True,
                description="Meaning: Filter providers by ownership source (official provider/operator entries vs unofficial/community entries).",
            )
            if o_idx < 0:
                break

            while True:
                s_idx = ask_choice(
                    "DNS Sanctions-Friendly Filter",
                    sanctions_opts,
                    allow_back=True,
                    description="Meaning: Filter providers by sanctions-friendliness (DNS services intended to help bypass sanctions/restrictions).",
                )
                if s_idx < 0:
                    break

                providers = filter_dns_providers(network_opts[n_idx], official_opts[o_idx], sanctions_opts[s_idx])
                if not providers:
                    warn("No providers match selected filters.")
                    continue

                while True:
                    p_idx = ask_choice(
                        "Select DNS Provider",
                        [f'{p["name"]} | {", ".join(p["dnsServers"])}' for p in providers],
                        allow_back=True,
                    )
                    if p_idx < 0:
                        break

                    provider = providers[p_idx]
                    servers = provider["dnsServers"]
                    info(f'\nSelected: {provider["name"]}')
                    info("DNS: " + ", ".join(servers))

                    actions: list[tuple[str, str]] = [("print", "Print recommended commands only")]
                    if manager_type == "resolve.conf":
                        actions.append(("resolv_conf", "Apply Linux resolv.conf"))
                    elif manager_type == "networkmanager":
                        actions.append(("nmcli", "Apply Linux nmcli connection DNS"))
                    elif manager_type == "systemd-resolved":
                        actions.append(("systemd_resolved", "Apply Linux systemd-resolved"))
                    elif manager_type == "windows-netsh":
                        actions.append(("windows_netsh", "Apply Windows netsh DNS"))
                    else:
                        warn("No apply option for detected DNS manager; only print mode is available.")

                    action_idx = ask_choice("DNS Action", [x[1] for x in actions], allow_back=True)
                    if action_idx < 0:
                        continue

                    selected_action = actions[action_idx][0]
                    if selected_action == "print":
                        print_dns_commands(servers)
                        return
                    if selected_action == "resolv_conf":
                        apply_dns_resolv_conf(servers, ctx)
                        return
                    if selected_action == "nmcli":
                        apply_dns_nmcli(servers, ctx)
                        return
                    if selected_action == "systemd_resolved":
                        apply_dns_systemd_resolved(servers, ctx)
                        return
                    if selected_action == "windows_netsh":
                        apply_dns_windows_netsh(servers, ctx)
                        return


def print_dns_commands(servers: list[str]) -> None:
    print("\n--- Linux resolv.conf ---")
    print("sudo cp /etc/resolv.conf /etc/resolv.conf.bak")
    print("sudo nano /etc/resolv.conf")
    for s in servers:
        print(f"nameserver {s}")

    print("\n--- Linux nmcli ---")
    print('nmcli connection show --active')
    print('sudo nmcli connection modify "Wired connection 1" ipv4.ignore-auto-dns yes')
    print(f'sudo nmcli connection modify "Wired connection 1" ipv4.dns "{" ".join(servers)}"')
    print('sudo nmcli connection up "Wired connection 1"')
    print("nmcli device show | grep -i dns")

    print("\n--- Linux systemd-resolved ---")
    print("sudo nano /etc/systemd/resolved.conf")
    print("[Resolve]")
    print(f'DNS={" ".join(servers)}')
    print("FallbackDNS=")
    print("sudo systemctl restart systemd-resolved")
    print("resolvectl status")

    print("\n--- Windows netsh ---")
    print('netsh interface show interface')
    if servers:
        print(f'netsh interface ip set dns name="Ethernet" static {servers[0]}')
        for i, s in enumerate(servers[1:], start=2):
            print(f'netsh interface ip add dns name="Ethernet" {s} index={i}')
    print("ipconfig /all")


def apply_dns_resolv_conf(servers: list[str], ctx: Ctx) -> None:
    if not require_root_for_file_writes():
        return
    target = Path("/etc/resolv.conf")
    backup_file(target, ctx)
    content = "\n".join([f"nameserver {s}" for s in servers]) + "\n"
    write_text_file(target, content, ctx)
    info("Applied DNS to /etc/resolv.conf")


def apply_dns_nmcli(servers: list[str], ctx: Ctx) -> None:
    conn = input('Connection name (example: "Wired connection 1"): ').strip()
    if not conn:
        warn("Empty connection name.")
        return
    run_command(f'nmcli connection show "{conn}"', ctx, shell=True)
    run_command(f'sudo nmcli connection modify "{conn}" ipv4.ignore-auto-dns yes', ctx, shell=True)
    run_command(f'sudo nmcli connection modify "{conn}" ipv4.dns "{" ".join(servers)}"', ctx, shell=True)
    run_command(f'sudo nmcli connection up "{conn}"', ctx, shell=True)
    run_command("nmcli device show | grep -i dns", ctx, shell=True)


def apply_dns_systemd_resolved(servers: list[str], ctx: Ctx) -> None:
    if not require_root_for_file_writes():
        return
    target = Path("/etc/systemd/resolved.conf")
    backup_file(target, ctx)
    dns_line = f'DNS={" ".join(servers)}'
    content = "[Resolve]\n" + dns_line + "\nFallbackDNS=\n"
    write_text_file(target, content, ctx)
    run_command("sudo systemctl restart systemd-resolved", ctx, shell=True)
    run_command("resolvectl status", ctx, shell=True)


def apply_dns_windows_netsh(servers: list[str], ctx: Ctx) -> None:
    nic = input('Windows interface name (example: "Ethernet"): ').strip() or "Ethernet"
    if not servers:
        warn("No DNS servers selected.")
        return
    run_command(f'netsh interface ip set dns name="{nic}" static {servers[0]}', ctx, shell=True)
    for i, s in enumerate(servers[1:], start=2):
        run_command(f'netsh interface ip add dns name="{nic}" {s} index={i}', ctx, shell=True)
    run_command("ipconfig /all", ctx, shell=True)


# -------------------- Linux repo mirror mode --------------------


def provider_supports_distro(provider: dict[str, Any], distro: str) -> bool:
    mirrors = provider.get("mirrors", {})
    if distro == "debian":
        return bool(mirrors.get("debian") or mirrors.get("debianSecurity"))
    if distro == "alpine":
        return bool(mirrors.get("alpine") or mirrors.get("alpineMain") or mirrors.get("alpineCommunity"))
    if distro == "opensuse":
        return bool(mirrors.get("opensuseReposCommand"))
    return bool(mirrors.get(distro))


def parse_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    p = Path("/etc/os-release")
    if not p.exists():
        return data
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        data[key.strip()] = val
    return data


def detect_linux_distro_release() -> tuple[str, str]:
    osr = parse_os_release()
    if not osr:
        return "", ""

    os_id = osr.get("ID", "").lower()
    id_like = osr.get("ID_LIKE", "").lower().split()
    codename = (osr.get("VERSION_CODENAME") or osr.get("UBUNTU_CODENAME") or osr.get("DEBIAN_CODENAME") or "").lower()
    version_id = osr.get("VERSION_ID", "").strip()

    # Debian-based
    if os_id == "ubuntu" or "ubuntu" in id_like:
        return "ubuntu", codename
    if os_id == "kali":
        return "kali", "kali-rolling"
    if os_id == "debian":
        if not codename:
            codename = {"13": "trixie", "12": "bookworm", "11": "bullseye"}.get(version_id, "")
        return "debian", codename

    # RHEL/Fedora-based
    if os_id == "fedora":
        return "fedora", version_id
    if os_id == "almalinux" or "almalinux" in id_like:
        return "almalinux", version_id

    # Arch family
    if os_id == "arch":
        return "archlinux", ""
    if os_id == "manjaro":
        return "manjaro", ""

    # Alpine
    if os_id == "alpine":
        base = ".".join(version_id.split(".")[:2]) if version_id else ""
        return "alpine", f"v{base}" if base else ""

    # OpenSUSE
    if os_id.startswith("opensuse"):
        base = ".".join(version_id.split(".")[:2]) if version_id else ""
        return "opensuse", base

    return "", ""


def repo_mode(ctx: Ctx) -> None:
    if not require_linux():
        return

    distro, release = detect_linux_distro_release()
    if not distro:
        err("Could not auto-detect distro from /etc/os-release.")
        return

    # Keep using detected value even if it is newer than docs list.
    if distro == "ubuntu":
        if not release:
            err("Could not auto-detect Ubuntu codename.")
            return
        if release not in UBUNTU_RELEASES:
            warn(f'Ubuntu release "{release}" is not in docs list; using detected value anyway.')
    elif distro == "debian":
        if not release:
            err("Could not auto-detect Debian codename.")
            return
        if release not in DEBIAN_RELEASES:
            warn(f'Debian release "{release}" is not in docs list; using detected value anyway.')
    elif distro == "alpine":
        if not release:
            err("Could not auto-detect Alpine version.")
            return
        if release not in ALPINE_RELEASES:
            warn(f'Alpine release "{release}" is not in docs list; using detected value anyway.')
    elif distro == "opensuse":
        if not release:
            err("Could not auto-detect OpenSUSE version.")
            return
        if release not in OPENSUSE_RELEASES:
            warn(f'OpenSUSE release "{release}" is not in docs list; using detected value anyway.')

    info(f"Auto-detected distro: {distro}")
    if release:
        info(f"Auto-detected release: {release}")

    providers = [p for p in LINUX_MIRROR_PROVIDERS if provider_supports_distro(p, distro)]
    if not providers:
        warn("No mirror provider for selected distro.")
        return
    p_idx = ask_choice("Select mirror provider", [p["name"] for p in providers], allow_back=True)
    if p_idx < 0:
        return
    provider = providers[p_idx]
    mirrors = provider.get("mirrors", {})
    info(f'Selected: {provider["name"]} for {distro}')

    if distro != "opensuse" and not require_root_for_file_writes():
        return

    post_change_update_cmd = ""

    if distro == "ubuntu":
        content = f"deb {mirrors['ubuntu']} {release} universe\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "kali":
        content = f"deb {mirrors['kali']} kali-rolling main contrib non-free non-free-firmware\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "debian":
        main_line = f"deb {mirrors['debian']} {release} main"
        sec_mirror = mirrors.get("debianSecurity")
        sec_line = f"deb {sec_mirror} {release}-security main" if sec_mirror else ""
        content = "\n".join([x for x in [main_line, sec_line] if x]) + "\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "fedora":
        fedora_url = mirrors["fedora"].rstrip("/")
        backup_dir = Path("/etc/yum.repos.d")
        backup_file(backup_dir / "fedora.repo", ctx)
        backup_file(backup_dir / "fedora-updates.repo", ctx)
        fedora_repo = (
            "[fedora]\n"
            "name=Fedora $releasever - $basearch\n"
            f"baseurl={fedora_url}/releases/$releasever/Everything/$basearch/os/\n"
            "enabled=1\n"
            "gpgcheck=1\n"
        )
        updates_repo = (
            "[updates]\n"
            "name=Fedora $releasever - $basearch - Updates\n"
            f"baseurl={fedora_url}/updates/$releasever/Everything/$basearch/\n"
            "enabled=1\n"
            "gpgcheck=1\n"
        )
        write_text_file(backup_dir / "fedora.repo", fedora_repo + "\n", ctx)
        write_text_file(backup_dir / "fedora-updates.repo", updates_repo + "\n", ctx)
        post_change_update_cmd = "sudo dnf clean all && sudo dnf makecache"
    elif distro == "almalinux":
        alma_url = mirrors["almalinux"].rstrip("/")
        repo_path = Path("/etc/yum.repos.d/almalinux.repo")
        backup_file(repo_path, ctx)
        content = (
            "[baseos]\n"
            "name=AlmaLinux $releasever - BaseOS\n"
            f"baseurl={alma_url}/$releasever/BaseOS/$basearch/os/\n"
            "enabled=1\n"
            "gpgcheck=1\n\n"
            "[appstream]\n"
            "name=AlmaLinux $releasever - AppStream\n"
            f"baseurl={alma_url}/$releasever/AppStream/$basearch/os/\n"
            "enabled=1\n"
            "gpgcheck=1\n"
        )
        write_text_file(repo_path, content, ctx)
        post_change_update_cmd = "sudo dnf clean all && sudo dnf makecache"
    elif distro == "archlinux":
        repo_path = Path("/etc/pacman.d/mirrorlist")
        backup_file(repo_path, ctx)
        write_text_file(repo_path, f"Server = {mirrors['archlinux']}\n", ctx)
        post_change_update_cmd = "sudo pacman -Syy"
    elif distro == "alpine":
        main = mirrors.get("alpineMain", "").replace("<VERSION>", release)
        community = mirrors.get("alpineCommunity", "").replace("<VERSION>", release)
        if not main or not community:
            base = mirrors.get("alpine", "").rstrip("/")
            main = main or f"{base}/{release}/main"
            community = community or f"{base}/{release}/community"
        content = f"{main}\n{community}\n"
        repo_path = Path("/etc/apk/repositories")
        backup_file(repo_path, ctx)
        write_text_file(repo_path, content, ctx)
        post_change_update_cmd = "sudo apk update"
    elif distro == "opensuse":
        command = mirrors["opensuseReposCommand"].replace("<VERSION>", release)
        run_command(command, ctx, shell=True)
        post_change_update_cmd = "sudo zypper refresh && zypper lr -u"
    elif distro == "manjaro":
        repo_path = Path("/etc/pacman.d/mirrorlist")
        backup_file(repo_path, ctx)
        write_text_file(repo_path, f"Server = {mirrors['manjaro']}\n", ctx)
        post_change_update_cmd = "sudo pacman -Syy"

    if post_change_update_cmd:
        info("Running repository update/refresh automatically...")
        run_command(post_change_update_cmd, ctx, shell=True)


# -------------------- Docker mirror mode --------------------


def docker_mode(ctx: Ctx) -> None:
    idx = ask_choice("Select Docker mirror", [f'{x["name"]} ({x["url"]})' for x in DOCKER_MIRRORS], allow_back=True)
    if idx < 0:
        return
    mirror = DOCKER_MIRRORS[idx]
    info(f'Selected Docker mirror: {mirror["name"]} -> {mirror["url"]}')

    if not require_linux():
        return
    if not require_root_for_file_writes():
        return

    daemon_path = Path("/etc/docker/daemon.json")
    backup_file(daemon_path, ctx)
    cfg = {
        "insecure-registries": [mirror["url"]],
        "registry-mirrors": [mirror["url"]],
    }
    write_text_file(daemon_path, json.dumps(cfg, indent=2) + "\n", ctx)

    if ask_yes_no("Restart Docker service now?", default=True):
        run_command("sudo systemctl daemon-reload", ctx, shell=True)
        run_command("sudo systemctl restart docker", ctx, shell=True)
    run_command('docker info | grep -i "Registry Mirrors"', ctx, shell=True)


# -------------------- Dev package mirror mode --------------------


def devpkg_mode(ctx: Ctx) -> None:
    p_idx = ask_choice("Select package mirror provider", [p["name"] for p in PKG_PROVIDERS], allow_back=True)
    if p_idx < 0:
        return
    provider = PKG_PROVIDERS[p_idx]
    mirrors = provider["mirrors"]

    lang_opts = ["nodejs", "python", "go", "java", "asp", "php"]
    l_idx = ask_choice("Select language/toolchain", lang_opts, allow_back=True)
    if l_idx < 0:
        return
    lang = lang_opts[l_idx]

    if lang == "nodejs":
        target_opts = ["node-install", "npm-registry", "yarn-registry"]
        t_idx = ask_choice("NodeJS target", target_opts, allow_back=True)
        if t_idx < 0:
            return
        target = target_opts[t_idx]
        if target == "node-install":
            base = mirrors["nodeDownload"].rstrip("/")
            info(f"NVM mirror base: {base}")
            print("Run these in your shell:")
            print(f'export NVM_NODEJS_ORG_MIRROR="{base}"')
            print("nvm install 20")
            print("nvm use 20")
        elif target == "npm-registry":
            run_command(f'npm config set registry "{mirrors["npmRegistry"]}"', ctx, shell=True)
            run_command("npm config get registry", ctx, shell=True)
        elif target == "yarn-registry":
            run_command(f'yarn config set registry "{mirrors["yarnRegistry"]}"', ctx, shell=True)
            run_command("yarn config get registry", ctx, shell=True)
        return

    if lang == "python":
        run_command(f'pip config set global.index-url "{mirrors["pypi"]}"', ctx, shell=True)
        run_command("pip config get global.index-url", ctx, shell=True)
        return

    if lang == "go":
        run_command(f'go env -w GOPROXY="{mirrors["goproxy"]},direct"', ctx, shell=True)
        run_command("go env GOPROXY", ctx, shell=True)
        return

    if lang == "java":
        target_opts = ["maven", "gradle"]
        t_idx = ask_choice("Java target", target_opts, allow_back=True)
        if t_idx < 0:
            return
        target = target_opts[t_idx]
        if target == "maven":
            m2 = Path.home() / ".m2" / "settings.xml"
            snippet = (
                "<mirrors>\n"
                "  <mirror>\n"
                "    <id>selected-mirror</id>\n"
                "    <mirrorOf>central</mirrorOf>\n"
                f'    <url>{mirrors["maven"]}</url>\n'
                "  </mirror>\n"
                "</mirrors>\n"
            )
            warn("Auto-merging XML is risky. Paste this into ~/.m2/settings.xml:")
            print(snippet)
            info(f"Suggested path: {m2}")
        else:
            snippet = (
                "repositories {\n"
                f'    maven {{ url "{mirrors["maven"]}" }}\n'
                "    mavenCentral()\n"
                "}\n"
            )
            warn("Add this to build.gradle/settings.gradle:")
            print(snippet)
        return

    if lang == "asp":
        run_command(f'dotnet nuget add source "{mirrors["nuget"]}" -n selected-provider', ctx, shell=True)
        run_command("dotnet nuget list source", ctx, shell=True)
        return

    if lang == "php":
        run_command(f'composer config -g repos.packagist composer "{mirrors["composer"]}"', ctx, shell=True)
        run_command("composer config -g --list", ctx, shell=True)
        return


# -------------------- Main menu --------------------


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    ctx = Ctx(dry_run=dry_run)

    print(logo())

    if dry_run:
        warn("Dry-run mode is ON. Commands will be printed only.")
    else:
        warn("Apply mode is ON. Changes will be executed.")

    while True:
        idx = ask_choice(
            "Main Menu",
            [
                "DNS restriction mode",
                "Linux OS repository mirror mode",
                "Docker registry mirror mode",
                "Development package server mode",
                "Exit",
            ],
            allow_back=False,
        )
        if idx == 0:
            dns_mode(ctx)
        elif idx == 1:
            repo_mode(ctx)
        elif idx == 2:
            docker_mode(ctx)
        elif idx == 3:
            devpkg_mode(ctx)
        else:
            print("Bye.")
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise SystemExit(130)
