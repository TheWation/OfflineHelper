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

import argparse
import datetime as _dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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

APT_KEYRINGS_DIR = Path("/usr/share/keyrings")

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


def write_binary_file(path: Path, data: bytes, ctx: Ctx) -> None:
    info(f"Write file: {path}")
    if ctx.dry_run:
        print(f"----- would write {len(data)} bytes -----")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _safe_keyring_basename(name: str) -> str | None:
    name = name.strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not name.endswith(".gpg"):
        name = name + ".gpg"
    return name


def default_keyring_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    base = Path(path).name
    if not base or base in (".", ".."):
        return "repo-keyring.gpg"
    if base.endswith(".asc"):
        return base[:-4] + ".gpg"
    if base.endswith(".gpg"):
        return base
    return base + ".gpg"


def install_apt_keyring_from_url(url: str, dest_basename: str | None, ctx: Ctx) -> Path | None:
    """
    Download key material from URL, pipe through gpg --dearmor, write to /usr/share/keyrings/<name>.gpg.
    Mirrors: curl -fsSL URL | sudo gpg --dearmor -o /usr/share/keyrings/...
    """
    raw_name = (dest_basename or "").strip() or default_keyring_filename_from_url(url)
    safe = _safe_keyring_basename(raw_name)
    if not safe:
        err("Invalid keyring filename (use a basename only, e.g. x-online.gpg).")
        return None
    dest = (APT_KEYRINGS_DIR / safe).resolve()

    if ctx.dry_run:
        info(f"Would: mkdir -p {APT_KEYRINGS_DIR} && curl -fsSL <url> | gpg --dearmor -o {dest}")
        return dest

    if not shutil.which("gpg"):
        err("gpg not found in PATH; cannot dearmor repository signing key.")
        return None

    try:
        req = Request(url, headers={"User-Agent": "OfflineHelper/1.0"})
        with urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except URLError as e:
        err(f"Failed to download keyring from URL: {e}")
        return None

    proc = subprocess.run(
        ["gpg", "--no-tty", "--batch", "--dearmor"],
        input=raw,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err(f"gpg --dearmor failed: {(proc.stderr or b'').decode(errors='replace')}")
        return None
    binary = proc.stdout
    if not binary:
        err("gpg --dearmor produced empty output.")
        return None

    APT_KEYRINGS_DIR.mkdir(parents=True, exist_ok=True)
    backup_file(dest, ctx)
    write_binary_file(dest, binary, ctx)
    info(f"Installed APT keyring: {dest}")
    return dest


def apt_signed_by_prefix(keyring_path: Path | None) -> str:
    if not keyring_path:
        return ""
    return f" [signed-by={keyring_path}]"


def extract_components_from_release_text(text: str) -> list[str] | None:
    """Parse the Components field from a Release / InRelease body (plain or clearsigned)."""
    m = re.search(r"(?m)^Components:\s*(.+)$", text)
    if not m:
        return None
    parts = m.group(1).strip().split()
    return parts if parts else None


def fetch_apt_repo_components(base_url: str, suite: str, ctx: Ctx) -> list[str] | None:
    """
    GET dists/<suite>/Release or InRelease and return the Components list.
    Skips network when ctx.dry_run (caller should use fallback).
    """
    if ctx.dry_run:
        return None
    root = base_url.rstrip("/")
    for fname in ("Release", "InRelease"):
        url = f"{root}/dists/{suite}/{fname}"
        try:
            req = Request(url, headers={"User-Agent": "OfflineHelper/1.0"})
            with urlopen(req, timeout=60) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            comps = extract_components_from_release_text(text)
            if comps:
                info(f"Detected APT components from {url}: {' '.join(comps)}")
                return comps
        except URLError as e:
            warn(f"Could not fetch {url}: {e}")
            continue
    return None


def resolve_apt_components_string(
    mirrors: dict[str, Any],
    base_url: str,
    suite: str,
    ctx: Ctx,
    fallback: list[str],
) -> str:
    """
    Space-separated component list for a deb line.
    Optional mirrors['aptComponents'] or ['apt_components'] overrides (e.g. 'main universe').
    Otherwise fetches Release; if that fails, uses fallback.
    """
    forced = mirrors.get("aptComponents") or mirrors.get("apt_components")
    if forced is not None and str(forced).strip():
        s = " ".join(str(forced).split())
        info(f"Using configured APT components: {s}")
        return s
    found = fetch_apt_repo_components(base_url, suite, ctx)
    if found:
        return " ".join(found)
    fb = " ".join(fallback)
    warn(f"Could not detect repository components from Release; using fallback: {fb}")
    return fb


def prompt_optional_apt_keyring(distro: str, mirrors: dict[str, Any]) -> None:
    if distro not in ("ubuntu", "debian", "kali"):
        return
    print()
    url = input("APT keyring URL (optional, Enter to skip; e.g. https://host/key.gpg): ").strip()
    if not url:
        return
    default_name = default_keyring_filename_from_url(url)
    name_hint = input(f"Filename under {APT_KEYRINGS_DIR} [{default_name}]: ").strip() or default_name
    mirrors["keyringUrl"] = url
    mirrors["keyringName"] = name_hint


# -------------------- DNS mode --------------------


def parse_dns_servers_arg(value: str) -> list[str]:
    """Parse comma/space-separated DNS server addresses."""
    parts = re.split(r"[\s,;]+", value.strip())
    return [p for p in parts if p]


def find_dns_provider_by_id(provider_id: str) -> dict[str, Any] | None:
    for p in DNS_PROVIDERS:
        if str(p.get("id", "")).lower() == provider_id.lower():
            return p
    return None


def find_linux_mirror_provider_by_id(provider_id: str) -> dict[str, Any] | None:
    for p in LINUX_MIRROR_PROVIDERS:
        if str(p.get("id", "")).lower() == provider_id.lower():
            return p
    return None


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


def dns_apply_method(
    servers: list[str],
    method: str,
    ctx: Ctx,
    nmcli_connection: str | None = None,
    windows_interface: str | None = None,
) -> bool:
    """Apply DNS using method name. Returns True if handled."""
    if method == "print":
        print_dns_commands(servers)
        return True
    if method == "resolv_conf":
        apply_dns_resolv_conf(servers, ctx)
        return True
    if method == "nmcli":
        apply_dns_nmcli(servers, ctx, connection=nmcli_connection)
        return True
    if method == "systemd_resolved":
        apply_dns_systemd_resolved(servers, ctx)
        return True
    if method == "windows_netsh":
        apply_dns_windows_netsh(servers, ctx, interface=windows_interface)
        return True
    return False


def dns_resolve_apply_method(
    servers: list[str],
    ctx: Ctx,
    manager_type: str,
    nmcli_connection: str | None = None,
    windows_interface: str | None = None,
) -> None:
    """Pick apply method from detected manager and run."""
    if manager_type == "resolve.conf":
        apply_dns_resolv_conf(servers, ctx)
    elif manager_type == "networkmanager":
        apply_dns_nmcli(servers, ctx, connection=nmcli_connection)
    elif manager_type == "systemd-resolved":
        apply_dns_systemd_resolved(servers, ctx)
    elif manager_type == "windows-netsh":
        apply_dns_windows_netsh(servers, ctx, interface=windows_interface)
    else:
        warn("No apply option for detected DNS manager; printing commands only.")
        print_dns_commands(servers)


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

                provider_labels = [f'{p["name"]} | {", ".join(p["dnsServers"])}' for p in providers]
                provider_labels.append("Custom — enter DNS server addresses manually")

                while True:
                    p_idx = ask_choice(
                        "Select DNS Provider",
                        provider_labels,
                        allow_back=True,
                    )
                    if p_idx < 0:
                        break

                    if p_idx == len(providers):
                        raw = input("DNS servers (comma or space separated): ").strip()
                        servers = parse_dns_servers_arg(raw)
                        if not servers:
                            warn("No DNS servers entered.")
                            continue
                        info("Custom DNS: " + ", ".join(servers))
                    else:
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


def apply_dns_nmcli(servers: list[str], ctx: Ctx, connection: str | None = None) -> None:
    if connection is None:
        conn = input('Connection name (example: "Wired connection 1"): ').strip()
    else:
        conn = connection.strip()
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


def apply_dns_windows_netsh(servers: list[str], ctx: Ctx, interface: str | None = None) -> None:
    if interface is None:
        nic = input('Windows interface name (example: "Ethernet"): ').strip() or "Ethernet"
    else:
        nic = interface.strip() or "Ethernet"
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


def prompt_custom_linux_mirrors(distro: str, release: str) -> dict[str, str] | None:
    """Interactive prompts to build a mirrors dict for apply_linux_repo_config."""
    info(f"Enter custom mirror URLs for detected distro: {distro}" + (f" ({release})" if release else ""))

    if distro == "ubuntu":
        u = input("Ubuntu archive base URL (example: https://mirror.example/ubuntu): ").strip().rstrip("/")
        if not u:
            return None
        return {"ubuntu": u + "/" if not u.endswith("/") else u}

    if distro == "kali":
        k = input("Kali archive base URL: ").strip().rstrip("/")
        if not k:
            return None
        return {"kali": k + "/" if not k.endswith("/") else k}

    if distro == "debian":
        main = input("Debian main mirror URL (example: https://mirror.example/debian): ").strip().rstrip("/")
        if not main:
            return None
        sec = input("Debian security mirror URL (optional, Enter to skip): ").strip().rstrip("/")
        out: dict[str, str] = {"debian": main + "/" if not main.endswith("/") else main}
        if sec:
            out["debianSecurity"] = sec + "/" if not sec.endswith("/") else sec
        return out

    if distro == "fedora":
        furl = input("Fedora mirror base URL (releases + updates tree root): ").strip().rstrip("/")
        if not furl:
            return None
        return {"fedora": furl + "/" if not furl.endswith("/") else furl}

    if distro == "almalinux":
        a = input("AlmaLinux mirror base URL: ").strip().rstrip("/")
        if not a:
            return None
        return {"almalinux": a + "/" if not a.endswith("/") else a}

    if distro in ("archlinux", "manjaro"):
        key = "archlinux" if distro == "archlinux" else "manjaro"
        s = input(
            f"Pacman Server URL line value (with $repo/$arch if needed, example: https://mirror/$repo/os/$arch): "
        ).strip()
        if not s:
            return None
        return {key: s}

    if distro == "alpine":
        print("Enter two repository lines (main and community), or a single base URL.")
        base = input("Alpine base URL (optional if you paste full lines next): ").strip().rstrip("/")
        line1 = input("Line 1 — main repo URL (or Enter to derive from base): ").strip()
        line2 = input("Line 2 — community repo URL (or Enter to derive from base): ").strip()
        if line1 and line2:
            return {"alpineMain": line1, "alpineCommunity": line2}
        if base:
            b = base + "/" if not base.endswith("/") else base
            return {
                "alpineMain": f"{b}{release}/main",
                "alpineCommunity": f"{b}{release}/community",
            }
        warn("Need either two repo lines or a base URL.")
        return None

    if distro == "opensuse":
        cmd = input(
            "Shell command to add repos (use <VERSION> for release; example: zypper addrepo ...): "
        ).strip()
        if not cmd:
            return None
        return {"opensuseReposCommand": cmd}

    warn("Custom mirror entry is not implemented for this distro in prompts.")
    return None


def _apt_keyring_path_from_mirrors(mirrors: dict[str, Any], distro: str, ctx: Ctx) -> Path | None:
    ku = mirrors.get("keyringUrl") or mirrors.get("keyring_url")
    if not ku:
        return None
    if distro not in ("ubuntu", "debian", "kali"):
        warn("keyringUrl is set but distro is not apt-based; ignoring keyring.")
        return None
    kn = mirrors.get("keyringName") or mirrors.get("keyring_name")
    return install_apt_keyring_from_url(str(ku), str(kn) if kn else None, ctx)


def apply_linux_repo_config(distro: str, release: str, mirrors: dict[str, Any], ctx: Ctx) -> None:
    """Write repo config for detected distro using provider-style mirrors dict."""
    post_change_update_cmd = ""

    apt_keyring: Path | None = None
    if distro in ("ubuntu", "debian", "kali"):
        apt_keyring = _apt_keyring_path_from_mirrors(mirrors, distro, ctx)
        wanted = mirrors.get("keyringUrl") or mirrors.get("keyring_url")
        if wanted and apt_keyring is None:
            err("Aborting: APT keyring installation failed.")
            return

    sb = apt_signed_by_prefix(apt_keyring)

    if distro == "ubuntu":
        comp_str = resolve_apt_components_string(
            mirrors,
            str(mirrors["ubuntu"]),
            release,
            ctx,
            fallback=["main"],
        )
        content = f"deb{sb} {mirrors['ubuntu']} {release} {comp_str}\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "kali":
        comp_str = resolve_apt_components_string(
            mirrors,
            str(mirrors["kali"]),
            "kali-rolling",
            ctx,
            fallback=["main", "contrib", "non-free", "non-free-firmware"],
        )
        content = f"deb{sb} {mirrors['kali']} kali-rolling {comp_str}\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "debian":
        main_comp = resolve_apt_components_string(
            mirrors,
            str(mirrors["debian"]),
            release,
            ctx,
            fallback=["main"],
        )
        main_line = f"deb{sb} {mirrors['debian']} {release} {main_comp}"
        sec_mirror = mirrors.get("debianSecurity")
        sec_line = ""
        if sec_mirror:
            sec_forced = mirrors.get("aptComponentsSecurity") or mirrors.get("apt_components_security")
            if sec_forced is not None and str(sec_forced).strip():
                sec_comp = " ".join(str(sec_forced).split())
                info(f"Using configured APT components (Debian security): {sec_comp}")
            else:
                sec_found = fetch_apt_repo_components(str(sec_mirror), f"{release}-security", ctx)
                sec_comp = " ".join(sec_found) if sec_found else "main"
                if not sec_found:
                    warn("Could not detect Debian security suite components; using main")
            sec_line = f"deb{sb} {sec_mirror} {release}-security {sec_comp}"
        content = "\n".join([x for x in [main_line, sec_line] if x]) + "\n"
        backup_file(Path("/etc/apt/sources.list"), ctx)
        write_text_file(Path("/etc/apt/sources.list"), content, ctx)
        post_change_update_cmd = "sudo apt update"
    elif distro == "fedora":
        fedora_url = str(mirrors["fedora"]).rstrip("/")
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
        alma_url = str(mirrors["almalinux"]).rstrip("/")
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
        main = str(mirrors.get("alpineMain", "")).replace("<VERSION>", release)
        community = str(mirrors.get("alpineCommunity", "")).replace("<VERSION>", release)
        if not main or not community:
            base = str(mirrors.get("alpine", "")).rstrip("/")
            main = main or f"{base}/{release}/main"
            community = community or f"{base}/{release}/community"
        content = f"{main}\n{community}\n"
        repo_path = Path("/etc/apk/repositories")
        backup_file(repo_path, ctx)
        write_text_file(repo_path, content, ctx)
        post_change_update_cmd = "sudo apk update"
    elif distro == "opensuse":
        command = str(mirrors["opensuseReposCommand"]).replace("<VERSION>", release)
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

    names = [p["name"] for p in providers]
    names.append("Custom mirror (enter URLs manually)")
    p_idx = ask_choice("Select mirror provider", names, allow_back=True)
    if p_idx < 0:
        return

    if p_idx == len(providers):
        custom = prompt_custom_linux_mirrors(distro, release)
        if not custom:
            warn("Custom mirror setup cancelled or incomplete.")
            return
        mirrors = dict(custom)
        info("Using custom mirror configuration.")
    else:
        provider = providers[p_idx]
        mirrors = dict(provider.get("mirrors", {}))
        if provider.get("keyringUrl"):
            mirrors["keyringUrl"] = provider["keyringUrl"]
        if provider.get("keyringName"):
            mirrors["keyringName"] = provider["keyringName"]
        info(f'Selected: {provider["name"]} for {distro}')

    prompt_optional_apt_keyring(distro, mirrors)

    if distro != "opensuse" and not require_root_for_file_writes():
        return

    apply_linux_repo_config(distro, release, mirrors, ctx)


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


# -------------------- CLI (non-interactive `run`) --------------------


def _mirrors_from_repo_cli_args(
    distro: str,
    release: str,
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Build mirrors dict from `run repo` flags; returns None if invalid."""
    if getattr(args, "provider_id", None):
        prov = find_linux_mirror_provider_by_id(args.provider_id)
        if not prov:
            err(f'Unknown linux mirror provider id: "{args.provider_id}"')
            return None
        if not provider_supports_distro(prov, distro):
            err(f'Provider "{args.provider_id}" does not support distro "{distro}".')
            return None
        mirrors = dict(prov.get("mirrors", {}))
        if prov.get("keyringUrl"):
            mirrors["keyringUrl"] = prov["keyringUrl"]
        if prov.get("keyringName"):
            mirrors["keyringName"] = prov["keyringName"]
        return mirrors

    if distro == "opensuse" and getattr(args, "custom_zypper_command", None):
        return {"opensuseReposCommand": args.custom_zypper_command.strip()}

    # Custom URLs
    if args.custom_url:
        u = args.custom_url.strip().rstrip("/")
        suf = "/" if not u.endswith("/") else ""
        if distro == "ubuntu":
            return {"ubuntu": u + suf}
        if distro == "kali":
            return {"kali": u + suf}
        if distro == "debian":
            out: dict[str, Any] = {"debian": u + suf}
            if getattr(args, "custom_security_url", None):
                s = args.custom_security_url.strip().rstrip("/")
                out["debianSecurity"] = s + ("/" if not s.endswith("/") else "")
            return out
        if distro == "fedora":
            return {"fedora": u + suf}
        if distro == "almalinux":
            return {"almalinux": u + suf}
        if distro in ("archlinux", "manjaro"):
            key = "archlinux" if distro == "archlinux" else "manjaro"
            return {key: args.custom_url.strip()}
        if distro == "alpine":
            if args.custom_alpine_main and args.custom_alpine_community:
                return {
                    "alpineMain": args.custom_alpine_main.strip(),
                    "alpineCommunity": args.custom_alpine_community.strip(),
                }
            b = u + suf
            return {
                "alpineMain": f"{b}{release}/main",
                "alpineCommunity": f"{b}{release}/community",
            }

    if distro == "alpine" and args.custom_alpine_main and args.custom_alpine_community:
        return {
            "alpineMain": args.custom_alpine_main.strip(),
            "alpineCommunity": args.custom_alpine_community.strip(),
        }

    err("For `run repo`, specify --provider-id or custom URL flags matching this distro (see --help).")
    return None


def cmd_run_dns(args: argparse.Namespace, ctx: Ctx) -> int:
    manager_type, _ = detect_dns_config()
    servers: list[str] = []

    if args.servers:
        servers = parse_dns_servers_arg(args.servers)
    elif args.provider_id:
        prov = find_dns_provider_by_id(args.provider_id)
        if not prov:
            err(f'Unknown DNS provider id: "{args.provider_id}"')
            return 2
        servers = list(prov.get("dnsServers") or [])
    else:
        err("Specify --servers or --provider-id.")
        return 2

    if not servers:
        err("No DNS servers resolved.")
        return 2

    action = args.action
    method = args.method

    if action == "print":
        print_dns_commands(servers)
        return 0

    if method == "auto":
        dns_resolve_apply_method(
            servers,
            ctx,
            manager_type,
            nmcli_connection=args.nmcli_connection,
            windows_interface=args.windows_interface,
        )
        return 0

    ok = dns_apply_method(
        servers,
        method,
        ctx,
        nmcli_connection=args.nmcli_connection,
        windows_interface=args.windows_interface,
    )
    return 0 if ok else 2


def cmd_run_repo(args: argparse.Namespace, ctx: Ctx) -> int:
    if not require_linux():
        return 2
    distro, release = detect_linux_distro_release()
    if not distro:
        err("Could not auto-detect distro from /etc/os-release.")
        return 2
    if distro == "ubuntu" and not release:
        err("Could not auto-detect Ubuntu codename.")
        return 2
    if distro == "debian" and not release:
        err("Could not auto-detect Debian codename.")
        return 2
    if distro == "alpine" and not release:
        err("Could not auto-detect Alpine version.")
        return 2
    if distro == "opensuse" and not release:
        err("Could not auto-detect OpenSUSE version.")
        return 2

    info(f"Detected distro: {distro}" + (f", release: {release}" if release else ""))

    mirrors = _mirrors_from_repo_cli_args(distro, release, args)
    if not mirrors:
        return 2

    if getattr(args, "keyring_url", None):
        if distro not in ("ubuntu", "debian", "kali"):
            warn("--keyring-url only applies to apt-based distros (Ubuntu/Debian/Kali); ignoring.")
        else:
            mirrors["keyringUrl"] = args.keyring_url.strip()
            if getattr(args, "keyring_name", None):
                mirrors["keyringName"] = args.keyring_name.strip()

    if getattr(args, "apt_components", None):
        mirrors["aptComponents"] = args.apt_components.strip()

    if distro != "opensuse" and not require_root_for_file_writes():
        return 2

    apply_linux_repo_config(distro, release, mirrors, ctx)
    return 0


def cmd_run_docker(args: argparse.Namespace, ctx: Ctx) -> int:
    if not args.mirror_id:
        err("Specify --mirror-id (see providers.json docker_mirrors).")
        return 2
    mid = args.mirror_id.lower()
    mirror = next((x for x in DOCKER_MIRRORS if str(x.get("id", "")).lower() == mid), None)
    if not mirror:
        err(f'Unknown Docker mirror id: "{args.mirror_id}"')
        return 2
    info(f'Selected Docker mirror: {mirror["name"]} -> {mirror["url"]}')
    if not require_linux():
        return 2
    if not require_root_for_file_writes():
        return 2
    daemon_path = Path("/etc/docker/daemon.json")
    backup_file(daemon_path, ctx)
    cfg = {
        "insecure-registries": [mirror["url"]],
        "registry-mirrors": [mirror["url"]],
    }
    write_text_file(daemon_path, json.dumps(cfg, indent=2) + "\n", ctx)
    if args.restart_docker:
        run_command("sudo systemctl daemon-reload", ctx, shell=True)
        run_command("sudo systemctl restart docker", ctx, shell=True)
    run_command('docker info | grep -i "Registry Mirrors"', ctx, shell=True)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Offline network helper: interactive menu by default, or `run` for non-interactive use.",
    )
    p.add_argument("--dry-run", action="store_true", help="Print commands / file contents only.")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    run_p = sub.add_parser("run", help="Run one action from arguments (no prompts).")
    run_sub = run_p.add_subparsers(dest="run_target", required=True, metavar="ACTION")

    dns_p = run_sub.add_parser("dns", help="Apply or print DNS settings.")
    dns_src = dns_p.add_mutually_exclusive_group(required=True)
    dns_src.add_argument(
        "--servers",
        metavar="LIST",
        help="Comma/space-separated DNS IPs.",
    )
    dns_src.add_argument(
        "--provider-id",
        metavar="ID",
        help="DNS provider id from providers.json.",
    )
    dns_p.add_argument(
        "--action",
        choices=("print", "apply"),
        default="apply",
        help="print = show sample commands only; apply = change system DNS.",
    )
    dns_p.add_argument(
        "--method",
        choices=("auto", "print", "resolv_conf", "nmcli", "systemd_resolved", "windows_netsh"),
        default="auto",
        help="With --action apply: auto = use detected manager; or force a backend.",
    )
    dns_p.add_argument(
        "--nmcli-connection",
        metavar="NAME",
        help="Required for nmcli when connection cannot be prompted (non-interactive).",
    )
    dns_p.add_argument(
        "--windows-interface",
        metavar="NAME",
        default="Ethernet",
        help="Interface name for Windows netsh (default: Ethernet).",
    )

    repo_p = run_sub.add_parser("repo", help="Configure Linux package mirrors on this machine.")
    repo_p.add_argument("--provider-id", metavar="ID", help="linux_mirror_providers id from providers.json.")
    repo_p.add_argument(
        "--custom-url",
        metavar="URL",
        help="Custom mirror: meaning depends on distro (Ubuntu/Kali/Debian main/Fedora/Alma/arch+manjaro Server value/Alpine base).",
    )
    repo_p.add_argument(
        "--custom-security-url",
        metavar="URL",
        help="Debian security mirror (with --custom-url as main).",
    )
    repo_p.add_argument(
        "--custom-alpine-main",
        metavar="URL",
        help="Alpine main repository line (with --custom-alpine-community).",
    )
    repo_p.add_argument(
        "--custom-alpine-community",
        metavar="URL",
        help="Alpine community repository line.",
    )
    repo_p.add_argument(
        "--custom-zypper-command",
        metavar="SHELL",
        help="OpenSUSE: shell command to add repos; use <VERSION> for detected release.",
    )
    repo_p.add_argument(
        "--keyring-url",
        metavar="URL",
        help="Ubuntu/Debian/Kali: download signing key, gpg --dearmor to /usr/share/keyrings, add signed-by to deb lines.",
    )
    repo_p.add_argument(
        "--keyring-name",
        metavar="FILE",
        help="Basename under /usr/share/keyrings (default: from URL path, e.g. x-online.gpg).",
    )
    repo_p.add_argument(
        "--apt-components",
        metavar="LIST",
        help="Ubuntu/Debian/Kali: override deb components (space-separated). Skips Release fetch.",
    )

    dock_p = run_sub.add_parser("docker", help="Write /etc/docker/daemon.json registry mirror.")
    dock_p.add_argument("--mirror-id", metavar="ID", required=True, help="docker_mirrors id from providers.json.")
    dock_p.add_argument(
        "--restart-docker",
        action="store_true",
        help="Run systemctl restart docker after writing daemon.json.",
    )

    return p


def interactive_main(ctx: Ctx) -> int:
    print(logo())

    if ctx.dry_run:
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


def main() -> int:
    parser = build_arg_parser()
    args, unknown = parser.parse_known_args()
    if unknown:
        err(f"Unknown arguments: {' '.join(unknown)}")
        return 2

    ctx = Ctx(dry_run=args.dry_run)

    if args.command == "run":
        if args.run_target == "dns":
            return cmd_run_dns(args, ctx)
        if args.run_target == "repo":
            return cmd_run_repo(args, ctx)
        if args.run_target == "docker":
            return cmd_run_docker(args, ctx)
        err(f"Unhandled run target: {args.run_target}")
        return 2

    if args.command is not None:
        err("Only `run` is supported as a subcommand. Use: OfflineHelper.py run <action> ...")
        return 2

    return interactive_main(ctx)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise SystemExit(130)
