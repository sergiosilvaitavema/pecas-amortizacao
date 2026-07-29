import re
import unicodedata
from time import sleep

from rpaflow.browser import Browser

from src.core.config import Config


class PortalFidc:
    """Automação de acesso ao portal FIDC Renault."""

    # ─── Login ───────────────────────────────────
    INPUT_USER = "//input[@id='email']"
    INPUT_PASS = "//input[@id='senha']"
    BTN_LOGIN = "//button[text()='Login']"

    # ─── Navegação ───────────────────────────────
    MENU_LIMITES = "//a[normalize-space()='Limites de Crédito']"
    MENU_LIMITE_ATUAL = "//a[normalize-space()='Limite Atual']"

    # ─── Tabela ──────────────────────────────────
    TABELA_LIMITES = "//table[@id='tbLimites']"
    HEADER_SPAN = "//span[@class='dt-column-title']"

    def __init__(self, config: Config, browser: Browser):
        self._config = config
        self._browser = browser
        self._log = config.log

    def executar(self) -> dict:
        """Fluxo: login → navegar → extrair limites. Retorna dict com valores."""
        self._log.info("[FIDC] Iniciando acesso ao portal FIDC")
        self._login()
        self._navegar_limites()
        dados = self._extrair_limites()
        self._log.info(f"[FIDC] Limites extraídos: {dados}")
        return dados

    def _login(self) -> None:
        """Realiza login no FIDC."""
        self._log.info("[FIDC] Realizando login")
        self._browser.fill_text(self.INPUT_USER, self._config.fidc_user)
        self._browser.fill_text(self.INPUT_PASS, self._config.fidc_password)
        self._browser.click(self.BTN_LOGIN)
        self._esperar_carregar()

    def _navegar_limites(self) -> None:
        """Navega para Limites de Crédito > Limite Atual."""
        self._log.info("[FIDC] Navegando para Limites de Crédito")
        self._browser.click(self.MENU_LIMITES, timeout=10000)
        self._browser.click(self.MENU_LIMITE_ATUAL, timeout=10000)
        self._esperar_carregar()

    def _extrair_limites(self) -> dict:
        """Extrai dados da tabela tbLimites como dict chave→valor."""
        self._log.info("[FIDC] Extraindo tabela de limites")

        page = self._browser.page
        tabela = page.locator(self.TABELA_LIMITES)
        tabela.wait_for(state="visible", timeout=15000)

        # Extrair headers (antes do <br>)
        headers_raw = tabela.locator("xpath=.//thead//span[@class='dt-column-title']").all()
        chaves = []
        for span in headers_raw:
            texto = span.evaluate("""
                (el) => {
                    var text = '';
                    for (var node of el.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            text += node.textContent;
                        }
                    }
                    return text.trim();
                }
            """)
            chaves.append(self._normalizar_chave(texto))

        # Extrair valores do tbody (única linha)
        valores = tabela.locator("xpath=.//tbody//tr").first.locator("xpath=.//td").all_text_contents()
        valores = [v.strip() for v in valores]

        # Montar dict
        dados = {}
        for i, chave in enumerate(chaves):
            if i < len(valores):
                dados[chave] = valores[i]

        return dados

    @staticmethod
    def _normalizar_chave(texto: str) -> str:
        """Normaliza chave: minúsculo, sem acento, espaço→underscore."""
        # Remove acentos
        nfkd = unicodedata.normalize("NFKD", texto)
        sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
        # Minúsculo e underscore
        return sem_acento.lower().strip().replace(" ", "_")

    def _esperar_carregar(self) -> None:
        """Espera a página carregar."""
        try:
            self._browser.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            sleep(5)
