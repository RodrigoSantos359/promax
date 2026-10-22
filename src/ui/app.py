"""
Aplicação Flask para interface de configuração de automações.

Para executar:
    python -c "from src.ui.app import app; app.run(debug=True)"

Acessar em: http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import logging
from datetime import datetime, timezone

from config.database import DatabaseService, SessionLocal, Company, Automation, RotinaMap, CampoMapConf, ExecutionLog, MapColRelRotina
from src.automation import AVAILABLE_ROUTINES
from src.automation.executor import TaskExecutor
from src.automation.scheduler import get_scheduler
from config.settings import FLASK_PORT, FLASK_DEBUG

logger = logging.getLogger(__name__)


def to_utc_iso(dt: datetime) -> str:
    """
    Serializa um datetime "ingênuo" (naive, sem tzinfo) para ISO 8601
    marcado explicitamente como UTC (ex: "2026-09-17T14:26:57+00:00").

    Todos os timestamps do banco são gravados via `datetime.utcnow()`, que
    produz valores em UTC mas SEM indicar isso na string. Sem essa marcação,
    o JavaScript do navegador (`new Date(...)`) interpreta a string como
    horário LOCAL em vez de UTC, exibindo a hora errada (deslocada pelo
    fuso horário, ex: +3h em relação ao horário de Brasília).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

# Criar app Flask
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_SORT_KEYS"] = False

# Inicializar executor
executor = TaskExecutor(logger=logger)


# ============================================================================
# ROTAS - Dashboard
# ============================================================================

@app.route("/")
def dashboard():
    """Dashboard principal com lista de automações."""
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        total_automations = db.query(Automation).count()

        today_start = datetime.utcnow().date()
        today_executions = db.query(ExecutionLog).filter(ExecutionLog.executed_at >= today_start).count()
        today_success = db.query(ExecutionLog).filter(
            ExecutionLog.executed_at >= today_start, ExecutionLog.status == "success"
        ).count()
        success_rate = round((today_success / today_executions) * 100) if today_executions else 0

        return render_template(
            "dashboard.html",
            companies=companies,
            total_automations=total_automations,
            today_executions=today_executions,
            success_rate=success_rate,
        )
    finally:
        db.close()


@app.route("/company/<int:company_id>")
def company_detail(company_id):
    """Detalhes de uma empresa."""
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return redirect(url_for("dashboard"))

        automations = db.query(Automation).filter(
            Automation.company_id == company_id
        ).all()

        return render_template(
            "company_detail.html",
            company=company,
            automations=automations
        )
    finally:
        db.close()


# ============================================================================
# ROTAS - API
# ============================================================================

@app.route("/api/companies", methods=["GET"])
def api_get_companies():
    """Obtém todas as empresas."""
    try:
        companies = DatabaseService.get_all_companies(active_only=False)
        return jsonify([{
            "id": c.id,
            "name": c.name,
            "unit": c.unit,
            "is_active": c.is_active,
            "created_at": to_utc_iso(c.created_at),
            "has_wkradar": bool(c.base_empresa_wkradar and c.usuario_wkradar and c.senha_wkradar),
            "has_bpo_acene": bool(c.bpo_acene_token),
        } for c in companies])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/companies/<int:company_id>", methods=["GET"])
