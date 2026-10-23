"""
Processamento de um registro de `arquivos_baixados` com status "baixado".

Dois formatos de layout são suportados (`map_col_rel_rotina.formato`):

- 'delimitado' (padrão, ex: CSV separado por ';'): lê o cabeçalho REAL do
  arquivo (primeira linha) e reconhece automaticamente suas colunas,
  comparando com o snapshot da última versão conhecida
  (`map_col_rel_rotina_versoes`). Se o cabeçalho for novo (nenhum layout
  ainda cadastrado) ou diferente do já registrado, o próprio
  `map_col_rel_rotina` é criado/atualizado automaticamente — sem precisar
  de cadastro manual prévio na tela.

- 'fixo' (ex: arquivos .inf de largura fixa, sem cabeçalho): as colunas vêm
  do layout configurado manualmente (`layout_fixo`, lista de
  {tamanho, coluna, nome}) — não há cabeçalho para auto-detectar, então
  esse layout precisa já existir (cadastrado à parte) e é tratado como
  estático.

Em ambos os casos, ao final: extrai as linhas de dados, insere na tabela
dinâmica (Postgres) resultante (preenchendo `id_empresa`, `id_rotina` e
`data` a partir do próprio registro de `arquivos_baixados`) e, concluída a
importação, remove o arquivo da pasta `data/arquivos` e o próprio registro
de `arquivos_baixados`.
"""

import os
from typing import List

from sqlalchemy import text as sql_text

from config.settings import logger
from src.database.dynamic_tables import (
    CODIGO_IBGE_COLUMN,
    CODIGO_MUNICIPIO_COLUMN,
    build_column_names,
    build_table_name,
    compute_column_names,
    parse_layout_fixo,
    postgres_engine,
    sync_dynamic_table,
)

FILE_ENCODING = "cp1252"

# Separadores candidatos ao reconhecer automaticamente o cabeçalho de um
# arquivo sem layout cadastrado — ';' é o único observado nos relatórios do
# PromaX até hoje, mas os demais ficam como fallback.
CANDIDATE_SPLIT_COLS = [";", ",", "\t", "|"]

FIXED_COLS = ["id_empresa", "id_rotina", "data"]


def _read_lines(caminho_arquivo: str) -> List[str]:
    with open(caminho_arquivo, "r", encoding=FILE_ENCODING, errors="replace", newline="") as f:
        return [line.rstrip("\r\n") for line in f if line.strip() != ""]


def _detect_split_col(header_line: str) -> str:
    """Escolhe, entre os separadores candidatos, o que quebra o cabeçalho em mais colunas."""
    best = max(CANDIDATE_SPLIT_COLS, key=lambda sep: len(header_line.split(sep)))
    return best if len(header_line.split(best)) > 1 else CANDIDATE_SPLIT_COLS[0]


def _get_mapeamento_atual(id_rotina: int):
    """Retorna (version_record, mapeamento) atuais para a rotina, ou (None, None)/(version_record, None)."""
    from config.database import DatabaseService

    base_table_name = build_table_name(id_rotina)
    version_record = DatabaseService.get_map_col_rel_rotina_version(id_rotina, base_table_name)

    mapeamento = None
    if version_record and version_record.id_mapeamento:
        mapeamento = DatabaseService.get_map_col_rel_rotina(version_record.id_mapeamento)
    if mapeamento is None:
        existentes = DatabaseService.get_map_col_rel_rotina_by_rotina(id_rotina)
        mapeamento = existentes[0] if existentes else None

    return version_record, mapeamento


