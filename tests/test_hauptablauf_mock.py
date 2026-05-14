"""Integrationstests mit Mock-ESP."""
import time, pytest, yaml

from plattenwechsler.config import Config
from plattenwechsler.core.fehler import FehlerBehandlung
from plattenwechsler.core.hauptablauf import Hauptablauf
from plattenwechsler.io_.gpio_manager import GpioManager
from plattenwechsler.io_.mock_esp_client import MockEspClient
from plattenwechsler.types import (
    SystemState, ErrorClass, AuftragQuelle, DruckerConfig,
)


TEST_CFG = {
    "system": {"log_level": "WARNING", "log_file": "/tmp/x.log"},
    "esp": {"port": "/dev/null", "baud": 115200, "ack_timeout_s": 1.0,
            "move_timeout_s": 5.0, "home_timeout_s": 5.0, "mech_timeout_s": 3.0,
            "heartbeat_timeout_s": 5.0, "reconnect_intervall_s": 1.0,
            "read_timeout_s": 0.1},
    "gpio": {"endschalter": {"x": 24, "z": 25}, "not_aus": None},
    "drucker": [
        {"id": 1, "name": "Drucker 1", "pin_fertig": 17,
         "pos_x": 100, "pos_z_anfahr": 200, "pos_z_tuer": 250,
         "pos_z_druckbett": 50, "door_arm_hub_mm": 50},
        {"id": 2, "name": "Drucker 2", "pin_fertig": 27,
         "pos_x": 400, "pos_z_anfahr": 200, "pos_z_tuer": 250,
         "pos_z_druckbett": 50, "door_arm_hub_mm": 50},
    ],
    "positionen": {
        "ablage":  {"x": 1200, "z": 100},
        "magazin": {"x": 1300, "z": 150},
    },
    "mqtt": {"enabled": False}, "telegram": {"enabled": False},
}


@pytest.fixture
def setup(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(TEST_CFG))
    cfg = Config(yaml.safe_load(cfg_file.read_text()), source_path=cfg_file)

    esp = MockEspClient(move_dauer_s=0.05, home_dauer_s=0.1,
                        mech_dauer_s=0.05)
    gpio = GpioManager(drucker_fertig_pins=cfg.gpio_drucker_fertig(),
                       endschalter_pins=cfg.gpio_endschalter(),
                       force_mock=True)
    gpio.setup()
    fehler = FehlerBehandlung()
    ha = Hauptablauf(cfg, esp, gpio, fehler)

    esp.start(); ha.start()
    deadline = time.time() + 3.0
    while time.time() < deadline and ha.state != SystemState.BEREITSCHAFT:
        time.sleep(0.05)

    yield {"cfg": cfg, "esp": esp, "ha": ha, "gpio": gpio, "fehler": fehler}
    ha.stop(); esp.stop(); gpio.teardown()


def warte(ha, state, t=3.0):
    deadline = time.time() + t
    while time.time() < deadline:
        if ha.state == state: return True
        time.sleep(0.02)
    return False


def warte_queue_leer(ha, t=20.0):
    deadline = time.time() + t
    while time.time() < deadline:
        if ha.queue.is_empty() and ha.state == SystemState.BEREITSCHAFT:
            return True
        time.sleep(0.05)
    return False


class TestGrundlagen:
    def test_init_erreicht_bereitschaft(self, setup):
        assert setup["ha"].state == SystemState.BEREITSCHAFT
        assert setup["esp"].status.referenced

    def test_kompletter_plattenwechsel(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        assert ha.auftrag_aufnehmen(2, AuftragQuelle.HMI)
        assert warte_queue_leer(ha, t=20.0)
        assert ha.stats.auftraege_erfolgreich == 1
        assert not esp.status.has_plate
        assert not ha.fehler.hat_fehler

    def test_dedup(self, setup):
        ha = setup["ha"]
        assert ha.auftrag_aufnehmen(1, AuftragQuelle.HMI)
        assert not ha.auftrag_aufnehmen(1, AuftragQuelle.HMI)


class TestFehler:
    def test_obstacle(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        esp.simuliere_fehler = "OBSTACLE"
        ha.auftrag_aufnehmen(1, AuftragQuelle.HMI)
        assert warte(ha, SystemState.FEHLER, t=5.0)
        assert ha.fehler.aktiver_fehler.klasse == ErrorClass.HINDERNIS

    def test_quittierung(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        esp.simuliere_fehler = "OBSTACLE"
        ha.auftrag_aufnehmen(2, AuftragQuelle.HMI)
        assert warte(ha, SystemState.FEHLER, t=5.0)
        esp.simuliere_fehler = None
        ha.fehler.quittieren()
        assert warte(ha, SystemState.BEREITSCHAFT, t=5.0)

    def test_tuer_oeffnet_nicht(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        # Türsensor meldet door_open=0 trotz Türarm AUF
        esp.tuer_offen_wenn_arm_aus = False
        ha.auftrag_aufnehmen(1, AuftragQuelle.HMI)
        assert warte(ha, SystemState.FEHLER, t=10.0)
        assert ha.fehler.aktiver_fehler.klasse == ErrorClass.TUERFEHLER


class TestService:
    def test_modus_aktivieren(self, setup):
        ha = setup["ha"]
        assert ha.service_modus_aktivieren()
        assert ha.state == SystemState.SERVICE
        ha.service_modus_verlassen()
        assert ha.state == SystemState.BEREITSCHAFT

    def test_fahre_zu_drucker(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        assert ha.service_modus_aktivieren()
        assert ha.service_fahre_zu_drucker(2)
        assert esp.status.x_mm == 400

    def test_fahre_zu_position(self, setup):
        ha = setup["ha"]; esp = setup["esp"]
        assert ha.service_modus_aktivieren()
        assert ha.service_fahre_zu_position("ablage")
        assert esp.status.x_mm == 1200
        assert esp.status.z_mm == 100

    def test_auftrag_im_service_abgelehnt(self, setup):
        ha = setup["ha"]
        ha.service_modus_aktivieren()
        assert not ha.auftrag_aufnehmen(1, AuftragQuelle.HMI)


class TestDruckerVerwaltung:
    def test_hinzufuegen_und_entfernen(self, setup):
        cfg = setup["cfg"]
        assert len(cfg.drucker_liste()) == 2
        new_id = cfg.naechste_freie_drucker_id()
        assert new_id == 3
        cfg.drucker_setzen(DruckerConfig(id=new_id, name="Test",
            pos_x=2000, pos_z_anfahr=100, pos_z_tuer=150,
            pos_z_druckbett=20, door_arm_hub_mm=40, pin_fertig=5))
        assert cfg.drucker(3) is not None
        assert cfg.drucker_entfernen(3)
        assert cfg.drucker(3) is None

    def test_aendern(self, setup):
        cfg = setup["cfg"]
        d = cfg.drucker(1)
        d.pos_x = 999
        cfg.drucker_setzen(d)
        assert cfg.drucker(1).pos_x == 999

    def test_persistenz(self, setup, tmp_path):
        cfg = setup["cfg"]
        d = cfg.drucker(1)
        d.pos_x = 1234
        cfg.drucker_setzen(d)
        # Nochmal laden
        cfg2 = Config(yaml.safe_load((tmp_path / "config.yaml").read_text()),
                      source_path=tmp_path / "config.yaml")
        assert cfg2.drucker(1).pos_x == 1234
