import pyodbc
import base64
import time
from datetime import datetime, timedelta
from typing import Optional


# ═══════════════════════════════════════════════════════
#  Conexão
# ═══════════════════════════════════════════════════════

def conectar(ip: str, database: str, user: str, password: str) -> pyodbc.Connection:
    """Abre conexão ODBC com o SQL Server."""
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={ip};"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
    )
    return pyodbc.connect(conn_str, autocommit=False)


# ═══════════════════════════════════════════════════════
#  Execução
# ═══════════════════════════════════════════════════════

def buscar_execucao_pendente(conn: pyodbc.Connection, processo: str) -> Optional[int]:
    """
    Busca o Id da execução mais recente (MAX(Id)) criada pelo C#.
    Verifica se StatusManual = 'SOLICITADO'.
    Retorna None se não encontrar.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT Id
        FROM financeiro.token_rpa_manual
        WHERE Id IN (
            SELECT MAX(Id) FROM financeiro.token_rpa_manual WHERE Processo = ?
        )
        AND StatusManual = 'SOLICITADO'
        """,
        processo,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return int(row[0])

def iniciar_execucao(conn: pyodbc.Connection, processo: str) -> int:
    """Insere novo registro na tabela token_rpa_manual e retorna o Id."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO financeiro.token_rpa_manual
            (AtualizadoEmManual, StatusManual, StatusTokenRobo, Processo)
        OUTPUT INSERTED.Id
        VALUES
            (GETDATE(), 'SOLICITADO', 'PENDENTE', ?)
        """,
        processo,
    )
    row = cursor.fetchone()
    conn.commit()
    return int(row[0])


def finalizar_execucao(conn: pyodbc.Connection, id_execucao: int, status: str):
    """Atualiza o StatusRobo ao final da execução."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE financeiro.token_rpa_manual
        SET StatusRobo = ?, AtualizadoEmManual = GETDATE()
        WHERE Id = ?
        """,
        status,
        id_execucao,
    )
    conn.commit()


# ═══════════════════════════════════════════════════════
#  Token
# ═══════════════════════════════════════════════════════

def buscar_status_token(conn: pyodbc.Connection, id_execucao: int) -> Optional[dict]:
    """Retorna o registro completo da execução atual."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT Id, StatusManual, StatusTokenRobo, TokenManual, AtualizadoEmManual
        FROM financeiro.token_rpa_manual
        WHERE Id = ?
        """,
        id_execucao,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "Id": row[0],
        "StatusManual": row[1],
        "StatusTokenRobo": row[2],
        "TokenManual": row[3],
        "AtualizadoEmManual": row[4],
    }


def gravar_status_robo(conn: pyodbc.Connection, id_execucao: int, status: str):
    """Atualiza o StatusTokenRobo."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE financeiro.token_rpa_manual
        SET StatusTokenRobo = ?
        WHERE Id = ?
        """,
        status,
        id_execucao,
    )
    conn.commit()


def aguardar_token_do_banco(
    conn: pyodbc.Connection,
    id_execucao: int,
    timeout_minutos: int = 6,
    polling_segundos: int = 3,
    limite_replay_segundos: int = 180,
) -> str:
    """
    Aguarda até que o usuário insira o token na tela C#.
    Retorna o token como string, ou lança exceção em caso de timeout/erro.
    """
    deadline = datetime.now() + timedelta(minutes=timeout_minutos)

    while datetime.now() < deadline:
        row = buscar_status_token(conn, id_execucao)

        if row is None:
            raise Exception("Registro não encontrado na tabela token_rpa_manual.")

        status_manual = row["StatusManual"]
        token = row["TokenManual"]
        atualizado_em = row["AtualizadoEmManual"]

        if status_manual == "ENVIADO" and token:
            if atualizado_em:
                tempo_decorrido = (datetime.now() - atualizado_em).total_seconds()
                if tempo_decorrido > limite_replay_segundos:
                    gravar_status_robo(conn, id_execucao, "EXPIRADO")
                    raise Exception(
                        "Token recebido, mas AtualizadoEmManual está muito antigo. Possível replay."
                    )
            return token

        if status_manual == "EXPIRADO":
            gravar_status_robo(conn, id_execucao, "EXPIRADO")
            raise Exception("Token expirado: usuário não inseriu a tempo.")

        if status_manual == "ERRO":
            gravar_status_robo(conn, id_execucao, "ERRO")
            raise Exception("Erro reportado pela tela C# durante espera do token.")

        time.sleep(polling_segundos)

    gravar_status_robo(conn, id_execucao, "EXPIRADO")
    raise Exception(f"Timeout de {timeout_minutos} minutos aguardando token do usuário.")


# ═══════════════════════════════════════════════════════
#  Mensagens (log na tela C#)
# ═══════════════════════════════════════════════════════

def limpar_mensagens(conn: pyodbc.Connection):
    """Limpa a tabela de mensagens no início de cada execução."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dbo.mensagens")
    conn.commit()


def logar_mensagem(conn: pyodbc.Connection, msg: str):
    """Insere uma mensagem de log para exibição na tela C#."""
    data = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO dbo.mensagens (Msg) VALUES (?)",
        f"{data} – {msg}",
    )
    conn.commit()


# ═══════════════════════════════════════════════════════
#  Credenciais (lidas do banco)
# ═══════════════════════════════════════════════════════

def descriptografar(senha_criptografada: str) -> str:
    """
    Descriptografa senha usando DPAPI (Windows).
    O C# usa ProtectedData.Protect/Unprotect com DataProtectionScope.CurrentUser.
    """
    if not senha_criptografada:
        return ""

    try:
        import win32crypt

        dados_protegidos = base64.b64decode(senha_criptografada)
        dados_desprotegidos = win32crypt.CryptUnprotectData(dados_protegidos, None, None, None, 0, 0)
        return dados_desprotegidos[1].decode("utf-8")
    except Exception:
        return ""


def carregar_credenciais(conn: pyodbc.Connection, processo: str) -> dict:
    """
    Carrega credenciais da tabela financeiro.configuracoes_rpa.
    Retorna dict com usuario, senha (descriptografada) e receber_por.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT Usuario, SenhaCriptografada, ReceberPor
        FROM financeiro.configuracoes_rpa
        WHERE Processo = ?
        """,
        processo,
    )
    row = cursor.fetchone()
    if row is None:
        raise Exception(
            f"Credenciais não configuradas para o processo '{processo}'. "
            "Configure pelo programa C#."
        )
    return {
        "usuario": row[0],
        "senha": descriptografar(row[1]),
        "receber_por": row[2],
    }
