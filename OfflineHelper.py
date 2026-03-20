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
    return '''
____    __    ____  ___   .___________. __    ______   .__   __. 
\   \  /  \  /   / /   \  |           ||  |  /  __  \  |  \ |  | 
 \   \/    \/   / /  ^  \ `---|  |----`|  | |  |  |  | |   \|  | 
  \            / /  /_\  \    |  |     |  | |  |  |  | |  . `  | 
   \    /\    / /  _____  \   |  |     |  | |  `--'  | |  |\   | 
    \__/  \__/ /__/     \__\  |__|     |__|  \______/  |__| \__| 

                     Offline Helper v1.0                                       
'''

# -------------------- Data (from offline docs) --------------------

DNS_PROVIDERS: list[dict[str, Any]] = [
    {"id": "tic", "name": "TIC (Official)", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["217.218.127.127", "217.218.155.155"]},
    {"id": "ifr-a", "name": "IPM", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["194.225.152.10"]},
    {"id": "tci", "name": "TCI", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["217.219.226.98", "217.219.227.30", "217.219.70.122", "87.107.110.110", "2.188.210.5", "2.188.184.19"]},
    {"id": "tmict", "name": "TMICT", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["31.24.234.37"]},
    {"id": "samantel", "name": "Samantel", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["91.245.229.1"]},
    {"id": "parvaz-system", "name": "Parvaz System", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.161.112.33", "185.161.112.34"]},
    {"id": "shatel", "name": "Shatel", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["80.75.14.219"]},
    {"id": "pishgaman", "name": "Pishgaman", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.229.204.52"]},
    {"id": "mobinnet", "name": "Mobinnet", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["80.210.51.202"]},
    {"id": "afranet", "name": "Afranet", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["212.16.76.19"]},
    {"id": "mtn", "name": "Irancell", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["94.184.225.25"]},
    {"id": "rightel", "name": "Rightel", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["94.182.17.205"]},
    {"id": "respina", "name": "Respina", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.176.59.209"]},
    {"id": "parsonline", "name": "Pars Online", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["195.245.70.230"]},
    {"id": "mci", "name": "MCI", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.112.38.16"]},
    {"id": "zitel", "name": "Zitel", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["188.213.66.141"]},
    {"id": "sabanet", "name": "Sabanet", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["93.126.25.10", "93.126.25.33"]},
    {"id": "ifr-b", "name": "IPM", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["194.225.152.12", "194.225.62.80"]},
    {"id": "fanap", "name": "Fanap Telecom", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.229.28.162"]},
    {"id": "arvancloud", "name": "ArvanCloud", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["185.49.84.2"]},
    {"id": "rassanet", "name": "Rassanet", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["102.37.12.10"]},
    {"id": "asiatech", "name": "Asiatech", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["91.92.208.152"]},
    {"id": "shecan", "name": "Shecan (Official)", "is_official": True, "is_sanctions_friendly": True, "is_in_iran": True, "dnsServers": ["178.22.122.100", "185.51.200.2"]},
    {"id": "shecan-unofficial", "name": "Shecan", "is_official": False, "is_sanctions_friendly": False, "is_in_iran": True, "dnsServers": ["178.22.122.246"]},
    {"id": "begzar", "name": "Begzar (Official)", "is_official": True, "is_sanctions_friendly": True, "is_in_iran": True, "dnsServers": ["185.55.224.24", "185.55.225.25", "185.55.226.26"]},
    {"id": "google", "name": "Google Public DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["8.8.8.8", "8.8.4.4"]},
    {"id": "cloudflare", "name": "Cloudflare DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["1.1.1.1", "1.0.0.1"]},
    {"id": "opendns", "name": "OpenDNS (Cisco)", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["208.67.222.222", "208.67.220.220"]},
    {"id": "quad9", "name": "Quad9 DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["9.9.9.9", "149.112.112.112"]},
    {"id": "lumen-level3", "name": "Lumen / Level 3 DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["205.171.2.65", "205.171.3.65"]},
    {"id": "verisign", "name": "Verisign Public DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["64.6.64.6", "64.6.65.6"]},
    {"id": "yandex", "name": "Yandex DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["77.88.8.8", "77.88.8.1"]},
    {"id": "cleanbrowsing", "name": "CleanBrowsing DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["185.228.168.9", "185.228.169.9"]},
    {"id": "comodo", "name": "Comodo Secure DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["8.26.56.26", "8.20.247.20"]},
    {"id": "controld", "name": "Control D DNS", "is_official": True, "is_sanctions_friendly": False, "is_in_iran": False, "dnsServers": ["76.76.2.0", "76.76.10.0"]},
]

DOCKER_MIRRORS = [
    {"id": "arvan", "name": "ArvanCloud", "url": "https://docker.arvancloud.ir"},
    {"id": "runflare", "name": "Runflare", "url": "https://mirror-docker.runflare.com"},
    {"id": "iranserver", "name": "IranServer", "url": "https://docker.iranserver.com"},
]

LINUX_MIRROR_PROVIDERS: list[dict[str, Any]] = [
    {"id": "ubuntu-ir-official", "name": "Official Mirror (Iran)", "mirrors": {"root": "https://ir.archive.ubuntu.com/ubuntu/", "ubuntu": "https://ir.archive.ubuntu.com/ubuntu/"}},
    {"id": "runflare", "name": "Runflare", "mirrors": {"root": "https://mirror-linux.runflare.com/", "ubuntu": "https://mirror-linux.runflare.com/ubuntu", "kali": "https://mirror-linux.runflare.com/kali", "debian": "https://mirror-linux.runflare.com/debian", "fedora": "https://mirror-linux.runflare.com/fedora", "almalinux": "https://mirror-linux.runflare.com/almalinux", "archlinux": "https://mirror-linux.runflare.com/archlinux", "alpine": "https://mirror-linux.runflare.com/alpine"}},
    {"id": "sindad", "name": "Sindad", "mirrors": {"root": "http://ir.ubuntu.sindad.cloud/ubuntu/", "ubuntu": "http://ir.ubuntu.sindad.cloud/ubuntu/"}},
    {"id": "shatel", "name": "Shatel", "mirrors": {"root": "https://mirror.shatel.ir/ubuntu/", "ubuntu": "https://mirror.shatel.ir/ubuntu/"}},
    {"id": "iranserver", "name": "IranServer", "mirrors": {"root": "http://mirror.iranserver.com/ubuntu/", "ubuntu": "http://mirror.iranserver.com/ubuntu/"}},
    {"id": "iut", "name": "Isfahan University of Technology", "mirrors": {"root": "https://repo.iut.ac.ir/repo/ubuntu/", "ubuntu": "https://repo.iut.ac.ir/repo/ubuntu/"}},
    {"id": "petiak", "name": "Petiak", "mirrors": {"root": "https://archive.ubuntu.petiak.ir/ubuntu/", "ubuntu": "https://archive.ubuntu.petiak.ir/ubuntu/"}},
    {"id": "pardisco", "name": "Pardisco", "mirrors": {"root": "https://mirrors.pardisco.co/ubuntu/", "ubuntu": "https://mirrors.pardisco.co/ubuntu/"}},
    {"id": "aminidc", "name": "AminIDC", "mirrors": {"root": "https://mirror.aminidc.com/ubuntu/", "ubuntu": "https://mirror.aminidc.com/ubuntu/"}},
    {"id": "zero-one", "name": "0-1", "mirrors": {"root": "https://mirror.0-1.cloud/ubuntu/", "ubuntu": "https://mirror.0-1.cloud/ubuntu/"}},
    {"id": "arvan", "name": "ArvanCloud", "mirrors": {
        "root": "http://mirror.arvancloud.ir/",
        "ubuntu": "http://mirror.arvancloud.ir/ubuntu",
        "debian": "http://mirror.arvancloud.ir/debian",
        "debianSecurity": "http://mirror.arvancloud.ir/debian-security",
        "alpineMain": "https://mirror.arvancloud.ir/alpine/<VERSION>/main",
        "alpineCommunity": "https://mirror.arvancloud.ir/alpine/<VERSION>/community",
        "archlinux": "https://mirror.arvancloud.ir/archlinux/$repo/os/$arch",
        "manjaro": "https://mirror.arvancloud.ir/manjaro/stable/$repo/$arch",
        "opensuseReposCommand": (
            'for i in "http://mirror.arvancloud.ir/opensuse/debug/distribution/leap/<VERSION>/repo/oss/ Arvancloud-Debug" '
            '"http://mirror.arvancloud.ir/opensuse/distribution/leap/<VERSION>/repo/non-oss/ Arvancloud-Non-Oss" '
            '"http://mirror.arvancloud.ir/opensuse/distribution/leap/<VERSION>/repo/oss/ Arvancloud-Oss" '
            '"http://mirror.arvancloud.ir/opensuse/source/distribution/leap/<VERSION>/repo/oss/ Arvancloud-Source" '
            '"http://mirror.arvancloud.ir/opensuse/update/leap/<VERSION>/oss Arvancloud-Update"; do sudo zypper addrepo --priority 1 -f $i; done'
        ),
    }},
]

PKG_PROVIDERS = [
    {"id": "runflare", "name": "Runflare", "mirrors": {
        "nodeDownload": "https://mirror-nodejs.runflare.com/dist/",
        "npmRegistry": "https://mirror-npm.runflare.com",
        "yarnRegistry": "https://mirror-npm.runflare.com",
        "goproxy": "https://mirror-go.runflare.com",
        "pypi": "https://mirror-pypi.runflare.com/simple",
        "maven": "https://mirror-maven.runflare.com/maven2",
        "nuget": "https://mirror-nuget.runflare.com/v3/index.json",
        "composer": "https://mirror-composer.runflare.com",
    }},
    {"id": "official", "name": "Official Repository", "mirrors": {
        "nodeDownload": "https://nodejs.org/dist/",
        "npmRegistry": "https://registry.npmjs.org",
        "yarnRegistry": "https://registry.yarnpkg.com",
        "goproxy": "https://proxy.golang.org",
        "pypi": "https://pypi.org/simple",
        "maven": "https://repo1.maven.org/maven2",
        "nuget": "https://api.nuget.org/v3/index.json",
        "composer": "https://repo.packagist.org",
    }},
]

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


def ask_choice(title: str, items: list[str], allow_back: bool = True) -> int:
    print()
    print(f"=== {title} ===")
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


def dns_mode(ctx: Ctx) -> None:
    network_opts = ["iran", "international", "all"]
    official_opts = ["all", "official", "unofficial"]
    sanctions_opts = ["all", "has", "does_not_have"]

    n_idx = ask_choice("DNS Network Type", network_opts, allow_back=False)
    o_idx = ask_choice("DNS Official Filter", official_opts, allow_back=False)
    s_idx = ask_choice("DNS Sanctions-Friendly Filter", sanctions_opts, allow_back=False)

    providers = filter_dns_providers(network_opts[n_idx], official_opts[o_idx], sanctions_opts[s_idx])
    if not providers:
        warn("No providers match selected filters.")
        return

    p_idx = ask_choice(
        "Select DNS Provider",
        [f'{p["name"]} | {", ".join(p["dnsServers"])}' for p in providers],
        allow_back=True,
    )
    if p_idx < 0:
        return
    provider = providers[p_idx]
    servers = provider["dnsServers"]
    info(f'Selected: {provider["name"]}')
    info("DNS: " + ", ".join(servers))

    action_idx = ask_choice(
        "DNS Action",
        [
            "Print recommended commands only",
            "Apply Linux resolv.conf",
            "Apply Linux nmcli connection DNS",
            "Apply Linux systemd-resolved",
            "Apply Windows netsh DNS",
        ],
        allow_back=True,
    )
    if action_idx < 0:
        return

    if action_idx == 0:
        print_dns_commands(servers)
        return
    if action_idx in (1, 2, 3):
        if not require_linux():
            return

    if action_idx == 1:
        apply_dns_resolv_conf(servers, ctx)
    elif action_idx == 2:
        apply_dns_nmcli(servers, ctx)
    elif action_idx == 3:
        apply_dns_systemd_resolved(servers, ctx)
    elif action_idx == 4:
        apply_dns_windows_netsh(servers, ctx)


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
