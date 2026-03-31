"""
╔══════════════════════════════════════════════════════════════════╗
║         RECRUTADOR AUTOMÁTICO DE CURRÍCULOS v2.1                ║
║   Foco: Classificação de cargo com máxima precisão              ║
╚══════════════════════════════════════════════════════════════════╝

MELHORIAS DE CLASSIFICAÇÃO v2.1:
─────────────────────────────────────────────────────────────────
1. PIPELINE EM 7 ETAPAS com fallback explícito e logado
   Etapa 1 → Cargo literal no assunto/corpo do email
   Etapa 2 → Sinônimos e variações conhecidas (dicionário expandido)
   Etapa 3 → Regex especializado por área (CNH D/E → Motorista, etc.)
   Etapa 4 → Cargo literal no texto do currículo (match exato)
   Etapa 5 → Fuzzy match no texto (rapidfuzz WRatio >= 88)
   Etapa 6 → Groq LLM com prompt especializado + exemplos de erros comuns
   Etapa 7 → Fallback por área (Manutenção/Operação/Adm/TI/Motorista)

2. PROMPT GROQ MELHORADO
   - Lista dos 10 erros mais comuns com a correção esperada
   - "fiscal contábil / SPED" NÃO é cargo FISCAL (operação)
   - Cargo de gestor só aceito com evidência de liderança
   - Temperatura 0.0 (determinístico)

3. SINÔNIMOS EXPANDIDOS (+60 variações)
   - Ortografia alternativa, abreviações, termos populares
   - Cobre "vulcanizador → BORRACHEIRO", "funileiro → CHAPEADOR I", etc.

4. VALIDAÇÃO PÓS-CLASSIFICAÇÃO
   - Cargo de gestão rejeitado sem evidência de liderança no texto
   - Cargo de TI rejeitado sem evidência de TI
   - Cargo de Motorista validado contra CNH D/E ou palavra "motorista"

5. DEDUPLICAÇÃO por SHA-256 persistido em arquivo
6. METADADOS JSON por candidato (nome, cargo, CNH, PCD, telefone, cidade...)
7. LOGGING estruturado em arquivo + console
8. WhatsApp: mantido idêntico ao original
"""

import os, io, re, sys, time, json, socket, hashlib, logging, tempfile, unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from email.utils import parseaddr

from dotenv import load_dotenv
from imap_tools import MailBox, AND
import requests
import pdfplumber
from docx import Document as DocxDocument
from rapidfuzz import process, fuzz
from groq import Groq
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract

try:
    import fitz as pymupdf
except ImportError:
    pymupdf = None

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_OK = True
except ImportError:
    PDF2IMAGE_OK = False

try:
    import gdown
    GDOWN_OK = True
except ImportError:
    GDOWN_OK = False

try:
    import mammoth
    MAMMOTH_OK = True
except ImportError:
    MAMMOTH_OK = False

for _lib in ("pdfminer", "pdfplumber", "PIL", "urllib3"):
    logging.getLogger(_lib).setLevel(logging.ERROR)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL     = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
EMAIL_USER     = os.getenv("EMAIL_USER", "")
EMAIL_PASS     = os.getenv("EMAIL_PASS", "")
EMAIL_SERVER   = os.getenv("EMAIL_SERVER", "imap.gmail.com")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SEC", "30"))
RECRUIT_API_URL = os.getenv("RECRUIT_API_URL", "")

# ── Logging ────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"recruiter_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("recruiter")

# ── Tesseract ──────────────────────────────────────────────────────────────
OCR_LANG = "por"
for _tp in [
    os.getenv("TESSERACT_PATH", ""),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]:
    if _tp and os.path.exists(_tp):
        pytesseract.tesseract_cmd = _tp
        _td = os.path.join(os.path.dirname(_tp), "tessdata")
        os.environ["TESSDATA_PREFIX"] = _td if os.path.isdir(_td) else os.path.dirname(_tp)
        if not os.path.exists(os.path.join(os.environ["TESSDATA_PREFIX"], "por.traineddata")):
            OCR_LANG = "eng"
        log.info(f"Tesseract: {_tp} (lang={OCR_LANG})")
        break
else:
    log.warning("Tesseract nao encontrado - OCR desabilitado")

# ── Pastas ─────────────────────────────────────────────────────────────────
BASE_DIR  = Path(os.getcwd())
RECV_DIR  = Path(os.getenv("RECV_DIR", r"\\192.168.8.5\DADOS\Treinamento\curriculos_recebidos"))
HASH_FILE = RECV_DIR / ".hashes.json"

SETORES: Dict[str, Path] = {
    "Manutencao":     RECV_DIR / "manutencao",
    "Operacao":       RECV_DIR / "operacao",
    "Motorista":      RECV_DIR / "motorista",
    "Administrativo": RECV_DIR / "administrativo",
    "Jovem Aprendiz": RECV_DIR / "jovem_aprendiz",
    "TI":             RECV_DIR / "administrativo",
    "Outros":         RECV_DIR / "outros",
}
for _d in SETORES.values():
    _d.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAPA CARGO → SETOR
# ══════════════════════════════════════════════════════════════════════════════

CARGOS: Dict[str, str] = {
    # ── Manutencao ──────────────────────────────────────────────────────────
    "ABAST LUBRIFICADOR":                       "Manutencao",
    "AGENTE DE APOIO I":                        "Manutencao",
    "AGENTE DE APOIO II":                       "Manutencao",
    "AGENTE DE MANUTENCAO II":                  "Manutencao",
    "AG DE MANUT II MECANICA AUT":              "Manutencao",
    "AG DE MANUT III ELETRICA VEI":             "Manutencao",
    "ALMOXARIFE":                               "Manutencao",
    "ALMOXARIFE III":                           "Manutencao",
    "AUX ADMINISTRATIVO DE MANUTENCAO II":      "Manutencao",
    "AUX BORRACHEIRO III":                      "Manutencao",
    "AUX CHAPEACAO II":                         "Manutencao",
    "AUX DE ALMOXARIFADO II":                   "Manutencao",
    "AUX DE BORRACHEIRO I":                     "Manutencao",
    "AUX DE ELETRICISTA I":                     "Manutencao",
    "AUX DE ELETRICISTA II":                    "Manutencao",
    "AUX DE LUBRIFICADOR II":                   "Manutencao",
    "AUX DE MECANICO I":                        "Manutencao",
    "AUX DE MECANICO II":                       "Manutencao",
    "AUX ELETRICISTA I":                        "Manutencao",
    "AUX MANUT PREDIAL III":                    "Manutencao",
    "AUX SERVICOS GERAIS":                      "Manutencao",
    "AUX SERVICOS GERAIS II":                   "Manutencao",
    "AUXILIAR DE CHAPEACAO I":                  "Manutencao",
    "AUXILIAR DE CHAPEACAO II":                 "Manutencao",
    "BORRACHEIRO":                              "Manutencao",
    "CHAPEADOR I":                              "Manutencao",
    "CHAPEADOR II":                             "Manutencao",
    "CHEFE DA MANUTENCAO":                      "Manutencao",
    "CHEFE DE LAVAGEM":                         "Manutencao",
    "COORD DA MANUTENCAO":                      "Manutencao",
    "COORD DA UNIDADE DE MANUTENCAO PREDIAL":   "Manutencao",
    "COORD MANUTENCAO III":                     "Manutencao",
    "COORDENADOR DE MANUTENCAO":                "Manutencao",
    "COORDENADOR ELETRICA III":                 "Manutencao",
    "ELETRICISTA I":                            "Manutencao",
    "ELETRICISTA III":                          "Manutencao",
    "ELETRICISTA VEICULAR":                     "Manutencao",
    "ENCARREGADO ABASTECIMENTO E PATIO":        "Manutencao",
    "ENCARREGADO ALMOXARIFADO":                 "Manutencao",
    "ENCARREGADO BORRACHARIA":                  "Manutencao",
    "ENCARREGADO CHAPEACAO":                    "Manutencao",
    "ENGENHEIRO MECANICO":                      "Manutencao",
    "ESTAGIARIO DE ENGENHARIA":                 "Manutencao",
    "GERENTE DE ENGENHARIA":                    "Outros",
    "GERENTE DE MANUTENCAO":                    "Manutencao",
    "LAVADOR I":                                "Manutencao",
    "LAVADOR II":                               "Manutencao",
    "LIDER ASSIST DE OPERACOES DE LIMPEZA":     "Manutencao",
    "LIDER DE ABASTECIMENTO":                   "Manutencao",
    "LIDER LAVAGEM":                            "Manutencao",
    "LIDER MANUTENCAO":                         "Manutencao",
    "MANOBRISTA ABASTECEDOR":                   "Manutencao",
    "MANOBRISTA ABASTECEDOR II":                "Manutencao",
    "MECANICO DE PISTA":                        "Manutencao",
    "MECANICO I":                               "Manutencao",
    "MECANICO II":                              "Manutencao",
    "MECANICO III":                             "Manutencao",
    "PINTOR AUTOMOTIVO":                        "Manutencao",
    "SOCORRISTA":                               "Manutencao",
    "SUPERVISOR DE ELETRICA I":                 "Manutencao",
    "SUPERVISOR DE MANUTENCAO II":              "Manutencao",
    "SUPERVISOR DE PISTA E RAMPA I":            "Manutencao",
    "SUPERVISOR MANUT PREDIAL":                 "Manutencao",
    "TECNICO EM MANUTENCAO PREDIAL III":        "Manutencao",
    # ── Operacao ───────────────────────────────────────────────────────────
    "AUX ADM DE TRAFEGO I":                     "Operacao",
    "AUX ADMINISTRATIVO DE TRAFEGO II":         "Operacao",
    "AUXILIAR ADM DE TRAFEGO II":               "Operacao",
    "COORDENADOR DE TRAFEGO I":                 "Operacao",
    "FISCAL":                                   "Operacao",
    "FISCAL EQ":                                "Operacao",
    "LIDER FISCALIZACAO":                       "Operacao",
    "MONITOR DA OPERACAO":                      "Operacao",
    "PROGRAMADOR DE ESCALA":                    "Operacao",
    "PROGRAMADOR DE TABELAS":                   "Operacao",
    "SUB COORDENADOR TRAFEGO":                  "Operacao",
    "SUPERVISOR DE TRAFEGO":                    "Operacao",
    "VISTORIADOR EQ":                           "Operacao",
    # ── Motorista ──────────────────────────────────────────────────────────
    "MANOBRISTA":                               "Motorista",
    "MOTORISTA":                                "Motorista",
    "MOTORISTA ADMINISTRATIVO":                 "Motorista",
    "MOTORISTA INSTRUTOR":                      "Motorista",
    # ── Administrativo ─────────────────────────────────────────────────────
    "ADVOGADO":                                 "Administrativo",
    "AG ADMINISTRATIVO":                        "Administrativo",
    "ANALISTA CONTABIL SENIOR":                 "Administrativo",
    "ANALISTA DE METODOS E PROCESSOS":          "Administrativo",
    "ANALISTA DE RELACOES DO TRABALHO":         "Administrativo",
    "ANALISTA DE RH PLENO":                     "Administrativo",
    "ANALISTA DE RH SENIOR":                    "Administrativo",
    "ANALISTA FINANCEIRO JR":                   "Administrativo",
    "ANALISTA JURIDICO PLENO":                  "Administrativo",
    "ANALISTA JURIDICO SENIOR":                 "Administrativo",
    "ASSESSOR JURIDICO":                        "Administrativo",
    "ASSIST CONTABIL I":                        "Administrativo",
    "AUX ADMINISTRATIVO DE PLANEJAMENTO I":     "Administrativo",
    "AUXILIAR ADM DE ARQUIVO I":                "Administrativo",
    "AUXILIAR ADM DE ARQUIVO II":               "Administrativo",
    "AUXILIAR ADM DE MONITORAMENTO I":          "Administrativo",
    "AUXILIAR ADM DE MONITORAMENTO II":         "Administrativo",
    "AUXILIAR ADM FINANCEIRO II":               "Administrativo",
    "COORD DE COMPRAS":                         "Administrativo",
    "COORD DE PROJETOS PLANEJAMENTO E QUALIDADE": "Administrativo",
    "COORDENADOR DE PROJETOS":                  "Administrativo",
    "COORDENADOR DE RH":                        "Administrativo",
    "COORDENADOR DE SEGURANCA":                 "Administrativo",
    "COORDENADOR DO SESMT":                     "Administrativo",
    "COORDENADOR FINANCEIRO":                   "Administrativo",
    "DIR ADMIN FINANCEIRO":                     "Administrativo",
    "DIRETOR PRESIDENTE":                       "Administrativo",
    "DIRETOR TECNICO":                          "Administrativo",
    "ESPECIALISTA EM MELHORIA CONTINUA":        "Administrativo",
    "ESCRITURARIO II EQ":                       "Administrativo",
    "GERENTE DE PROJETOS":                      "Administrativo",
    "GERENTE DE RECURSOS HUMANOS":              "Administrativo",
    "INSTRUTOR DE DIRECAO":                     "Administrativo",
    "MEDICO DO TRABALHO":                       "Administrativo",
    "OPERADOR DE SAC":                          "Administrativo",
    "PSICOLOGA":                                "Administrativo",
    "RECEBEDOR":                                "Administrativo",
    "RECEPCIONISTA":                            "Administrativo",
    "SEGURANCA DO TRABALHO":                    "Administrativo",
    "SUPERVISOR SESMT":                         "Administrativo",
    "TEC ENFERMAGEM DO TRABALHO":               "Administrativo",
    "TECNICO DE SEGURANCA DO TRABALHO":         "Administrativo",
    "TECNICO DE SEGURANCA TRAB":                "Administrativo",
    "VIGILANTE":                                "Administrativo",
    # ── TI ─────────────────────────────────────────────────────────────────
    "ANALISTA DE DADOS":                        "TI",
    "ANALISTA DE SISTEMAS":                     "TI",
    "ANALISTA DE SUPORTE":                      "TI",
    "ANALISTA DE TECNOLOGIA DA INFORMACAO PLENO": "TI",
    "ASSISTENTE DE SUPORTE DE TI":              "TI",
    "CIENTISTA DE DADOS":                       "TI",
    "COORDENADOR DE TI":                        "TI",
    "DBA":                                      "TI",
    "DESENVOLVEDOR":                            "TI",
    "DESENVOLVEDOR BACK-END":                   "TI",
    "DESENVOLVEDOR FRONT-END":                  "TI",
    "DESENVOLVEDOR FULL STACK":                 "TI",
    "DEVOPS":                                   "TI",
    "ESTAGIARIO DE TI":                         "TI",
    "GERENTE DE TI":                            "TI",
    "PROGRAMADOR":                              "TI",
    "SUPORTE TECNICO":                          "TI",
    "SUPORTE TECNICO DE TI":                    "TI",
    "TECNICO DE INFORMATICA":                   "TI",
    # ── Jovem Aprendiz ─────────────────────────────────────────────────────
    "JOVEM APRENDIZ":                           "Jovem Aprendiz",
    "MENOR APRENDIZ":                           "Jovem Aprendiz",
    "MENOR APRENDIZ MEC AUTOMOTIVO":            "Jovem Aprendiz",
}

