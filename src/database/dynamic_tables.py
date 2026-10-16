"""
Geração/atualização automática de tabelas de dados a partir dos mapeamentos
configurados na tabela `map_col_rel_rotina`.

Cada registro de `MapColRelRotina` descreve as colunas de um arquivo de
relatório baixado por uma automação — via cabeçalho real (formato
'delimitado', ex: CSV separado por ';') ou via layout de posições fixas
(formato 'fixo', ex: arquivos .inf, sem cabeçalho, campos definidos por
tamanho/coluna) — e este módulo usa isso para criar (ou evoluir) uma tabela
dedicada no Postgres, pronta para armazenar as linhas desses arquivos.

Diferente do restante do projeto (empresas, rotinas, execuções), que
continua no SQLite (`config/database.py`), estas tabelas dinâmicas de dados
de relatório vivem no Postgres (`config/settings.POSTGRES_URL`).

Versionamento (só se aplica ao formato 'delimitado'): cada vez que um
mapeamento é salvo, as colunas sanitizadas do cabeçalho são comparadas com o
snapshot registrado na tabela auxiliar `map_col_rel_rotina_versoes`
(`config/database.MapColRelRotinaVersion`) para o mesmo `id_rotina` +
nome-base da tabela. Se baterem, a tabela já criada é reaproveitada; se
diferirem, uma NOVA tabela é criada com sufixo `_v<N>` incrementado,
preservando as versões anteriores intactas. Para o formato 'fixo' não há
cabeçalho para comparar — o layout é sempre configurado manualmente e
tratado como estático (nunca gera uma nova versão sozinho).
"""

import json
from typing import List

from sqlalchemy import create_engine, inspect, text as sql_text

from config.settings import POSTGRES_URL, logger
from src.utils.sanitize import dedupe_identifiers, sanitize_identifier

# Colunas fixas (nome -> tipo SQL), sempre presentes na tabela dinâmica,
# nesta ordem, antes das colunas extraídas do cabeçalho do relatório.
FIXED_COLUMNS = [
    ("id_empresa", "INTEGER"),
    ("id_rotina", "INTEGER"),
    # Data de execução que gerou o arquivo (normalmente o dia anterior à execução).
    ("data", "DATE"),
]

postgres_engine = create_engine(POSTGRES_URL, echo=False)

# Nomes reservados pelas colunas fixas (+ "id" da PK) — se o próprio
# cabeçalho do relatório tiver uma coluna que sanitize para um destes nomes
# (ex: um cabeçalho com "Data"), ela recebe sufixo (_2, _3...) para não
# colidir com a coluna fixa de mesmo nome.
RESERVED_COLUMN_NAMES = ["id"] + [col for col, _ in FIXED_COLUMNS]

# Nome sanitizado do campo "CODIGO MUNICIPIO" (layouts fixos, ex: 01.20.12):
# quando presente, uma coluna extra "codigo_ibge" é adicionada à tabela
# (resolvida em `file_processor.py` via `src/database/municipios_ibge.py`).
CODIGO_MUNICIPIO_COLUMN = "codigo_municipio"
CODIGO_IBGE_COLUMN = "codigo_ibge"


def build_table_name(id_rotina: int) -> str:
    """Nome-base da tabela (sem sufixo de versão): rel_<id_rotina>_<routine_id sanitizado>."""
    from config.database import DatabaseService

    rotina = DatabaseService.get_rotina_map(id_rotina)
    routine_id = rotina.routine_id if rotina else str(id_rotina)
    suffix = sanitize_identifier(routine_id) or "sem_rotina"
    return f"rel_{id_rotina}_{suffix}"


def build_column_names(text_cabe: str, split_col: str) -> List[str]:
    """Extrai e sanitiza os nomes de coluna a partir do cabeçalho bruto (formato 'delimitado')."""
    raw_names = text_cabe.split(split_col)
    sanitized = [sanitize_identifier(raw) or f"col_{i + 1}" for i, raw in enumerate(raw_names)]
    return dedupe_identifiers(sanitized, reserved=RESERVED_COLUMN_NAMES)


def parse_layout_fixo(raw_json: str):
    """
    Interpreta `MapColRelRotina.layout_fixo`, aceitando dois formatos:

    - lista simples: `[{"tamanho":..,"coluna":..,"nome":..}, ...]` (sem
      filtro de linhas — ex: rotina 01.20.12, um dump limpo sem cabeçalho).
    - dict: `{"campos": [...], "ignorar_linhas_com": ["texto1", "texto2"],
      "exigir_preenchido": "nome_do_campo"}` — usado quando o arquivo é um
      relatório "impresso", com banners/cabeçalhos de página repetidos ao
      longo do arquivo (ex: rotina 16.03.05): qualquer linha que CONTENHA um
      dos textos em `ignorar_linhas_com` é descartada antes de extrair os
      campos. `exigir_preenchido` (opcional) descarta, depois de extrair os
      campos pelas posições, qualquer linha cujo campo indicado (pelo
      `nome` original, não o sanitizado) tenha vindo vazio — útil para
      relatórios com linhas de CONTINUAÇÃO de um mesmo registro (ex: rotina
      01.20.01.12, onde cada banco tem uma 2ª linha só com números de
      agência/identificação, sem repetir "Codigo").

    Returns:
        tuple[list[dict], list[str], Optional[str]]: (campos, padroes_para_ignorar, exigir_preenchido)
    """
    parsed = json.loads(raw_json)
    if isinstance(parsed, dict):
        return (
            parsed.get("campos", []),
            parsed.get("ignorar_linhas_com", []),
            parsed.get("exigir_preenchido"),
        )
    return parsed, [], None