def _ensure_layout_delimitado_atualizado(arquivo, header_line: str):
    """
    Garante que exista um `MapColRelRotina` (formato 'delimitado') cujo
    cabeçalho registrado bata com o cabeçalho REAL do arquivo — criando um
    novo mapeamento (se a rotina nunca teve nenhum) ou atualizando o
    `text_cabe` do mapeamento já associado à linhagem atual (se o
    cabeçalho mudou). Em ambos os casos, isso já aciona `sync_dynamic_table`
    (via `DatabaseService`), então o versionamento da tabela dinâmica é
    tratado automaticamente.

    Returns:
        MapColRelRotinaVersion atualizado (após o reconhecimento), ou None
        em caso de falha.
    """
    from config.database import DatabaseService

    base_table_name = build_table_name(arquivo.id_rotina)
    version_record, mapeamento = _get_mapeamento_atual(arquivo.id_rotina)

    if mapeamento is not None:
        colunas_atuais = build_column_names(header_line, mapeamento.split_col)
        if version_record and ",".join(colunas_atuais) == version_record.colunas:
            # Cabeçalho já bate com o que está registrado — nada a fazer.
            return version_record

        split_col = mapeamento.split_col
        quant_col = len(header_line.split(split_col))
        logger.info(
            f"ArquivoBaixado {arquivo.id}: cabeçalho do arquivo mudou em relação ao mapeamento "
            f"{mapeamento.id} — atualizando 'text_cabe' automaticamente"
        )
        DatabaseService.update_map_col_rel_rotina(
            mapeamento.id, quant_col=quant_col, split_col=split_col, text_cabe=header_line
        )
    else:
        split_col = _detect_split_col(header_line)
        quant_col = len(header_line.split(split_col))

        if quant_col <= 1:
            # Nenhum separador conhecido encontrado no "cabeçalho" — não é
            # um arquivo delimitado de verdade (ex: um .inf de largura fixa,
            # sem cabeçalho, baixado via "salvar"). Cadastrar aqui criaria
            # uma tabela de 1 coluna com a linha inteira dentro — em vez
            # disso, sinaliza que precisa de configuração manual (formato
            # 'fixo', com `layout_fixo`).
            logger.error(
                f"ArquivoBaixado {arquivo.id}: não foi encontrado nenhum separador conhecido no arquivo "
                f"(id_rotina={arquivo.id_rotina}) — provavelmente é um arquivo de largura fixa; "
                "cadastre manualmente um MapColRelRotina com formato='fixo' e 'layout_fixo' definido."
            )
            return None

        rotina = DatabaseService.get_rotina_map(arquivo.id_rotina)
        nome_rotina = rotina.nome if rotina else f"rotina {arquivo.id_rotina}"
        logger.info(
            f"ArquivoBaixado {arquivo.id}: nenhum layout cadastrado para id_rotina={arquivo.id_rotina} — "
            f"cadastrando automaticamente a partir do cabeçalho real do arquivo (split='{split_col}')"
        )
        DatabaseService.create_map_col_rel_rotina(
            id_rotina=arquivo.id_rotina,
            nome_rel=f"[Auto] {nome_rotina}",
            quant_col=quant_col,
            split_col=split_col,
            text_cabe=header_line,
        )

    return DatabaseService.get_map_col_rel_rotina_version(arquivo.id_rotina, base_table_name)


def _finalize_importado(arquivo) -> None:
    """
    Importação concluída: remove o arquivo da pasta `data/arquivos` e o
    próprio registro de `arquivos_baixados` (best-effort — qualquer falha
    aqui é só logada, os dados já foram inseridos com sucesso na tabela
    dinâmica antes desta chamada).
    """
    from config.database import DatabaseService

    if arquivo.nome_arquivo and os.path.isfile(arquivo.nome_arquivo):
        try:
            os.remove(arquivo.nome_arquivo)
            logger.info(f"ArquivoBaixado {arquivo.id}: arquivo '{arquivo.nome_arquivo}' removido do disco")
        except OSError as e:
            logger.error(f"ArquivoBaixado {arquivo.id}: falha ao remover arquivo '{arquivo.nome_arquivo}': {e}")

    try:
        DatabaseService.delete_arquivo_baixado(arquivo.id)
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao remover registro de 'arquivos_baixados': {e}")