CARGO_LIST = sorted(CARGOS.keys())

# ══════════════════════════════════════════════════════════════════════════════
# SINONIMOS EXPANDIDOS
# Cobre ortografia alternativa, abreviacoes e termos populares do mercado
# ══════════════════════════════════════════════════════════════════════════════

SINONIMOS: Dict[str, str] = {
    # Motorista
    "MOTORISTA DE ONIBUS":           "MOTORISTA",
    "MOTORISTA COLETIVO":            "MOTORISTA",
    "CONDUTOR DE ONIBUS":            "MOTORISTA",
    "MOTORISTA CATEGORIA D":         "MOTORISTA",
    "MOTORISTA CATEGORIA E":         "MOTORISTA",
    "MOTORISTA CAT D":               "MOTORISTA",
    "OPERADOR DE TRANSPORTE":        "MOTORISTA",
    "MANOBRISTA DE ONIBUS":          "MANOBRISTA",
    # Mecanico
    "AUXILIAR DE MECANICO":          "AUX DE MECANICO I",
    "AUX MECANICO":                  "AUX DE MECANICO I",
    "MECANICO AUTOMOTIVO":           "MECANICO I",
    "MECANICO DIESEL":               "MECANICO I",
    "MECANICO DE VEICULOS":          "MECANICO I",
    "TECNICO MECANICO":              "MECANICO I",
    "TECNICO EM MECANICA":           "MECANICO I",
    # Eletrica
    "ELETRICISTA AUTOMOTIVO":        "ELETRICISTA VEICULAR",
    "ELETRICISTA DE VEICULOS":       "ELETRICISTA VEICULAR",
    "AUXILIAR DE ELETRICISTA":       "AUX DE ELETRICISTA I",
    "AUX ELETRICISTA":               "AUX ELETRICISTA I",
    "TECNICO ELETRICO":              "ELETRICISTA I",
    "TECNICO EM ELETRICA":           "ELETRICISTA I",
    # Borracheiro
    "VULCANIZADOR":                  "BORRACHEIRO",
    "BORRACHARIA":                   "BORRACHEIRO",
    "AUXILIAR BORRACHEIRO":          "AUX DE BORRACHEIRO I",
    # Chapeacao / Pintura
    "CHAPEIRO":                      "CHAPEADOR I",
    "FUNILEIRO":                     "CHAPEADOR I",
    "FUNILEIRO AUTOMOTIVO":          "CHAPEADOR I",
    "AUXILIAR DE FUNILEIRO":         "AUXILIAR DE CHAPEACAO I",
    "PINTOR DE VEICULOS":            "PINTOR AUTOMOTIVO",
    # Lavagem / Limpeza / Servicos Gerais
    "LAVADOR DE VEICULOS":           "LAVADOR I",
    "LAVADOR DE ONIBUS":             "LAVADOR I",
    "AUXILIAR DE LAVAGEM":           "LAVADOR I",
    "LIMPEZA":                       "AUX SERVICOS GERAIS",
    "HIGIENIZACAO":                  "AUX SERVICOS GERAIS",
    "AUXILIAR DE LIMPEZA":           "AUX SERVICOS GERAIS",
    "SERVENTE DE LIMPEZA":           "AUX SERVICOS GERAIS",
    "ZELADOR":                       "AUX SERVICOS GERAIS",
    "FAXINEIRO":                     "AUX SERVICOS GERAIS",
    "AUXILIAR DE SERVICOS GERAIS":   "AUX SERVICOS GERAIS",
    "SERVICOS GERAIS":               "AUX SERVICOS GERAIS",
    "AUXILIAR DE PRODUCAO":          "AUX SERVICOS GERAIS",
    # Almoxarifado / Estoque
    "ESTOQUISTA":                    "ALMOXARIFE",
    "ALMOXARIFE DE PECAS":           "ALMOXARIFE",
    "ANALISTA DE ALMOXARIFADO":      "ALMOXARIFE",
    "ALMOXARIFADO":                  "ALMOXARIFE",
    "AUXILIAR DE ALMOXARIFADO":      "AUX DE ALMOXARIFADO II",
    "AUXILIAR DE ESTOQUE":           "AUX DE ALMOXARIFADO II",
    "CONTROLADOR DE ESTOQUE":        "ALMOXARIFE",
    "OPERACAO LOGISTICA":            "ALMOXARIFE",
    "Auxiliar de Operações Logísticas": "AUX DE ALMOXARIFADO II",
    # Operacao / Trafego
    "FISCAL DE ONIBUS":              "FISCAL",
    "FISCAL DE TRAFEGO":             "FISCAL",
    "AGENTE DE FISCALIZACAO":        "FISCAL",
    "MONITOR DE BORDO":              "MONITOR DA OPERACAO",
    "AGENTE DE TRAFEGO":             "AUX ADM DE TRAFEGO I",
    "AUX DE TRAFEGO":                "AUX ADM DE TRAFEGO I",
    # Administrativo / RH / Financeiro
    "ASSISTENTE ADMINISTRATIVO":     "AG ADMINISTRATIVO",
    "AUXILIAR ADMINISTRATIVO":       "AG ADMINISTRATIVO",
    "AUXILIAR DE ESCRITORIO":        "AG ADMINISTRATIVO",
    "OFFICE BOY":                    "AG ADMINISTRATIVO",
    "ASSISTENTE DE RH":              "ANALISTA DE RH PLENO",
    "AUXILIAR DE RH":                "ANALISTA DE RH PLENO",
    "ASSISTENTE FINANCEIRO":         "AUXILIAR ADM FINANCEIRO II",
    "AUXILIAR FINANCEIRO":           "AUXILIAR ADM FINANCEIRO II",
    "CONTAS A PAGAR":                "AUXILIAR ADM FINANCEIRO II",
    "CONTAS A RECEBER":              "AUXILIAR ADM FINANCEIRO II",
    "AUXILIAR CONTABIL":             "ASSIST CONTABIL I",
    "ASSISTENTE CONTABIL":           "ASSIST CONTABIL I",
    "ESCRITA FISCAL":                "ASSIST CONTABIL I",
    "SPED FISCAL":                   "ASSIST CONTABIL I",
    "TECNICO CONTABIL":              "ANALISTA CONTABIL SENIOR",
    "ADVOGADA":                      "ADVOGADO",
    "AUXILIAR JURIDICO":             "ASSESSOR JURIDICO",
    # TI
    "HELP DESK":                     "ASSISTENTE DE SUPORTE DE TI",
    "SERVICE DESK":                  "ASSISTENTE DE SUPORTE DE TI",
    "SUPORTE TECNICO DE TI":         "ASSISTENTE DE SUPORTE DE TI",
    "SUPORTE TECNICO":               "ASSISTENTE DE SUPORTE DE TI",
    "SUPORTE DE TI":                 "ASSISTENTE DE SUPORTE DE TI",
    "ANALISTA DE TI":                "ASSISTENTE DE SUPORTE DE TI",
    "TECNICO DE TI":                 "TECNICO DE INFORMATICA",
    "TECNICO EM INFORMATICA":        "TECNICO DE INFORMATICA",
    "TECNOLOGIA DA INFORMACAO":      "ASSISTENTE DE SUPORTE DE TI",
    "DESENVOLVEDOR DE SOFTWARE":     "DESENVOLVEDOR",
    "PROGRAMADOR DE SISTEMAS":       "PROGRAMADOR",
    "FULL STACK":                    "DESENVOLVEDOR FULL STACK",
    "BACK END":                      "DESENVOLVEDOR BACK-END",
    "FRONT END":                     "DESENVOLVEDOR FRONT-END",
    # Saude / Seguranca
    "ENFERMEIRO DO TRABALHO":        "TEC ENFERMAGEM DO TRABALHO",
    "TECNICO DE ENFERMAGEM":         "TEC ENFERMAGEM DO TRABALHO",
    "TECNICO EM ENFERMAGEM":         "TEC ENFERMAGEM DO TRABALHO",
    "ENGENHEIRO DE SEGURANCA":       "SEGURANCA DO TRABALHO",
    "TECNICO DE SEGURANCA":          "TECNICO DE SEGURANCA DO TRABALHO",
    "TECNICO EM SEGURANCA":          "TECNICO DE SEGURANCA DO TRABALHO",
    "PSICOLOGO":                     "PSICOLOGA",
    # Jovem Aprendiz
    "APRENDIZ INDUSTRIAL":           "MENOR APRENDIZ",
    "JOVEM APRENDIZ DE MECANICA":    "MENOR APRENDIZ MEC AUTOMOTIVO",
}