def api_get_company(company_id):
    """Obtém os detalhes de uma empresa (sem a senha)."""
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return jsonify({"error": "Empresa não encontrada"}), 404

        return jsonify({
            "id": company.id,
            "name": company.name,
            "promax_url": company.promax_url,
            "username": company.username,
            "unit": company.unit,
            "is_active": company.is_active,
            "created_at": to_utc_iso(company.created_at),
            "updated_at": to_utc_iso(company.updated_at),
            # senha_wkradar e token_wkradar nunca são expostos pela API.
            "base_empresa_wkradar": company.base_empresa_wkradar,
            "usuario_wkradar": company.usuario_wkradar,
            "has_wkradar": bool(company.base_empresa_wkradar and company.usuario_wkradar and company.senha_wkradar),
            # bpo_acene_token nunca é exposto — só se está configurado.
            "has_bpo_acene": bool(company.bpo_acene_token),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/companies", methods=["POST"])
def api_create_company():
    """Cria uma nova empresa."""
    try:
        data = request.get_json()

        company = DatabaseService.create_company(
            name=data["name"],
            promax_url=data["promax_url"],
            username=data["username"],
            password=data["password"],
            unit=data["unit"],
            base_empresa_wkradar=data.get("base_empresa_wkradar"),
            usuario_wkradar=data.get("usuario_wkradar"),
            senha_wkradar=data.get("senha_wkradar"),
            bpo_acene_token=data.get("bpo_acene_token") or None,
        )

        return jsonify({
            "id": company.id,
            "name": company.name,
            "message": "Empresa criada com sucesso"
        }), 201

    except Exception as e:
        logger.error(f"Erro ao criar empresa: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/companies/<int:company_id>", methods=["PUT"])
def api_update_company(company_id):
    """Atualiza uma empresa existente. Senha só é alterada se informada."""
    try:
        data = request.get_json() or {}

        company = DatabaseService.update_company(
            company_id=company_id,
            name=data.get("name"),
            promax_url=data.get("promax_url"),
            username=data.get("username"),
            password=data.get("password") or None,
            unit=data.get("unit"),
            is_active=data.get("is_active"),
            base_empresa_wkradar=data.get("base_empresa_wkradar"),
            usuario_wkradar=data.get("usuario_wkradar"),
            senha_wkradar=data.get("senha_wkradar") or None,
            bpo_acene_token=data.get("bpo_acene_token") or None,
        )

        return jsonify({
            "id": company.id,
            "name": company.name,
            "message": "Empresa atualizada com sucesso"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Erro ao atualizar empresa: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/companies/<int:company_id>/wkradar-token", methods=["POST"])
def api_test_wkradar_token(company_id):
    """
    Testa as credenciais WKRADAR de uma empresa buscando um token novo na
    API. Não persiste nada de relevante (o token é só cacheado
    best-effort em `Company.token_wkradar`, já que expira em ~10 minutos) —
    serve para o usuário confirmar, no cadastro, que as credenciais estão
    corretas.
    """
    from src.integrations.wkradar_client import get_wkradar_token

    try:
        resultado = get_wkradar_token(company_id)
        status_code = 200 if resultado.get("status") == "success" else 400
        return jsonify(resultado), status_code
    except Exception as e:
        logger.error(f"Erro ao testar token WKRADAR (company_id={company_id}): {str(e)}")
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/api/routines", methods=["GET"])
def api_get_routines():
    """Lista as rotinas de automação disponíveis (registradas em src/automation)."""
    try:
        routines = [
            {
                "id": routine_id,
                "name": getattr(RoutineClass, "ROUTINE_NAME", routine_id),
            }
            for routine_id, RoutineClass in AVAILABLE_ROUTINES.items()
        ]
        return jsonify(routines)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automations", methods=["GET"])
def api_get_automations():
    """Obtém todas as automações. Filtra por company_id se informado na query string."""
    try:
        db = SessionLocal()
        query = db.query(Automation)

        company_id = request.args.get("company_id", type=int)
        if company_id is not None:
            query = query.filter(Automation.company_id == company_id)

        automations = query.all()
        db.close()

        def parse_schedule_config(raw):
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None

        return jsonify([{
            "id": a.id,
            "company_id": a.company_id,
            "routine_id": a.routine_id,
            "routine_name": a.routine_name,
            "is_active": a.is_active,
            "execution_time": a.execution_time,
            "interval": a.interval,
            "schedule_config": parse_schedule_config(a.schedule_config),
            "max_retries": a.max_retries,
            "retry_delay": a.retry_delay,
            "last_execution": to_utc_iso(a.last_execution),
            "last_status": a.last_status,
            "last_error": a.last_error,
            "last_summary": a.last_summary,
        } for a in automations])

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals():
            db.close()


@app.route("/api/automations", methods=["POST"])
def api_create_automation():
    """Cria uma nova automação vinculada a uma empresa/unidade."""
    try:
        data = request.get_json()

        routine_id = data["routine_id"]
        routine_name = data.get("routine_name") or AVAILABLE_ROUTINES.get(routine_id) and getattr(
            AVAILABLE_ROUTINES[routine_id], "ROUTINE_NAME", routine_id
        ) or routine_id

        start_date_raw = data.get("start_date") or datetime.utcnow().isoformat()

        schedule_config = data.get("schedule_config")
        schedule_config_json = json.dumps(schedule_config) if schedule_config else None

        automation = DatabaseService.create_automation(
            company_id=data["company_id"],
            routine_id=routine_id,
            routine_name=routine_name,
            start_date=datetime.fromisoformat(start_date_raw),
            execution_time=data["execution_time"],
            interval=data["interval"],
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 60),
            is_active=data.get("is_active", True),
            schedule_config=schedule_config_json,
        )

        try:
            get_scheduler().schedule_automation(automation.id)
        except Exception as e:
            logger.warning(f"Automação {automation.id} criada, mas falhou ao agendar: {str(e)}")

        return jsonify({
            "id": automation.id,
            "message": "Automação criada com sucesso"
        }), 201

    except Exception as e:
        logger.error(f"Erro ao criar automação: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/automations/<int:automation_id>", methods=["PUT"])
def api_update_automation(automation_id):
    """Atualiza uma automação existente (nome, rotina, horário, frequência, etc)."""
    try:
        data = request.get_json() or {}

        schedule_config = data.get("schedule_config")
        schedule_config_json = json.dumps(schedule_config) if schedule_config else None

        automation = DatabaseService.update_automation(
            automation_id=automation_id,
            routine_id=data.get("routine_id"),
            routine_name=data.get("routine_name"),
            execution_time=data.get("execution_time"),
            interval=data.get("interval"),
            max_retries=data.get("max_retries"),
            retry_delay=data.get("retry_delay"),
            is_active=data.get("is_active"),
            schedule_config=schedule_config_json,
            clear_schedule_config=("schedule_config" in data and not schedule_config),
        )

        try:
            get_scheduler().schedule_automation(automation.id)
        except Exception as e:
            logger.warning(f"Automação {automation.id} atualizada, mas falhou ao reagendar: {str(e)}")

        return jsonify({
            "id": automation.id,
            "message": "Automação atualizada com sucesso"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Erro ao atualizar automação: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/automations/<int:automation_id>/toggle", methods=["POST"])
def api_toggle_automation(automation_id):
    """Ativa ou desativa uma automação."""
    try:
        data = request.get_json() or {}

        if "is_active" in data:
            new_status = bool(data["is_active"])
        else:
            db = SessionLocal()
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            db.close()
            if not automation:
                return jsonify({"error": "Automação não encontrada"}), 404
            new_status = not automation.is_active

        automation = DatabaseService.set_automation_active(automation_id, new_status)

        try:
            get_scheduler().schedule_automation(automation.id)
        except Exception as e:
            logger.warning(f"Status da automação {automation.id} atualizado, mas falhou ao (re)agendar: {str(e)}")

        return jsonify({
            "id": automation.id,
            "is_active": automation.is_active,
            "message": "Status atualizado com sucesso"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Erro ao atualizar status da automação: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/automations/<int:automation_id>/execute", methods=["POST"])
def api_execute_automation(automation_id):
    """Executa uma automação imediatamente."""
    try:
        data = request.get_json() or {}
        headless = data.get("headless", True)

        # Obter company_id
        db = SessionLocal()
        automation = db.query(Automation).filter(Automation.id == automation_id).first()
        db.close()

        if not automation:
            return jsonify({"error": "Automação não encontrada"}), 404

        if not automation.is_active:
            return jsonify({"error": "Automação está desativada — ative-a antes de executar"}), 400

        # Executar
        result = executor.execute_automation(
            automation_id=automation_id,
            company_id=automation.company_id,
            headless=headless,
        )

        return jsonify(result), 200 if result["status"] == "success" else 400

    except Exception as e:
        logger.error(f"Erro ao executar automação: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/automations/<int:automation_id>/execute-with-retry", methods=["POST"])
def api_execute_with_retry(automation_id):
    """Executa uma automação com retry automático."""
    try:
        data = request.get_json() or {}
        headless = data.get("headless", True)

        # Obter company_id
        db = SessionLocal()
        automation = db.query(Automation).filter(Automation.id == automation_id).first()
        db.close()

        if not automation:
            return jsonify({"error": "Automação não encontrada"}), 404

        if not automation.is_active:
            return jsonify({"error": "Automação está desativada — ative-a antes de executar"}), 400

        # Executar com retry
        result = executor.execute_with_retry(
            automation_id=automation_id,
            company_id=automation.company_id,
            headless=headless,
        )

        return jsonify(result), 200 if result["status"] == "success" else 400

    except Exception as e:
        logger.error(f"Erro ao executar automação: {str(e)}")
        return jsonify({"error": str(e)}), 500


def _serialize_campo(campo: CampoMapConf) -> dict:
    return {
        "id": campo.id,
        "rotina_map_id": campo.rotina_map_id,
        "nome_campo": campo.nome_campo,
        "select": campo.select,
        "tipo": campo.tipo,
        "info_inserir": campo.info_inserir,
        "ordem": campo.ordem,
        "gerar_lista_opcoes": campo.gerar_lista_opcoes,
        "opcoes_modo": campo.opcoes_modo,
        "opcoes_lista": json.loads(campo.opcoes_lista) if campo.opcoes_lista else [],
    }


def _serialize_rotina_map(rotina_map: RotinaMap, include_campos: bool = False, num_automations: int = None) -> dict:
    data = {
        "id": rotina_map.id,
        "routine_id": rotina_map.routine_id,
        "nome": rotina_map.nome,
        "exclusivo": rotina_map.exclusivo,
        "csv_button_name": rotina_map.csv_button_name,
        "report_ready_timeout": rotina_map.report_ready_timeout,
    }
    if num_automations is not None:
        data["num_automations"] = num_automations
    if include_campos:
        data["campos"] = [_serialize_campo(c) for c in rotina_map.campos_map]
    return data


# ============================================================================
# ROTAS - API: Rotinas Map (editor global de rotinas/campos)
# ============================================================================

@app.route("/api/rotinas-map", methods=["GET"])
def api_get_rotinas_map():
    """Lista todas as RotinaMap cadastradas, com contagem de automações e campos."""
    db = SessionLocal()
    try:
        rotinas = db.query(RotinaMap).order_by(RotinaMap.routine_id).all()
        result = []
        for r in rotinas:
            num_automations = db.query(Automation).filter(Automation.rotina_map_id == r.id).count()
            data = _serialize_rotina_map(r, num_automations=num_automations)
            data["num_campos"] = len(r.campos_map)
            result.append(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/rotinas-map/<int:rotina_map_id>", methods=["GET"])
def api_get_rotina_map(rotina_map_id):
    """Obtém uma RotinaMap com seus campos mapeados."""
    db = SessionLocal()
    try:
        rotina_map = db.query(RotinaMap).filter(RotinaMap.id == rotina_map_id).first()
        if not rotina_map:
            return jsonify({"error": "RotinaMap não encontrada"}), 404
        return jsonify(_serialize_rotina_map(rotina_map, include_campos=True))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/rotinas-map/<int:rotina_map_id>", methods=["PUT"])
def api_update_rotina_map(rotina_map_id):
    """Atualiza o nome de uma RotinaMap."""
    try:
        data = request.get_json() or {}
        rotina_map = DatabaseService.update_rotina_map(
            rotina_map_id,
            nome=data.get("nome"),
            csv_button_name=data.get("csv_button_name"),
            report_ready_timeout=data.get("report_ready_timeout"),
        )
        return jsonify(_serialize_rotina_map(rotina_map))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/rotinas-map/<int:rotina_map_id>", methods=["DELETE"])
def api_delete_rotina_map(rotina_map_id):
    """Remove uma RotinaMap e seus campos (cascade)."""
    try:
        DatabaseService.delete_rotina_map(rotina_map_id)
        return jsonify({"message": "RotinaMap removida com sucesso"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/rotinas-map/<int:rotina_map_id>/campos", methods=["POST"])
def api_create_campo_direto(rotina_map_id):
    """Cria um campo diretamente numa RotinaMap (modo global, sem contexto de automação)."""
    try:
        data = request.get_json() or {}
        campo = DatabaseService.create_campo_map_conf(
            rotina_map_id=rotina_map_id,
            nome_campo=data["nome_campo"],
            select=data["select"],
            tipo=data["tipo"],
            info_inserir=data.get("info_inserir"),
            ordem=data.get("ordem"),
            gerar_lista_opcoes=data.get("gerar_lista_opcoes", False),
            opcoes_modo=data.get("opcoes_modo"),
            opcoes_lista=json.dumps(data["opcoes_lista"]) if data.get("opcoes_lista") else None,
        )
        return jsonify(_serialize_campo(campo)), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/campos-map-conf/<int:campo_id>", methods=["PUT"])
def api_update_campo(campo_id):
    """Atualiza um campo mapeado (nome, seletor, tipo, valor)."""
    try:
        data = request.get_json() or {}
        campo = DatabaseService.update_campo_map_conf(
            campo_id=campo_id,
            nome_campo=data.get("nome_campo"),
            select=data.get("select"),
            tipo=data.get("tipo"),
            info_inserir=data.get("info_inserir"),
            ordem=data.get("ordem"),
            gerar_lista_opcoes=data.get("gerar_lista_opcoes"),
            opcoes_modo=data.get("opcoes_modo"),
            opcoes_lista=json.dumps(data["opcoes_lista"]) if data.get("opcoes_lista") is not None else None,
        )
        return jsonify(_serialize_campo(campo))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/campos-map-conf/<int:campo_id>", methods=["DELETE"])
def api_delete_campo(campo_id):
    """Remove um campo mapeado."""
    try:
        DatabaseService.delete_campo_map_conf(campo_id)
        return jsonify({"message": "Campo removido com sucesso"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _serialize_map_col(mapeamento: MapColRelRotina) -> dict:
    return {
        "id": mapeamento.id,
        "id_rotina": mapeamento.id_rotina,
        "nome_rel": mapeamento.nome_rel,
        "quant_col": mapeamento.quant_col,
        "split_col": mapeamento.split_col,
        "text_cabe": mapeamento.text_cabe,
        # 'delimitado' (padrão) ou 'fixo' (layout de largura fixa, ex: .inf —
        # sem cadastro via esta tela; ver src/database/file_processor.py).
        "formato": mapeamento.formato,
        "layout_fixo": json.loads(mapeamento.layout_fixo) if mapeamento.layout_fixo else None,
    }


@app.route("/api/map-col-rel-rotina", methods=["GET"])
def api_get_map_col_rel_rotina():
    """Lista os mapeamentos de colunas de relatório de uma RotinaMap (?id_rotina=)."""
    try:
        id_rotina = request.args.get("id_rotina", type=int)
        if not id_rotina:
            return jsonify({"error": "Parâmetro 'id_rotina' é obrigatório"}), 400
        mapeamentos = DatabaseService.get_map_col_rel_rotina_by_rotina(id_rotina)
        return jsonify([_serialize_map_col(m) for m in mapeamentos])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/map-col-rel-rotina", methods=["POST"])
def api_create_map_col_rel_rotina():
    """Cria um mapeamento de colunas de relatório para uma RotinaMap."""
    try:
        data = request.get_json() or {}
        mapeamento = DatabaseService.create_map_col_rel_rotina(
            id_rotina=data["id_rotina"],
            nome_rel=data["nome_rel"],
            quant_col=data["quant_col"],
            split_col=data["split_col"],
            text_cabe=data["text_cabe"],
        )
        return jsonify(_serialize_map_col(mapeamento)), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/map-col-rel-rotina/<int:mapeamento_id>", methods=["PUT"])
def api_update_map_col_rel_rotina(mapeamento_id):
    """Atualiza um mapeamento de colunas de relatório."""
    try:
        data = request.get_json() or {}
        mapeamento = DatabaseService.update_map_col_rel_rotina(
            mapeamento_id=mapeamento_id,
            nome_rel=data.get("nome_rel"),
            quant_col=data.get("quant_col"),
            split_col=data.get("split_col"),
            text_cabe=data.get("text_cabe"),
        )
        return jsonify(_serialize_map_col(mapeamento))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/map-col-rel-rotina/<int:mapeamento_id>", methods=["DELETE"])
def api_delete_map_col_rel_rotina(mapeamento_id):
    """Remove um mapeamento de colunas de relatório."""
    try:
        DatabaseService.delete_map_col_rel_rotina(mapeamento_id)
        return jsonify({"message": "Mapeamento removido com sucesso"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/automations/<int:automation_id>/rotina-map", methods=["GET"])
def api_get_automation_rotina_map(automation_id):
    """Obtém a RotinaMap (com campos) atualmente usada por uma automação."""
    db = SessionLocal()
    try:
        automation = db.query(Automation).filter(Automation.id == automation_id).first()
        if not automation:
            return jsonify({"error": "Automação não encontrada"}), 404

        if not automation.rotina_map_id:
            return jsonify({"rotina_map": None, "campos": []})

        rotina_map = db.query(RotinaMap).filter(RotinaMap.id == automation.rotina_map_id).first()
        if not rotina_map:
            return jsonify({"rotina_map": None, "campos": []})

        num_automations = db.query(Automation).filter(Automation.rotina_map_id == rotina_map.id).count()

        return jsonify({
            "rotina_map": _serialize_rotina_map(rotina_map, num_automations=num_automations),
            "campos": [_serialize_campo(c) for c in rotina_map.campos_map],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/automations/<int:automation_id>/campos-map-conf", methods=["POST"])
def api_save_campo_for_automation(automation_id):
    """
    Cria ou atualiza um campo mapeado para a automação.

    Se `tornar_exclusivo=True` e a RotinaMap atual ainda for compartilhada,
    bifurca (fork) antes de salvar, protegendo outras automações que usam
    a mesma RotinaMap.
    """
    try:
        data = request.get_json() or {}

        campo = DatabaseService.save_campo_map_conf_for_automation(
            automation_id=automation_id,
            nome_campo=data["nome_campo"],
            select=data["select"],
            tipo=data["tipo"],
            info_inserir=data.get("info_inserir"),
            campo_id=data.get("campo_id"),
            tornar_exclusivo=data.get("tornar_exclusivo", False),
            ordem=data.get("ordem"),
            gerar_lista_opcoes=data.get("gerar_lista_opcoes", False),
            opcoes_modo=data.get("opcoes_modo"),
            opcoes_lista=json.dumps(data["opcoes_lista"]) if data.get("opcoes_lista") else None,
        )

        return jsonify(_serialize_campo(campo)), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Erro ao salvar campo para automação {automation_id}: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/logs/<int:automation_id>", methods=["GET"])
def api_get_logs(automation_id):
    """Obtém logs de execução de uma automação."""
    try:
        db = SessionLocal()
        logs = db.query(ExecutionLog).filter(
            ExecutionLog.automation_id == automation_id
        ).order_by(ExecutionLog.executed_at.desc()).limit(10).all()
        db.close()

        def parse_result_data(raw):
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None

        return jsonify([{
            "id": log.id,
            "executed_at": to_utc_iso(log.executed_at),
            "status": log.status,
            "processed_count": log.processed_count,
            "error_count": log.error_count,
            "duration_seconds": log.duration_seconds,
            "error_message": log.error_message,
            "result_data": parse_result_data(log.result_data),
        } for log in logs])

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handler para página não encontrada."""
    return jsonify({"error": "Página não encontrada"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handler para erro interno."""
    logger.error(f"Erro interno: {str(error)}")
    return jsonify({"error": "Erro interno do servidor"}), 500


# ============================================================================
# Context Processors
# ============================================================================

@app.context_processor
def inject_globals():
    """Injeta variáveis globais nos templates."""
    return {
        "app_name": "- PromaX Automation Suite",
        "version": "1.0.0",
        "year": datetime.utcnow().year,
    }


# ============================================================================
# CLI Commands
# ============================================================================

@app.cli.command()
def init_db():
    """Inicializa o banco de dados."""
    from config.database import init_db
    init_db()
    print("✓ Banco de dados inicializado")


@app.cli.command()
def create_sample_data():
    """Cria dados de exemplo."""
    from config.database import Company
    from config.settings import PROMAX_URL, PROMAX_DEFAULT_USER, PROMAX_DEFAULT_PASSWORD

    try:
        company = DatabaseService.create_company(
            name="Dibrasa - Demo",
            promax_url=PROMAX_URL,
            username=PROMAX_DEFAULT_USER,
            password=PROMAX_DEFAULT_PASSWORD,
            unit="161.0001 - Dibrasa",
        )
        print(f"✓ Empresa de demo criada: {company.name}")
    except Exception as e:
        print(f"✗ Erro: {str(e)}")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    logger.info("Iniciando PromaX Automation Flask App")
    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
    )
