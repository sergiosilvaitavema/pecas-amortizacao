import configparser
import os
from datetime import date, datetime
from pathlib import Path

from rpaflow.ini import Ini
from rpaflow.json import Json
from rpaflow.log import Log


class Config:

    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent.parent
        secrets_path = base_dir / "secrets.ini"
        settings_path = base_dir / "settings.ini"

        self._secrets = Ini(filepath=str(secrets_path))
        self._settings = Ini(filepath=str(settings_path))
        self._secrets._config._interpolation = configparser.RawConfigParser()._interpolation

        log_path = base_dir / "logs" / "execucao.log"
        os.makedirs(log_path.parent, exist_ok=True)
        self._log = Log(
            path=str(log_path),
            level="DEBUG",
            format_console="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <level>{level: <8}</level> - {message}",
            format_file="{time:YYYY-MM-DD HH:mm:ss} - {level: <8} - {message}",
        )

        config_pecas_path = self._settings.get("FLOORPLAN", "caminho_config_pecas")
        self._pecas = Json().load(config_pecas_path)

    @property
    def log(self) -> Log:
        return self._log

    # ─── Portal FIDC ─────────────────────────────
    @property
    def fidc_site(self) -> str:
        return self._secrets.get("PORTAL_FIDC", "site")

    @property
    def fidc_user(self) -> str:
        return self._secrets.get("PORTAL_FIDC", "usuario")

    @property
    def fidc_password(self) -> str:
        return self._secrets.get("PORTAL_FIDC", "senha")

    # ─── Portal Floorplan ────────────────────────
    @property
    def floorplan_site(self) -> str:
        return self._secrets.get("PORTAL_FLOORPLAN", "site")

    @property
    def floorplan_user(self) -> str:
        return self._secrets.get("PORTAL_FLOORPLAN", "usuario")

    @property
    def floorplan_password(self) -> str:
        return self._secrets.get("PORTAL_FLOORPLAN", "senha")

    # ─── Configurações Floorplan ──────────────────
    @property
    def data_inicio(self) -> date:
        raw = self._pecas.get("data_inicio")
        return datetime.strptime(raw, "%Y-%m-%d").date()

    @property
    def data_fim(self) -> date:
        raw = self._pecas.get("data_fim")
        return datetime.strptime(raw, "%Y-%m-%d").date()

    @property
    def empresa(self) -> str:
        return self._settings.get("FLOORPLAN", "empresa")

    @property
    def menu_pecas(self) -> str:
        return self._settings.get("FLOORPLAN", "menu_pecas")

    @property
    def menu_pagamento(self) -> str:
        return self._settings.get("FLOORPLAN", "menu_pagamento")

    @property
    def menu_amortizacao(self) -> str:
        return self._settings.get("FLOORPLAN", "menu_amortizacao")

    @property
    def select_opcao(self) -> str:
        return self._settings.get("FLOORPLAN", "select_opcao")

    # ─── Banco de dados ─────────────────────────
    @property
    def db_ip(self) -> str:
        return self._secrets.get("BANCO", "ip")

    @property
    def db_database(self) -> str:
        return self._secrets.get("BANCO", "database")

    @property
    def db_user(self) -> str:
        return self._secrets.get("BANCO", "user")

    @property
    def db_password(self) -> str:
        return self._secrets.get("BANCO", "pass")

    @property
    def processo(self) -> str:
        return "Renault Floorplan Saldo Dividas"
