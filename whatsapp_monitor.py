import time
import threading
import subprocess
import os
import re
import logging
import requests
from flask import Flask, request, jsonify

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Variáveis Globais
CALLBACK_PROCESSAR = None
NODE_PROCESS       = None
FLASK_APP          = Flask(__name__)
PORT               = 5000


# =============================================================================
# FLASK SERVER — Recebe webhooks do whatsapp_monitor.js (Node.js)
# =============================================================================

@FLASK_APP.route('/whatsapp_webhook', methods=['POST'])
def whatsapp_webhook():
    """Recebe mensagens do WPPConnect (Node.js) e repassa ao bot.py."""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        file_path = data.get('filePath') or ''

        logger.info(
            f"[WPP] Recebido: sender={data.get('sender')} "
            f"type={data.get('type')} filePath={file_path}"
        )

        # Valida se o arquivo realmente existe antes de encaminhar
        if file_path and not os.path.exists(file_path):
            logger.warning(f"[WPP] Arquivo não encontrado em disco: {file_path}")
            return jsonify({"status": "error", "message": "Arquivo não encontrado"}), 400

        if CALLBACK_PROCESSAR:
            # Limpa o número: remove @c.us e qualquer não-dígito
            telefone_raw = data.get('from', '')
            telefone = re.sub(r'\D', '', telefone_raw.replace('@c.us', ''))
            # Mantém no máximo os 13 dígitos finais (DDI+DDD+número)
            if len(telefone) > 13:
                telefone = telefone[-13:]

            candidato = {
                "nome":      data.get('sender', 'Desconhecido'),
                "telefone":  telefone,
                "texto":     data.get('body', ''),
                "arquivo":   file_path if file_path else None,
                "tipo":      data.get('type', 'chat'),
                "timestamp": data.get('timestamp'),
            }

            # Processa em thread separada para não bloquear o Flask
            threading.Thread(
                target=_processar_e_limpar,
                args=(candidato,),
                daemon=True,
            ).start()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _processar_e_limpar(candidato: dict):
    """
    Chama o callback do bot.py e, após conclusão, apaga o arquivo temporário
    da pasta downloads — evitando que a pasta cresça indefinidamente.
    """
    arquivo = candidato.get("arquivo")
    try:
        if CALLBACK_PROCESSAR:
            CALLBACK_PROCESSAR(candidato)
    except Exception as e:
        logger.error(f"[WPP] Erro no callback de processamento: {e}")
    finally:
        # Remove o arquivo temporário independentemente do resultado
        if arquivo and os.path.exists(arquivo):
            try:
                # Só apaga se ainda estiver dentro da pasta downloads
                downloads_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), '..', 'downloads'
                )
                downloads_dir = os.path.realpath(downloads_dir)
                arquivo_real  = os.path.realpath(arquivo)
                if arquivo_real.startswith(downloads_dir):
                    os.unlink(arquivo_real)
                    logger.info(f"[WPP] Arquivo temporário removido: {arquivo_real}")
            except Exception as e:
                logger.warning(f"[WPP] Não foi possível remover arquivo temporário: {e}")


def run_flask():
    """Roda o servidor Flask sem logs de acesso para não poluir o terminal."""
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    FLASK_APP.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


# =============================================================================
# CONTROLE DO PROCESSO NODE.JS
# =============================================================================

def iniciar_node_service():
    """Inicia o script Node.js do WPPConnect."""
    global NODE_PROCESS

    node_script = os.path.join(os.getcwd(), 'wpp_service', 'index.js')
    if not os.path.exists(node_script):
        logger.error(f"Script Node não encontrado em: {node_script}")
        return

    logger.info("Iniciando serviço WPPConnect (Node.js)...")
    try:
        env = os.environ.copy()
        env.setdefault('WPP_MARK_SEEN', 'true')
        NODE_PROCESS = subprocess.Popen(
            ['node', node_script],
            cwd=os.path.join(os.getcwd(), 'wpp_service'),
            shell=(os.name == 'nt'),   # shell=True apenas no Windows
            env=env,
        )
    except Exception as e:
        logger.error(f"Falha ao iniciar Node.js: {e}")


# =============================================================================
# INTERFACE PARA O BOT.PY
# =============================================================================

def iniciar_whatsapp(callback_processar_candidato):
    """
    Chamada pelo bot.py para iniciar a integração WhatsApp.
    Sobe o Flask (webhook) e o processo Node.js, e fica monitorando.
    """
    global CALLBACK_PROCESSAR
    CALLBACK_PROCESSAR = callback_processar_candidato

    # 1. Flask em thread daemon
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"[WPP] Servidor de integração Flask iniciado na porta {PORT}")

    # 2. Processo Node.js
    iniciar_node_service()

    # 3. Loop de monitoramento — reinicia o Node se morrer
    while True:
        time.sleep(10)
        if NODE_PROCESS and NODE_PROCESS.poll() is not None:
            logger.warning("[WPP] Processo Node.js encerrou inesperadamente. Reiniciando...")
            iniciar_node_service()


def verificar_whatsapp():
    """
    Chamada periodicamente pelo bot.py para forçar verificação de não lidas.
    Chama o endpoint GET /check-unread do Node.js.
    """
    try:
        requests.get("http://localhost:3000/check-unread", timeout=2)
    except Exception:
        pass  # Node ainda não subiu ou indisponível — ignora silenciosamente


# =============================================================================
# Classe dummy — mantida para compatibilidade com imports antigos
# =============================================================================

class WhatsAppBot:
    def __init__(self):
        pass
    def iniciar(self):
        pass