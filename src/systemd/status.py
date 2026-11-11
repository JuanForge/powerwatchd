import traceback
from typing import Literal

from pydbus import SystemBus


def status(name: str, bus) -> dict[
                                                    Literal["status", "boot"],
                                                    Literal[
                                                        "active", "reloading", "inactive", "failed",
                                                        "activating", "deactivating", "maintenance",
                                                        "unknown", "error",
                                                        "enabled", "disabled", "static", "indirect", "masked"
                                                    ]
                                                ] | None:
    """
    - False:            Erreur.
    
    - status
        - "active":        🟢 Actif
        - "reloading":     🔄 Rechargement
        - "inactive":      ⚪ Inactif
        - "failed":        🔴 Échec
        - "activating":    🟡 Démarrage en cours
        - "deactivating":  🟠 Arrêt en cours
        - "maintenance":   🛠️ Maintenance
        - "unknown":       ❓ Inconnu
    
    - boot :
        - "enabled"	    Lancé au boot.
        - "disabled"	Pas lancé au boot.
        - "static"	    Le service n’a pas de section [Install]. 0x05
        - "indirect"	Activé indirectement par une autre unité via un lien dans un dossier target.
        - "masked"	    Le service est masqué.
    """
    try:
        systemd = bus.get(".systemd1")
        
        full_unit_name = f"{name}.service"
        unit_path = systemd.GetUnit(full_unit_name)
        enabled_state = systemd.GetUnitFileState(full_unit_name)
        unit = bus.get(".systemd1", unit_path)
        
        return {"status": unit.ActiveState,
                "boot": enabled_state}
    except Exception:  # noqa: BLE001
        print(f"[❌] Error for {name} : {traceback.format_exc()}")
        return None