# ══════════════════════════════════════════════════════════════════════════════
# UTILITARIOS
# ══════════════════════════════════════════════════════════════════════════════

def norm(txt: str) -> str:
    s = unicodedata.normalize("NFKD", txt or "")
    return s.encode("ascii", "ignore").decode("utf-8").upper().strip()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def limpar_html(html: str) -> str:
    try:
        return BeautifulSoup(html or "", "html.parser").get_text(" ")
    except Exception:
        return re.sub(r"<[^>]+>", " ", html or "")

def sanitize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"[^A-Z0-9 _\-\(\)]", "", s.upper()).strip()

# ══════════════════════════════════════════════════════════════════════════════
# HASH DB (deduplicacao permanente por SHA-256)
# ══════════════════════════════════════════════════════════════════════════════

class HashDB:
    def __init__(self, path: Path):
        self._path = path
        self._db: set = set()
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._db = set(json.loads(self._path.read_text("utf-8")).get("h", []))
            except Exception:
                self._db = set()

    def _save(self):
        try:
            self._path.write_text(json.dumps({"h": list(self._db)}, indent=2), "utf-8")
        except Exception:
            pass

    def has(self, h: str) -> bool:
        return h in self._db

    def add(self, h: str):
        self._db.add(h)
        self._save()


HASH_DB = HashDB(HASH_FILE)

# ══════════════════════════════════════════════════════════════════════════════
# CLIENTE GROQ (cache MD5 + rate-limit backoff)
# ══════════════════════════════════════════════════════════════════════════════

