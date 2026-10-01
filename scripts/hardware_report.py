"""Schreibt hardware_report.json in den Projektordner und gibt eine Kurzfassung aus."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import hardware  # noqa: E402


def main() -> None:
    report = hardware.collect()
    (ROOT / "hardware_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    cpu = report["prozessor"][0] if report["prozessor"] else {}
    print("Rechner:", report["rechner"].get("Model"), report["rechner"].get("SystemFamily"))
    print("Prozessor:", cpu.get("Name"), f'({cpu.get("NumberOfCores")} Kerne)')
    print("Arbeitsspeicher:", report["arbeitsspeicher_gesamt_gb"], "GB,",
          report["speicher_module"]["takt_mts"], "MT/s")
    print("Grafik:", [g["Name"] for g in report["grafik"]])
    print("Vulkan-Geräte:", report["vulkan_geraete"] or "keine gefunden")
    print("Energiemodus:", report["energiemodus"])
    print("Empfohlene Modellgröße:",
          hardware.recommend_model_size(report["arbeitsspeicher_gesamt_gb"]))
    print("Bericht gespeichert: hardware_report.json")


if __name__ == "__main__":
    main()
