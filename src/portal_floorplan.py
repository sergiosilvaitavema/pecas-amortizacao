from datetime import datetime
from time import sleep

from rpaflow.browser import Browser

from src.core.config import Config
from src.db_floorplan import (
    aguardar_token_do_banco,
    gravar_status_robo,
    limpar_mensagens,
    logar_mensagem,
)


class PortalFloorplan:
    """Automação de acesso ao portal Floorplan Renault."""

    # ─── Botão "Acessar portal" ─────────────────
    BTN_ACESSAR_PORTAL = "//button[normalize-space()='Acessar portal']"

    # ─── Shadow DOM (via propriedade sr) ─────────
    INPUT_USER = "#inputUser"
    INPUT_PASS = "#inputPassword"

    # ─── Botão login (fora do shadow) ────────────
    BTN_LOGIN = "//button[@id='kc-form-login-btn']"

    # ─── Verificação em duas etapas ─────────────
    CHECKBOX_PHONE = '//input[@id="email"]/ancestor::label[1]//span[@class="checkmark"]'
    BTN_SEND_CODE = '//button[@id="sendButton"]'
    INPUT_TOKEN = '//input[@id="token"]'

    # ─── Seleção de empresa ─────────────────────
    INPUT_BARRA = "//input[starts-with(@id,'Form_BarraNavegacao')]"

    # ─── Select option ──────────────────────────
    SELECT_CABECALHO = "//select[starts-with(@id,'form_dados_cabecalho')]"

    # ─── Status de processamento ────────────────
    ST_PENDENTE = "PENDENTE"
    ST_PROCESSADO = "PROCESSADO"
    ST_FALHA = "FALHA"

    # ─── Paginação ──────────────────────────────
    BTN_NEXT_PAGE_DISABLED = "//a[contains(@class,'ui-paginator-next') and contains(@class,'ui-state-disabled')]"
    PAGINATOR_NUM = "//span[@class='ui-paginator-pages']/a[text()='{}']"
    PAGINATOR_NUM_ACTIVE = "//span[@class='ui-paginator-pages']/a[text()='{}' and contains(@class,'ui-state-active')]"

    # ─── Tabela ─────────────────────────────────
    LINHAS_TABELA = "//table[@role='grid']/tbody/tr"
    LINK_NF = "//table[@role='grid']/tbody/tr[{}]/td[1]/a[@class='linkPagina']"
    COL_VENCIMENTO = "//table[@role='grid']/tbody/tr[{}]/td[4]"

    def __init__(self, config: Config, browser: Browser, db_conn, id_execucao: int):
        self._config = config
        self._browser = browser
        self._log = config.log
        self._db_conn = db_conn
        self._id_execucao = id_execucao

        # ─── XPaths dinâmicos (dependem de config) ───
        empresa = config.empresa
        self.CARD_EMPRESA = (
            f"//button[@class='cadastro-card' and "
            f"contains(normalize-space(),'{empresa}')]"
        )
        self.MENU_PECAS = f"//a[normalize-space()='{config.menu_pecas}']"
        self.MENU_PAGAMENTO = f"(//a[normalize-space()='{config.menu_pagamento}'])[last()]"
        self.MENU_AMORTIZACAO = f"//a[normalize-space()='{config.menu_amortizacao}']"

    # ════════════════════════════════════════════
    #  Fluxo principal
    # ════════════════════════════════════════════

    def executar(self) -> None:
        """Fluxo completo: portal → login → empresa → tabela → vencimentos."""
        self._log.info("[Floorplan] Iniciando acesso ao portal Floorplan")
        limpar_mensagens(self._db_conn)
        logar_mensagem(self._db_conn, "Robo iniciado")

        try:
            self._abrir_portal()
            self._login()
            self._log.info("[Floorplan] Login concluído")
            logar_mensagem(self._db_conn, "Login concluído")

            self._browser.switch_to_tab(0)

            self._selecionar_empresa()
            self._selecionar_opcao()
            self._processar_vencimentos()

            gravar_status_robo(self._db_conn, self._id_execucao, "SUCESSO")
            logar_mensagem(self._db_conn, "Robo finalizado")
        except Exception as e:
            self._log.error(f"[Floorplan] Erro na execução: {e}")
            gravar_status_robo(self._db_conn, self._id_execucao, "ERRO")
            logar_mensagem(self._db_conn, f"ERRO: {e}")
            raise

    # ════════════════════════════════════════════
    #  Portal / Login
    # ════════════════════════════════════════════

    def _abrir_portal(self) -> None:
        """Clica 'Acessar portal' e captura nova janela."""
        self._log.info("[Floorplan] Clicando em 'Acessar portal'")

        page = self._browser.page
        with page.context.expect_page() as new_page_info:
            self._browser.click(self.BTN_ACESSAR_PORTAL, timeout=15000)

        nova_pagina = new_page_info.value
        nova_pagina.wait_for_load_state("domcontentloaded")

        for _ in range(30):
            if len(self._browser.get_tabs()) > 1:
                break
            sleep(1)

        tabs = self._browser.get_tabs()
        self._browser.switch_to_tab(len(tabs) - 1)
        self._esperar_carregar()

    def _login(self) -> None:
        """Realiza login via shadow DOM (propriedade sr)."""
        self._log.info("[Floorplan] Realizando login (shadow DOM)")

        page = self._browser.page

        page.locator("login-form").wait_for(state="attached", timeout=30000)
        sleep(2)

        page.evaluate(f"""
            (function() {{
                var el = document.querySelector('login-form');
                var sr = el.sr;

                var userInput = sr.querySelector('{self.INPUT_USER}');
                var passInput = sr.querySelector('{self.INPUT_PASS}');

                userInput.value = '{self._config.floorplan_user}';
                userInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                userInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

                passInput.value = '{self._config.floorplan_password}';
                passInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                passInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }})()
        """)
        self._log.info("[Floorplan] Credenciais preenchidas")
        logar_mensagem(self._db_conn, "Credenciais preenchidas")

        self._browser.click(self.BTN_LOGIN, timeout=10000)
        self._esperar_carregar()

        sleep(2)
        self._browser.click(self.CHECKBOX_PHONE, timeout=10000)
        sleep(1)
        self._browser.click(self.BTN_SEND_CODE, timeout=10000)
        self._log.info("[Floorplan] Codigo de verificacao enviado")
        logar_mensagem(self._db_conn, "Codigo de verificação enviado. Aguardando token...")
        self._esperar_carregar()
        sleep(1)

        # Sinaliza ao C# que está aguardando o token
        gravar_status_robo(self._db_conn, self._id_execucao, "ESPERANDO_TOKEN")
        self._log.info("[Floorplan] Aguardando token via banco de dados...")
        logar_mensagem(self._db_conn, "Robô aguardando token do usuário")

        # Aguarda o token ser inserido pelo usuário na tela C#
        token = aguardar_token_do_banco(self._db_conn, self._id_execucao)
        self._log.info("[Floorplan] Token recebido com sucesso")
        logar_mensagem(self._db_conn, "Token recebido. Processando login...")

        self._browser.fill_text(self.INPUT_TOKEN, text=token, timeout=10000)
        sleep(0.2)
        self._browser.click(self.BTN_LOGIN, timeout=10000)
        self._esperar_carregar()

    # ════════════════════════════════════════════
    #  Navegação do portal
    # ════════════════════════════════════════════

    def _selecionar_empresa(self) -> None:
        """Seleciona empresa e navega até 'Amortização Por Relação'."""
        self._log.info(f"[Floorplan] Selecionando empresa {self._config.empresa}")
        self._browser.click(self.CARD_EMPRESA, timeout=15000)
        self._esperar_carregar()

        self._browser.click(self.INPUT_BARRA, timeout=10000)
        self._browser.hover(self.MENU_PECAS, timeout=10000)
        self._browser.hover(self.MENU_PAGAMENTO, timeout=10000)
        self._browser.click(self.MENU_AMORTIZACAO, timeout=10000)
        self._esperar_carregar()
        self._log.info("[Floorplan] Navegação até Amortização concluída")

    def _selecionar_opcao(self) -> None:
        """Seleciona option no select de cabeçalho."""
        valor = self._config.select_opcao
        self._log.info(f"[Floorplan] Selecionando option '{valor}'")

        select = self._browser.find_element_in_frames(self.SELECT_CABECALHO, timeout=15000)
        select.select_option(value=valor)
        self._esperar_carregar()
        self._log.info(f"[Floorplan] Option '{valor}' selecionada")

    # ════════════════════════════════════════════
    #  Processamento de vencimentos
    # ════════════════════════════════════════════

    def _processar_vencimentos(self) -> None:
        """Percorre páginas usando last(), processando uma NF por vez.

        Fluxo simples:
        1. Navega até a página (usa last() se não visível)
        2. Coleta NFs do range
        3. Se tem NF pendente → processa, go_back, repete
        4. Se não tem → avança pra próxima página
        """
        self._log.info(
            f"[Floorplan] Buscando vencimentos de "
            f"{self._config.data_inicio.strftime('%d/%m/%Y')} a {self._config.data_fim.strftime('%d/%m/%Y')}"
        )

        pagina = 1
        total_submetidas = 0
        todos_nfs: list[dict[str, str]] = []
        resultados: list[dict[str, str]] = []

        while not self._estou_na_ultima_pagina():
            # ─── Navegar até a página (last() se necessário) ───
            self._navegar_ate_pagina(pagina)
            self._esperar_carregar()

            # ─── Coletar NFs do range nesta página ───────────
            nfs_dict = self._coletar_nfs_do_range()

            if nfs_dict:
                nfs_existentes = {item["nf"] for item in todos_nfs}
                novas = 0
                for nf, data in nfs_dict.items():
                    if nf not in nfs_existentes:
                        todos_nfs.append({
                            "nf": nf,
                            "data": data,
                            "status": self.ST_PENDENTE
                        })
                        novas += 1

                datas = self._obter_datas_da_pagina()
                self._log.info(
                    f"[Floorplan] Página {pagina}: {novas} nova(s), "
                    f"{len(nfs_dict)} no range — "
                    f"NFs: {', '.join(nfs_dict.keys())} | "
                    f"datas: {', '.join(datas)}"
                )
            else:
                self._log.info(f"[Floorplan] Página {pagina}: nenhuma data no range")

            # ─── Encontrar primeira PENDENTE visível ─────────
            alvo = None
            for item in todos_nfs:
                if item["status"] != self.ST_PENDENTE:
                    continue
                link = self._encontrar_link_nf(item["nf"])
                if link:
                    alvo = item
                    break

            if not alvo:
                # Sem NF pendente → avança pra próxima página
                pagina += 1
                continue

            # ─── Processar NF ────────────────────────────────
            self._log.info(
                f"[Floorplan] Página {pagina}: clicando NF {alvo['nf']} "
                f"— vencimento {alvo['data']}"
            )

            if self._clicar_link_nf(alvo["nf"]):
                self._esperar_carregar()
                sleep(1)

                # TODO: coletar dados da página de detalhes

                self._browser.click_in_frames("//button[@id='form_dados_cabecalho:btConfAmortizacao']", timeout=10000)
                self._esperar_carregar()
                sleep(0.1)
                self._browser.click_in_frames("//button[normalize-space()='Sim']", timeout=10000)
                # self._esperar_carregar()
                # sleep(0.1)

                # self._browser.page.go_back()
                self._esperar_carregar()
                self._selecionar_opcao()

                alvo["status"] = self.ST_PROCESSADO
                resultados.append({
                    "nf": alvo["nf"], "data": alvo["data"], "status": self.ST_PROCESSADO
                })
                total_submetidas += 1
            else:
                self._log.warning(
                    f"[Floorplan] Página {pagina}: falha ao clicar NF {alvo['nf']}"
                )
                alvo["status"] = self.ST_FALHA
                resultados.append({
                    "nf": alvo["nf"], "data": alvo["data"], "status": self.ST_FALHA
                })

        # ─── Resumo ───────────────────────────────────────────
        self._imprimir_resumo(resultados)
        self._log.info(f"[Floorplan] Finalizado — {total_submetidas} NF(s) submetida(s)")

    def _imprimir_resumo(self, resultados: list[dict[str, str]]) -> None:
        """Imprime resumo por data: encontrados, processados, falhas."""
        resumo: dict[str, dict[str, int]] = {}

        for r in resultados:
            data = r["data"]
            if data not in resumo:
                resumo[data] = {"processados": 0, "falhas": 0}
            if r["status"] == self.ST_PROCESSADO:
                resumo[data]["processados"] += 1
            elif r["status"] == self.ST_FALHA:
                resumo[data]["falhas"] += 1

        self._log.info("[Floorplan] ═══ Resumo por data ═══")
        for data in sorted(resumo.keys()):
            info = resumo[data]
            total = info["processados"] + info["falhas"]
            self._log.info(
                f"[Floorplan] {data} → encontrados: {total}, "
                f"processados: {info['processados']}, falhas: {info['falhas']}"
            )

    # ════════════════════════════════════════════
    #  Coleta e filtro
    # ════════════════════════════════════════════

    def _coletar_nfs_do_range(self) -> dict[str, str]:
        """Retorna {nf: data} das NFs da página atual cujo vencimento está no range."""
        linhas = self._browser.find_all_in_frames(self.LINHAS_TABELA, timeout=5000)
        nfs: dict[str, str] = {}

        for i in range(1, len(linhas) + 1):
            try:
                link = self._browser.find_element_in_frames(
                    self.LINK_NF.format(i), timeout=3000
                )
                nf_texto = link.inner_text().strip()

                data_el = self._browser.find_element_in_frames(
                    self.COL_VENCIMENTO.format(i), timeout=3000
                )
                data_str = data_el.inner_text().strip()

                if not data_str:
                    continue

                dt = datetime.strptime(data_str, "%d/%m/%Y").date()
                if self._config.data_inicio <= dt <= self._config.data_fim:
                    nfs[nf_texto] = data_str
            except Exception:
                continue

        return nfs

    def _obter_datas_da_pagina(self) -> list[str]:
        """Retorna as datas de vencimento visíveis na página atual (para log)."""
        linhas = self._browser.find_all_in_frames(self.LINHAS_TABELA, timeout=5000)
        datas: list[str] = []

        for i in range(1, len(linhas) + 1):
            try:
                data_el = self._browser.find_element_in_frames(
                    self.COL_VENCIMENTO.format(i), timeout=3000
                )
                data_str = data_el.inner_text().strip()
                if data_str:
                    datas.append(data_str)
            except Exception:
                continue

        return datas

    # ════════════════════════════════════════════
    #  Paginação
    # ════════════════════════════════════════════

    # ─── Navegação por last() ────────────────────

    def _clicar_last(self) -> bool:
        """Clica no último número visível do paginator pra avançar a janela."""
        try:
            ultimo = self._browser.page.query_selector(
                "//span[@class='ui-paginator-pages']/a[last()]"
            )
            if ultimo:
                ultimo.click()
                self._esperar_carregar()
                return True
        except Exception:
            pass
        return False

    def _navegar_ate_pagina(self, pagina: int) -> None:
        """Navega até a página alvo usando last() até ela ficar visível, depois clica."""
        if self._pagina_visivel(pagina):
            self._clicar_pagina(pagina)
            return

        for _ in range(150):
            if not self._clicar_last():
                break
            if self._pagina_visivel(pagina):
                self._clicar_pagina(pagina)
                return
            if self._estou_na_ultima_pagina():
                break

    # ─── Localização de links ───────────────────

    def _encontrar_link_nf(self, nf: str):
        """Busca o link da NF na página atual pelo texto."""
        xpath = (
            f"//table[@role='grid']//a[@class='linkPagina'"
            f" and normalize-space()='{nf}']"
        )
        return self._browser.page.query_selector(xpath)

    def _clicar_link_nf(self, nf: str) -> bool:
        """Encontra o link da NF e clica com retry. Retorna False se falhar."""
        link = self._encontrar_link_nf(nf)
        if not link:
            return False
        try:
            link.click()
            return True
        except Exception:
            # Stale element — tenta encontrar de novo
            link = self._encontrar_link_nf(nf)
            if not link:
                return False
            try:
                link.click()
                return True
            except Exception:
                return False

    def _pagina_visivel(self, num: int) -> bool:
        """Verifica se o número da página está visível no paginator."""
        xpath = self.PAGINATOR_NUM.format(num)
        return self._browser.page.query_selector(xpath) is not None

    def _esperar_pagina_ativa(self, num: int, timeout: int = 5) -> bool:
        """Aguarda até a página ficar ativa no paginator."""
        xpath = self.PAGINATOR_NUM_ACTIVE.format(num)
        for _ in range(timeout * 10):
            if self._browser.page.query_selector(xpath):
                return True
            sleep(0.1)
        return False

    def _clicar_pagina(self, num: int) -> bool:
        """Clica no número da página e aguarda ficar ativa. Retorna True se confirmou."""
        try:
            xpath = self.PAGINATOR_NUM.format(num)
            el = self._browser.page.query_selector(xpath)
            if el:
                el.click()
        except Exception:
            try:
                el = self._browser.page.query_selector(self.PAGINATOR_NUM.format(num))
                if el:
                    el.click()
            except Exception:
                return False

        return self._esperar_pagina_ativa(num)

    def _estou_na_ultima_pagina(self) -> bool:
        """True se o botão Next está desabilitado."""
        btn = self._browser.page.query_selector(self.BTN_NEXT_PAGE_DISABLED)
        return btn is not None

    # ════════════════════════════════════════════
    #  Utilitários
    # ════════════════════════════════════════════

    def _esperar_carregar(self) -> None:
        """Espera a página carregar."""
        try:
            self._browser.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            sleep(5)