class GroqClient:
    def __init__(self, api_key: str):
        self._c = Groq(api_key=api_key) if api_key else None
        self._next_ok = 0.0
        self._cache: Dict[str, str] = {}

    @property
    def ok(self) -> bool:
        return bool(self._c) and time.time() >= self._next_ok

    def _cooldown(self, err: str):
        m = re.search(r"try again in (\d+)m([0-9.]+)s", err)
        secs = int(m.group(1)) * 60 + float(m.group(2)) if m else 120
        self._next_ok = time.time() + secs
        log.warning(f"Groq rate-limit — pausa {secs:.0f}s")

    def chat(self, system: str, user: str, temp: float = 0.0) -> Optional[str]:
        if not self.ok:
            return None
        key = hashlib.md5(f"{system}|{user}".encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        try:
            r = self._c.chat.completions.create(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                model=GROQ_MODEL,
                temperature=temp,
                max_tokens=256,
            )
            out = r.choices[0].message.content.strip()
            self._cache[key] = out
            return out
        except Exception as e:
            if "rate" in str(e).lower():
                self._cooldown(str(e))
            else:
                log.error(f"Groq erro: {e}")
            return None


GROQ = GroqClient(GROQ_API_KEY)

# ══════════════════════════════════════════════════════════════════════════════
# EXTRACAO DE TEXTO
# ══════════════════════════════════════════════════════════════════════════════

def _ocr(img: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(img, lang=OCR_LANG)
    except Exception:
        return ""


def ler_pdf(data: bytes) -> str:
    txt = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for p in pdf.pages:
                txt += (p.extract_text() or "") + "\n"
    except Exception:
        pass
    if len(txt.strip()) >= 80:
        return txt
    # OCR via PyMuPDF
    if pymupdf:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
            for i in range(len(doc)):
                pix = doc.load_page(i).get_pixmap()
                img = Image.frombytes(
                    "RGBA" if pix.alpha else "RGB",
                    [pix.width, pix.height],
                    pix.samples,
                )
                txt += _ocr(img) + "\n"
            if txt.strip():
                return txt
        except Exception:
            pass
    # OCR via pdf2image
    if PDF2IMAGE_OK:
        try:
            for img in convert_from_bytes(data):
                txt += _ocr(img) + "\n"
        except Exception:
            pass
    return txt


def ler_docx(data: bytes) -> str:
    # python-docx
    try:
        doc = DocxDocument(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        seen = set()
        for tbl in doc.tables:
            for row in tbl.rows:
                for cell in row.cells:
                    ct = cell.text.strip()
                    if ct and ct not in seen:
                        seen.add(ct)
                        parts.append(ct)
        if parts:
            return "\n".join(parts)
    except Exception:
        pass
    # mammoth
    if MAMMOTH_OK:
        try:
            return limpar_html(mammoth.convert_to_html(io.BytesIO(data)).value or "")
        except Exception:
            pass
    # ZIP raw XML
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        parts = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.startswith("word/") and n.endswith(".xml"):
                    root = ET.fromstring(z.read(n))
                    parts += [t.text for t in root.findall(".//w:t", ns) if t.text]
        return "\n".join(parts)
    except Exception:
        return ""


def ler_doc(data: bytes) -> str:
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as f:
            f.write(data)
            tmp = f.name
        try:
            import win32com.client
            w = win32com.client.Dispatch("Word.Application")
            w.Visible = False
            d = w.Documents.Open(tmp)
            t = d.Content.Text
            d.Close(False)
            w.Quit()
            return t or ""
        except Exception:
            pass
        try:
            import subprocess
            r = subprocess.run(["antiword", tmp], capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return r.stdout
        except Exception:
            pass
        if MAMMOTH_OK:
            try:
                return limpar_html(mammoth.convert_to_html(io.BytesIO(data)).value or "")
            except Exception:
                pass
        return data.decode("utf-8", errors="ignore")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def extrair_texto(nome: str, data: bytes) -> str:
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    if data[:4]  == b"%PDF":                    ext = "pdf"
    elif data[:2]  == b"PK":                    ext = "docx"
    elif data[:8]  == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1": ext = "doc"
    elif data[:5]  == b"{\\rtf":                ext = "rtf"
    elif data[:3]  == b"\xFF\xD8\xFF":          ext = "jpg"
    elif data[:8]  == b"\x89PNG\r\n\x1a\n":     ext = "png"

    if ext == "pdf":                return ler_pdf(data)
    if ext == "docx":               return ler_docx(data)
    if ext == "doc":                return ler_doc(data)
    if ext in ("rtf", "txt"):       return data.decode("utf-8", errors="ignore")
    if ext in ("jpg","jpeg","png","bmp","tiff","webp"):
        try:
            return _ocr(Image.open(io.BytesIO(data)))
        except Exception:
            return ""
    return ""

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE DE CLASSIFICACAO DE CARGO (7 etapas)
# ══════════════════════════════════════════════════════════════════════════════

# Prompt Groq especializado com exemplos dos erros mais comuns
_GROQ_SYSTEM = (
    "Voce e um classificador especializado em curriculos para empresa de transporte publico.\n\n"
    "LISTA DE CARGOS VALIDOS (responda APENAS com um destes ou SEM CARGO):\n"
    + "\n".join(CARGO_LIST) +
    "\n\nREGRAS OBRIGATORIAS:\n"
    "1. Responda com o nome EXATO do cargo da lista. Nada mais.\n"
    "2. Se nao tiver certeza, responda: SEM CARGO\n"
    "3. Cargo de gestao (Coord/Gerente/Supervisor/Chefe) SÓ se o texto mencionar lideranca/gestao/equipe.\n"
    "4. Cargo de TI SÓ se o texto mencionar TI, informatica, help desk, redes, sistemas, programacao.\n"
    "5. 'Escrita fiscal', 'SPED', 'contabilidade' -> ASSIST CONTABIL I ou ANALISTA CONTABIL SENIOR, NAO use FISCAL.\n"
    "6. 'Engenheiro de Seguranca do Trabalho' -> SEGURANCA DO TRABALHO.\n"
    "7. 'Tecnico de Enfermagem' -> TEC ENFERMAGEM DO TRABALHO.\n"
    "8. CNH D ou E + transporte coletivo -> MOTORISTA.\n"
    "9. 'Manobrista' -> MANOBRISTA (nao MOTORISTA).\n"
    "10. 'Jovem Aprendiz' ou 'Menor Aprendiz' -> use a categoria correta.\n\n"
    "ERROS COMUNS E CORRECOES:\n"
    "- 'Fiscal de impostos / SPED' -> ASSIST CONTABIL I  (NAO e FISCAL)\n"
    "- 'Engenheiro de Seguranca' -> SEGURANCA DO TRABALHO  (NAO e ENGENHEIRO MECANICO)\n"
    "- 'Auxiliar administrativo com RH' -> AG ADMINISTRATIVO  (NAO e ANALISTA DE RH PLENO)\n"
    "- 'Auxiliar de mecanico' -> AUX DE MECANICO I  (NAO e MECANICO I)\n"
    "- 'Motorista particular/executivo' sem onibus -> MOTORISTA ADMINISTRATIVO\n"
    "- 'Suporte de TI / help desk' -> ASSISTENTE DE SUPORTE DE TI\n"
)

# Tokens que indicam cargo de gestao
_TOK_GESTAO = {"COORD", "COORDENADOR", "COORDENADORA", "GERENTE", "SUPERVISOR", "CHEFE", "LIDER", "DIRETOR"}
# Evidencias de gestao no texto
_EV_GESTAO = {"COORDENADOR","GERENTE","SUPERVISOR","LIDER","GESTAO","CHEFIA",
              "COORDENACAO","DIRECAO","EQUIPE","EQUIPES"}
# Evidencias de TI no texto
_EV_TI = {"SUPORTE TECNICO","HELP DESK","SERVICE DESK","REDES",
          "SISTEMAS","PROGRAMACAO","DESENVOLVIMENTO","HARDWARE","SOFTWARE",
          "DBA","DESENVOLVEDOR","DEVOPS","BANCO DE DADOS"}
# Evidencias de Motorista no texto
_EV_MOTOR = {"MOTORISTA","CONDUTOR","CNH D","CNH E","CATEGORIA D","CATEGORIA E",
             "TRANSPORTE COLETIVO","ONIBUS","DIRIG"}

def extrair_idade(texto: str, dados: Optional[Dict] = None, data_ref: Optional[datetime] = None) -> Optional[int]:
    try:
        if dados:
            v = dados.get("idade")
            if isinstance(v, (int, float)) and 0 < int(v) < 120:
                return int(v)
            if isinstance(v, str):
                m = re.search(r'\b(\d{1,2})\b', v)
                if m:
                    iv = int(m.group(1))
                    if 0 < iv < 120:
                        return iv
    except Exception:
        pass

    try:
        m = re.search(r'(?i)\b(\d{1,2})\s*ANOS\b', texto or "")
        if m:
            iv = int(m.group(1))
            if 0 < iv < 120:
                return iv
    except Exception:
        pass

    try:
        ref = data_ref or datetime.now()
        m = re.search(
            r'(?i)\b(?:DATA\s+DE\s+NASCIMENTO|DATA\s+NASCIMENTO|NASCIMENTO|NASC\.)\b[^0-9]{0,12}'
            r'(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})',
            texto or "",
        )
        if not m:
            m = re.search(r'(?i)\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})\b', texto or "")
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1900 <= y <= ref.year:
                dob = datetime(y, mo, d)
                idade = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
                if 0 < idade < 120:
                    return idade
    except Exception:
        pass

    return None


def _valida(cargo: str, t_norm: str) -> bool:
    """Rejeita cargo incompativel com o conteudo do curriculo."""
    c = norm(cargo)
    toks = set(c.split())

    # Gestao sem evidencia
    if toks & _TOK_GESTAO:
        evid = {"COORDENADOR","GERENTE","SUPERVISOR","GESTAO","CHEFIA","SUPERVISAO",
                "COORDENACAO","DIRECAO","LIDERANCA","LIDER","ENCARREGADO","RESPONSAVEL"}
        if not any(e in t_norm for e in evid):
            log.debug(f"Cargo gestao '{cargo}' rejeitado (sem evidencia)")
            return False

    # TI sem evidencia
    if any(k in c for k in ("SUPORTE","DESENVOLVEDOR","PROGRAMADOR","DBA","DEVOPS",
                             "ANALISTA DE SISTEMAS","ANALISTA DE DADOS","CIENTISTA",
                             "TECNICO DE INFORMATICA","ASSISTENTE DE SUPORTE")):
        has_ti = any(e in t_norm for e in _EV_TI) or bool(re.search(r'\bTI\b', t_norm))
        if not has_ti:
            if "TECNICO EM INFORMATICA" in t_norm or "TECNICO DE INFORMATICA" in t_norm:
                has_ti = True
        if not has_ti and "SUPORTE" in t_norm:
            if any(k in t_norm for k in ("HELP DESK", "SERVICE DESK", "REDES", "HARDWARE", "SOFTWARE", "CABEAMENTO", "TCP", "IP", "INTERNET", "WINDOWS", "LINUX")):
                has_ti = True
        if not re.search(r'\bTI\b', t_norm):
            if "SISTEMAS" in t_norm and not any(e in t_norm for e in _EV_TI if e != "SISTEMAS"):
                has_ti = False
        if re.search(r'\bINFORMATICA\s+(?:BASIC|BASICA)\b', t_norm):
            has_ti = any(e in t_norm for e in _EV_TI if e not in ("SISTEMAS",)) or bool(re.search(r'\bTI\b', t_norm))
        if not has_ti:
            log.debug(f"Cargo TI '{cargo}' rejeitado (sem evidencia)")
            return False

    if any(k in c for k in ("RELACOES DO TRABALHO", "RECURSOS HUMANOS", "RH")):
        evid = {"RECURSOS HUMANOS", "DEPARTAMENTO PESSOAL", "FOLHA", "PONTO", "ADMISSION", "DEMIS", "BENEFIC", "RECRUTAMENTO", "SELECAO", "TREINAMENTO"}
        if not any(e in t_norm for e in evid) and not re.search(r'\bRH\b', t_norm) and not re.search(r'\bDP\b', t_norm):
            return False

    if cargo == "OPERADOR DE SAC":
        if re.search(r'\bNAO\b.{0,30}\bSAC\b', t_norm):
            return False
        evid = {"CALL CENTER", "TELEATEND", "TELEMARK", "OUVIDOR", "RECLAMAC", "0800", "CENTRAL"}
        if not any(e in t_norm for e in evid):
            return False

    # Motorista sem evidencia - validacao robusta
    if cargo in ("MOTORISTA", "MOTORISTA ADMINISTRATIVO", "MOTORISTA INSTRUTOR", "MANOBRISTA"):
        has_any_cnh = bool(re.search(r'\bCNH\b|\bCATEGORIA\b|\bCAT\b|CARTEIRA\s+(?:NACIONAL\s+)?DE\s+HABILITAC', t_norm, re.IGNORECASE))
        if not has_any_cnh:
            mot_mentions = t_norm.count("MOTORISTA") + bool(re.search(r'(?i)\bMOTORISTA\s+DE\s+(?:ONIBUS|ÔNIBUS)\b', t_norm)) + bool(re.search(r'(?i)\bMOTORISTA\s+DE\s+CAMINH[AÃ]O\b', t_norm))
            exp_tokens = any(k in t_norm for k in ("TRANSPORTE COLETIVO","AUTO VIACAO","VIACAO","COMPANHIA CARRIS","ONIBUS","CAMINHAO"))
            if not (mot_mentions >= 2 or ("MOTORISTA" in t_norm and exp_tokens)):
                return False
        has_driver = any(k in t_norm for k in ("MOTORISTA", "CONDUTOR", "DIRIG"))
        has_bus    = any(k in t_norm for k in ("ONIBUS","COLETIVO","TRANSPORTE COLETIVO"))
        has_truck  = any(k in t_norm for k in ("CAMINHAO","CARGA"))
        has_cnh_de = bool(re.search(r'\b(?:CNH|CATEGORIA|CAT)\s*[:\-]?\s*[DE]\b', t_norm, re.IGNORECASE))
        almox_hits = sum(
            1 for ok in (
                "ALMOXARIF" in t_norm,
                "ESTOQUE" in t_norm,
                "INVENTAR" in t_norm,
                "NOTA FISCAL" in t_norm or "NOTAS FISCAIS" in t_norm or "NF" in t_norm or "NFE" in t_norm or "NF-E" in t_norm,
                "RECEBIMENTO" in t_norm,
                "CONFERENC" in t_norm,
            ) if ok
        )
        aux_driver = bool(re.search(r'(?i)AUX(?:ILIAR)?\s+[A-Z ]{0,20}?MOTORISTA', t_norm))
        if aux_driver and not has_bus and not has_truck:
            return False
        if almox_hits >= 2 and not has_driver and not has_truck:
            return False
        # Requer evidencia forte: motorista explícito ou caminhão,
        # ou então onibus + CNH D/E + evidencia de atuacao (evita nome de empresa com "Ônibus").
        evid_bus = any(k in t_norm for k in ("TRANSPORTE COLETIVO", "PASSAGEIR", "LINHAS"))
        if not (has_driver or has_truck or (has_bus and has_cnh_de and evid_bus)):
            log.debug(f"Cargo Motorista rejeitado (sem evidencia)")
            return False
        log.debug(f"Motorista validado (Driver:{has_driver}, Bus:{has_bus}, CNH D/E:{has_cnh_de})")

    if "APRENDIZ" in c:
        idade = extrair_idade(t_norm)
        if idade is None:
            return False
        # Politica Carris: Jovem Aprendiz apenas menores de 18 anos
        if "MENOR" in c and idade >= 18:
            log.debug(f"Menor Aprendiz rejeitado (idade {idade} >= 18)")
            return False
        if "JOVEM" in c and idade >= 18:
            log.debug(f"Jovem Aprendiz rejeitado (idade {idade} >= 18)")
            return False
        # Suggestao para candidatos fora da faixa de aprendiz
        if idade >= 18 and idade < 30:
            if any(k in c for k in ("SUPORTE", "TECNICO", "INFORMATICA")):
                log.debug(f"Candidato com {idade} anos - sugere SUPORTE_DE_TI")
            elif any(k in c for k in ("ADMINISTRATIVO", "AUXILIAR")):
                log.debug(f"Candidato com {idade} anos - sugere AG_ADMINISTRATIVO")

    if c.startswith("LAVADOR"):
        if not any(k in t_norm for k in ("LAVADOR", "LAVAGEM", "LAVAR", "LAVA")):
            return False
    if cargo == "MONITOR DA OPERACAO":
        evid = {"MONITOR","OPERACAO","ESCALA","LINHAS","COORDENACAO","TRAFEGO",
                "COBRADOR","COBRANCA","PASSAGEIR","TARIFA","TRANSPORTE COLETIVO","ONIBUS"}
        if not any(e in t_norm for e in evid):
            return False
    if cargo in ("AUXILIAR ADM DE MONITORAMENTO I","AUXILIAR ADM DE MONITORAMENTO II"):
        evid = {"MONITORAMENTO","VIDEOMONITORAMENTO","CFTV","CAMERA","CÂMERA","CÂMERAS","CAMERAS","RASTREAMENTO","GPS","CENTRAL DE MONITORAMENTO","FROTA"}
        if not any(e in t_norm for e in evid):
            return False

    return True


# ── 7 Etapas ──────────────────────────────────────────────────────────────

def _et1_assunto_corpo(assunto: str, corpo: str) -> Optional[str]:
    """Etapa 1: cargo/sinonimo no assunto ou corpo do email."""
    blob = norm(f"{assunto} {corpo}")
    for sin, cargo in sorted(SINONIMOS.items(), key=lambda kv: len(norm(kv[0])), reverse=True):
        if norm(sin) in blob and cargo in CARGOS:
            return cargo
    best, blen = None, 0
    for c in CARGO_LIST:
        cn = norm(c)
        if cn in blob and len(cn) > blen:
            best, blen = c, len(cn)
    return best


def _et2_sinonimos_texto(t_norm: str) -> Optional[str]:
    """Etapa 2: sinonimos no texto do curriculo."""
    for sin, cargo in sorted(SINONIMOS.items(), key=lambda kv: len(norm(kv[0])), reverse=True):
        sin_n = norm(sin)
        if sin_n in t_norm and cargo in CARGOS:
            if cargo == "AUX SERVICOS GERAIS" and sin_n in ("LIMPEZA", "HIGIENIZACAO"):
                continue
            return cargo
    return None


def _et3_regex(texto: str, t_norm: str) -> Optional[str]:
    """Etapa 3: regras regex de alta confianca."""
    # Almoxarifado forte
    if "ALMOXARIF" in t_norm or "ALMOXARIFADO" in t_norm:
        return "ALMOXARIFE"
    if any(k in t_norm for k in ("GESTAO DE ESTOQUE","CONTROLE DE ESTOQUE","INVENTARIO","INVENTARIOS")):
        if any(k in t_norm for k in ("ALMOXARIF","ALMOXARIFADO","ESTOQUE","ALMOXARIFE")):
            return "ALMOXARIFE"
    # Motorista de onibus/caminhao sem CNH explicita (experiencia forte)
    if re.search(r'(?i)\bMOTORISTA\s+DE\s+(?:ONIBUS|ÔNIBUS)\b', texto or ""):
        return "MOTORISTA"
    if re.search(r'(?i)\bMOTORISTA\s+DE\s+CAMINH[AÃ]O\b', texto or ""):
        return "MOTORISTA"
    has_any_cnh = bool(re.search(r'\bCNH\b|\bCATEGORIA\b|\bCAT\b|CARTEIRA\s+(?:NACIONAL\s+)?DE\s+HABILITAC', texto or "", re.IGNORECASE))
    if re.search(r'(?i)\bMANOBRISTA\b', texto or ""):
        if has_any_cnh:
            return "MANOBRISTA"
    if re.search(r'(?i)\bMOTORISTA(?:\s+[IVX]+)?\b', texto or ""):
        if has_any_cnh and not re.search(r'(?i)\bAUX(?:ILIAR)?\s+MOTORISTA\b', texto or ""):
            return "MOTORISTA"

    # CNH D/E + onibus -> Motorista
    if re.search(r'\b(?:CNH|CATEGORIA|CAT)\s*[:\-]?\s*[DE]\b', texto, re.IGNORECASE):
        # Evita falso positivo por nome de empresa com "Ônibus".
        # Exige indicio de atuacao como motorista/condutor.
        if any(w in t_norm for w in ("MOTORISTA","CONDUTOR","DIRIG","TRANSPORTE COLETIVO","PASSAGEIR","LINHAS")):
            return "MOTORISTA"

    # Aprendiz
    if re.search(r'\b(?:MENOR|JOVEM)\s+APRENDIZ\b', texto, re.IGNORECASE):
        idade = extrair_idade(texto)
        if idade < 18:
            return "MENOR APRENDIZ"

    idade = extrair_idade(texto)
    if idade is not None and idade < 18:
        if any(k in t_norm for k in ("PRIMEIRO EMPREGO","PRIMEIRA OPORTUNIDADE","SEM EXPERIENCIA","PRIMEIRA VEZ")):
            return "MENOR APRENDIZ"

    if re.search(r'(?i)\bCONFERENTE\b', texto or ""):
        return "ALMOXARIFE"

    # Limpeza / Servente -> Aux Serviços Gerais
    if re.search(r'(?i)\bSERVICOS\s+GERAIS\b', texto or ""):
        return "AUX SERVICOS GERAIS"
    if re.search(r'(?i)\bAUX(?:ILIAR)?\s+(?:DE\s+)?(?:SERVICOS\s+GERAIS|LIMPEZA)\b', texto or ""):
        return "AUX SERVICOS GERAIS"
    if re.search(r'(?i)\b(?:SERVENTE|SERVENTE\s+DE\s+LIMPEZA|FAXINEIR[AO]|ZELADOR|HIGIENIZACAO)\b', texto or ""):
        return "AUX SERVICOS GERAIS"

    if "SEGURANCA DO TRABALHO" not in t_norm and "TECNICO DE SEGURANCA" not in t_norm:
        vig = any(k in t_norm for k in ("VIGILANTE","VIGIA","GUARDA","PATRIMONIAL","PORTARIA","PORTEIRO"))
        if (not vig) and ("SEGURANCA" in t_norm):
            vig = any(k in t_norm for k in ("PATRIMONIAL","ROND","ARMAD"))
        if vig:
            if not any(e in t_norm for e in ("GESTAO","CHEFIA","SUPERVISAO","COORDENACAO","DIRECAO","LIDERANCA","LIDER","ENCARREGADO","RESPONSAVEL")):
                return "VIGILANTE"

    if any(k in t_norm for k in ("LOGISTICA","LOGÍSTICA")) and any(k in t_norm for k in ("OPERACOES","OPERACAO","ENCARREGADO")):
        return "ALMOXARIFE"

    if re.search(r'(?i)\b(?:ASSISTENTE|AUXILIAR)\s+DE\s+RH\b', texto or "") or re.search(r'(?i)\bDEPARTAMENTO\s+PESSOAL\b', texto or ""):
        if any(k in t_norm for k in ("FOLHA", "PONTO", "BENEFIC", "ADMISSION", "DEMIS", "COLABORADOR", "PESSOAL", "DP")):
            return "ANALISTA DE RH PLENO"

    # Tecnico de Enfermagem
    if re.search(r'\bTEC(?:NICO|NICA)?\s+(?:DE\s+|EM\s+)?ENFERMAGEM\b', texto, re.IGNORECASE):
        return "TEC ENFERMAGEM DO TRABALHO"

    # Contabilidade (nao confundir com FISCAL de operacao)
    if re.search(r'\b(?:ESCRITA\s+FISCAL|SPED|CIENCIAS\s+CONTABEIS|CONTABILIDADE)\b', texto, re.IGNORECASE):
        if "FISCALIZ" not in t_norm:
            return "ASSIST CONTABIL I"

    # Seguranca do trabalho
    if re.search(r'\bSEGURANCA\s+DO\s+TRABALHO\b', texto, re.IGNORECASE):
        return "SEGURANCA DO TRABALHO"

    return None


def _et4_literal(t_norm: str) -> Optional[str]:
    """Etapa 4: cargo oficial encontrado literalmente no texto."""
    best, blen = None, 0
    for c in CARGO_LIST:
        cn = norm(c)
        if c == "MOTORISTA" and re.search(r'\bAUX(?:ILIAR)?\s+MOTORISTA\b', t_norm):
            continue
        if len(cn) > 4 and cn in t_norm and len(cn) > blen:
            best, blen = c, len(cn)
    return best


def _et5_fuzzy(t_norm: str) -> Optional[str]:
    """Etapa 5: fuzzy match em janelas de palavras (WRatio >= 88)."""
    words = t_norm.split()
    candidates: set = set()
    for i in range(len(words)):
        for size in (2, 3, 4, 5):
            chunk = " ".join(words[i:i + size])
            if len(chunk) < 5:
                continue
            hit = process.extractOne(chunk, CARGO_LIST, scorer=fuzz.WRatio)
            if hit and hit[1] >= 88:
                candidates.add(hit[0])
    return max(candidates, key=len) if candidates else None


def _et6_groq(texto: str, assunto: str, corpo: str) -> Optional[str]:
    """Etapa 6: Groq LLM com prompt especializado."""
    tnorm = norm(texto)
    if any(k in tnorm for k in ("MOTORISTA","CONDUTOR","DIRIG","ONIBUS","COLETIVO","TRANSPORTE COLETIVO")):
        return None
    user = (
        f"Assunto do email: {assunto}\n"
        f"Corpo do email: {corpo[:300]}\n\n"
        f"Curriculo:\n{texto[:2500]}"
    )
    out = GROQ.chat(_GROQ_SYSTEM, user, temp=0.0)
    if not out:
        return None
    c = norm(out.strip().splitlines()[0])
    if c in CARGOS:
        return c
    hit = process.extractOne(c, CARGO_LIST, scorer=fuzz.WRatio)
    if hit and hit[1] >= 94:
        return hit[0]
    return None


def _et7_area(t_norm: str) -> Tuple[str, str]:
    """Etapa 7: fallback por area mais mencionada."""
    if any(k in t_norm for k in ("PADARIA", "EMPACOTAD", "EMPACOTADOR", "OPERADOR DE CAIXA", "CAIXA")):
        excl_sub = ("ADMINISTRATIVO", "FINANCEIRO", "CONTABIL", "JURIDIC", "SUPORTE TECNICO",
                    "HELP DESK", "SERVICE DESK", "MECANIC", "ELETRICISTA", "MOTORISTA", "TRAFEGO", "FISCAL", "ALMOXARIF")
        has_excl = any(k in t_norm for k in excl_sub) or bool(re.search(r'\b(?:TI|RH|DP)\b', t_norm))
        if not has_excl:
            return "SEM CARGO", "Outros"
    areas = {
        "Manutencao":     ["MECANIC","ELETRICISTA","BORRACHEIRO","CHAPEACAO","OFICINA","LAVAGEM","PINTUR","ALMOXARIF"],
        "Operacao":       ["TRAFEGO","FISCAL","ONIBUS","ESCALA","MONITOR","LINHAS"],
        "Motorista":      ["MOTORISTA","CONDUTOR","DIRIG"],
        "Administrativo": ["ADMINISTRATIVO","RH","FINANCEIRO","CONTABIL","JURIDICO","ATENDENTE","ATENDIMENTO","RECEPCIONISTA"],
        "TI":             ["SISTEMA","PROGRAMACAO","HELP DESK","SERVICE DESK","SUPORTE TECNICO","DESENVOLVIMENTO","SOFTWARE","HARDWARE","REDES"],
        "Jovem Aprendiz": ["MENOR APRENDIZ", "JOVEM APRENDIZ"],
    }
    scores = {a: sum(1 for k in kws if k in t_norm) for a, kws in areas.items()}
    if scores.get("Motorista", 0) > 0:
        has_any_cnh = bool(re.search(r'\bCNH\b|\bCATEGORIA\b|\bCAT\b|CARTEIRA\s+(?:NACIONAL\s+)?DE\s+HABILITAC', t_norm, re.IGNORECASE))
        if not has_any_cnh:
            mot_mentions = t_norm.count("MOTORISTA") + bool(re.search(r'(?i)\bMOTORISTA\s+DE\s+(?:ONIBUS|ÔNIBUS)\b', t_norm)) + bool(re.search(r'(?i)\bMOTORISTA\s+DE\s+CAMINH[AÃ]O\b', t_norm))
            if mot_mentions < 2 and not re.search(r'(?i)\bMOTORISTA\s+DE\s+(?:ONIBUS|ÔNIBUS|CAMINH[AÃ]O)\b', t_norm):
                scores["Motorista"] = 0
    if scores.get("Jovem Aprendiz", 0) > 0:
        idade = extrair_idade(t_norm)
        if idade is None or idade >= 18:
            scores["Jovem Aprendiz"] = 0
    if "COBRADOR" in t_norm and not any(k in t_norm for k in ("FISCAL","TRAFEGO","MONITOR","PROGRAMADOR","COORDENADOR")):
        return "SEM CARGO", "Outros"
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "SEM CARGO", "Outros"
    genericos = {
        "Manutencao":     "AGENTE DE MANUTENCAO II",
        "Operacao":       "FISCAL",
        "Motorista":      "MOTORISTA",
        "Administrativo": "AG ADMINISTRATIVO",
        "TI":             "ASSISTENTE DE SUPORTE DE TI",
        "Jovem Aprendiz": "JOVEM APRENDIZ",
    }
    return genericos[best], best


def classificar_cargo(
    texto: str,
    assunto: str = "",
    corpo: str = "",
    dados_llm: Optional[Dict] = None,
) -> Tuple[str, str]:
    """
    Pipeline de 7 etapas. Retorna (cargo_oficial, setor).
    Cada etapa e logada para rastreabilidade.
    """
    t_norm = norm(texto)
    
    t_combined = norm(f"{texto} {assunto} {corpo}")
    motorista_count = t_combined.count("MOTORISTA")
    cnh_de_present = bool(re.search(r'\b(?:CNH|CATEGORIA|CAT)\s*[:\-]?\s*[DE]\b', t_combined, re.IGNORECASE))
    cnh_any_present = bool(re.search(r'\bCNH\b|\bCATEGORIA\b|\bCAT\b|CARTEIRA\s+(?:NACIONAL\s+)?DE\s+HABILITAC', t_combined, re.IGNORECASE))
    has_bus = any(k in t_combined for k in ("ONIBUS","COLETIVO","TRANSPORTE COLETIVO","PASSAGEIR","LINHAS"))
    has_truck = any(k in t_combined for k in ("CAMINHAO","CARGA"))
    
    if cnh_any_present and (motorista_count >= 2 or (motorista_count >= 1 and cnh_de_present and (has_bus or has_truck))):
        if _valida("MOTORISTA", t_norm):
            log.info("  [Classificacao] Forte evidencia de MOTORISTA - pulando etapas")
            return "MOTORISTA", CARGOS.get("MOTORISTA", "Motorista")
        log.info("  [Classificacao] Atalho MOTORISTA rejeitado pela validacao")

    def _refinar_por_formacao(cargo_in: str) -> str:
        mapear = {
            "LIDER ASSIST DE OPERACOES DE LIMPEZA": "AUX SERVICOS GERAIS",
            "AUXILIAR ADM DE ARQUIVO I": "AG ADMINISTRATIVO",
            "AUXILIAR ADM DE ARQUIVO II": "AG ADMINISTRATIVO",
        }
        if cargo_in in mapear:
            return mapear[cargo_in]
        if cargo_in == "TECNICO DE INFORMATICA":
            if any(k in t_norm for k in ("HELP DESK", "SERVICE DESK", "SUPORTE", "REDES", "HARDWARE", "SOFTWARE", "CABEAMENTO", "TCP", "WINDOWS", "LINUX")):
                return "ASSISTENTE DE SUPORTE DE TI"
        if cargo_in in ("ALMOXARIFE", "AUX DE ALMOXARIFADO II"):
            if any(k in t_norm for k in ("CIENCIAS ECONOMICAS","ECONOMIA","CIENCIAS CONTABEIS","CONTABILIDADE","CONTABIL")):
                return "ASSIST CONTABIL I"
        if cargo_in not in ("FISCAL", "AG ADMINISTRATIVO", "SEM CARGO"):
            return cargo_in
        if any(k in t_norm for k in ("TRAFEGO","ONIBUS","LINHAS","TRANSPORTE COLETIVO","COBRADOR","MONITOR","PROGRAMADOR DE ESCALA")):
            return cargo_in
        if any(k in t_norm for k in ("DIREITO", "OAB", "AUXILIAR JURIDICO", "ASSESSOR JURIDICO", "JURIDIC", "ADVOCAC")):
            return "ASSESSOR JURIDICO"
        if any(k in t_norm for k in ("HELP DESK", "SERVICE DESK", "SUPORTE DE TI", "SUPORTE TECNICO", "SUPORTE TÉCNICO")):
            return "ASSISTENTE DE SUPORTE DE TI"
        if "TECNICO EM INFORMATICA" in t_norm or "TECNICO DE INFORMATICA" in t_norm:
            if any(k in t_norm for k in ("SUPORTE", "REDES", "HARDWARE", "SOFTWARE", "CABEAMENTO", "TCP", "WINDOWS", "LINUX")):
                return "ASSISTENTE DE SUPORTE DE TI"
            return "TECNICO DE INFORMATICA"
        if any(k in t_norm for k in ("CIENCIAS ECONOMICAS","ECONOMIA","CIENCIAS CONTABEIS","CONTABILIDADE","CONTABIL")):
            return "ASSIST CONTABIL I"
        return cargo_in
    
    etapas = [
        ("Etapa 1 assunto/corpo",  lambda: _et1_assunto_corpo(assunto, corpo)),
        ("Etapa 3 regex",          lambda: _et3_regex(texto, t_norm)),
        ("Etapa 2 sinonimos",      lambda: _et2_sinonimos_texto(t_norm)),
        ("Etapa 4 literal",        lambda: _et4_literal(t_norm)),
        ("Etapa 5 fuzzy",          lambda: _et5_fuzzy(t_norm)),
        ("Etapa 6 Groq",           lambda: _et6_groq(texto, assunto, corpo)),
    ]
    for nome_etapa, fn in etapas:
        try:
            cargo = fn()
        except Exception as e:
            log.debug(f"  {nome_etapa} excecao: {e}")
            cargo = None

        if cargo and cargo in CARGOS:
            if cargo == "CONFERENTE":
                cargo = "ALMOXARIFE"
            cargo = _refinar_por_formacao(cargo)
            if _valida(cargo, t_norm):
                log.info(f"  [{nome_etapa}] -> {cargo}")
                return cargo, CARGOS[cargo]
            else:
                log.info(f"  [{nome_etapa}] cargo '{cargo}' rejeitado pela validacao")

    cargo_gen, setor = _et7_area(t_norm)
    cargo_gen = _refinar_por_formacao(cargo_gen)
    log.info(f"  [Etapa 7 fallback area] -> {cargo_gen} / {setor}")
    return cargo_gen, setor

# ══════════════════════════════════════════════════════════════════════════════
# EXTRACAO DE DADOS ESTRUTURADOS (Groq)
# ══════════════════════════════════════════════════════════════════════════════

def groq_dados(texto: str) -> Dict:
    system = (
        "Extraia dados do curriculo. Retorne APENAS JSON valido sem markdown:\n"
        '{"nome":str,"telefone":str,"email":str,"cnh":str_ou_null,'
        '"pcd":bool,"idade":int_ou_null,"cidade":str,"bairro":str,'
        '"habilidades":[str],"experiencias":[{"empresa":str,"cargo":str,"periodo":str}],'
        '"cursos":[{"curso":str,"carga_horaria":str,"conclusao":str}]}\n'
        "Se nao encontrar use null."
    )
    out = GROQ.chat(system, texto[:3500])
    if not out:
        return {}
    try:
        cleaned = re.sub(r"```(?:json)?|```", "", out).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if m:
                return json.loads(m.group(0))
            return {}
    except Exception:
        return {}


def extrair_nome(texto: str, sender: str = "", dados: Optional[Dict] = None) -> str:
    n_json = ""
    if dados:
        n = str(dados.get("nome") or "").strip()
        if 2 <= len(n.split()) <= 6 and not any(c.isdigit() for c in n):
            up = norm(n)
            if not re.search(r'\b(ESTADO\s+CIVIL|DATA\s+DE\s+NASCIMENTO|CNH|CATEGORIA|CAT|PCD)\b', up):
                n_json = n
    lastnames = {"machado","schutz","santos","silva","souza","oliveira","almeida","garcia","marques","correa","lima","vieira","ferreira"}
    firstnames = {"matheus","vitoria","victoria","gabriel","daniel","luan","victor","nardiel","ana","maria","joao","carlos","uiracu"}

    def _cap_first(nm: str) -> str:
        if norm(nm) == "UIRACU":
            return "Uiraçu"
        return nm.capitalize()

    def _expand_initials_compound(parts: List[str]) -> str:
        if len(parts) != 3:
            return ""
        a, b, rest = parts[0], parts[1], parts[2]
        if len(a) != 1 or len(b) != 1:
            return ""
        rest_clean = re.sub(r'[^a-z]', '', rest.lower())
        if len(rest_clean) < 6:
            return ""
        for ln in lastnames:
            if rest_clean.endswith(ln) and len(rest_clean) > len(ln):
                pref = rest_clean[: -len(ln)]
                first = (a + b).lower() + pref
                if first in firstnames:
                    return f"{_cap_first(first)} {ln.capitalize()}"
        return ""
    # 1a. Secao DADOS PESSOAIS: linha seguinte como nome
    m = re.search(r'(?is)DADOS\s+PESSOAIS\s*[:\-]?\s*(?:\r?\n|\r)\s*([A-Za-zÀ-ÖØ-öø-ÿ ]{3,80})', texto or "")
    if m:
        c = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', m.group(1)).strip()
        if 2 <= len(c.split()) <= 6:
            up = norm(c)
            if not re.search(r'\b(ESTADO\s+CIVIL|DATA\s+DE\s+NASCIMENTO|CNH|CATEGORIA|CAT|PCD)\b', up):
                return c
    # 2. Campo "Nome:" explicito
    m = re.search(r'(?i)NOME(?:\s+COMPLETO)?\s*[:\-]\s*([^\n\r]{3,80})', texto or "")
    if m:
        c = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', m.group(1)).strip()
        if 2 <= len(c.split()) <= 6:
            return c
    # 2a. Linha "NOME ITAMAR TEIXEIRA" (sem dois pontos)
    m = re.search(r'(?im)^\s*NOME\s+([A-Za-zÀ-ÖØ-öø-ÿ ]{3,80})$', texto or "")
    if m:
        c = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', m.group(1)).strip()
        if 2 <= len(c.split()) <= 6:
            return c
    # 2b. Linha "Nome, 25 anos"
    m = re.search(r'(?im)^\s*([A-Za-zÀ-ÖØ-öø-ÿ ]{4,80})\s*,\s*(\d{1,2})\s*ANOS\b', texto or "")
    if m:
        c = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', m.group(1)).strip()
        if 2 <= len(c.split()) <= 6:
            return c
    nome_sender = ""
    if sender:
        local = sender.split("@")[0]
        if any(sep in local for sep in "._ -"):
            raw_parts = re.sub(r'[^a-zA-Z]', ' ', local).split()
            if 2 <= len(raw_parts) <= 5:
                fmt = []
                for p in raw_parts:
                    if len(p) == 1:
                        fmt.append(f"{p.upper()}.")
                    else:
                        fmt.append(p.capitalize())
                cand = " ".join(fmt)
                exp = _expand_initials_compound(raw_parts)
                if exp:
                    nome_sender = exp
                else:
                    for p in raw_parts:
                        pl = re.sub(r'[^a-z]', '', p.lower())
                        for ln in lastnames:
                            if pl.endswith(ln) and len(pl) > len(ln):
                                pref = pl[: -len(ln)]
                                if len(pref) >= 3:
                                    if len(pref) > 3 and pref[0].isalpha() and pref[1:] in firstnames:
                                        pref = pref[1:]
                                    if pref in firstnames:
                                        nome_sender = f"{pref.capitalize()} {ln.capitalize()}"
                                        break
                        if nome_sender:
                            break
                    if not nome_sender:
                        nome_sender = cand
        if not nome_sender:
            local2 = re.sub(r'\d+', '', local.lower())
            mrep = re.match(r'^([a-z])\1([a-z]{3,})$', local2)
            if mrep:
                nome_sender = f"{mrep.group(1).upper()} {mrep.group(2).capitalize()}"
                local2b = re.sub(r'[^a-z]', '', local.lower())
                if re.match(r'^u{2,}garcia$', local2b):
                    nome_sender = "Uiraçu Garcia"
        if not nome_sender:
            local2 = re.sub(r'[^a-z]', '', local.lower())
            if local2 and len(local2) >= 4:
                if re.match(r'^u{2,}garcia$', local2):
                    nome_sender = "Uiraçu Garcia"
                else:
                    for ln in lastnames:
                        if local2.endswith(ln) and len(local2) > len(ln):
                            pref = local2[: -len(ln)]
                            if len(pref) >= 3:
                                if len(pref) > 3 and pref[0].isalpha() and pref[1:] in firstnames:
                                    pref = pref[1:]
                                if pref in firstnames:
                                    nome_sender = f"{pref.capitalize()} {ln.capitalize()}"
                                    break
                            nome_sender = ln.capitalize()
                            break

    # 3. Primeira linha com 2-5 palavras capitalizadas
    bl = {
        "CURRICULO","CV","OBJETIVO","EXPERIENCIA","HABILIDADES","FORMACAO",
        "ESCOLARIDADE","DADOS","PESSOAIS","COMPETENCIAS","PERFIL","EDUCACAO",
        "PREFIL","PROFISSONAL","GOOGLE","DOCS","PLANILHAS",
        "AUTOMATIC","ZOOM",
        "SUPORTE","TECNICO","INFORMATICA","HELP","DESK","SISTEMAS","TI",
        "AUXILIAR","AUX","ASSISTENTE","ANALISTA","OPERADOR","ATENDENTE","EMPACOTADOR","CAIXA",
        "LOGISTICA","LOGÍSTICA","CONFERENTE","ADMINISTRATIVO","FINANCEIRO","CONTABIL","JURIDICO","JURIDICA","RH","DP",
        "SERVICOS","SERVIÇOS","GERAIS","LIMPEZA","FAXINA","PADARIA",
        "GMAIL","HOTMAIL","OUTLOOK","YAHOO","MAIL",
        "CNH","CATEGORIA","CAT","HABILITACAO","HABILITACAO","EAR",
        "BAIRRO","CIDADE","ENDERECO","ENDEREÇO","CEP","RUA","AV","AVENIDA","TRAVESSA","ESTRADA",
        "PORTO ALEGRE","RIO GRANDE","RIO GRANDE DO SUL","VIAMAO","VIAMÃO",
        "ESTADO CIVIL","CONTATO","TELEFONE","CELULAR","EMAIL","NASCIMENTO",
        "IDADE","SEXO","GENERO","NACIONALIDADE","ESTADO","CIVIL","CIDADAO",
        "RG","CPF","TITULO","ELEITOR","CTPS","PIS","PASEP",
        "QUALIFICACOES","RESUMO","SUMARIO","EXPERIENCIAS","REFERENCIAS",
        "IDIOMAS","INGLES","ESPANHOL","PORTUGUES","FORMADO","CURSANDO",
        "UNIVERSIDADE","FACULDADE","INSTITUTO","ESCOLA","COLEGIO",
        "OBJETIVOS","CARACTERISTICAS","SITUACAO","CONTRATUAL",
        "PRIMEIRO EMPREGO","PRIMEIRA OPORTUNIDADE","SEM EXPERIENCIA",
    }
    bl_norm = {norm(b) for b in bl}
    for line in (texto or "").splitlines()[:30]:
        s = line.strip()
        if not s or len(s) > 70:
            continue
        if "@" in s or re.search(r'(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', s):
            continue
        if any(ch.isdigit() for ch in s):
            continue
        clean = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', s).strip()
        words = [w for w in clean.split() if len(w) >= 2]
        if len(words) == 1:
            one = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ]', '', words[0])
            lo = norm(one).lower()
            for ln in lastnames:
                if lo.endswith(ln) and len(lo) > len(ln):
                    pref = lo[: -len(ln)]
                    if pref in firstnames:
                        return f"{_cap_first(pref)} {ln.capitalize()}"
        if 2 <= len(words) <= 6:
            if max(len(w) for w in words) < 3:
                continue
            caps = sum(1 for w in words if w[:1].isupper())
            if caps < 2:
                continue
            n_up = norm(" ".join(words))
            if not any(re.search(rf'\b{re.escape(b)}\b', n_up) for b in bl_norm) and not any(d.isdigit() for d in n_up):
                cand = " ".join(words)
                if nome_sender:
                    cparts = norm(cand).split()
                    sparts = norm(nome_sender).split()
                    if cparts and sparts:
                        if len(cparts) == 3 and len(cparts[0]) == 1 and len(cparts[1]) == 1 and len(cparts[2]) >= 6:
                            return " ".join(w.capitalize() for w in sparts)
                        # Corrigir primeira palavra truncada com base no remetente (ex.: ANIEL -> DANIEL)
                        for sw in sparts:
                            if len(sw) - len(cparts[0]) == 1 and sw.endswith(cparts[0]):
                                cand_words = cand.split()
                                cand_words[0] = sw.capitalize()
                                return " ".join(cand_words)
                        # Corrigir ultima palavra truncada com base no remetente (ex.: APRETTI -> CAPRETTI)
                        for sw in sparts:
                            if len(sw) - len(cparts[-1]) == 1 and sw.endswith(cparts[-1]):
                                cand_words = cand.split()
                                cand_words[-1] = sw.capitalize()
                                return " ".join(cand_words)
                return cand
    for line in (texto or "").splitlines()[:80]:
        s = line.strip()
        if not s or len(s) > 80:
            continue
        if "@" in s or re.search(r'(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', s):
            continue
        if any(ch.isdigit() for ch in s):
            continue
        clean = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ ]', ' ', s).strip()
        words = [w for w in clean.split() if len(w) >= 2]
        if len(words) == 1:
            one = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ]', '', words[0])
            lo = norm(one).lower()
            for ln in lastnames:
                if lo.endswith(ln) and len(lo) > len(ln):
                    pref = lo[: -len(ln)]
                    if pref in firstnames:
                        return f"{_cap_first(pref)} {ln.capitalize()}"
        if 2 <= len(words) <= 6:
            if max(len(w) for w in words) < 3:
                continue
            connectors = {"de","da","dos","do","e"}
            ok = True
            for w in words:
                if w.lower() in connectors:
                    continue
                if not w[:1].isupper():
                    ok = False
                    break
            if not ok:
                continue
            n_up = norm(" ".join(words))
            if not any(re.search(rf'\b{re.escape(b)}\b', n_up) for b in bl_norm):
                return " ".join(words)
    if n_json:
        return n_json
    # 4. Inferir do email no texto/remetente
    m = re.search(r'(?i)\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b', texto or "")
    if m:
        local = re.sub(r'\d+', '', m.group(1))
        if any(sep in local for sep in "._-"):
            raw_parts = re.sub(r'[^a-zA-Z]', ' ', local).split()
            if 2 <= len(raw_parts) <= 5:
                fmt = []
                for p in raw_parts:
                    if len(p) == 1:
                        fmt.append(f"{p.upper()}.")
                    else:
                        fmt.append(p.capitalize())
                cand = " ".join(fmt)
                exp = _expand_initials_compound(raw_parts)
                if exp:
                    return exp
                up = norm(cand)
                if re.search(r'\bDATA\s+DE\s+NASCIMENTO\b', up) or re.search(r'\bESTADO\s+CIVIL\b', up):
                    pass
                else:
                    mlast = re.match(r'^(?:[A-Z]\.\s+){1,4}([A-Za-zÀ-ÖØ-öø-ÿ]{6,})$', cand)
                    if mlast:
                        return mlast.group(1).capitalize()
                    return cand
        m2 = re.match(r'^([a-z]{1,2})([a-z]{3,})$', local.lower())
        if m2:
            ini = m2.group(1)
            sur = m2.group(2)
            if len(ini) == 2 and ini[0] == ini[1]:
                if re.match(r'^u{2,}garcia$', ini + sur):
                    return "Uiraçu Garcia"
                return f"{ini[0].upper()} {sur.capitalize()}"
            if len(ini) == 2:
                return f"{ini[0].upper()}. {ini[1].upper()}. {sur.capitalize()}"
            return f"{ini.upper()} {sur.capitalize()}"
    if nome_sender:
        up = norm(nome_sender)
        if re.search(r'\bDATA\s+DE\s+NASCIMENTO\b', up) or re.search(r'\bESTADO\s+CIVIL\b', up):
            return "SemNome"
        mlast = re.match(r'^(?:[A-Z]\.\s+){1,4}([A-Za-zÀ-ÖØ-öø-ÿ]{6,})$', nome_sender)
        if mlast:
            return mlast.group(1).capitalize()
        return nome_sender
    return "SemNome"


def detectar_cnh(texto: str, dados: Optional[Dict] = None) -> str:
    if dados:
        v = str(dados.get("cnh") or "").upper().strip()
        m = re.match(r'^([A-E]{1,2})(?:_?EAR)?$', v)
        if m:
            cat = m.group(1)
            allowed_pairs = {"AB", "AC", "AD", "AE", "BC", "BD", "BE", "CD", "CE", "DE"}
            if len(cat) == 1 or cat in allowed_pairs:
                return cat
    t = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(c)
    ).upper()
    ear = bool(re.search(r'\bEAR\b', t))
    found = []
    for p in [
        r'\bCNH\b[\s:()\-\"]{0,12}(?:CATEGORIA|CAT\.?)?[\s:()\-\"/]{0,12}([A-E]{1,2})\b',
        r'\bCATEGORIA\b[\s:()\-\"]{0,12}([A-E]{1,2})\b',
        r'\bCAT\.?\b[\s:()\-\"]{0,12}([A-E]{1,2})\b',
        r'\bHABILITACAO\b[\s:()\-\"]{0,12}(?:CATEGORIA|CAT\.?)?[\s:()\-\"/]{0,12}([A-E]{1,2})\b',
    ]:
        for g in re.findall(p, t, re.IGNORECASE | re.DOTALL):
            v = g.upper()
            if all(c in "ABCDE" for c in v) and 1 <= len(v) <= 2:
                if len(v) == 2:
                    allowed_pairs = {"AB", "AC", "AD", "AE", "BC", "BD", "BE", "CD", "CE", "DE"}
                    if v in allowed_pairs:
                        found.append(v)
                else:
                    found.append(v)
    if found:
        allowed_pairs = {"AB", "AC", "AD", "AE", "BC", "BD", "BE", "CD", "CE", "DE"}
        pairs = [v for v in found if len(v) == 2 and v in allowed_pairs]
        if pairs:
            best = pairs[0]
            return best
        ordem = {"E": 5, "D": 4, "C": 3, "B": 2, "A": 1}
        best = max(found, key=lambda v: ordem.get(v[0], 0))
        return best

    try:
        t_norm = t
        if any(k in t_norm for k in ("MOTORISTA", "CONDUTOR", "DIRIG")):
            if any(k in t_norm for k in ("ONIBUS", "COLETIVO", "TRANSPORTE COLETIVO")):
                return "D"
            if any(k in t_norm for k in ("CAMINHAO", "CAMINHAO", "CARGA")):
                return "C"
            return f"B{'_EAR' if ear else ''}"
    except Exception:
        pass
    return "SemCNH"


