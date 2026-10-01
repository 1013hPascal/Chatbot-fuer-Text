"""Hardwarebericht (Phase 0). Liest die tatsächliche Ausstattung des Rechners aus."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys

import psutil


def _powershell_json(command: str):
    """Führt einen PowerShell-Befehl aus, der JSON ausgibt. Bei Fehler: None."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"{command} | ConvertTo-Json -Depth 3"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(out.stdout) if out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def gpu_names() -> list[str]:
    data = _as_list(_powershell_json("Get-CimInstance Win32_VideoController | "
                                     "Select-Object Name"))
    return [d["Name"] for d in data if d.get("Name")]


def vulkan_devices() -> list[str]:
    exe = shutil.which("vulkaninfo")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--summary"], capture_output=True, text=True, timeout=30,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split("=", 1)[1].strip() for line in out.splitlines()
            if line.strip().startswith("deviceName")]


def collect() -> dict:
    cpu = _as_list(_powershell_json(
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,"
        "NumberOfLogicalProcessors,MaxClockSpeed"))
    modules = _as_list(_powershell_json(
        "Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel,Capacity,Speed,"
        "ConfiguredClockSpeed,SMBIOSMemoryType"))
    system = _powershell_json("Get-CimInstance Win32_ComputerSystem | "
                              "Select-Object Manufacturer,Model,SystemFamily") or {}
    video = _as_list(_powershell_json("Get-CimInstance Win32_VideoController | "
                                      "Select-Object Name,DriverVersion"))
    power = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    ollama = subprocess.run(["ollama", "--version"], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip() \
        if shutil.which("ollama") else "nicht gefunden"
    speeds = {m.get("ConfiguredClockSpeed") or m.get("Speed") for m in modules}
    return {
        "rechner": system,
        "prozessor": cpu,
        "arbeitsspeicher_gesamt_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "speicher_module": {
            "anzahl": len(modules),
            "gesamt_gb": round(sum(m.get("Capacity", 0) for m in modules) / 2**30, 1),
            "takt_mts": sorted(s for s in speeds if s),
            "hinweis": "Bei aufgelöteten Speicherchips (LPDDR5X) zählt jeder Chip als "
                       "Modul. Die Anzahl sagt dann nichts über Dual-Channel.",
        },
        "grafik": video,
        "vulkan_geraete": vulkan_devices(),
        "freier_speicherplatz_gb": round(shutil.disk_usage("C:\\").free / 2**30, 1),
        "python": sys.version.split()[0],
        "windows": platform.platform(),
        "energiemodus": power,
        "ollama": ollama,
    }


def recommend_model_size(total_ram_gb: float) -> str:
    """Richtwert aus Abschnitt 4.5: Modelldatei höchstens etwa halber Arbeitsspeicher."""
    if total_ram_gb >= 30:
        return "bis etwa 12 bis 14 Milliarden Parameter (Q4_K_M)"
    if total_ram_gb >= 14:
        return "etwa 3 bis 8 Milliarden Parameter (Q4_K_M)"
    return "bis etwa 3 Milliarden Parameter (Q4_K_M)"