def _ja_importado(nome_tabela: str, arquivo, registros: List[dict]) -> bool:
    """
    Verifica se este arquivo já foi importado antes, para não duplicar linhas
    na tabela dinâmica (reprocessamento manual, reexecução da automação para o
    mesmo dia, ou a corrida entre o monitor e uma chamada manual).

    A checagem é por `id_empresa` + `id_rotina` + `data`. Quando os registros
    trazem a coluna `portador` (ex: extrato 12.04.07.03, que gera um arquivo
    por portador no mesmo dia), a checagem também considera o portador: um
    portador ainda não importado no dia não é considerado duplicado.
    """
    portadores = sorted({str(r["portador"]).strip() for r in registros if r.get("portador")})
    if portadores:
        query = sql_text(
            f'SELECT 1 FROM "{nome_tabela}" '
            "WHERE id_empresa = :id_empresa AND id_rotina = :id_rotina AND data = :data "
            "AND portador = ANY(:portadores) LIMIT 1"
        )
        params = {
            "id_empresa": arquivo.id_empresa, "id_rotina": arquivo.id_rotina,
            "data": arquivo.data, "portadores": portadores,
        }
    else:
        query = sql_text(
            f'SELECT 1 FROM "{nome_tabela}" '
            "WHERE id_empresa = :id_empresa AND id_rotina = :id_rotina AND data = :data LIMIT 1"
        )
        params = {"id_empresa": arquivo.id_empresa, "id_rotina": arquivo.id_rotina, "data": arquivo.data}
    with postgres_engine.connect() as conn:
        existe = conn.execute(query, params).first()
    return existe is not None


def _insert_registros(arquivo, nome_tabela: str, colunas_reais: List[str], registros: List[dict]) -> str:
    """Insere os registros já montados na tabela dinâmica e finaliza (remove arquivo + registro)."""
    if not registros:
        logger.info(f"ArquivoBaixado {arquivo.id}: layout reconhecido, mas o arquivo não tem linhas de dados")
        _finalize_importado(arquivo)
        return "removido"

    if _ja_importado(nome_tabela, arquivo, registros):
        logger.warning(
            f"ArquivoBaixado {arquivo.id}: já existem dados importados para id_empresa={arquivo.id_empresa}, "
            f"id_rotina={arquivo.id_rotina}, data={arquivo.data} em '{nome_tabela}' — pulando importação "
            "para não duplicar"
        )
        _finalize_importado(arquivo)
        return "removido"

    colunas_sql = ", ".join(f'"{c}"' for c in FIXED_COLS + colunas_reais)
    placeholders = ", ".join(f":{c}" for c in FIXED_COLS + colunas_reais)
    insert_sql = f'INSERT INTO "{nome_tabela}" ({colunas_sql}) VALUES ({placeholders})'

    try:
        with postgres_engine.begin() as conn:
            conn.execute(sql_text(insert_sql), registros)
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao inserir {len(registros)} linha(s) na tabela '{nome_tabela}': {e}")
        return "erro_processamento"

    logger.info(f"ArquivoBaixado {arquivo.id}: {len(registros)} linha(s) inserida(s) com sucesso na tabela '{nome_tabela}'")
    # Antes de apagar o original: guarda uma cópia para envio à API BPO ACENE
    # (só rotinas configuradas; nunca interrompe a importação).
    from src.integrations.bpo_acene_outbox import enfileirar_arquivo

    enfileirar_arquivo(arquivo)
    _finalize_importado(arquivo)
    return "removido"


def _process_delimitado(arquivo, linhas: List[str]) -> str:
    header_line = linhas[0]

    try:
        version_record = _ensure_layout_delimitado_atualizado(arquivo, header_line)
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao reconhecer/cadastrar layout: {e}")
        return "erro_layout_ausente"

    if version_record is None:
        logger.error(f"ArquivoBaixado {arquivo.id}: não foi possível determinar a tabela dinâmica para id_rotina={arquivo.id_rotina}")
        return "erro_layout_ausente"

    from config.database import DatabaseService

    mapeamento = (
        DatabaseService.get_map_col_rel_rotina(version_record.id_mapeamento)
        if version_record.id_mapeamento
        else None
    )
    if mapeamento is None:
        logger.error(
            f"ArquivoBaixado {arquivo.id}: MapColRelRotina de referência (id={version_record.id_mapeamento}) "
            "não encontrado após o reconhecimento do layout"
        )
        return "erro_layout_ausente"

    colunas_reais = build_column_names(header_line, mapeamento.split_col)
    linhas_dados = linhas[1:]

    registros = []
    for linha in linhas_dados:
        valores = linha.split(mapeamento.split_col)
        # normaliza o tamanho da linha ao número de colunas esperado
        # (preenche faltantes com None, descarta excedentes)
        valores = (valores + [None] * len(colunas_reais))[: len(colunas_reais)]
        registro = {"id_empresa": arquivo.id_empresa, "id_rotina": arquivo.id_rotina, "data": arquivo.data}
        registro.update(dict(zip(colunas_reais, valores)))
        registros.append(registro)

    return _insert_registros(arquivo, version_record.nome_tabela_atual, colunas_reais, registros)