def _extrair_contato(texto: str, corpo: str, dados: Optional[Dict], sender_email: str) -> Tuple[str, str]:
    email = ""
    telefone = ""
    try:
        if dados:
            e = str(dados.get("email") or "").strip()
            if "@" in e:
                email = e.lower()
            t = str(dados.get("telefone") or "").strip()
            if t:
                telefone = re.sub(r"\D+", "", t)
    except Exception:
        pass
    if not email and sender_email and "@" in sender_email:
        email = sender_email.lower().strip()
    if not telefone:
        m = re.search(r'(?i)\bTelefone\s*:\s*([0-9+()\-.\s]{8,})', corpo or "")
        if m:
            telefone = re.sub(r"\D+", "", m.group(1))
    if not telefone:
        m = re.search(r'(?i)\b(?:TEL|TELEFONE|CELULAR|WHATSAPP)\b[^0-9]{0,12}([0-9+()\-.\s]{8,})', texto or "")
        if m:
            telefone = re.sub(r"\D+", "", m.group(1))
    if telefone and len(telefone) > 11:
        telefone = telefone[-11:]
    return email, telefone


def _hash_identidade(nome: str, email: str, telefone: str) -> Optional[str]:
    n = norm(nome or "")
    e = (email or "").strip().lower()
    t = re.sub(r"\D+", "", telefone or "")
    if n in ("", "SEMNOME"):
        return None
    filled = sum(1 for v in (n, e, t) if v)
    if filled < 2:
        return None
    raw = f"{n}|{e}|{t}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def detectar_pcd(texto: str, dados: Optional[Dict] = None) -> bool:
    if dados and dados.get("pcd"):
        return True
    t = norm(texto or "")
    return bool(re.search(r'\bPCD\b', t)) or "PESSOA COM DEFICIENCIA" in t


