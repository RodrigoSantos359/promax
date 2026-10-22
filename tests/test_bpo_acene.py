"""
Testes do envio de relatórios para a API BPO ACENE (client + fila).

A API é sempre simulada (monkeypatch de `requests.post` / `enviar_arquivo`);
o banco de configuração é um SQLite temporário (veja `conftest.py`).

    pytest tests/test_bpo_acene.py -v
"""

import os
from datetime import date, datetime

import pytest
import requests

from config.database import DatabaseService, init_db
from src.integrations import bpo_acene_client as client
from src.integrations import bpo_acene_outbox as outbox

URL_TESTE = "https://bpo.teste"


class FakeResponse:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo

    def json(self):
        if self._corpo is None:
            raise ValueError("sem JSON")
        return self._corpo


@pytest.fixture(scope="module", autouse=True)
def banco():
    init_db()


@pytest.fixture
def arquivo_relatorio(tmp_path):
    caminho = tmp_path / "14.05.05_PWNR_filipe_123.csv.inf"
    caminho.write_text("Fornecedor;Nome;Titulo\n000077;JOSE;000133\n", encoding="cp1252")
    return caminho


@pytest.fixture
def empresa():
    nome = f"Empresa Teste {datetime.now():%H%M%S%f}"
    company = DatabaseService.create_company(
        name=nome, promax_url="https://x", username="u", password="p", unit="161.0001",
        bpo_acene_token="token-de-teste",
    )
    return company


@pytest.fixture
def url_configurada(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    monkeypatch.setattr(outbox, "BPO_ACENE_OUTBOX_DIR", tmp_path / "outbox")
    (tmp_path / "outbox").mkdir()


# ---------------------------------------------------------------- client


def test_envio_aceito_devolve_lote(monkeypatch, arquivo_relatorio):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    chamadas = {}

    def fake_post(url, headers, data, files, timeout, verify):
        chamadas.update(url=url, headers=headers, data=data, nome=files["arquivo"][0])
        return FakeResponse(202, {"lote": {"id": 42, "status": "processando"}, "duplicado": False})

    monkeypatch.setattr(client.requests, "post", fake_post)
    r = client.enviar_arquivo("tk", "2026-09", str(arquivo_relatorio), arquivo_relatorio.name)

    assert r.resultado == client.ENVIADO
    assert (r.lote_id, r.lote_status, r.http_status) == (42, "processando", 202)
    assert chamadas["url"] == f"{URL_TESTE}/api/bpo/promax/importacoes"
    assert chamadas["headers"]["Authorization"] == "Bearer tk"
    assert chamadas["data"] == {"competencia": "2026-09"}
    assert chamadas["nome"] == arquivo_relatorio.name


def test_arquivo_ja_recebido_e_duplicado(monkeypatch, arquivo_relatorio):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    monkeypatch.setattr(
        client.requests, "post",
        lambda *a, **k: FakeResponse(200, {"lote": {"id": 7, "status": "importado"}, "duplicado": True}),
    )
    r = client.enviar_arquivo("tk", "2026-09", str(arquivo_relatorio), arquivo_relatorio.name)
    assert r.resultado == client.DUPLICADO
    assert r.lote_id == 7


@pytest.mark.parametrize("status", [401, 403, 422])
def test_erros_definitivos_sao_rejeitados(monkeypatch, arquivo_relatorio, status):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    corpo = {"message": "A competência 09/2026 está fechada.", "errors": {"competencia": ["fechada"]}}
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: FakeResponse(status, corpo))
    r = client.enviar_arquivo("tk", "2026-09", str(arquivo_relatorio), arquivo_relatorio.name)
    assert r.resultado == client.REJEITADO
    assert "fechada" in r.mensagem and "competencia" in r.mensagem


@pytest.mark.parametrize("status", [429, 500, 503])
def test_erros_temporarios_pedem_nova_tentativa(monkeypatch, arquivo_relatorio, status):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: FakeResponse(status))
    r = client.enviar_arquivo("tk", "2026-09", str(arquivo_relatorio), arquivo_relatorio.name)
    assert r.resultado == client.TENTAR_NOVAMENTE
    assert r.http_status == status


def test_falha_de_rede_pede_nova_tentativa(monkeypatch, arquivo_relatorio):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)

    def falha(*a, **k):
        raise requests.ConnectionError("sem rota")

    monkeypatch.setattr(client.requests, "post", falha)
    r = client.enviar_arquivo("tk", "2026-09", str(arquivo_relatorio), arquivo_relatorio.name)
    assert r.resultado == client.TENTAR_NOVAMENTE


def test_extensao_nao_aceita_nem_chama_a_api(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "BPO_ACENE_URL", URL_TESTE)
    caminho = tmp_path / "relatorio.xlsx"
    caminho.write_bytes(b"x")
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: pytest.fail("não deveria chamar a API"))
    r = client.enviar_arquivo("tk", "2026-09", str(caminho), caminho.name)
    assert r.resultado == client.REJEITADO


# ---------------------------------------------------------------- fila


def _arquivo_baixado(empresa, caminho, data_ref=date(2026, 9, 30)):
    return DatabaseService.create_arquivo_baixado(
        id_rotina=1, id_empresa=empresa.id, nome_arquivo=str(caminho), data=data_ref, status="baixado"
    )


