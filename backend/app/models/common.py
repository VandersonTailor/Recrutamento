import enum


class SourceChannel(str, enum.Enum):
    email = "email"
    whatsapp = "whatsapp"
    unknown = "unknown"


class ApplicationStage(str, enum.Enum):
    recebido = "Recebido"
    em_analise = "Em análise"
    pre_selecionado = "Pré-selecionado"
    entrevista = "Entrevista"
    teste_tecnico = "Teste técnico"
    banco_talentos = "Banco de talentos"
    aprovado = "Aprovado"
    reprovado = "Reprovado"


class SeniorityLevel(str, enum.Enum):
    junior = "Júnior"
    pleno = "Pleno"
    senior = "Sênior"
    indefinido = "Indefinido"