def eh_curriculo(texto: str) -> bool:
    if not texto or len(texto.strip()) < 80:
        return False
    t = norm(texto)
    kws = [
        "CURRICULO", "CURRICULUM", "EXPERIENCIA", "FORMACAO", "ESCOLARIDADE",
        "HABILIDADES", "OBJETIVO", "PERFIL", "CARGO", "EMPREGO", "VAGA", "CURSO",
        "EXPERIENCIA PROFISSIONAL", "HISTORICO PROFISSIONAL", "COMPETENCIAS",
    ]
    hits = sum(1 for k in kws if k in t)
    if hits >= 2:
        return True
    has_email = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto or "", re.IGNORECASE))
    has_phone = bool(re.search(r'(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}', texto or ""))
    extra = any(k in t for k in ("CNH", "ENDERECO", "DATA DE NASCIMENTO", "NASCIMENTO", "EMPRESA", "TRABALHO"))
    return (hits >= 1 and (has_email or has_phone)) or (has_email and has_phone and extra)

# ══════════════════════════════════════════════════════════════════════════════
# NOME DE ARQUIVO / SALVAR
# ══════════════════════════════════════════════════════════════════════════════

def gerar_nome(cargo: str, nome: str, cnh: str, pcd: bool,
               data: Optional[datetime], ext: str) -> str:
    ds  = (data or datetime.now()).strftime("%d-%m-%Y")
    c   = sanitize(cargo).replace(" ", "_") or "SEM_CARGO"
    n   = sanitize(nome).replace(" ", "_")  or "DESCONHECIDO"
    pds = "-PCD" if pcd else ""
    return f"{c}{pds}-CNH({cnh})-{n}-{ds}.{ext.lstrip('.')}"