def test_enfileira_copia_com_competencia_do_mes(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    monkeypatch.setattr(outbox, "_codigo_rotina", lambda id_rotina: "14.05.05")
    envio_id = outbox.enfileirar_arquivo(_arquivo_baixado(empresa, arquivo_relatorio))

    envio = next(e for e in DatabaseService.get_envios_bpo() if e.id == envio_id)
    assert envio.status == "pendente"
    assert envio.competencia == "2026-09"
    assert envio.nome_arquivo == arquivo_relatorio.name
    assert os.path.isfile(envio.caminho_arquivo)
    assert envio.caminho_arquivo != str(arquivo_relatorio)  # é uma cópia


def test_nao_enfileira_rotina_fora_da_lista(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    monkeypatch.setattr(outbox, "_codigo_rotina", lambda id_rotina: "16.03.05")
    assert outbox.enfileirar_arquivo(_arquivo_baixado(empresa, arquivo_relatorio)) is None


def test_nao_enfileira_sem_servidor_configurado(monkeypatch, empresa, arquivo_relatorio):
    monkeypatch.setattr(client, "BPO_ACENE_URL", "")
    monkeypatch.setattr(outbox, "_codigo_rotina", lambda id_rotina: "14.05.05")
    assert outbox.enfileirar_arquivo(_arquivo_baixado(empresa, arquivo_relatorio)) is None


def test_nao_enfileira_empresa_sem_token(monkeypatch, url_configurada, arquivo_relatorio):
    sem_token = DatabaseService.create_company(
        name=f"Sem token {datetime.now():%H%M%S%f}", promax_url="https://x", username="u", password="p", unit="1",
    )
    monkeypatch.setattr(outbox, "_codigo_rotina", lambda id_rotina: "14.05.05")
    assert outbox.enfileirar_arquivo(_arquivo_baixado(sem_token, arquivo_relatorio)) is None


def _envio_pendente(monkeypatch, empresa, arquivo_relatorio):
    monkeypatch.setattr(outbox, "_codigo_rotina", lambda id_rotina: "12.04.07.03")
    envio_id = outbox.enfileirar_arquivo(_arquivo_baixado(empresa, arquivo_relatorio))
    return next(e for e in DatabaseService.get_envios_bpo() if e.id == envio_id)


def _recarregar(envio_id):
    return next(e for e in DatabaseService.get_envios_bpo() if e.id == envio_id)


def test_envio_com_sucesso_grava_lote_e_apaga_copia(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    envio = _envio_pendente(monkeypatch, empresa, arquivo_relatorio)
    recebido = {}

    def fake_enviar(token, competencia, caminho, nome):
        recebido.update(token=token, competencia=competencia)
        return client.ResultadoEnvio(client.ENVIADO, http_status=202, lote_id=99, lote_status="processando")

    monkeypatch.setattr(outbox.client, "enviar_arquivo", fake_enviar)
    assert outbox.processar_envio(envio) == "enviado"

    atualizado = _recarregar(envio.id)
    assert recebido == {"token": "token-de-teste", "competencia": "2026-09"}
    assert (atualizado.status, atualizado.lote_id, atualizado.tentativas) == ("enviado", 99, 1)
    assert atualizado.enviado_em is not None
    assert not os.path.exists(envio.caminho_arquivo)


def test_falha_temporaria_reagenda(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    envio = _envio_pendente(monkeypatch, empresa, arquivo_relatorio)
    monkeypatch.setattr(
        outbox.client, "enviar_arquivo",
        lambda *a: client.ResultadoEnvio(client.TENTAR_NOVAMENTE, http_status=503, mensagem="indisponível"),
    )
    assert outbox.processar_envio(envio) == "pendente"

    atualizado = _recarregar(envio.id)
    assert atualizado.tentativas == 1
    assert atualizado.proxima_tentativa > datetime.utcnow()
    assert os.path.exists(envio.caminho_arquivo)
    # ainda não chegou a hora da nova tentativa
    assert envio.id not in [e.id for e in DatabaseService.get_envios_bpo_prontos(datetime.utcnow())]


def test_desiste_apos_maximo_de_tentativas(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    envio = _envio_pendente(monkeypatch, empresa, arquivo_relatorio)
    DatabaseService.update_envio_bpo(envio.id, tentativas=outbox.MAX_TENTATIVAS - 1)
    monkeypatch.setattr(
        outbox.client, "enviar_arquivo", lambda *a: client.ResultadoEnvio(client.TENTAR_NOVAMENTE, mensagem="x")
    )
    assert outbox.processar_envio(_recarregar(envio.id)) == "erro"


def test_rejeicao_mantem_copia_e_permite_reenviar(monkeypatch, url_configurada, empresa, arquivo_relatorio):
    envio = _envio_pendente(monkeypatch, empresa, arquivo_relatorio)
    monkeypatch.setattr(
        outbox.client, "enviar_arquivo",
        lambda *a: client.ResultadoEnvio(client.REJEITADO, http_status=422, mensagem="filial do Promax não configurada"),
    )
    assert outbox.processar_envio(envio) == "rejeitado"
    atualizado = _recarregar(envio.id)
    assert atualizado.mensagem == "filial do Promax não configurada"
    assert os.path.exists(envio.caminho_arquivo)

    outbox.reenviar(envio.id)
    assert _recarregar(envio.id).status == "pendente"


def test_token_fica_criptografado_no_banco(empresa):
    db_company = DatabaseService.get_company(empresa.id)
    assert db_company.bpo_acene_token != "token-de-teste"
    assert DatabaseService.get_company_bpo_acene_token(empresa.id) == "token-de-teste"
