import json
import re
from dataclasses import dataclass

from groq import Groq

from app.core.config import get_settings
from app.models.common import SeniorityLevel


@dataclass(frozen=True)
class ResumeAnalysis:
    nome: str | None
    telefone: str | None
    email: str | None
    experiencias: list[str]
    formacao: list[str]
    cursos: list[str]
    tecnologias: list[str]
    habilidades: list[str]
    tempo_experiencia_anos: float | None
    senioridade: str
    score_aderencia: float | None
    justificativa_score: str | None
    pontos_fortes: list[str]
    pontos_atencao: list[str]
    raw_json: dict


def analyze_resume(*, resume_text: str, job_title: str | None, job_description: str | None, job_requirements: str | None) -> ResumeAnalysis:
    settings = get_settings()
    provider = (settings.ai_provider or "disabled").lower()
    if provider == "groq" and settings.groq_api_key:
        return _analyze_with_groq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            resume_text=resume_text,
            job_title=job_title,
            job_description=job_description,
            job_requirements=job_requirements,
        )
    return _analyze_disabled(resume_text=resume_text, job_title=job_title)


def _analyze_with_groq(
    *,
    api_key: str,
    model: str,
    resume_text: str,
    job_title: str | None,
    job_description: str | None,
    job_requirements: str | None,
) -> ResumeAnalysis:
    client = Groq(api_key=api_key)

    prompt = _build_prompt(
        resume_text=resume_text,
        job_title=job_title,
        job_description=job_description,
        job_requirements=job_requirements,
    )

    completion = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": "Você é um analista de recrutamento e deve responder somente com JSON válido."},
            {"role": "user", "content": prompt},
        ],
    )

    content = completion.choices[0].message.content or ""
    data = _safe_json_load(content)
    return _to_analysis(data)


def _build_prompt(*, resume_text: str, job_title: str | None, job_description: str | None, job_requirements: str | None) -> str:
    return f"""
Tarefa: analisar currículo e gerar um JSON.

Regras:
- Retorne SOMENTE JSON válido (sem markdown, sem texto fora do JSON).
- Se não tiver certeza, use null ou lista vazia.
- score_aderencia deve ser número entre 0 e 100.
- senioridade deve ser um destes valores: "Júnior", "Pleno", "Sênior", "Indefinido".

Esquema JSON:
{{
  "nome": string|null,
  "telefone": string|null,
  "email": string|null,
  "experiencias": [string],
  "formacao": [string],
  "cursos": [string],
  "tecnologias": [string],
  "habilidades": [string],
  "tempo_experiencia_anos": number|null,
  "senioridade": "Júnior"|"Pleno"|"Sênior"|"Indefinido",
  "score_aderencia": number|null,
  "justificativa_score": string|null,
  "pontos_fortes": [string],
  "pontos_atencao": [string]
}}

Vaga:
- cargo: {job_title or ""}
- descricao: {job_description or ""}
- requisitos: {job_requirements or ""}

Currículo (texto extraído):
{resume_text[:20000]}
""".strip()


def _safe_json_load(content: str) -> dict:
    content = content.strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except Exception:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end >= 0 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except Exception:
            return {}
    return {}


def _to_analysis(data: dict) -> ResumeAnalysis:
    senioridade = str(data.get("senioridade") or SeniorityLevel.indefinido.value)
    if senioridade not in {
        SeniorityLevel.junior.value,
        SeniorityLevel.pleno.value,
        SeniorityLevel.senior.value,
        SeniorityLevel.indefinido.value,
    }:
        senioridade = SeniorityLevel.indefinido.value

    score = data.get("score_aderencia")
    if isinstance(score, int | float):
        score_val: float | None = float(score)
    else:
        score_val = None

    tempo = data.get("tempo_experiencia_anos")
    if isinstance(tempo, int | float):
        tempo_val: float | None = float(tempo)
    else:
        tempo_val = None

    return ResumeAnalysis(
        nome=_to_opt_str(data.get("nome")),
        telefone=_to_opt_str(data.get("telefone")),
        email=_to_opt_str(data.get("email")),
        experiencias=_to_list_str(data.get("experiencias")),
        formacao=_to_list_str(data.get("formacao")),
        cursos=_to_list_str(data.get("cursos")),
        tecnologias=_to_list_str(data.get("tecnologias")),
        habilidades=_to_list_str(data.get("habilidades")),
        tempo_experiencia_anos=tempo_val,
        senioridade=senioridade,
        score_aderencia=score_val,
        justificativa_score=_to_opt_str(data.get("justificativa_score")),
        pontos_fortes=_to_list_str(data.get("pontos_fortes")),
        pontos_atencao=_to_list_str(data.get("pontos_atencao")),
        raw_json=data,
    )


def _to_opt_str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _to_list_str(v: object) -> list[str]:
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            sx = str(x).strip()
            if sx:
                out.append(sx)
        return out
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _analyze_disabled(*, resume_text: str, job_title: str | None) -> ResumeAnalysis:
    email = None
    m_email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", resume_text or "", flags=re.IGNORECASE)
    if m_email:
        email = m_email.group(0)

    phone = None
    m_phone = re.search(r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", resume_text or "")
    if m_phone:
        phone = re.sub(r"\s+", " ", m_phone.group(0)).strip()

    nome = None
    if resume_text:
        first_line = (resume_text.splitlines() or [""])[0].strip()
        if 3 <= len(first_line) <= 80:
            nome = first_line

    score = None
    justificativa = None
    if job_title and resume_text:
        tokens = {t.lower() for t in re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", resume_text)}
        jt = {t.lower() for t in re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", job_title)}
        if jt:
            overlap = len(tokens.intersection(jt)) / max(1, len(jt))
            score = float(min(100.0, max(0.0, overlap * 100.0)))
            justificativa = "Score heurístico (MVP) por sobreposição de termos do cargo no currículo."

    return ResumeAnalysis(
        nome=nome,
        telefone=phone,
        email=email,
        experiencias=[],
        formacao=[],
        cursos=[],
        tecnologias=[],
        habilidades=[],
        tempo_experiencia_anos=None,
        senioridade=SeniorityLevel.indefinido.value,
        score_aderencia=score,
        justificativa_score=justificativa,
        pontos_fortes=[],
        pontos_atencao=[],
        raw_json={},
    )
