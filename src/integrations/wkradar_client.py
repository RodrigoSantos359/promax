"""
Client de integração com a API WKRADAR.

A WKRADAR exige um token de autenticação (endpoint `/api/v1/token`), obtido
por empresa a partir de 3 credenciais cadastradas em `Company`
(`base_empresa_wkradar`, `usuario_wkradar`, `senha_wkradar`). Esse token
expira em ~10 minutos — por isso NÃO é persistido: `get_wkradar_token()`
sempre busca um token novo na API a cada chamada e o devolve só em memória,
no retorno da própria função (a coluna `Company.token_wkradar` existe no
banco, mas nunca é escrita por este módulo).

O endpoint atual está num IP interno (https://172.20.5.8) com certificado
provavelmente não confiável por uma CA pública — por isso as chamadas usam
`verify=False`, com o warning correspondente suprimido.
"""

from typing import Any, Dict, Optional

import requests
import urllib3

from config.settings import WKRADAR_TOKEN_URL, logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WKRADAR_REQUEST_TIMEOUT = 15


def get_wkradar_token(company_id: int) -> Dict[str, Any]:
    """
    Busca um novo token de acesso à API WKRADAR para a empresa informada.

    Args:
        company_id: ID da empresa (`Company.id`), já com as credenciais
            WKRADAR cadastradas (`base_empresa_wkradar`, `usuario_wkradar`,
            `senha_wkradar`).

    Returns:
        dict: {"status": "success", "token": str, "expiration": str,
               "expiration_brazil": str, "expires_in": int} em caso de
              sucesso, ou {"status": "failed", "error": str} em caso de
              falha (credenciais ausentes, erro de rede, resposta inválida).
    """
    from config.database import DatabaseService

    credenciais = DatabaseService.get_company_wkradar_credentials(company_id)
    if credenciais is None:
        return {
            "status": "failed",
            "error": f"Empresa {company_id} não tem credenciais WKRADAR cadastradas",
        }

    payload = {
        "empresa": credenciais["empresa"],
        "nomeUsuario": credenciais["nomeUsuario"],
        "senha": credenciais["senha"],
        "idIntegrador": "",
    }

    try:
        response = requests.post(
            WKRADAR_TOKEN_URL, json=payload, timeout=WKRADAR_REQUEST_TIMEOUT, verify=False
        )
    except requests.RequestException as e:
        logger.error(f"Falha ao obter token WKRADAR (company_id={company_id}): {e}")
        return {"status": "failed", "error": str(e)}

    if not response.ok:
        # A API WKRADAR retorna erros de negócio (ex: credenciais inválidas)
        # como {"Erros": [{"Descricao": "..."}]} no corpo, com status 400 —
        # extrai essa mensagem quando disponível, em vez de só "400 Client Error".
        mensagem_erro = f"HTTP {response.status_code}"
        try:
            erros = response.json().get("Erros")
            if erros:
                mensagem_erro = "; ".join(e.get("Descricao", str(e)) for e in erros)
        except ValueError:
            pass
        logger.error(f"API WKRADAR recusou a requisição (company_id={company_id}): {mensagem_erro}")
        return {"status": "failed", "error": mensagem_erro}

    try:
        data = response.json()
    except ValueError as e:
        logger.error(f"Resposta inválida (não-JSON) da API WKRADAR (company_id={company_id}): {e}")
        return {"status": "failed", "error": "Resposta inválida da API WKRADAR"}

    token = data.get("token")
    if not token:
        logger.error(f"API WKRADAR não retornou 'token' (company_id={company_id}): {data}")
        return {"status": "failed", "error": "API WKRADAR não retornou um token válido"}

    return {
        "status": "success",
        "token": token,
        "expiration": data.get("expiration"),
        "expiration_brazil": data.get("expirationBrazil"),
        "expires_in": data.get("expiresIn"),
    }


__all__ = ["get_wkradar_token", "WKRADAR_TOKEN_URL"]
