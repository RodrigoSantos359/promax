"""
Configuração comum dos testes: aponta o SQLite de configuração para um
arquivo temporário e usa uma chave Fernet de teste ANTES de qualquer import
de `config.*` — assim os testes nunca tocam no banco real (data/promax.db).
`load_dotenv()` não sobrescreve variáveis já definidas no ambiente.
"""

import os
import tempfile

from cryptography.fernet import Fernet

_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="promax_test_"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
