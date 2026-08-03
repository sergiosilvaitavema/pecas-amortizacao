from rpaflow.browser import Browser

from src.core.config import Config
from src.portal_floorplan import PortalFloorplan
from src.db_floorplan import conectar, buscar_execucao_pendente, finalizar_execucao, gravar_status_robo, limpar_mensagens, logar_mensagem


def main():
    config = Config()

    # Conexão com o banco
    db_conn = conectar(config.db_ip, config.db_database, config.db_user, config.db_password)

    # Busca a execução que o C# criou (StatusTokenRobo = 'PENDENTE')
    id_execucao = buscar_execucao_pendente(db_conn, config.processo)
    if id_execucao is None:
        limpar_mensagens(db_conn)
        logar_mensagem(db_conn, "Nenhuma execução pendente. Clique 'Iniciar Robô' no programa C#.")
        config.log.error("[Main] Nenhuma execução pendente encontrada. Clique 'Iniciar Robô' no programa C# primeiro.")
        db_conn.close()
        return

    try:
        # Browser único com duas páginas
        browser = Browser()
        browser.start(config.floorplan_site)
        browser.maximize()

        floorplan = PortalFloorplan(config, browser, db_conn, id_execucao)
        floorplan.executar()
    except Exception as e:
        config.log.error(f"[Main] Erro fatal: {e}")
    finally:
        db_conn.close()


if __name__ == "__main__":
    main()
