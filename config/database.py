"""
Database configuration e models usando SQLAlchemy.

Para usar:
    from config.database import SessionLocal, Base, Company, Automation
    session = SessionLocal()
    company = session.query(Company).first()
"""

import json
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from cryptography.fernet import Fernet

from config.settings import DATABASE_URL, ENCRYPTION_KEY, logger

# Setup database engine
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Company(Base):
    """Modelo de Empresa/Cliente PromaX."""

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    promax_url = Column(String(500), nullable=False)
    username = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=False)
    unit = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    # Parâmetros de acesso à API WKRADAR (opcional, por empresa) — usados para
    # obter o token de autenticação (endpoint /api/v1/token), consumido por
    # outras rotinas que precisem de dados da WKRADAR. O token retornado por
    # essa API expira em ~10 minutos, então NÃO é uma credencial fixa: o valor
    # em `token_wkradar` é só um cache best-effort do último token obtido
    # (veja `src/integrations/wkradar_client.py`) — quem for consumir a API
    # deve sempre validar a expiração antes de usar, e buscar um novo se
    # necessário.
    base_empresa_wkradar = Column(String(255), nullable=True)
    usuario_wkradar = Column(String(255), nullable=True)
    senha_wkradar = Column(Text, nullable=True)  # armazenada criptografada (Fernet), igual password_encrypted
    token_wkradar = Column(Text, nullable=True)
    # Token de integração da API BPO ACENE (emitido por empresa no BPO, em
    # Cadastros › Integrações). Credencial fixa — armazenada criptografada
    # (Fernet) e nunca exposta pela API do painel.
    bpo_acene_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    automations = relationship("Automation", back_populates="company", cascade="all, delete-orphan")
    execution_logs = relationship("ExecutionLog", back_populates="company", cascade="all, delete-orphan")

    def set_senha_wkradar(self, senha: str) -> None:
        """Criptografa e salva a senha de acesso à API WKRADAR."""
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            self.senha_wkradar = cipher.encrypt(senha.encode()).decode()
        except Exception as e:
            logger.error(f"Erro ao criptografar senha WKRADAR: {str(e)}")
            raise

    def get_senha_wkradar(self) -> Optional[str]:
        """Descriptografa a senha de acesso à API WKRADAR (None se não configurada)."""
        if not self.senha_wkradar:
            return None
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            return cipher.decrypt(self.senha_wkradar.encode()).decode()
        except Exception as e:
            logger.error(f"Erro ao descriptografar senha WKRADAR: {str(e)}")
            raise

    def set_bpo_acene_token(self, token: str) -> None:
        """Criptografa e salva o token de integração da API BPO ACENE."""
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            self.bpo_acene_token = cipher.encrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Erro ao criptografar token BPO ACENE: {str(e)}")
            raise

    def get_bpo_acene_token(self) -> Optional[str]:
        """Descriptografa o token da API BPO ACENE (None se não configurado)."""
        if not self.bpo_acene_token:
            return None
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            return cipher.decrypt(self.bpo_acene_token.encode()).decode()
        except Exception as e:
            logger.error(f"Erro ao descriptografar token BPO ACENE: {str(e)}")
            raise

    def set_password(self, password: str) -> None:
        """Criptografa e salva a senha."""
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            encrypted = cipher.encrypt(password.encode())
            self.password_encrypted = encrypted.decode()
        except Exception as e:
            logger.error(f"Erro ao criptografar senha: {str(e)}")
            raise

    def get_password(self) -> str:
        """Descriptografa a senha armazenada."""
        try:
            cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
            decrypted = cipher.decrypt(self.password_encrypted.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Erro ao descriptografar senha: {str(e)}")
            raise

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}')>"


class Automation(Base):
    """Modelo de Automação/Rotina."""

    __tablename__ = "automations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    rotina_map_id = Column(Integer, ForeignKey("rotinas_map.id"), nullable=True)
    routine_id = Column(String(20), nullable=False)  # ex: "14.05.05"
    routine_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, nullable=False)
    execution_time = Column(String(5), nullable=False)  # HH:MM
    interval = Column(String(20), nullable=False)  # 'daily', 'weekly', 'monthly'
    schedule_config = Column(Text, nullable=True)  # JSON com detalhes de agendamento (dias da semana, dia do mês, etc)
    max_retries = Column(Integer, default=3)
    retry_delay = Column(Integer, default=60)  # segundos
    last_execution = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)  # 'success', 'failed'
    last_error = Column(Text, nullable=True)
    last_summary = Column(Text, nullable=True)  # ex: "4/30 baixados, 26 sem dados no período, 0 erro(s)"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    company = relationship("Company", back_populates="automations")
    execution_logs = relationship("ExecutionLog", back_populates="automation", cascade="all, delete-orphan")
    rotina_map = relationship("RotinaMap", back_populates="automations")

    def __repr__(self):
        return f"<Automation(id={self.id}, routine_id='{self.routine_id}', company_id={self.company_id})>"