def build_fixed_width_column_names(campos: List[dict]) -> List[str]:
    """Sanitiza os nomes de coluna a partir do layout de largura fixa (formato 'fixo')."""
    raw_names = [item["nome"] for item in campos]
    sanitized = [sanitize_identifier(raw) or f"col_{i + 1}" for i, raw in enumerate(raw_names)]
    return dedupe_identifiers(sanitized, reserved=RESERVED_COLUMN_NAMES)


def compute_column_names(mapeamento) -> List[str]:
    """
    Calcula as colunas de dados de um `MapColRelRotina`, no formato que for
    (delimitado ou fixo). Se o layout incluir o campo "CODIGO MUNICIPIO"
    (ex: rotina 01.20.12), acrescenta a coluna derivada "codigo_ibge" —
    resolvida à parte, na importação, via tabela auxiliar de municípios.
    """
    if mapeamento.formato == "fixo":
        campos, _, _ = parse_layout_fixo(mapeamento.layout_fixo)
        columns = build_fixed_width_column_names(campos)
    else:
        columns = build_column_names(mapeamento.text_cabe, mapeamento.split_col)

    if CODIGO_MUNICIPIO_COLUMN in columns and CODIGO_IBGE_COLUMN not in columns:
        columns = columns + [CODIGO_IBGE_COLUMN]

    return columns


def _create_or_alter_table(table_name: str, column_names: List[str]) -> None:
    """Cria a tabela no Postgres se não existir, ou adiciona colunas (fixas/dinâmicas) que faltarem."""
    inspector = inspect(postgres_engine)

    if not inspector.has_table(table_name):
        fixed_sql = ", ".join(f'"{col}" {sql_type}' for col, sql_type in FIXED_COLUMNS)
        columns_sql = ", ".join(f'"{col}" TEXT' for col in column_names)
        create_sql = (
            f'CREATE TABLE "{table_name}" ('
            "id SERIAL PRIMARY KEY, "
            f"{fixed_sql}"
            + (f", {columns_sql}" if columns_sql else "")
            + ")"
        )
        with postgres_engine.begin() as conn:
            conn.execute(sql_text(create_sql))
        logger.info(f"Tabela dinâmica criada no Postgres: {table_name} ({len(column_names)} coluna(s) de dados)")
        return

    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
    missing_fixed = [(col, sql_type) for col, sql_type in FIXED_COLUMNS if col not in existing_columns]
    new_columns = [col for col in column_names if col not in existing_columns]

    if missing_fixed or new_columns:
        with postgres_engine.begin() as conn:
            for col, sql_type in missing_fixed:
                conn.execute(sql_text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" {sql_type}'))
            for col in new_columns:
                conn.execute(sql_text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" TEXT'))
        logger.info(
            f"Tabela dinâmica '{table_name}' ajustada "
            f"(+{len(missing_fixed)} coluna(s) fixa(s), +{len(new_columns)} coluna(s): {new_columns})"
        )
    else:
        logger.debug(f"Tabela dinâmica '{table_name}' já continha todas as colunas esperadas")


def sync_dynamic_table(mapeamento) -> str:
    """
    Sincroniza a tabela de dados (Postgres) correspondente a este mapeamento
    (`config.database.MapColRelRotina`).

    Formato 'delimitado': versiona — se as colunas sanitizadas do cabeçalho
    baterem com o snapshot da última versão já registrada, reaproveita a
    tabela existente; se diferirem, cria uma nova tabela com sufixo `_v<N>`
    incrementado (a versão anterior é preservada, nunca apagada/renomeada).

    Formato 'fixo': não há cabeçalho para comparar — o layout é estático
    (configurado manualmente), então sempre reaproveita a versão já
    registrada (ou cria a v1, na primeira vez).

    O nome-base da tabela depende só de `id_rotina` (via `routine_id` da
    RotinaMap associada) — não do `nome_rel` do mapeamento — então vários
    mapeamentos da mesma rotina compartilham a mesma linhagem de versões.

    Returns:
        str: nome (com sufixo de versão) da tabela sincronizada.
    """
    from config.database import DatabaseService

    id_rotina = mapeamento.id_rotina
    base_table_name = build_table_name(id_rotina)
    column_names = compute_column_names(mapeamento)
    columns_snapshot = ",".join(column_names)

    version_record = DatabaseService.get_map_col_rel_rotina_version(id_rotina, base_table_name)

    if version_record is None:
        versao = 1
        table_name = f"{base_table_name}_v{versao}"
        _create_or_alter_table(table_name, column_names)
        DatabaseService.upsert_map_col_rel_rotina_version(
            id_rotina=id_rotina,
            id_mapeamento=mapeamento.id,
            base_nome_tabela=base_table_name,
            versao=versao,
            nome_tabela_atual=table_name,
            colunas=columns_snapshot,
        )
        logger.info(f"Tabela dinâmica (versão inicial) registrada: {table_name}")
    elif mapeamento.formato == "fixo" or version_record.colunas == columns_snapshot:
        table_name = version_record.nome_tabela_atual
        logger.debug(f"Layout sem alteração de colunas — reaproveitando tabela '{table_name}'")
        _create_or_alter_table(table_name, column_names)
    else:
        versao = version_record.versao + 1
        table_name = f"{base_table_name}_v{versao}"
        _create_or_alter_table(table_name, column_names)
        DatabaseService.upsert_map_col_rel_rotina_version(
            id_rotina=id_rotina,
            id_mapeamento=mapeamento.id,
            base_nome_tabela=base_table_name,
            versao=versao,
            nome_tabela_atual=table_name,
            colunas=columns_snapshot,
        )
        logger.info(
            f"Cabeçalho mudou: nova versão de tabela criada '{table_name}' "
            f"(versão anterior preservada: '{version_record.nome_tabela_atual}')"
        )

    return table_name