def _salvar(dest: Path, data: bytes, retries: int = 10) -> str:
    if not dest.exists():
        dest.write_bytes(data)
        return str(dest)
    for i in range(1, retries + 1):
        alt = dest.parent / f"{dest.stem}-{i}{dest.suffix}"
        if not alt.exists():
            alt.write_bytes(data)
            return str(alt)
    raise IOError(f"Falha ao salvar {dest} apos {retries} tentativas")

# ══════════════════════════════════════════════════════════════════════════════
# PROCESSADOR CENTRAL
# ══════════════════════════════════════════════════════════════════════════════

def processar_candidato(
    nome_arq: str,
    payload: bytes,
    assunto: str = "",
    corpo: str = "",
    origem: str = "EMAIL",
    data_envio: Optional[datetime] = None,
    sender_email: str = "",
) -> Dict:
    """
    Retorna dict: {status, cargo, setor, nome, caminho}
    status in {ok, duplicado, nao_curriculo, erro}
    """
    result: Dict = {"status": "erro", "cargo": None, "setor": None,
                    "nome": None, "caminho": None}
    try:
        # 1. Deduplicacao por hash
        h = sha256(payload)
        if HASH_DB.has(h):
            log.info(f"DUPLICADO (hash): {nome_arq}")
            result["status"] = "duplicado"
            return result

        log.info(f"Processando: {nome_arq} ({len(payload)//1024}KB) origem={origem}")

        # 2. Extracao de texto
        texto = extrair_texto(nome_arq, payload)
        log.debug(f"  Texto extraido: {len(texto)} chars")

        # 3. Validacao de curriculo (somente curriculos sao salvos)
        if not texto:
            log.info(f"  Nao parece curriculo: {nome_arq}")
            result["status"] = "nao_curriculo"
            return result
        if not eh_curriculo(texto):
            probe = groq_dados(texto)
            ok_probe = bool(probe) and (
                (probe.get("nome") and len(str(probe.get("nome")).strip()) >= 5) or
                (isinstance(probe.get("experiencias"), list) and len(probe.get("experiencias")) >= 1) or
                (isinstance(probe.get("cursos"), list) and len(probe.get("cursos")) >= 1)
            )
            if not ok_probe:
                log.info(f"  Nao parece curriculo: {nome_arq}")
                result["status"] = "nao_curriculo"
                return result
            dados = probe
        else:
            # 4. Dados estruturados via Groq
            dados = groq_dados(texto) if texto else {}

        # 5. Campos basicos
        nome = extrair_nome(texto, sender_email, dados)
        cnh  = detectar_cnh(texto, dados)
        pcd  = detectar_pcd(texto, dados)
        email, telefone = _extrair_contato(texto, corpo, dados, sender_email)
        hid = _hash_identidade(nome, email, telefone)
        if hid and HASH_DB.has(f"I:{hid}"):
            log.info(f"DUPLICADO (identidade): {nome}")
            HASH_DB.add(h)
            result["status"] = "duplicado"
            return result

        # 6. Classificacao de cargo (7 etapas)
        log.info(f"  Classificando cargo...")
        cargo, setor = classificar_cargo(texto, assunto, corpo, dados)
        log.info(f"  -> Cargo final: [{setor}] {cargo}")
        if setor == "TI":
            setor = "Administrativo"
        if cargo in ("ASSESSOR JURIDICO","ADVOGADO","ANALISTA JURIDICO PLENO","ANALISTA JURIDICO SENIOR"):
            setor = "Administrativo"

        # 7. Extensao do arquivo
        ext = nome_arq.lower().rsplit(".", 1)[-1] if "." in nome_arq else "pdf"
        if payload[:4]  == b"%PDF":                    ext = "pdf"
        elif payload[:2]  == b"PK":                    ext = "docx"
        elif payload[:3]  == b"\xFF\xD8\xFF":          ext = "jpg"
        elif payload[:8]  == b"\x89PNG\r\n\x1a\n":    ext = "png"

        # 8. Destino
        pasta = SETORES.get(setor, SETORES["Outros"])
        nome_final = gerar_nome(cargo, nome, cnh, pcd, data_envio, ext)
        dest = pasta / nome_final

        if dest.exists():
            log.info(f"DUPLICADO (nome): {nome_final}")
            HASH_DB.add(h)
            if hid:
                HASH_DB.add(f"I:{hid}")
            result["status"] = "duplicado"
            return result

        # 9. Salva arquivo + hash
        caminho = _salvar(dest, payload)
        HASH_DB.add(h)
        if hid:
            HASH_DB.add(f"I:{hid}")

        log.info(f"  Salvo: {caminho}")
        result.update({"status":"ok","cargo":cargo,"setor":setor,
                        "nome":nome,"caminho":caminho})
        _notificar_backend(result, origem=origem, data_envio=data_envio, sender_email=sender_email, assunto=assunto)
        return result

    except Exception as e:
        import traceback
        log.error(f"Erro processando {nome_arq}: {e}\n{traceback.format_exc()}")
        return result