class ExecutionLog(Base):
    """Modelo de Log de Execução."""

    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    automation_id = Column(Integer, ForeignKey("automations.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # 'success', 'failed', 'retry'
    processed_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    result_data = Column(Text, nullable=True)  # JSON string

    # Relacionamentos
    automation = relationship("Automation", back_populates="execution_logs")
    company = relationship("Company", back_populates="execution_logs")

    def __repr__(self):
        return f"<ExecutionLog(id={self.id}, automation_id={self.automation_id}, status='{self.status}')>"


class RotinaMap(Base):
    """
    Mapeamento de rotina — agrupa os campos (`CampoMapConf`) da tela de uma
    rotina PromaX (ex: "14.05.05"), ficando entre `Automation` e
    `CampoMapConf`.

    Uma RotinaMap com `exclusivo=False` é uma definição COMPARTILHADA: várias
    automações (de diferentes empresas) podem apontar para a mesma RotinaMap
    (via `Automation.rotina_map_id`), reaproveitando os mesmos campos.

    Quando um usuário edita os campos de uma automação e marca "exclusivo",
    a RotinaMap compartilhada é bifurcada (copiada, com `exclusivo=True`)
    junto com todos os seus `CampoMapConf`, e a automação passa a apontar
    para essa cópia — sem afetar as demais automações que usam a versão
    compartilhada original. Veja `DatabaseService.fork_rotina_map()`.
    """

    __tablename__ = "rotinas_map"

    id = Column(Integer, primary_key=True, index=True)
    routine_id = Column(String(20), nullable=False)  # ex: "14.05.05"
    nome = Column(String(255), nullable=False)
    exclusivo = Column(Boolean, default=False, nullable=False)
    # Nome (atributo `name`) do botão usado para exportar/baixar o arquivo
    # do relatório, quando diferente do padrão "GerExecl" (CSV). Algumas
    # telas desabilitam "GerExecl" para certos relatórios e exigem clicar em
    # "salvar" (Salvar, accesskey S) em vez disso — ex: rotina 01.20.12.
    # Null/vazio = usa o padrão "GerExecl".
    csv_button_name = Column(String(50), nullable=True)
    # Segundos a esperar pelo relatório ficar pronto após clicar em
    # "Visualizar", quando maior que o padrão (30s). Algumas telas geram o
    # relatório de forma muito mais lenta no servidor (ex: rotina 12.06.07
    # "Situação dos Títulos", observado levando 5-8 minutos) — sem isso, a
    # automação desiste antes do relatório terminar e nunca baixa o CSV.
    # Null/vazio = usa o padrão de `trigger_report_and_download`.
    report_ready_timeout = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    automations = relationship("Automation", back_populates="rotina_map")
    campos_map = relationship(
        "CampoMapConf",
        back_populates="rotina_map",
        cascade="all, delete-orphan",
        order_by="CampoMapConf.ordem, CampoMapConf.id",
    )
    mapeamentos_colunas = relationship(
        "MapColRelRotina",
        back_populates="rotina_map",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<RotinaMap(id={self.id}, routine_id='{self.routine_id}', exclusivo={self.exclusivo})>"


class CampoMapConf(Base):
    """
    Mapeamento de campos do formulário PromaX para uma rotina (RotinaMap).

    Cada linha descreve UM campo da tela da rotina (ex: 14.05.05) e como
    preenchê-lo: qual seletor usar, o tipo de campo (select, text, checkbox,
    radio, botao, date, ...) e a informação a inserir/selecionar.

    Convenção de `info_inserir` conforme `tipo`:
        - 'select':      valor/texto da opção a ser selecionada
        - 'text':        texto literal a ser digitado no campo
        - 'checkbox':    '1' marca o checkbox (verdadeiro); ausente/vazio deixa desmarcado
        - 'radio':       '1' seleciona esta opção específica do grupo de radio
                         (o `select` guarda o HTML do <input type="radio"> com o
                         `value` exato dessa opção; outras opções do mesmo grupo
                         ficam em linhas separadas, cada uma com seu próprio
                         `select` e `info_inserir`)
        - 'botao'/'button': não usa `info_inserir` — a automação sempre clica
                         no elemento (útil para botões auxiliares da tela,
                         diferente do botão principal de gerar relatório)
        - 'date'/'data': não é usado diretamente — o valor é calculado em runtime como
                       (data de execução da automação - 1 dia)

    A ORDEM de preenchimento é explícita via a coluna `ordem` (crescente),
    não adivinhada pelo tipo do campo: telas diferentes têm comportamentos
    diferentes (ex: um botão "Adicionar" pode resetar outros campos da tela
    ao ser clicado — nesse caso ele deve vir ANTES desses campos; já um
    botão "Gerar Relatório" deve vir DEPOIS). Configure `ordem` pelo editor
    de rotinas de acordo com o comportamento real da tela.
    """

    __tablename__ = "camps_map_conf"

    id = Column(Integer, primary_key=True, index=True)
    rotina_map_id = Column(Integer, ForeignKey("rotinas_map.id"), nullable=False)
    nome_campo = Column(String(255), nullable=False)
    select = Column(Text, nullable=False)  # seletor CSS/XPath do campo no HTML
    tipo = Column(String(50), nullable=False)  # 'select', 'text', 'checkbox', 'radio', 'botao', 'date', etc
    info_inserir = Column(Text, nullable=True)
    ordem = Column(Integer, nullable=False, default=0)  # ordem de preenchimento (crescente)
    gerar_lista_opcoes = Column(Boolean, default=False, nullable=False)  # gera 1 relatório por opção (só 'select')
    opcoes_modo = Column(String(10), nullable=True)  # 'manual' ou 'todas' (só quando gerar_lista_opcoes=True)
    opcoes_lista = Column(Text, nullable=True)  # JSON: lista de opções (modo 'manual')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    rotina_map = relationship("RotinaMap", back_populates="campos_map")

    def resolve_value(self, execution_date: datetime = None):
        """
        Resolve o valor a ser inserido/selecionado no campo em tempo de execução.

        - 'date'/'data': ignora `info_inserir` e calcula (data de execução - 1 dia),
          formatada como DD/MM/AAAA (padrão de datas do PromaX).
        - 'checkbox'/'radio': retorna True se `info_inserir == '1'`, senão False.
        - 'botao'/'button': não é usado — a automação sempre clica no elemento.
        - demais tipos ('select', 'text', ...): retorna `info_inserir` como está.
        """
        from datetime import timedelta

        if self.tipo in ("date", "data"):
            base_date = execution_date or datetime.utcnow()
            return (base_date - timedelta(days=1)).strftime("%d/%m/%Y")

        if self.tipo in ("checkbox", "radio"):
            return self.info_inserir == "1"

        return self.info_inserir

    def __repr__(self):
        return f"<CampoMapConf(id={self.id}, nome_campo='{self.nome_campo}', tipo='{self.tipo}')>"


class MapColRelRotina(Base):
    """
    Mapeamento das colunas do arquivo (CSV) gerado pelo relatório de uma
    RotinaMap — descreve como interpretar o arquivo baixado (separador,
    quantidade de colunas, cabeçalho original), para uso posterior por
    quem for ler/processar esses arquivos.
    """

    __tablename__ = "map_col_rel_rotina"

    id = Column(Integer, primary_key=True, index=True)
    id_rotina = Column(Integer, ForeignKey("rotinas_map.id"), nullable=False)
    nome_rel = Column(String(255), nullable=False)
    quant_col = Column(Integer, nullable=False)
    split_col = Column(String(10), nullable=False)
    text_cabe = Column(Text, nullable=False)
    # 'delimitado' (padrão, ex: CSV separado por ';', reconhecido automaticamente
    # a partir do cabeçalho real do arquivo) ou 'fixo' (arquivo de largura fixa,
    # ex: .inf — não tem cabeçalho, o layout vem de `layout_fixo` e é sempre
    # configurado manualmente, nunca auto-detectado).
    formato = Column(String(20), nullable=False, default="delimitado")
    # JSON com a lista de campos do layout de largura fixa (quando formato='fixo'):
    # [{"tamanho": 5, "coluna": 1, "nome": "COLIGO CLIENTE"}, ...]. Null quando formato='delimitado'.
    layout_fixo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    rotina_map = relationship("RotinaMap", back_populates="mapeamentos_colunas")

    def __repr__(self):
        return f"<MapColRelRotina(id={self.id}, nome_rel='{self.nome_rel}', id_rotina={self.id_rotina})>"


class MapColRelRotinaVersion(Base):
    """
    Registro auxiliar da última versão da tabela dinâmica de dados (Postgres)
    gerada para cada mapeamento de colunas de relatório (`MapColRelRotina`).

    Sempre que o cabeçalho (`text_cabe`) de um mapeamento é salvo, comparamos
    as colunas sanitizadas resultantes com o snapshot aqui registrado para o
    mesmo `id_rotina` + nome-base da tabela (`base_nome_tabela`): se baterem,
    reaproveitamos a tabela já criada (`nome_tabela_atual`); se diferirem,
    incrementamos `versao` e criamos uma nova tabela com o sufixo `_v<N>`,
    preservando a(s) versão(ões) anterior(es) intacta(s).
    """

    __tablename__ = "map_col_rel_rotina_versoes"
    __table_args__ = (
        UniqueConstraint("id_rotina", "base_nome_tabela", name="uq_map_col_rel_rotina_versao"),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_rotina = Column(Integer, ForeignKey("rotinas_map.id"), nullable=False)
    id_mapeamento = Column(Integer, ForeignKey("map_col_rel_rotina.id"), nullable=True)
    base_nome_tabela = Column(String(255), nullable=False)
    versao = Column(Integer, nullable=False, default=1)
    nome_tabela_atual = Column(String(255), nullable=False)
    colunas = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return (
            f"<MapColRelRotinaVersion(id_rotina={self.id_rotina}, "
            f"base='{self.base_nome_tabela}', versao={self.versao})>"
        )


class ArquivoBaixado(Base):
    """
    Registro auxiliar de cada arquivo baixado (ou tentativa de download) por
    uma automação — nome do arquivo, rotina e empresa de origem, data de
    referência dos dados e status, para auditoria e associação correta entre
    o arquivo, a rotina e a empresa que o gerou.
    """

    __tablename__ = "arquivos_baixados"

    id = Column(Integer, primary_key=True, index=True)
    id_rotina = Column(Integer, ForeignKey("rotinas_map.id"), nullable=True)
    id_empresa = Column(Integer, ForeignKey("companies.id"), nullable=True)
    nome_arquivo = Column(String(500), nullable=True)
    # Data de referência dos dados do arquivo: data do disparo da automação
    # menos 1 dia (mesma convenção da coluna "data" das tabelas dinâmicas).
    data = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)  # 'success', 'failed', 'sem_dados'
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<ArquivoBaixado(id={self.id}, id_rotina={self.id_rotina}, "
            f"nome_arquivo='{self.nome_arquivo}', status='{self.status}')>"
        )


class EnvioBpo(Base):
    """
    Fila de envio de arquivos de relatório para a API BPO ACENE. Cada
    registro aponta para uma CÓPIA do arquivo baixado (em
    `BPO_ACENE_OUTBOX_DIR`), porque o original é apagado assim que a
    importação no Postgres termina. Processada por
    `src/integrations/bpo_acene_outbox.py`, com novas tentativas em caso de
    falha de rede/servidor.
    """

    __tablename__ = "envios_bpo"

    id = Column(Integer, primary_key=True, index=True)
    id_empresa = Column(Integer, ForeignKey("companies.id"), nullable=False)
    id_rotina = Column(Integer, ForeignKey("rotinas_map.id"), nullable=True)
    competencia = Column(String(7), nullable=False)  # AAAA-MM
    caminho_arquivo = Column(String(500), nullable=False)
    nome_arquivo = Column(String(255), nullable=False)  # nome original, enviado à API
    # 'pendente', 'enviado', 'duplicado' (já recebido antes), 'rejeitado'
    # (erro definitivo: 401/403/422...) ou 'erro' (esgotou as tentativas).
    status = Column(String(20), nullable=False, default="pendente")
    tentativas = Column(Integer, nullable=False, default=0)
    proxima_tentativa = Column(DateTime, nullable=True)
    http_status = Column(Integer, nullable=True)
    lote_id = Column(Integer, nullable=True)
    lote_status = Column(String(30), nullable=True)
    mensagem = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    enviado_em = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<EnvioBpo(id={self.id}, competencia='{self.competencia}', status='{self.status}')>"


def init_db() -> None:
    """Cria todas as tabelas no banco de dados e aplica migrações leves de colunas novas."""
    try:
        Base.metadata.create_all(bind=engine)
        _migrate_add_missing_columns()
        _migrate_rotinas_map()
        _migrate_rotina_map_ownership()
        _migrate_campo_ordem()
        _migrate_campo_opcoes_lista()
        logger.info("Banco de dados inicializado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {str(e)}")
        raise


def _migrate_add_missing_columns() -> None:
    """
    Adiciona colunas novas em tabelas já existentes (SQLite não tem ALTER TABLE
    automático via create_all). Cada ALTER é ignorado se a coluna já existir.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "automations" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("automations")}

    if "schedule_config" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE automations ADD COLUMN schedule_config TEXT"))
        logger.info("Coluna 'schedule_config' adicionada à tabela 'automations'")

    if "rotina_map_id" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE automations ADD COLUMN rotina_map_id INTEGER REFERENCES rotinas_map(id)"))
        logger.info("Coluna 'rotina_map_id' adicionada à tabela 'automations'")

    if "last_summary" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE automations ADD COLUMN last_summary TEXT"))
        logger.info("Coluna 'last_summary' adicionada à tabela 'automations'")

    if "rotinas_map" in inspector.get_table_names():
        rotinas_map_columns = {col["name"] for col in inspector.get_columns("rotinas_map")}
        if "csv_button_name" not in rotinas_map_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE rotinas_map ADD COLUMN csv_button_name VARCHAR(50)"))
            logger.info("Coluna 'csv_button_name' adicionada à tabela 'rotinas_map'")

        if "report_ready_timeout" not in rotinas_map_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE rotinas_map ADD COLUMN report_ready_timeout INTEGER"))
            logger.info("Coluna 'report_ready_timeout' adicionada à tabela 'rotinas_map'")

    if "companies" in inspector.get_table_names():
        companies_columns = {col["name"] for col in inspector.get_columns("companies")}
        novas_colunas_wkradar = {
            "base_empresa_wkradar": "VARCHAR(255)",
            "usuario_wkradar": "VARCHAR(255)",
            "senha_wkradar": "TEXT",
            "token_wkradar": "TEXT",
            "bpo_acene_token": "TEXT",
        }
        for coluna, tipo_sql in novas_colunas_wkradar.items():
            if coluna not in companies_columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE companies ADD COLUMN {coluna} {tipo_sql}"))
                logger.info(f"Coluna '{coluna}' adicionada à tabela 'companies'")

    if "map_col_rel_rotina" in inspector.get_table_names():
        map_col_columns = {col["name"] for col in inspector.get_columns("map_col_rel_rotina")}

        if "formato" not in map_col_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE map_col_rel_rotina ADD COLUMN formato VARCHAR(20) NOT NULL DEFAULT 'delimitado'"))
            logger.info("Coluna 'formato' adicionada à tabela 'map_col_rel_rotina'")

        if "layout_fixo" not in map_col_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE map_col_rel_rotina ADD COLUMN layout_fixo TEXT"))
            logger.info("Coluna 'layout_fixo' adicionada à tabela 'map_col_rel_rotina'")


def _migrate_rotinas_map() -> None:
    """
    Migra `camps_map_conf` do esquema antigo (coluna `automation_id` direto)
    para o novo esquema (`Automation` -> `RotinaMap` -> `CampoMapConf`),
    preservando os dados já cadastrados.

    Para cada `automation_id` distinto encontrado em `camps_map_conf`, cria
    um `RotinaMap` correspondente (usando routine_id/routine_name da própria
    automação) e reatribui os campos a ele via `rotina_map_id`. Em seguida
    reconstrói a tabela sem a coluna antiga `automation_id` — o SQLite não
    permite `DROP COLUMN` numa coluna usada em constraint de FOREIGN KEY,
    então é preciso recriar a tabela e copiar os dados.

    Idempotente: se `camps_map_conf` não tiver mais a coluna
    `automation_id`, não faz nada.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "camps_map_conf" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("camps_map_conf")}

    if "automation_id" not in existing_columns:
        return

    logger.info("Migrando camps_map_conf: automation_id -> rotina_map_id (via rotinas_map)")

    with engine.begin() as conn:
        if "rotina_map_id" not in existing_columns:
            conn.execute(text("ALTER TABLE camps_map_conf ADD COLUMN rotina_map_id INTEGER"))

        distinct_automation_ids = conn.execute(
            text("SELECT DISTINCT automation_id FROM camps_map_conf")
        ).fetchall()

        for (automation_id,) in distinct_automation_ids:
            automation_row = conn.execute(
                text("SELECT routine_id, routine_name FROM automations WHERE id = :aid"),
                {"aid": automation_id},
            ).fetchone()

            if automation_row is None:
                logger.warning(
                    f"Automação {automation_id} não encontrada; "
                    f"campos mapeados órfãos não foram migrados"
                )
                continue

            routine_id, routine_name = automation_row

            existing_map = conn.execute(
                text("SELECT id FROM rotinas_map WHERE automation_id = :aid"),
                {"aid": automation_id},
            ).fetchone()

            if existing_map:
                rotina_map_id = existing_map[0]
            else:
                insert_result = conn.execute(
                    text(
                        "INSERT INTO rotinas_map (automation_id, routine_id, nome, created_at, updated_at) "
                        "VALUES (:aid, :rid, :nome, :now, :now)"
                    ),
                    {
                        "aid": automation_id,
                        "rid": routine_id,
                        "nome": routine_name,
                        "now": datetime.utcnow(),
                    },
                )
                rotina_map_id = insert_result.lastrowid
                logger.info(
                    f"RotinaMap criado para automação {automation_id}: "
                    f"id={rotina_map_id}, routine_id={routine_id}"
                )

            conn.execute(
                text(
                    "UPDATE camps_map_conf SET rotina_map_id = :rmid "
                    "WHERE automation_id = :aid"
                ),
                {"rmid": rotina_map_id, "aid": automation_id},
            )

        # SQLite não permite DROP COLUMN em coluna usada por FOREIGN KEY;
        # reconstrói a tabela sem `automation_id`.
        conn.execute(text("ALTER TABLE camps_map_conf RENAME TO camps_map_conf_old"))
        conn.execute(text(
            """
            CREATE TABLE camps_map_conf (
                id INTEGER PRIMARY KEY,
                rotina_map_id INTEGER NOT NULL REFERENCES rotinas_map(id),
                nome_campo VARCHAR(255) NOT NULL,
                "select" TEXT NOT NULL,
                tipo VARCHAR(50) NOT NULL,
                info_inserir TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO camps_map_conf
                (id, rotina_map_id, nome_campo, "select", tipo, info_inserir, created_at, updated_at)
            SELECT id, rotina_map_id, nome_campo, "select", tipo, info_inserir, created_at, updated_at
            FROM camps_map_conf_old
            """
        ))
        conn.execute(text("DROP TABLE camps_map_conf_old"))

    logger.info("Migração de camps_map_conf para rotinas_map concluída")


def _migrate_rotina_map_ownership() -> None:
    """
    Migra o vínculo RotinaMap -> Automation (antiga coluna
    `rotinas_map.automation_id`) para o sentido inverso
    `Automation.rotina_map_id`, que permite várias automações
    compartilharem a mesma RotinaMap. Também adiciona a coluna `exclusivo`
    em `rotinas_map`.

    Idempotente: se `rotinas_map` não tiver mais a coluna `automation_id`,
    não faz nada.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "rotinas_map" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("rotinas_map")}

    if "automation_id" not in existing_columns:
        return

    logger.info("Migrando rotinas_map: automation_id -> automations.rotina_map_id (+ coluna exclusivo)")

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, automation_id FROM rotinas_map")).fetchall()
        for rotina_map_id, automation_id in rows:
            if automation_id is not None:
                conn.execute(
                    text("UPDATE automations SET rotina_map_id = :rmid WHERE id = :aid"),
                    {"rmid": rotina_map_id, "aid": automation_id},
                )

        conn.execute(text("ALTER TABLE rotinas_map RENAME TO rotinas_map_old"))
        conn.execute(text(
            """
            CREATE TABLE rotinas_map (
                id INTEGER PRIMARY KEY,
                routine_id VARCHAR(20) NOT NULL,
                nome VARCHAR(255) NOT NULL,
                exclusivo BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO rotinas_map (id, routine_id, nome, exclusivo, created_at, updated_at)
            SELECT id, routine_id, nome, 0, created_at, updated_at FROM rotinas_map_old
            """
        ))
        conn.execute(text("DROP TABLE rotinas_map_old"))

    logger.info("Migração de rotinas_map (ownership + exclusivo) concluída")


def _migrate_campo_ordem() -> None:
    """
    Adiciona a coluna `ordem` em `camps_map_conf`, inicializando os
    registros existentes com a ordem atual (por `id`) — nada muda até o
    usuário reordenar explicitamente pelo editor de rotinas.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "camps_map_conf" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("camps_map_conf")}

    if "ordem" in existing_columns:
        return

    logger.info("Adicionando coluna 'ordem' em camps_map_conf")

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE camps_map_conf ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("UPDATE camps_map_conf SET ordem = id"))

    logger.info("Coluna 'ordem' adicionada e inicializada por id")


def _migrate_campo_opcoes_lista() -> None:
    """
    Adiciona as colunas `gerar_lista_opcoes`, `opcoes_modo` e `opcoes_lista`
    em `camps_map_conf` (suporte a gerar vários relatórios, um por opção de
    um campo 'select'). Registros existentes ficam com `gerar_lista_opcoes`
    desligado, sem nenhuma mudança de comportamento.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "camps_map_conf" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("camps_map_conf")}

    if "gerar_lista_opcoes" in existing_columns:
        return

    logger.info("Adicionando colunas 'gerar_lista_opcoes', 'opcoes_modo', 'opcoes_lista' em camps_map_conf")

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE camps_map_conf ADD COLUMN gerar_lista_opcoes BOOLEAN NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE camps_map_conf ADD COLUMN opcoes_modo VARCHAR(10)"))
        conn.execute(text("ALTER TABLE camps_map_conf ADD COLUMN opcoes_lista TEXT"))

    logger.info("Colunas de lista de opções adicionadas em camps_map_conf")


def get_db():
    """
    Dependency injection para obter sessão de banco de dados.

    Uso:
        db = get_db()
        company = db.query(Company).first()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_default_company() -> None:
    """
    Garante que a empresa Dibrasa (dados de acesso ao PromaX) exista no banco.

    Idempotente: se a empresa "Dibrasa" já existir, não faz nada.
    Usa as credenciais padrão configuradas em config/settings.py (.env).
    """
    from config.settings import PROMAX_URL, PROMAX_DEFAULT_USER, PROMAX_DEFAULT_PASSWORD

    db = SessionLocal()
    try:
        existing = db.query(Company).filter(Company.name == "Dibrasa").first()
        if existing:
            logger.info("Empresa 'Dibrasa' já existe no banco de dados (seed ignorado)")
            return

        company = Company(
            name="Dibrasa",
            promax_url=PROMAX_URL,
            username=PROMAX_DEFAULT_USER,
            unit="161.0001 - Dibrasa",
        )
        company.set_password(PROMAX_DEFAULT_PASSWORD)
        db.add(company)
        db.commit()
        logger.info("Empresa 'Dibrasa' criada automaticamente (seed)")
    finally:
        db.close()


# Database utility functions
class DatabaseService:
    """Serviço de utilidades de banco de dados."""

    @staticmethod
    def create_company(
        name: str,
        promax_url: str,
        username: str,
        password: str,
        unit: str,
        base_empresa_wkradar: str = None,
        usuario_wkradar: str = None,
        senha_wkradar: str = None,
        bpo_acene_token: str = None,
    ) -> Company:
        """Cria uma nova empresa (parâmetros WKRADAR e token BPO ACENE são opcionais)."""
        db = SessionLocal()
        try:
            company = Company(
                name=name,
                promax_url=promax_url,
                username=username,
                unit=unit,
                base_empresa_wkradar=base_empresa_wkradar or None,
                usuario_wkradar=usuario_wkradar or None,
            )
            company.set_password(password)
            if senha_wkradar:
                company.set_senha_wkradar(senha_wkradar)
            if bpo_acene_token:
                company.set_bpo_acene_token(bpo_acene_token.strip())
            db.add(company)
            db.commit()
            db.refresh(company)
            logger.info(f"Empresa criada: {name}")
            return company
        finally:
            db.close()

    @staticmethod
    def get_company(company_id: int) -> Company:
        """Obtém uma empresa pelo ID."""
        db = SessionLocal()
        try:
            return db.query(Company).filter(Company.id == company_id).first()
        finally:
            db.close()

    @staticmethod
    def get_company_wkradar_credentials(company_id: int) -> Optional[dict]:
        """
        Retorna as credenciais de acesso à API WKRADAR de uma empresa (senha
        já descriptografada), ou None se a empresa não tiver essas
        credenciais configuradas. Usado por `src/integrations/wkradar_client.py`
        para buscar o token — nunca expor isto em uma resposta de API.
        """
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company or not (company.base_empresa_wkradar and company.usuario_wkradar and company.senha_wkradar):
                return None
            return {
                "empresa": company.base_empresa_wkradar,
                "nomeUsuario": company.usuario_wkradar,
                "senha": company.get_senha_wkradar(),
            }
        finally:
            db.close()

    @staticmethod
    def get_company_bpo_acene_token(company_id: int) -> Optional[str]:
        """
        Token da API BPO ACENE da empresa (já descriptografado), ou None se
        não configurado. Usado só por `src/integrations/bpo_acene_outbox.py`
        — nunca expor isto em uma resposta de API.
        """
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            return company.get_bpo_acene_token() if company else None
        finally:
            db.close()

    @staticmethod
    def get_company_by_name(name: str) -> Company:
        """Obtém uma empresa pelo nome."""
        db = SessionLocal()
        try:
            return db.query(Company).filter(Company.name == name).first()
        finally:
            db.close()

    @staticmethod
    def get_all_companies(active_only: bool = True):
        """Obtém todas as empresas."""
        db = SessionLocal()
        try:
            query = db.query(Company)
            if active_only:
                query = query.filter(Company.is_active == True)
            return query.all()
        finally:
            db.close()

    @staticmethod
    def update_company(
        company_id: int,
        name: str = None,
        promax_url: str = None,
        username: str = None,
        password: str = None,
        unit: str = None,
        is_active: bool = None,
        base_empresa_wkradar: str = None,
        usuario_wkradar: str = None,
        senha_wkradar: str = None,
        bpo_acene_token: str = None,
    ) -> Company:
        """
        Atualiza os campos informados de uma empresa existente.

        `password`/`senha_wkradar`/`bpo_acene_token` só são alteradas se
        informadas (não vazias) — permite editar os demais campos sem
        precisar redigitar as credenciais.
        """
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise ValueError(f"Empresa não encontrada: {company_id}")

            if name is not None:
                company.name = name
            if promax_url is not None:
                company.promax_url = promax_url
            if username is not None:
                company.username = username
            if unit is not None:
                company.unit = unit
            if is_active is not None:
                company.is_active = is_active
            if password:
                company.set_password(password)
            if base_empresa_wkradar is not None:
                company.base_empresa_wkradar = base_empresa_wkradar or None
            if usuario_wkradar is not None:
                company.usuario_wkradar = usuario_wkradar or None
            if senha_wkradar:
                company.set_senha_wkradar(senha_wkradar)
            if bpo_acene_token:
                company.set_bpo_acene_token(bpo_acene_token.strip())

            db.commit()
            db.refresh(company)
            logger.info(f"Empresa atualizada: {company_id}")
            return company
        finally:
            db.close()

    @staticmethod
    def create_automation(
        company_id: int,
        routine_id: str,
        routine_name: str,
        start_date: datetime,
        execution_time: str,
        interval: str,
        max_retries: int = 3,
        retry_delay: int = 60,
        is_active: bool = True,
        schedule_config: str = None,
    ) -> Automation:
        """
        Cria uma nova automação.

        Resolve automaticamente a RotinaMap: reaproveita a RotinaMap
        compartilhada (`exclusivo=False`) já existente para `routine_id`, se
        houver; caso contrário cria uma nova RotinaMap vazia (sem copiar
        campos), que poderá ser preenchida depois pelo editor de rotinas.
        """
        db = SessionLocal()
        try:
            rotina_map = (
                db.query(RotinaMap)
                .filter(RotinaMap.routine_id == routine_id, RotinaMap.exclusivo == False)
                .first()
            )

            if rotina_map is None:
                rotina_map = RotinaMap(routine_id=routine_id, nome=routine_name, exclusivo=False)
                db.add(rotina_map)
                db.flush()
                logger.info(f"RotinaMap compartilhada criada para routine_id={routine_id} (id={rotina_map.id})")

            automation = Automation(
                company_id=company_id,
                rotina_map_id=rotina_map.id,
                routine_id=routine_id,
                routine_name=routine_name,
                start_date=start_date,
                execution_time=execution_time,
                interval=interval,
                max_retries=max_retries,
                retry_delay=retry_delay,
                is_active=is_active,
                schedule_config=schedule_config,
            )
            db.add(automation)
            db.commit()
            db.refresh(automation)
            logger.info(f"Automação criada: {routine_id} (ID: {automation.id}, rotina_map_id={rotina_map.id})")
            return automation
        finally:
            db.close()

    @staticmethod
    def update_automation(
        automation_id: int,
        routine_id: str = None,
        routine_name: str = None,
        execution_time: str = None,
        interval: str = None,
        max_retries: int = None,
        retry_delay: int = None,
        is_active: bool = None,
        schedule_config: str = None,
        clear_schedule_config: bool = False,
    ) -> Automation:
        """Atualiza os campos informados de uma automação existente."""
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")

            if routine_id is not None:
                automation.routine_id = routine_id
            if routine_name is not None:
                automation.routine_name = routine_name
            if execution_time is not None:
                automation.execution_time = execution_time
            if interval is not None:
                automation.interval = interval
            if max_retries is not None:
                automation.max_retries = max_retries
            if retry_delay is not None:
                automation.retry_delay = retry_delay
            if is_active is not None:
                automation.is_active = is_active
            if clear_schedule_config:
                automation.schedule_config = None
            elif schedule_config is not None:
                automation.schedule_config = schedule_config

            db.commit()
            db.refresh(automation)
            logger.info(f"Automação atualizada: {automation_id}")
            return automation
        finally:
            db.close()

    @staticmethod
    def set_automation_active(automation_id: int, is_active: bool) -> Automation:
        """Ativa ou desativa uma automação."""
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")
            automation.is_active = is_active
            db.commit()
            db.refresh(automation)
            logger.info(f"Automação {automation_id} {'ativada' if is_active else 'desativada'}")
            return automation
        finally:
            db.close()

    @staticmethod
    def create_rotina_map(routine_id: str, nome: str, exclusivo: bool = False) -> "RotinaMap":
        """Cria uma RotinaMap (compartilhada por padrão)."""
        db = SessionLocal()
        try:
            rotina_map = RotinaMap(routine_id=routine_id, nome=nome, exclusivo=exclusivo)
            db.add(rotina_map)
            db.commit()
            db.refresh(rotina_map)
            logger.info(f"RotinaMap criada: {nome} (routine_id={routine_id}, exclusivo={exclusivo})")
            return rotina_map
        finally:
            db.close()

    @staticmethod
    def get_rotina_map(rotina_map_id: int) -> "RotinaMap":
        """Obtém uma RotinaMap pelo ID."""
        db = SessionLocal()
        try:
            return db.query(RotinaMap).filter(RotinaMap.id == rotina_map_id).first()
        finally:
            db.close()

    @staticmethod
    def get_all_rotinas_map():
        """Obtém todas as RotinaMap cadastradas (para a tela de gerenciamento global)."""
        db = SessionLocal()
        try:
            return db.query(RotinaMap).order_by(RotinaMap.routine_id).all()
        finally:
            db.close()

    @staticmethod
    def update_rotina_map(
        rotina_map_id: int,
        nome: str = None,
        csv_button_name: str = None,
        report_ready_timeout: int = None,
    ) -> "RotinaMap":
        """Atualiza o nome, o botão de exportação (se diferente do padrão "GerExecl") e/ou o timeout de espera do relatório de uma RotinaMap."""
        db = SessionLocal()
        try:
            rotina_map = db.query(RotinaMap).filter(RotinaMap.id == rotina_map_id).first()
            if not rotina_map:
                raise ValueError(f"RotinaMap não encontrada: {rotina_map_id}")
            if nome is not None:
                rotina_map.nome = nome
            if csv_button_name is not None:
                rotina_map.csv_button_name = csv_button_name or None
            if report_ready_timeout is not None:
                rotina_map.report_ready_timeout = report_ready_timeout or None
            db.commit()
            db.refresh(rotina_map)
            return rotina_map
        finally:
            db.close()

    @staticmethod
    def delete_rotina_map(rotina_map_id: int) -> None:
        """Remove uma RotinaMap e seus campos (cascade)."""
        db = SessionLocal()
        try:
            rotina_map = db.query(RotinaMap).filter(RotinaMap.id == rotina_map_id).first()
            if not rotina_map:
                raise ValueError(f"RotinaMap não encontrada: {rotina_map_id}")
            db.delete(rotina_map)
            db.commit()
            logger.info(f"RotinaMap removida: {rotina_map_id}")
        finally:
            db.close()

    @staticmethod
    def fork_rotina_map(automation_id: int) -> "RotinaMap":
        """
        Bifurca (copy-on-write) a RotinaMap compartilhada usada por uma
        automação: cria uma nova RotinaMap `exclusivo=True` com o mesmo
        `routine_id`/`nome`, copia todos os `CampoMapConf` da RotinaMap
        original para a nova, e reaponta `Automation.rotina_map_id` para a
        cópia — sem alterar a RotinaMap/campos originais (que continuam
        servindo outras automações).

        Se a RotinaMap atual da automação já for `exclusivo=True`, não faz
        nada e apenas a retorna (evita bifurcações redundantes).

        Args:
            automation_id: ID da automação cuja RotinaMap será bifurcada

        Returns:
            RotinaMap: a RotinaMap exclusiva (nova, ou a já existente)

        Raises:
            ValueError: se a automação ou sua RotinaMap não existirem
        """
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")
            if not automation.rotina_map_id:
                raise ValueError(f"Automação {automation_id} não tem RotinaMap associada")

            original = db.query(RotinaMap).filter(RotinaMap.id == automation.rotina_map_id).first()
            if not original:
                raise ValueError(f"RotinaMap não encontrada: {automation.rotina_map_id}")

            if original.exclusivo:
                return original

            fork = RotinaMap(routine_id=original.routine_id, nome=original.nome, exclusivo=True)
            db.add(fork)
            db.flush()

            campos_originais = db.query(CampoMapConf).filter(
                CampoMapConf.rotina_map_id == original.id
            ).all()

            for campo in campos_originais:
                db.add(CampoMapConf(
                    rotina_map_id=fork.id,
                    nome_campo=campo.nome_campo,
                    select=campo.select,
                    tipo=campo.tipo,
                    info_inserir=campo.info_inserir,
                ))

            automation.rotina_map_id = fork.id
            db.commit()
            db.refresh(fork)

            logger.info(
                f"RotinaMap {original.id} bifurcada para {fork.id} (exclusiva da automação {automation_id}), "
                f"{len(campos_originais)} campo(s) copiado(s)"
            )
            return fork
        finally:
            db.close()

    @staticmethod
    def create_campo_map_conf(
        rotina_map_id: int,
        nome_campo: str,
        select: str,
        tipo: str,
        info_inserir: str = None,
        ordem: int = None,
        gerar_lista_opcoes: bool = False,
        opcoes_modo: str = None,
        opcoes_lista: str = None,
    ) -> "CampoMapConf":
        """
        Cria um mapeamento de campo (seletor + tipo + valor) para uma RotinaMap.

        Se `ordem` não for informado, o campo vai para o final da lista
        (maior `ordem` da RotinaMap + 10 — o espaçamento facilita inserir
        campos "entre" outros depois, editando a ordem manualmente).

        `gerar_lista_opcoes`/`opcoes_modo`/`opcoes_lista`: suporte a gerar um
        relatório por opção de um campo 'select' (`opcoes_modo='manual'` usa
        a lista em `opcoes_lista` — JSON de strings; `opcoes_modo='todas'`
        varre em tempo de execução todas as opções existentes no <select>).
        """
        db = SessionLocal()
        try:
            if ordem is None:
                max_ordem = db.query(CampoMapConf).filter(
                    CampoMapConf.rotina_map_id == rotina_map_id
                ).order_by(CampoMapConf.ordem.desc()).first()
                ordem = (max_ordem.ordem + 10) if max_ordem else 10

            campo = CampoMapConf(
                rotina_map_id=rotina_map_id,
                nome_campo=nome_campo,
                select=select,
                tipo=tipo,
                info_inserir=info_inserir,
                ordem=ordem,
                gerar_lista_opcoes=gerar_lista_opcoes,
                opcoes_modo=opcoes_modo,
                opcoes_lista=opcoes_lista,
            )
            db.add(campo)
            db.commit()
            db.refresh(campo)
            logger.info(f"Campo mapeado criado: {nome_campo} (rotina_map_id={rotina_map_id}, ordem={ordem})")
            return campo
        finally:
            db.close()

    @staticmethod
    def get_campos_map_conf(rotina_map_id: int):
        """Obtém todos os mapeamentos de campo de uma RotinaMap, na ordem de preenchimento."""
        db = SessionLocal()
        try:
            return db.query(CampoMapConf).filter(
                CampoMapConf.rotina_map_id == rotina_map_id
            ).order_by(CampoMapConf.ordem, CampoMapConf.id).all()
        finally:
            db.close()

    @staticmethod
    def get_campos_map_conf_by_automation(automation_id: int):
        """
        Obtém todos os mapeamentos de campo da RotinaMap usada por uma
        automação, na ordem de preenchimento (`ordem`, depois `id`).
        """
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation or not automation.rotina_map_id:
                return []

            return db.query(CampoMapConf).filter(
                CampoMapConf.rotina_map_id == automation.rotina_map_id
            ).order_by(CampoMapConf.ordem, CampoMapConf.id).all()
        finally:
            db.close()

    @staticmethod
    def save_campo_map_conf_for_automation(
        automation_id: int,
        nome_campo: str,
        select: str,
        tipo: str,
        info_inserir: str = None,
        campo_id: int = None,
        tornar_exclusivo: bool = False,
        ordem: int = None,
        gerar_lista_opcoes: bool = None,
        opcoes_modo: str = None,
        opcoes_lista: str = None,
    ) -> "CampoMapConf":
        """
        Cria ou atualiza um campo mapeado para a automação, aplicando a
        regra de exclusividade (item 4): se `tornar_exclusivo=True` e a
        RotinaMap atual da automação ainda for compartilhada, bifurca
        (`fork_rotina_map`) antes de salvar — assim a edição não afeta
        outras automações que usam a mesma RotinaMap.

        Args:
            automation_id: automação sendo editada
            nome_campo, select, tipo, info_inserir: dados do campo
            campo_id: se informado, atualiza esse campo; senão, cria um novo
            tornar_exclusivo: marca/força a bifurcação antes de salvar

        Returns:
            CampoMapConf: o campo criado/atualizado (já na RotinaMap correta)
        """
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")
            rotina_map_id = automation.rotina_map_id
        finally:
            db.close()

        if tornar_exclusivo:
            fork = DatabaseService.fork_rotina_map(automation_id)
            rotina_map_id = fork.id

        if not rotina_map_id:
            raise ValueError(f"Automação {automation_id} não tem RotinaMap associada")

        if campo_id:
            return DatabaseService.update_campo_map_conf(
                campo_id=campo_id,
                nome_campo=nome_campo,
                select=select,
                tipo=tipo,
                info_inserir=info_inserir,
                ordem=ordem,
                gerar_lista_opcoes=gerar_lista_opcoes,
                opcoes_modo=opcoes_modo,
                opcoes_lista=opcoes_lista,
            )

        return DatabaseService.create_campo_map_conf(
            rotina_map_id=rotina_map_id,
            nome_campo=nome_campo,
            select=select,
            tipo=tipo,
            info_inserir=info_inserir,
            ordem=ordem,
            gerar_lista_opcoes=bool(gerar_lista_opcoes),
            opcoes_modo=opcoes_modo,
            opcoes_lista=opcoes_lista,
        )

    @staticmethod
    def update_campo_map_conf(
        campo_id: int,
        nome_campo: str = None,
        select: str = None,
        tipo: str = None,
        info_inserir: str = None,
        ordem: int = None,
        gerar_lista_opcoes: bool = None,
        opcoes_modo: str = None,
        opcoes_lista: str = None,
    ) -> "CampoMapConf":
        """Atualiza os campos informados de um mapeamento existente."""
        db = SessionLocal()
        try:
            campo = db.query(CampoMapConf).filter(CampoMapConf.id == campo_id).first()
            if not campo:
                raise ValueError(f"Mapeamento de campo não encontrado: {campo_id}")

            if nome_campo is not None:
                campo.nome_campo = nome_campo
            if select is not None:
                campo.select = select
            if tipo is not None:
                campo.tipo = tipo
            if info_inserir is not None:
                campo.info_inserir = info_inserir
            if ordem is not None:
                campo.ordem = ordem
            if gerar_lista_opcoes is not None:
                campo.gerar_lista_opcoes = gerar_lista_opcoes
            if opcoes_modo is not None:
                campo.opcoes_modo = opcoes_modo
            if opcoes_lista is not None:
                campo.opcoes_lista = opcoes_lista

            db.commit()
            db.refresh(campo)
            logger.info(f"Mapeamento de campo atualizado: {campo_id}")
            return campo
        finally:
            db.close()

    @staticmethod
    def delete_campo_map_conf(campo_id: int) -> None:
        """Remove um mapeamento de campo."""
        db = SessionLocal()
        try:
            campo = db.query(CampoMapConf).filter(CampoMapConf.id == campo_id).first()
            if not campo:
                raise ValueError(f"Mapeamento de campo não encontrado: {campo_id}")
            db.delete(campo)
            db.commit()
            logger.info(f"Mapeamento de campo removido: {campo_id}")
        finally:
            db.close()

    @staticmethod
    def _build_last_summary(result_data: str = None) -> str:
        """
        Monta um resumo amigável para automações com geração de relatório em
        lote (campo 'select' com "lista de opções a ser gerada"): quantos
        arquivos baixaram, quantos ficaram sem dados no período (normal —
        varia aleatoriamente a cada execução) e quantos deram erro de fato.

        Retorna None se `result_data` não tiver a chave 'reports' (ou seja,
        automação sem geração em lote — não há resumo a mostrar).
        """
        if not result_data:
            return None
        try:
            data = json.loads(result_data)
        except (TypeError, ValueError):
            return None

        reports = data.get("reports")
        if not isinstance(reports, list) or not reports:
            return None

        total = len(reports)
        ok = sum(1 for r in reports if r.get("downloaded_file"))
        sem_dados = sum(1 for r in reports if r.get("sem_dados"))
        erro = total - ok - sem_dados

        partes = [f"{ok}/{total} baixado(s)"]
        if sem_dados:
            partes.append(f"{sem_dados} sem dados no período")
        if erro:
            partes.append(f"{erro} com erro")
        return ", ".join(partes)

    @staticmethod
    def log_execution(
        automation_id: int,
        company_id: int,
        status: str,
        processed_count: int = 0,
        error_count: int = 0,
        error_message: str = None,
        duration_seconds: float = None,
        retry_count: int = 0,
        result_data: str = None,
    ) -> ExecutionLog:
        """Registra execução de uma automação."""
        db = SessionLocal()
        try:
            log = ExecutionLog(
                automation_id=automation_id,
                company_id=company_id,
                status=status,
                processed_count=processed_count,
                error_count=error_count,
                error_message=error_message,
                duration_seconds=duration_seconds,
                retry_count=retry_count,
                result_data=result_data,
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            # Atualizar última execução na automação
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if automation:
                automation.last_execution = datetime.utcnow()
                automation.last_status = status
                automation.last_error = error_message
                automation.last_summary = DatabaseService._build_last_summary(result_data)
                db.commit()

            logger.info(f"Execução registrada: automation_id={automation_id}, status={status}")
            return log
        finally:
            db.close()

    @staticmethod
    def create_map_col_rel_rotina(
        id_rotina: int,
        nome_rel: str,
        quant_col: int,
        split_col: str,
        text_cabe: str,
        formato: str = "delimitado",
        layout_fixo: str = None,
    ) -> "MapColRelRotina":
        """Cria um mapeamento de colunas de relatório para uma RotinaMap."""
        db = SessionLocal()
        try:
            mapeamento = MapColRelRotina(
                id_rotina=id_rotina,
                nome_rel=nome_rel,
                quant_col=quant_col,
                split_col=split_col,
                text_cabe=text_cabe,
                formato=formato,
                layout_fixo=layout_fixo,
            )
            db.add(mapeamento)
            db.commit()
            db.refresh(mapeamento)
            logger.info(f"MapColRelRotina criado: {nome_rel} (id_rotina={id_rotina}, formato={formato})")

            try:
                from src.database.dynamic_tables import sync_dynamic_table

                sync_dynamic_table(mapeamento)
            except Exception as e:
                logger.error(f"Falha ao sincronizar tabela dinâmica para MapColRelRotina {mapeamento.id}: {e}")

            return mapeamento
        finally:
            db.close()

    @staticmethod
    def get_map_col_rel_rotina_by_rotina(id_rotina: int):
        """Obtém todos os mapeamentos de colunas de relatório de uma RotinaMap."""
        db = SessionLocal()
        try:
            return (
                db.query(MapColRelRotina)
                .filter(MapColRelRotina.id_rotina == id_rotina)
                .order_by(MapColRelRotina.id)
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def update_map_col_rel_rotina(
        mapeamento_id: int,
        nome_rel: str = None,
        quant_col: int = None,
        split_col: str = None,
        text_cabe: str = None,
        formato: str = None,
        layout_fixo: str = None,
    ) -> "MapColRelRotina":
        """Atualiza os campos informados de um mapeamento de colunas de relatório."""
        db = SessionLocal()
        try:
            mapeamento = db.query(MapColRelRotina).filter(MapColRelRotina.id == mapeamento_id).first()
            if not mapeamento:
                raise ValueError(f"MapColRelRotina não encontrado: {mapeamento_id}")

            if nome_rel is not None:
                mapeamento.nome_rel = nome_rel
            if quant_col is not None:
                mapeamento.quant_col = quant_col
            if split_col is not None:
                mapeamento.split_col = split_col
            if text_cabe is not None:
                mapeamento.text_cabe = text_cabe
            if formato is not None:
                mapeamento.formato = formato
            if layout_fixo is not None:
                mapeamento.layout_fixo = layout_fixo

            db.commit()
            db.refresh(mapeamento)
            logger.info(f"MapColRelRotina atualizado: {mapeamento_id}")

            try:
                from src.database.dynamic_tables import sync_dynamic_table

                sync_dynamic_table(mapeamento)
            except Exception as e:
                logger.error(f"Falha ao sincronizar tabela dinâmica para MapColRelRotina {mapeamento_id}: {e}")

            return mapeamento
        finally:
            db.close()

    @staticmethod
    def delete_map_col_rel_rotina(mapeamento_id: int) -> None:
        """Remove um mapeamento de colunas de relatório."""
        db = SessionLocal()
        try:
            mapeamento = db.query(MapColRelRotina).filter(MapColRelRotina.id == mapeamento_id).first()
            if not mapeamento:
                raise ValueError(f"MapColRelRotina não encontrado: {mapeamento_id}")
            db.delete(mapeamento)
            db.commit()
            logger.info(f"MapColRelRotina removido: {mapeamento_id}")
        finally:
            db.close()

    @staticmethod
    def get_map_col_rel_rotina_version(id_rotina: int, base_nome_tabela: str):
        """Obtém o registro de versão atual da tabela dinâmica de dados, se existir."""
        db = SessionLocal()
        try:
            return (
                db.query(MapColRelRotinaVersion)
                .filter(
                    MapColRelRotinaVersion.id_rotina == id_rotina,
                    MapColRelRotinaVersion.base_nome_tabela == base_nome_tabela,
                )
                .first()
            )
        finally:
            db.close()

    @staticmethod
    def upsert_map_col_rel_rotina_version(
        id_rotina: int,
        base_nome_tabela: str,
        versao: int,
        nome_tabela_atual: str,
        colunas: str,
        id_mapeamento: int = None,
    ) -> "MapColRelRotinaVersion":
        """Cria ou atualiza o registro de versão atual da tabela dinâmica de dados."""
        db = SessionLocal()
        try:
            registro = (
                db.query(MapColRelRotinaVersion)
                .filter(
                    MapColRelRotinaVersion.id_rotina == id_rotina,
                    MapColRelRotinaVersion.base_nome_tabela == base_nome_tabela,
                )
                .first()
            )
            if registro is None:
                registro = MapColRelRotinaVersion(
                    id_rotina=id_rotina,
                    id_mapeamento=id_mapeamento,
                    base_nome_tabela=base_nome_tabela,
                    versao=versao,
                    nome_tabela_atual=nome_tabela_atual,
                    colunas=colunas,
                )
                db.add(registro)
            else:
                registro.id_mapeamento = id_mapeamento
                registro.versao = versao
                registro.nome_tabela_atual = nome_tabela_atual
                registro.colunas = colunas

            db.commit()
            db.refresh(registro)
            logger.info(
                f"MapColRelRotinaVersion registrado: base='{base_nome_tabela}', "
                f"versao={versao}, tabela='{nome_tabela_atual}'"
            )
            return registro
        finally:
            db.close()

    @staticmethod
    def create_arquivo_baixado(
        id_rotina: Optional[int],
        id_empresa: Optional[int],
        nome_arquivo: Optional[str],
        data,
        status: str,
    ) -> "ArquivoBaixado":
        """Registra um arquivo baixado (ou tentativa de download) por uma automação."""
        db = SessionLocal()
        try:
            registro = ArquivoBaixado(
                id_rotina=id_rotina,
                id_empresa=id_empresa,
                nome_arquivo=nome_arquivo,
                data=data,
                status=status,
            )
            db.add(registro)
            db.commit()
            db.refresh(registro)
            logger.info(
                f"ArquivoBaixado registrado: id_rotina={id_rotina}, id_empresa={id_empresa}, "
                f"nome_arquivo='{nome_arquivo}', status='{status}'"
            )
            return registro
        finally:
            db.close()

    @staticmethod
    def get_arquivos_baixados(id_rotina: int = None, id_empresa: int = None, status: str = None):
        """Lista arquivos baixados, opcionalmente filtrando por rotina, empresa e/ou status."""
        db = SessionLocal()
        try:
            query = db.query(ArquivoBaixado)
            if id_rotina is not None:
                query = query.filter(ArquivoBaixado.id_rotina == id_rotina)
            if id_empresa is not None:
                query = query.filter(ArquivoBaixado.id_empresa == id_empresa)
            if status is not None:
                query = query.filter(ArquivoBaixado.status == status)
            return query.order_by(ArquivoBaixado.id.desc()).all()
        finally:
            db.close()

    @staticmethod
    def update_arquivo_baixado_status(arquivo_id: int, status: str) -> None:
        """Atualiza o status de um registro de `arquivos_baixados` (ex: após processar seu conteúdo)."""
        db = SessionLocal()
        try:
            registro = db.query(ArquivoBaixado).filter(ArquivoBaixado.id == arquivo_id).first()
            if not registro:
                raise ValueError(f"ArquivoBaixado não encontrado: {arquivo_id}")
            registro.status = status
            db.commit()
            logger.info(f"ArquivoBaixado {arquivo_id}: status atualizado para '{status}'")
        finally:
            db.close()

    @staticmethod
    def create_envio_bpo(
        id_empresa: int,
        id_rotina: Optional[int],
        competencia: str,
        caminho_arquivo: str,
        nome_arquivo: str,
    ) -> "EnvioBpo":
        """Registra um arquivo na fila de envio para a API BPO ACENE (status 'pendente')."""
        db = SessionLocal()
        try:
            registro = EnvioBpo(
                id_empresa=id_empresa,
                id_rotina=id_rotina,
                competencia=competencia,
                caminho_arquivo=caminho_arquivo,
                nome_arquivo=nome_arquivo,
                status="pendente",
                tentativas=0,
            )
            db.add(registro)
            db.commit()
            db.refresh(registro)
            logger.info(
                f"EnvioBpo {registro.id} enfileirado: id_empresa={id_empresa}, id_rotina={id_rotina}, "
                f"competencia={competencia}, arquivo='{nome_arquivo}'"
            )
            return registro
        finally:
            db.close()

    @staticmethod
    def get_envios_bpo_prontos(agora: datetime) -> list:
        """Envios pendentes cuja próxima tentativa já chegou (ou nunca tentados), do mais antigo ao mais novo."""
        db = SessionLocal()
        try:
            return (
                db.query(EnvioBpo)
                .filter(EnvioBpo.status == "pendente")
                .filter((EnvioBpo.proxima_tentativa == None) | (EnvioBpo.proxima_tentativa <= agora))  # noqa: E711
                .order_by(EnvioBpo.id)
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def get_envios_bpo(status: str = None, limit: int = 100) -> list:
        """Lista os envios mais recentes para a API BPO ACENE (opcionalmente por status)."""
        db = SessionLocal()
        try:
            query = db.query(EnvioBpo)
            if status is not None:
                query = query.filter(EnvioBpo.status == status)
            return query.order_by(EnvioBpo.id.desc()).limit(limit).all()
        finally:
            db.close()

    @staticmethod
    def update_envio_bpo(envio_id: int, **campos) -> None:
        """Atualiza campos de um envio (status, tentativas, lote, mensagem...)."""
        db = SessionLocal()
        try:
            registro = db.query(EnvioBpo).filter(EnvioBpo.id == envio_id).first()
            if not registro:
                raise ValueError(f"EnvioBpo não encontrado: {envio_id}")
            for campo, valor in campos.items():
                setattr(registro, campo, valor)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def delete_arquivo_baixado(arquivo_id: int) -> None:
        """Remove um registro de `arquivos_baixados` (ex: após a importação ser concluída)."""
        db = SessionLocal()
        try:
            registro = db.query(ArquivoBaixado).filter(ArquivoBaixado.id == arquivo_id).first()
            if not registro:
                raise ValueError(f"ArquivoBaixado não encontrado: {arquivo_id}")
            db.delete(registro)
            db.commit()
            logger.info(f"ArquivoBaixado {arquivo_id}: registro removido")
        finally:
            db.close()

    @staticmethod
    def get_map_col_rel_rotina(mapeamento_id: int) -> "MapColRelRotina":
        """Obtém um mapeamento de colunas de relatório pelo ID."""
        db = SessionLocal()
        try:
            return db.query(MapColRelRotina).filter(MapColRelRotina.id == mapeamento_id).first()
        finally:
            db.close()


__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "Company",
    "Automation",
    "ExecutionLog",
    "RotinaMap",
    "CampoMapConf",
    "MapColRelRotina",
    "MapColRelRotinaVersion",
    "ArquivoBaixado",
    "init_db",
    "get_db",
    "DatabaseService",
]
