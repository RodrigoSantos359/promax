"""
Sanitização de texto livre (ex: cabeçalhos de relatório) para identificadores
SQL seguros (nomes de tabela/coluna).
"""

import re
import unicodedata
from typing import Iterable, List, Optional


def sanitize_identifier(text: str) -> str:
    """
    Converte um texto livre em um identificador SQL seguro: ascii, minúsculo,
    sem acentuação (ex: "ção" -> "cao"), com '.', ',', '+' e '-' apenas
    removidos (juntando as palavras, ex: "NF-e" -> "nfe"), '/' e espaços
    trocados por '_' (ex: "Cod/Fornecedor" -> "cod_fornecedor"), e qualquer
    outro caractere fora de a-z0-9_ descartado.
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()

    # '.', ',', '+' e '-' apenas juntam as palavras, sem separador
    ascii_text = re.sub(r"[.,+\-]", "", ascii_text)
    # '/' e espaços em branco se tornam '_'
    ascii_text = ascii_text.replace("/", "_")
    ascii_text = re.sub(r"\s+", "_", ascii_text)
    # qualquer outro caractere fora de a-z0-9_ é descartado
    ascii_text = re.sub(r"[^a-z0-9_]", "", ascii_text)
    # colapsa underscores repetidos e remove das pontas
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")

    return ascii_text


def dedupe_identifiers(names: List[str], reserved: Optional[Iterable[str]] = None) -> List[str]:
    """
    Garante nomes únicos numa lista já sanitizada, sufixando duplicatas com
    _2, _3, etc. Se `reserved` for informado (ex: nomes de colunas fixas que
    já existem na tabela), qualquer nome da lista que colida com um deles
    também recebe sufixo — evitando colisão com essas colunas reservadas.
    """
    seen = {name: 1 for name in (reserved or [])}
    result = []
    for name in names:
        if name not in seen:
            seen[name] = 1
            result.append(name)
        else:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
    return result