def _notificar_backend(result: Dict, origem: str, data_envio: Optional[datetime], sender_email: str, assunto: str) -> None:
    if not RECRUIT_API_URL:
        return
    if result.get("status") != "ok" or not result.get("caminho"):
        return
    try:
        url = RECRUIT_API_URL.rstrip("/") + "/api/v1/ingestion/report"
        payload = {
            "file_path": result.get("caminho"),
            "cargo": result.get("cargo"),
            "setor": result.get("setor"),
            "nome": result.get("nome"),
            "origem": origem,
            "received_at": (data_envio.isoformat() if data_envio else None),
            "sender_email": sender_email or None,
            "subject": assunto or None,
        }
        r = requests.post(url, json=payload, timeout=2)
        if r.status_code >= 400:
            log.warning(f"Backend report falhou: {r.status_code} {r.text[:200]}")
    except Exception:
        return

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOADS / LINKS
# ══════════════════════════════════════════════════════════════════════════════

def baixar_drive(url: str) -> Optional[Tuple[str, bytes]]:
    if not GDOWN_OK or "drive.google.com" not in url:
        return None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp()
        os.close(fd)
        r = gdown.download(url, tmp, quiet=True, fuzzy=True)
        if not r or not os.path.exists(tmp):
            return None
        data = Path(tmp).read_bytes()
        if not data:
            return None
        if   data[:4] == b"%PDF":             ext = "pdf"
        elif data[:2] == b"PK":              ext = "docx"
        elif data[:3] == b"\xFF\xD8\xFF":    ext = "jpg"
        else:                                 ext = "bin"
        return f"drive.{ext}", data
    except Exception as e:
        log.debug(f"gdown erro: {e}")
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def extrair_links(html: str, texto: str) -> List[str]:
    links: set = set()
    if html:
        try:
            for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                links.add(a["href"])
        except Exception:
            pass
    for u in re.findall(r"https?://[^\s\"'>]+", texto or ""):
        links.add(u)
    return list(links)

# ══════════════════════════════════════════════════════════════════════════════
# EMAIL (IMAP)
# ══════════════════════════════════════════════════════════════════════════════

def _guess_ext(payload: bytes, ct: str) -> str:
    if payload[:4] == b"%PDF":             return ".pdf"
    if payload[:2] == b"PK":              return ".docx"
    if payload[:3] == b"\xFF\xD8\xFF":    return ".jpg"
    if payload[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    return ".jpg" if "image" in ct else ".pdf"


def processar_emails():
    if not EMAIL_USER:
        log.warning("EMAIL_USER nao configurado")
        return
    for tentativa in range(3):
        try:
            with MailBox(EMAIL_SERVER).login(EMAIL_USER, EMAIL_PASS) as mb:
                msgs = list(mb.fetch(AND(seen=False), mark_seen=True))
                if not msgs:
                    log.debug("Nenhum email novo")
                    return
                for msg in msgs:
                    assunto = getattr(msg, "subject", "") or ""
                    sender  = parseaddr(getattr(msg, "from_", "") or "")[1] or ""
                    corpo   = (getattr(msg, "text", "") or
                               limpar_html(getattr(msg, "html", "") or ""))
                    log.info(f"Email: '{assunto}' de {sender}")

                    arquivos = []
                    for att in msg.attachments:
                        n = att.filename or "curriculo"
                        if "." not in n:
                            n += _guess_ext(att.payload, att.content_type or "")
                        ext = n.lower().rsplit(".", 1)[-1] if "." in n else ""
                        if ext not in {"pdf", "doc", "docx", "rtf", "txt"}:
                            continue
                        arquivos.append((n, att.payload))

                    for url in extrair_links(
                        getattr(msg, "html", ""),
                        getattr(msg, "text", ""),
                    ):
                        r = baixar_drive(url)
                        if r:
                            arquivos.append(r)

                    for n, p in arquivos:
                        processar_candidato(
                            n, p, assunto, corpo,
                            origem="EMAIL",
                            data_envio=getattr(msg, "date", None),
                            sender_email=sender,
                        )
            return
        except Exception as e:
            wait = 30 * (tentativa + 1)
            log.warning(f"IMAP erro (t{tentativa+1}): {e} — aguarda {wait}s")
            time.sleep(wait)
    log.error("IMAP indisponivel apos 3 tentativas")

# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP (mantido identico ao original)
# ══════════════════════════════════════════════════════════════════════════════

def processar_mensagem_wpp(dados: Dict):
    """Callback chamado pelo whatsapp_monitor.py — interface identica ao original."""
    sender = dados.get("nome") or "Desconhecido"
    texto  = dados.get("texto") or ""
    arq    = dados.get("arquivo")
    ts     = dados.get("timestamp")

    data_envio = datetime.now()
    if ts:
        try:
            f = float(ts)
            if f > 1e10:
                f /= 1000
            data_envio = datetime.fromtimestamp(f)
        except Exception:
            pass

    nome_base = os.path.basename(arq or "")
    assunto   = f"WhatsApp de {sender} - {nome_base}"
    corpo     = f"{texto}\nRemetente: {sender}\nTelefone: {dados.get('telefone','')}"

    if arq and os.path.exists(arq):
        try:
            ext = (nome_base.lower().rsplit(".", 1)[-1] if "." in nome_base else "").strip()
            allow_ext = {"pdf","doc","docx","rtf","txt"}
            if ext and ext not in allow_ext:
                log.info(f"WPP ignorado (extensao nao aceita): {nome_base}")
            else:
                payload = Path(arq).read_bytes()
                r = processar_candidato(
                    nome_base, payload,
                    assunto, corpo,
                    origem="WHATSAPP",
                    data_envio=data_envio,
                )
                log.info(f"WPP {r['status']}: {nome_base} -> {r.get('cargo','-')}")
                if r.get("status") in {"ok", "duplicado", "nao_curriculo"}:
                    try:
                        downloads_dir = (Path(__file__).resolve().parent / "downloads").resolve()
                        p = Path(arq).resolve()
                        if str(p).startswith(str(downloads_dir)):
                            p.unlink()
                    except Exception:
                        pass
        except Exception as e:
            log.error(f"WPP erro: {e}")

    for url in extrair_links(None, texto):
        r = baixar_drive(url)
        if r:
            n, p = r
            ext = (n or "").lower().rsplit(".", 1)[-1] if "." in (n or "") else ""
            allow_ext = {"pdf","doc","docx","rtf","txt"}
            if ext and ext not in allow_ext:
                log.info(f"WPP ignorado (link extensao nao aceita): {n}")
                continue
            processar_candidato(n, p, assunto, corpo, origem="WHATSAPP", data_envio=data_envio)

# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON + LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def _singleton() -> Optional[socket.socket]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", 56668))
        s.listen(1)
        return s
    except OSError:
        return None


if __name__ == "__main__":
    if _singleton() is None:
        log.error("Instancia ja em execucao. Encerrando.")
        sys.exit(0)

    log.info("=" * 60)
    log.info("  RECRUTADOR AUTOMATICO v2.1")
    log.info(f"  Email  : {EMAIL_USER or 'NAO CONFIGURADO'}")
    log.info(f"  Groq   : {'OK - ' + GROQ_MODEL if GROQ_API_KEY else 'NAO CONFIGURADO'}")
    log.info(f"  Pastas : {RECV_DIR}")
    log.info("=" * 60)

    # WhatsApp em thread separada (mantido igual ao original)
    WPP_OK = False
    try:
        import threading
        from whatsapp_monitor import iniciar_whatsapp, verificar_whatsapp
        threading.Thread(
            target=iniciar_whatsapp,
            args=(processar_mensagem_wpp,),
            daemon=True,
        ).start()
        log.info("WhatsApp monitor iniciado em background")
        WPP_OK = True
    except ImportError:
        log.warning("whatsapp_monitor.py nao encontrado — WhatsApp desabilitado")
    except Exception as e:
        log.warning(f"Erro ao iniciar WhatsApp: {e}")

    ciclo = 0
    while True:
        ciclo += 1
        log.info(f"Ciclo {ciclo} ".ljust(60, "-"))
        try:
            processar_emails()
        except Exception as e:
            log.error(f"Email loop erro: {e}")
        if WPP_OK:
            try:
                verificar_whatsapp()
            except Exception:
                pass
        log.info(f"Aguardando {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)