def _process_fixo(arquivo, linhas: List[str], mapeamento) -> str:
    from src.database import municipios_ibge

    try:
        layout, ignorar_padroes, exigir_preenchido = parse_layout_fixo(mapeamento.layout_fixo)
    except (TypeError, ValueError) as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: layout_fixo inválido no mapeamento {mapeamento.id}: {e}")
        return "erro_layout_ausente"

    if ignorar_padroes:
        antes = len(linhas)
        linhas = [l for l in linhas if not any(p in l for p in ignorar_padroes)]
        logger.info(
            f"ArquivoBaixado {arquivo.id}: {antes - len(linhas)} linha(s) de banner/cabeçalho "
            f"ignorada(s) (de {antes} totais)"
        )

    try:
        nome_tabela = sync_dynamic_table(mapeamento)
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao sincronizar tabela dinâmica: {e}")
        return "erro_layout_ausente"

    colunas_reais = compute_column_names(mapeamento)
    nomes_layout = colunas_reais[: len(layout)]
    tem_codigo_municipio = CODIGO_MUNICIPIO_COLUMN in nomes_layout

    lookup_ibge = municipios_ibge.load_lookup_map() if tem_codigo_municipio else {}

    idx_exigido = None
    if exigir_preenchido:
        nomes_originais = [item["nome"] for item in layout]
        if exigir_preenchido in nomes_originais:
            idx_exigido = nomes_originais.index(exigir_preenchido)

    registros = []
    for linha in linhas:
        valores = [linha[item["coluna"] - 1: item["coluna"] - 1 + item["tamanho"]].strip() for item in layout]

        if idx_exigido is not None and not valores[idx_exigido]:
            continue

        registro = {"id_empresa": arquivo.id_empresa, "id_rotina": arquivo.id_rotina, "data": arquivo.data}
        registro.update(dict(zip(nomes_layout, valores)))

        if tem_codigo_municipio:
            parsed = municipios_ibge.parse_codigo_municipio(registro.get(CODIGO_MUNICIPIO_COLUMN))
            registro[CODIGO_IBGE_COLUMN] = lookup_ibge.get(parsed[1]) if parsed else None

        registros.append(registro)

    return _insert_registros(arquivo, nome_tabela, colunas_reais, registros)


def process_arquivo_baixado(arquivo) -> str:
    """
    Processa um `ArquivoBaixado` (status "baixado"): reconhece/valida o
    layout do arquivo (delimitado ou fixo — veja docstring do módulo),
    garante que a tabela dinâmica esteja sincronizada, e então extrai e
    insere os dados.

    Args:
        arquivo: instância de `config.database.ArquivoBaixado`.

    Returns:
        str: "removido" em caso de sucesso (arquivo e registro já foram
            removidos por esta função — nada mais a fazer), ou um dos
            "erro_arquivo_ausente", "erro_layout_ausente", "erro_processamento"
            em caso de falha (registro é mantido, com o status atualizado,
            para diagnóstico).
    """
    if not arquivo.nome_arquivo:
        logger.warning(f"ArquivoBaixado {arquivo.id}: sem nome_arquivo — nada a processar")
        return "erro_arquivo_ausente"

    if not os.path.isfile(arquivo.nome_arquivo):
        logger.error(f"ArquivoBaixado {arquivo.id}: arquivo não encontrado em disco: '{arquivo.nome_arquivo}'")
        return "erro_arquivo_ausente"

    try:
        linhas = _read_lines(arquivo.nome_arquivo)
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao ler arquivo '{arquivo.nome_arquivo}': {e}")
        return "erro_arquivo_ausente"

    if not linhas:
        logger.error(f"ArquivoBaixado {arquivo.id}: arquivo '{arquivo.nome_arquivo}' está vazio")
        return "erro_arquivo_ausente"

    _, mapeamento_existente = _get_mapeamento_atual(arquivo.id_rotina)

    if mapeamento_existente is not None and mapeamento_existente.formato == "fixo":
        return _process_fixo(arquivo, linhas, mapeamento_existente)

    return _process_delimitado(arquivo, linhas)
