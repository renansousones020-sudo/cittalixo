from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json
import sqlite3
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cittalixo.db"

app = FastAPI(
    title="CittaLixo API - Recife & Olinda",
    description=(
        "API gratuita para consulta e gerenciamento de Ecopontos/Ecoestações "
        "e rotas/horários de coleta domiciliar em Recife e Olinda."
    ),
    version="3.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Modelos de dados (Pydantic)
class PontoBase(BaseModel):
    nome: str = Field(..., min_length=2, description="Nome do ecoponto ou rota de coleta")
    cidade: str = Field(default="Olinda", description="Cidade (Olinda ou Recife)")
    bairro: str = Field(default="Centro", description="Bairro do ponto ou rota")
    categoria: str = Field(
        default="Ecoponto",
        description="Categoria: 'Ecoponto' (ponto fixo) ou 'Coleta Domiciliar' (caminhão)",
    )
    tipo: str = Field(..., description="Tipos de resíduos aceitos (ex: Recicláveis, Eletrônicos, Entulho)")
    endereco: str = Field(..., description="Endereço ou ruas percorridas pelo caminhão")
    horario: str = Field(
        default="Seg a Sáb: 08h às 16h",
        description="Dias e horários de funcionamento ou passagem do caminhão",
    )
    dias_semana: str = Field(
        default="Seg,Ter,Qua,Qui,Sex,Sab",
        description="Dias da semana abreviados para verificação automática (Dom,Seg,Ter,Qua,Qui,Sex,Sab)",
    )
    hora_inicio: str = Field(default="08:00", description="Hora de início (HH:MM)")
    hora_fim: str = Field(default="16:00", description="Hora de término (HH:MM)")
    observacoes: str = Field(
        default="",
        description="Informações extras (limite de volume, regras de descarte, contato)",
    )
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude geográfica inicial")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude geográfica inicial")
    rota_coordenadas: List[List[float]] = Field(
        default_factory=list,
        description="Lista de coordenadas [[lat, lng], ...] seguindo o traçado real das ruas (OSRM/OpenStreetMap)",
    )


class PontoCreate(PontoBase):
    pass


class PontoResponse(PontoBase):
    id: int


# Modelos de Denúncias de Descarte Irregular / Ponto Crítico de Lixo
class DenunciaBase(BaseModel):
    titulo: str = Field(..., min_length=3, description="Título curto do problema (ex: Entulho acumulado na calçada)")
    cidade: str = Field(default="Olinda", description="Cidade (Olinda ou Recife)")
    bairro: str = Field(..., description="Bairro da ocorrência")
    endereco: str = Field(..., description="Endereço ou ponto de referência")
    tipo_residuo: str = Field(default="Entulho / Lixo Misto", description="Tipo de resíduo descartado irregularmente")
    gravidade: str = Field(default="Crítico", description="Nível: Moderado, Alto ou Crítico")
    descricao: str = Field(default="", description="Detalhes sobre o acúmulo de lixo")
    status: str = Field(default="Pendente", description="Status: 'Pendente' ou 'Resolvido'")
    data_registro: str = Field(default="Hoje", description="Data/hora do relato")
    confirmacoes: int = Field(default=1, ge=0, description="Quantidade de moradores que confirmaram ('Ainda está lá! +1')")
    nao_esta_mais: int = Field(default=0, ge=0, description="Quantidade de moradores que relataram que já foi limpo ('Não está mais lá')")
    ultimo_voto_ainda_la_em: str = Field(default="", description="Timestamp ISO do último voto 'Ainda está lá'")
    ultimo_voto_recolhido_em: str = Field(default="", description="Timestamp ISO do último voto 'Já foi recolhido'")
    foto_base64: str = Field(default="", description="Foto opcional comprimida em Base64")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class DenunciaCreate(DenunciaBase):
    pass


class DenunciaResponse(DenunciaBase):
    id: int


# Modelos de Agendamento de Coleta de Volumosos / Cata-Treco
class CataTrecoBase(BaseModel):
    solicitante: str = Field(..., min_length=2, description="Nome do morador solicitante")
    cidade: str = Field(default="Olinda", description="Cidade (Olinda ou Recife)")
    bairro: str = Field(..., description="Bairro da coleta")
    endereco: str = Field(..., description="Endereço completo para recolhimento na calçada")
    itens_volumosos: str = Field(..., description="Itens (ex: Sofá velho, Colchão, Geladeira, Restos de Poda)")
    turno_preferido: str = Field(default="Manhã (08h às 12h)", description="Turno preferido para retirada")
    data_agendada: str = Field(default="Próxima semana", description="Data solicitada")
    observacoes: str = Field(default="", description="Referência ou observações")
    status: str = Field(default="Agendado", description="Status: 'Agendado' ou 'Recolhido'")
    foto_base64: str = Field(default="", description="Foto opcional do item volumoso em Base64")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class CataTrecoCreate(CataTrecoBase):
    pass


class CataTrecoResponse(CataTrecoBase):
    id: int
    protocolo: str


CATATRECO_INICIAIS = [
    {
        "protocolo": "CT-2026-001",
        "solicitante": "Morador - Bairro Novo",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "endereco": "Rua Cândido Pessoa, 140 - Bairro Novo",
        "itens_volumosos": "1 Sofá de 3 lugares e 1 Colchão de casal",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Quinta-feira",
        "observacoes": "Deixado na calçada no início da manhã conforme orientação.",
        "status": "Agendado",
        "latitude": -8.0012,
        "longitude": -34.8428,
    },
    {
        "protocolo": "CT-2026-002",
        "solicitante": "Moradora - Casa Caiada",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "endereco": "Av. Carlos de Lima Cavalcanti, 920",
        "itens_volumosos": "Geladeira antiga inoperante e galhos de poda",
        "turno_preferido": "Tarde (13h às 17h)",
        "data_agendada": "Sexta-feira",
        "observacoes": "Próximo à padaria principal.",
        "status": "Agendado",
        "latitude": -7.9865,
        "longitude": -34.8415,
    },
    {
        "protocolo": "CT-2026-003",
        "solicitante": "Condomínio Boa Vista",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "endereco": "Rua da Imperatriz, 210 - Boa Vista",
        "itens_volumosos": "Armário de madeira desmontado e cadeiras quebradas",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Sábado",
        "observacoes": "Portaria avisa quando o caminhão Cata-Treco chegar.",
        "status": "Agendado",
        "latitude": -8.0602,
        "longitude": -34.8854,
    },
    {
        "protocolo": "CT-2026-004",
        "solicitante": "Morador - Ouro Preto",
        "cidade": "Olinda",
        "bairro": "Ouro Preto",
        "endereco": "Estrada de Ouro Preto, 410 - Ouro Preto",
        "itens_volumosos": "1 Guarda-roupa de 6 portas desmontado e 2 cadeiras",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Segunda-feira",
        "observacoes": "Em frente ao mercadinho local, madeira já amarrada.",
        "status": "Agendado",
        "latitude": -7.9935,
        "longitude": -34.8625
    },
    {
        "protocolo": "CT-2026-005",
        "solicitante": "Moradora - Rio Doce (2ª Etapa)",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "endereco": "Av. Brasil, 580 - Rio Doce",
        "itens_volumosos": "1 Fogão 4 bocas enferrujado e 1 Colchão de solteiro",
        "turno_preferido": "Tarde (13h às 17h)",
        "data_agendada": "Terça-feira",
        "observacoes": "Deixarei na calçada após as 12h30.",
        "status": "Agendado",
        "latitude": -7.9622,
        "longitude": -34.8395
    },
    {
        "protocolo": "CT-2026-006",
        "solicitante": "Morador - Peixinhos",
        "cidade": "Olinda",
        "bairro": "Peixinhos",
        "endereco": "Av. Presidente Kennedy, 1120 - Peixinhos",
        "itens_volumosos": "1 Poltrona rasgada e tábuas de cama antiga",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Quarta-feira",
        "observacoes": "Recolhimento concluído pela equipe municipal.",
        "status": "Recolhido",
        "latitude": -8.0135,
        "longitude": -34.868
    },
    {
        "protocolo": "CT-2026-007",
        "solicitante": "Edifício Mar de Boa Viagem",
        "cidade": "Recife",
        "bairro": "Boa Viagem",
        "endereco": "Av. Conselheiro Aguiar, 2350 - Boa Viagem",
        "itens_volumosos": "1 Sofá retrátil de 3 lugares e 1 Mesa de centro quebrada",
        "turno_preferido": "Tarde (13h às 17h)",
        "data_agendada": "Quinta-feira",
        "observacoes": "Zelador acompanha a retirada no recuo do prédio.",
        "status": "Agendado",
        "latitude": -8.118,
        "longitude": -34.899
    },
    {
        "protocolo": "CT-2026-008",
        "solicitante": "Moradora - Casa Amarela",
        "cidade": "Recife",
        "bairro": "Casa Amarela",
        "endereco": "Av. Norte Miguel Arraes, 3100 - Casa Amarela",
        "itens_volumosos": "1 Máquina de lavar inoperante e feixes de poda",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Sexta-feira",
        "observacoes": "Ao lado da parada de ônibus.",
        "status": "Agendado",
        "latitude": -8.0266,
        "longitude": -34.9181
    },
    {
        "protocolo": "CT-2026-009",
        "solicitante": "Morador - Torre",
        "cidade": "Recife",
        "bairro": "Torre",
        "endereco": "Rua Real da Torre, 690 - Torre",
        "itens_volumosos": "2 Colchões velhos e 1 Estante de MDF desmontada",
        "turno_preferido": "Tarde (13h às 17h)",
        "data_agendada": "Quarta-feira",
        "observacoes": "Retirado pela equipe da EMLURB.",
        "status": "Recolhido",
        "latitude": -8.0452,
        "longitude": -34.911
    },
    {
        "protocolo": "CT-2026-010",
        "solicitante": "Morador - Imbiribeira",
        "cidade": "Recife",
        "bairro": "Imbiribeira",
        "endereco": "Av. Mascarenhas de Morais, 1800 - Imbiribeira",
        "itens_volumosos": "1 Geladeira antiga sem motor e 3 caixotes de madeira",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Sábado",
        "observacoes": "Próximo à passarela.",
        "status": "Agendado",
        "latitude": -8.0965,
        "longitude": -34.9112
    },
]


DENUNCIAS_INICIAIS = [
    {
        "titulo": "Descarte irregular de entulho e móveis velhos",
        "cidade": "Olinda",
        "bairro": "Peixinhos",
        "endereco": "Esquina próx. à Av. Presidente Kennedy, Peixinhos",
        "tipo_residuo": "Entulho, Restos de Obra e Sofá Velho",
        "gravidade": "Crítico",
        "descricao": "Calçada obstruída por metralha e restos de madeira. Necessita recolhimento urgente.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "latitude": -8.0145,
        "longitude": -34.8662,
    },
    {
        "titulo": "Lixo domiciliar fora do horário na ladeira",
        "cidade": "Olinda",
        "bairro": "Varadouro",
        "endereco": "Próx. ao Mercado Eufrásio Barbosa",
        "tipo_residuo": "Sacolas plásticas e orgânicos",
        "gravidade": "Alto",
        "descricao": "Sacos rasgados acumulando água de chuva antes do horário do caminhão.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "latitude": -8.0182,
        "longitude": -34.8531,
    },
    {
        "titulo": "Ponto crítico de galhos de poda e plástico",
        "cidade": "Recife",
        "bairro": "Santo Amaro",
        "endereco": "Rua Araripina, Santo Amaro",
        "tipo_residuo": "Poda de árvore e recicláveis sujos",
        "gravidade": "Crítico",
        "descricao": "Descarte clandestino noturno próximo ao canal.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "latitude": -8.0492,
        "longitude": -34.8765,
    },
    {
        "titulo": "Metralha e restos de cerâmica descartados na esquina",
        "cidade": "Olinda",
        "bairro": "Ouro Preto",
        "endereco": "Rua Peixe Agulha, próx. à Cohab - Ouro Preto",
        "tipo_residuo": "Entulho de obra, tijolos e sacos plásticos",
        "gravidade": "Crítico",
        "descricao": "Descarte feito na madrugada obstruindo metade da passagem de pedestres.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 5,
        "nao_esta_mais": 1,
        "ultimo_voto_ainda_la_em": "2026-11-09T10:30:00",
        "ultimo_voto_recolhido_em": "2026-11-09T09:00:00",
        "latitude": -7.9948,
        "longitude": -34.8655
    },
    {
        "titulo": "Garrafas PET e sacolas acumuladas na margem do canal",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "endereco": "Av. Tiradentes, próx. à ponte do canal - Rio Doce",
        "tipo_residuo": "Plásticos, garrafas PET e isopor",
        "gravidade": "Crítico",
        "descricao": "Risco de entupimento da drenagem em dias de chuva forte.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 6,
        "nao_esta_mais": 0,
        "ultimo_voto_ainda_la_em": "2026-11-09T11:00:00",
        "ultimo_voto_recolhido_em": "",
        "latitude": -7.9642,
        "longitude": -34.8401
    },
    {
        "titulo": "Galhos de poda e colchão velho na calçada",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "endereco": "Rua Dr. Manoel de Barros Lima, próx. à Praça 12 de Março",
        "tipo_residuo": "Poda de árvore e volumoso",
        "gravidade": "Alto",
        "descricao": "Moradores relataram que o caminhão de coleta passou hoje pela manhã.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 2,
        "nao_esta_mais": 4,
        "ultimo_voto_ainda_la_em": "2026-11-08T14:00:00",
        "ultimo_voto_recolhido_em": "2026-11-09T11:20:00",
        "latitude": -7.9832,
        "longitude": -34.8404
    },
    {
        "titulo": "Sacos de lixo rasgados fora do horário na orla",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "endereco": "Rua Cândido Pessoa, próx. à Av. Beira-Mar - Bairro Novo",
        "tipo_residuo": "Lixo domiciliar e orgânico",
        "gravidade": "Moderado",
        "descricao": "Ponto já limpo pela equipe noturna da prefeitura.",
        "status": "Resolvido",
        "data_registro": "Resolvido recentemente",
        "confirmacoes": 3,
        "nao_esta_mais": 5,
        "ultimo_voto_ainda_la_em": "2026-11-07T18:00:00",
        "ultimo_voto_recolhido_em": "2026-11-08T09:00:00",
        "latitude": -8.0005,
        "longitude": -34.842
    },
    {
        "titulo": "Sacos de ráfia com entulho de reforma na calçada",
        "cidade": "Recife",
        "bairro": "Boa Viagem",
        "endereco": "Av. Conselheiro Aguiar, esquina próx. à pracinha - Boa Viagem",
        "tipo_residuo": "Metralha ensacada e restos de gesso",
        "gravidade": "Alto",
        "descricao": "Deixado sem caçamba estacionária há mais de 48h.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 4,
        "nao_esta_mais": 1,
        "ultimo_voto_ainda_la_em": "2026-11-09T10:45:00",
        "ultimo_voto_recolhido_em": "2026-11-09T08:15:00",
        "latitude": -8.1165,
        "longitude": -34.8998
    },
    {
        "titulo": "Caixotes quebrados e resíduos orgânicos pós-feira",
        "cidade": "Recife",
        "bairro": "Casa Amarela",
        "endereco": "Arredores do Largo de Casa Amarela",
        "tipo_residuo": "Madeira, papelão molhado e orgânicos",
        "gravidade": "Crítico",
        "descricao": "Atraindo insetos e obstruindo a sarjeta.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 7,
        "nao_esta_mais": 1,
        "ultimo_voto_ainda_la_em": "2026-11-09T12:00:00",
        "ultimo_voto_recolhido_em": "2026-11-09T09:30:00",
        "latitude": -8.0274,
        "longitude": -34.9172
    },
    {
        "titulo": "Restos de móveis de MDF e papelão na esquina",
        "cidade": "Recife",
        "bairro": "Torre",
        "endereco": "Próx. à Rua Real da Torre, 450 - Torre",
        "tipo_residuo": "Móveis desmontados e papelão",
        "gravidade": "Moderado",
        "descricao": "Vizinhos informaram que a equipe de limpeza já recolheu os itens.",
        "status": "Pendente",
        "data_registro": "Relato comunitário recente",
        "confirmacoes": 1,
        "nao_esta_mais": 3,
        "ultimo_voto_ainda_la_em": "2026-11-08T16:00:00",
        "ultimo_voto_recolhido_em": "2026-11-09T11:40:00",
        "latitude": -8.0468,
        "longitude": -34.9095
    },
]


ROTAS_REAIS_OSRM = {'Coleta Domiciliar - Rio Doce e Jardim Atlântico': [[-7.96021, -34.83706], [-7.9603, -34.8371], [-7.96038, -34.83711], [-7.96054, -34.83715], [-7.96064, -34.83718], [-7.96076, -34.83722], [-7.96087, -34.83725], [-7.96086, -34.83731], [-7.9608, -34.83755], [-7.96078, -34.83774], [-7.96076, -34.83794], [-7.96075, -34.83816], [-7.96074, -34.83852], [-7.96073, -34.83857], [-7.96071, -34.83906], [-7.96087, -34.83911], [-7.96111, -34.83918], [-7.96144, -34.83928], [-7.96165, -34.83934], [-7.9617, -34.83936], [-7.96197, -34.83945], [-7.96223, -34.83953], [-7.96259, -34.83964], [-7.96311, -34.8398], [-7.96342, -34.8399], [-7.9637, -34.83999], [-7.96389, -34.84005], [-7.96392, -34.84006], [-7.96394, -34.84007], [-7.96421, -34.84015], [-7.96427, -34.84017], [-7.96443, -34.84022], [-7.96448, -34.84024], [-7.96468, -34.84029], [-7.96473, -34.8403], [-7.96499, -34.84037], [-7.96534, -34.84018], [-7.96553, -34.84006], [-7.96573, -34.83994], [-7.96589, -34.83984], [-7.96596, -34.8398], [-7.96601, -34.83976], [-7.96613, -34.83964], [-7.96645, -34.83929], [-7.96661, -34.8391], [-7.96677, -34.8389], [-7.96683, -34.83883], [-7.96689, -34.8387], [-7.96694, -34.83859], [-7.96697, -34.83849], [-7.967, -34.83837], [-7.96706, -34.83816], [-7.9671, -34.83803], [-7.96716, -34.83782], [-7.96729, -34.83743], [-7.96738, -34.83717], [-7.96751, -34.83676], [-7.96759, -34.83652], [-7.96764, -34.83636], [-7.96784, -34.83644], [-7.96805, -34.83653], [-7.96842, -34.83669], [-7.96869, -34.8368], [-7.96858, -34.83706], [-7.96844, -34.83737], [-7.96835, -34.83759], [-7.96897, -34.83786], [-7.96957, -34.83812], [-7.96993, -34.83828], [-7.9702, -34.8384], [-7.97082, -34.83867], [-7.97146, -34.83896], [-7.97206, -34.83921], [-7.97272, -34.8395], [-7.97294, -34.83959], [-7.97334, -34.83977], [-7.97395, -34.84003], [-7.9741, -34.84011], [-7.97457, -34.84031], [-7.97492, -34.84047], [-7.97542, -34.84069], [-7.97578, -34.84087], [-7.97619, -34.84107], [-7.97634, -34.84072], [-7.97648, -34.84043], [-7.97684, -34.83969], [-7.97713, -34.83905], [-7.97716, -34.83898]], 'Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada': [[-7.98233, -34.84069], [-7.98248, -34.84088], [-7.98252, -34.84083], [-7.98265, -34.84051], [-7.98289, -34.83993], [-7.98301, -34.83964], [-7.98311, -34.83939], [-7.98337, -34.83879], [-7.98364, -34.83815], [-7.98407, -34.83837], [-7.98458, -34.83861], [-7.98471, -34.83867], [-7.98478, -34.83871], [-7.98596, -34.83929], [-7.98607, -34.83935], [-7.98664, -34.83962], [-7.98735, -34.83998], [-7.98787, -34.84022], [-7.98817, -34.84036], [-7.98843, -34.84052], [-7.98892, -34.84075], [-7.98938, -34.84097], [-7.98946, -34.84101], [-7.99062, -34.84158], [-7.99064, -34.84159], [-7.99152, -34.84202], [-7.99165, -34.84209], [-7.99176, -34.84218], [-7.99199, -34.84229], [-7.99232, -34.84245], [-7.99242, -34.8425], [-7.99303, -34.8428], [-7.99355, -34.84305], [-7.994, -34.84327], [-7.99411, -34.84329], [-7.99584, -34.84415], [-7.99609, -34.84428], [-7.99656, -34.84452], [-7.99715, -34.84479], [-7.99812, -34.84525], [-7.99858, -34.84548], [-7.99904, -34.84571], [-7.9994, -34.84589], [-7.99947, -34.84593], [-7.99974, -34.84609], [-7.99986, -34.84616], [-8.00009, -34.84629], [-8.00014, -34.84634], [-8.00017, -34.84636], [-8.00024, -34.84642], [-8.00031, -34.84646], [-8.00044, -34.84654], [-8.00054, -34.84659], [-8.00066, -34.84664], [-8.00074, -34.84664], [-8.00093, -34.84664], [-8.00108, -34.84664], [-8.00113, -34.84663], [-8.0012, -34.84662], [-8.00136, -34.8466], [-8.00137, -34.84654], [-8.00139, -34.84641], [-8.00145, -34.84608], [-8.00149, -34.84575], [-8.00156, -34.84512], [-8.00166, -34.84442], [-8.00174, -34.84389]], 'Coleta Domiciliar - Sítio Histórico e Varadouro': [[-8.0194, -34.85522], [-8.01939, -34.85521], [-8.01939, -34.85514], [-8.01939, -34.85505], [-8.01941, -34.85491], [-8.01941, -34.85476], [-8.01945, -34.85471], [-8.01955, -34.85444], [-8.0197, -34.85422], [-8.01971, -34.85426], [-8.0198, -34.85448], [-8.0198, -34.85449], [-8.01989, -34.8548], [-8.01995, -34.85494], [-8.02003, -34.85514], [-8.02005, -34.8552], [-8.02006, -34.85527], [-8.02006, -34.85533], [-8.02004, -34.85541], [-8.02004, -34.85544], [-8.02006, -34.8555], [-8.02009, -34.85553], [-8.02012, -34.85554], [-8.02015, -34.85555], [-8.02018, -34.85554], [-8.02021, -34.85553], [-8.02024, -34.85551], [-8.02026, -34.85549], [-8.02012, -34.85514], [-8.02005, -34.85496], [-8.02004, -34.85489], [-8.02003, -34.85481], [-8.02005, -34.85471], [-8.02009, -34.85459], [-8.02015, -34.85445], [-8.02035, -34.85413], [-8.02045, -34.85396], [-8.02078, -34.85333], [-8.02085, -34.85321], [-8.02093, -34.85299], [-8.02099, -34.85279], [-8.02102, -34.85257], [-8.02101, -34.85246], [-8.02099, -34.85232], [-8.02096, -34.85221], [-8.02092, -34.85211], [-8.02087, -34.85196], [-8.02077, -34.85175], [-8.02055, -34.85133], [-8.02028, -34.85086], [-8.02006, -34.8506], [-8.01992, -34.85043], [-8.0188, -34.84924], [-8.01845, -34.84886], [-8.01836, -34.84878], [-8.01824, -34.84869], [-8.01807, -34.84857], [-8.01797, -34.84849], [-8.01788, -34.84844], [-8.01783, -34.8484], [-8.01766, -34.84829], [-8.01753, -34.84822], [-8.01736, -34.84808], [-8.01712, -34.84799], [-8.01706, -34.84797], [-8.01702, -34.84796], [-8.01697, -34.84796], [-8.01693, -34.84797], [-8.01688, -34.848], [-8.01685, -34.84801], [-8.01681, -34.84806], [-8.01672, -34.84818], [-8.01662, -34.84844], [-8.01661, -34.84849], [-8.0166, -34.84852], [-8.01657, -34.84861], [-8.01655, -34.84873], [-8.01652, -34.84889], [-8.0165, -34.84905], [-8.01664, -34.8489], [-8.01668, -34.84886], [-8.01671, -34.84883], [-8.01683, -34.84867], [-8.0169, -34.84861], [-8.01695, -34.84856], [-8.01701, -34.84851], [-8.01711, -34.84847], [-8.01725, -34.84845], [-8.01734, -34.84844], [-8.01761, -34.84843], [-8.01763, -34.84841], [-8.01765, -34.8484], [-8.01765, -34.84839], [-8.01766, -34.84836], [-8.01766, -34.84832], [-8.01766, -34.84829], [-8.01753, -34.84822], [-8.01736, -34.84808], [-8.01712, -34.84799], [-8.01706, -34.84797], [-8.01702, -34.84796], [-8.01697, -34.84796], [-8.01693, -34.84797], [-8.01688, -34.848], [-8.01685, -34.84801], [-8.01681, -34.84806], [-8.01672, -34.84818], [-8.01662, -34.84844], [-8.01661, -34.84849], [-8.0166, -34.84852], [-8.01657, -34.84861], [-8.01655, -34.84873], [-8.01652, -34.84889], [-8.0165, -34.84905], [-8.01638, -34.84915], [-8.01624, -34.84928], [-8.01591, -34.84959], [-8.01556, -34.84994], [-8.01534, -34.84967], [-8.01486, -34.84914], [-8.01417, -34.84845], [-8.01402, -34.84829]], 'Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)': [[-8.02659, -34.91815], [-8.02639, -34.91782], [-8.02662, -34.91779], [-8.02666, -34.91778], [-8.02675, -34.91776], [-8.02681, -34.91772], [-8.02694, -34.91764], [-8.02795, -34.91696], [-8.02817, -34.91686], [-8.02863, -34.91708], [-8.02874, -34.91714], [-8.02894, -34.91723], [-8.02912, -34.91734], [-8.0294, -34.91674], [-8.02945, -34.91663], [-8.02958, -34.91633], [-8.02985, -34.91573], [-8.03, -34.91538], [-8.03023, -34.91481], [-8.03049, -34.9149], [-8.03062, -34.91494], [-8.03148, -34.91525], [-8.03153, -34.91527], [-8.03158, -34.91514], [-8.03159, -34.91509], [-8.03163, -34.91496], [-8.0317, -34.91475], [-8.03171, -34.9147], [-8.03172, -34.91467], [-8.03175, -34.9146], [-8.03177, -34.91453], [-8.03192, -34.91405], [-8.032, -34.91382], [-8.03205, -34.91364], [-8.03208, -34.91355], [-8.03225, -34.91304], [-8.03227, -34.91297], [-8.03242, -34.91249], [-8.03261, -34.91191], [-8.03264, -34.91182], [-8.03283, -34.9112], [-8.03304, -34.91056], [-8.03307, -34.91047], [-8.03301, -34.91041], [-8.03299, -34.9104], [-8.03287, -34.9103], [-8.03285, -34.91024], [-8.03285, -34.9102], [-8.03287, -34.91014], [-8.0329, -34.91011], [-8.03294, -34.91005], [-8.03291, -34.90974], [-8.03286, -34.90937], [-8.03284, -34.90916], [-8.03278, -34.90863], [-8.03278, -34.90854], [-8.03276, -34.90839], [-8.03272, -34.9081], [-8.0327, -34.90796], [-8.03272, -34.90761], [-8.03278, -34.90748], [-8.03281, -34.90738], [-8.03283, -34.90735], [-8.03288, -34.90733], [-8.03303, -34.90745], [-8.03311, -34.90751], [-8.03319, -34.90753], [-8.03324, -34.90751], [-8.0333, -34.90743], [-8.03333, -34.90737], [-8.03342, -34.90714], [-8.03348, -34.907], [-8.03352, -34.90691], [-8.03371, -34.90664], [-8.03377, -34.90649], [-8.03384, -34.90624], [-8.03393, -34.90592], [-8.03393, -34.90585], [-8.03392, -34.90561], [-8.03373, -34.90506], [-8.03368, -34.90489], [-8.03364, -34.90477], [-8.03364, -34.90475], [-8.03359, -34.90456], [-8.03355, -34.90445], [-8.0335, -34.90428], [-8.03338, -34.90387], [-8.0333, -34.90366], [-8.03327, -34.90357], [-8.03322, -34.90349], [-8.03319, -34.90344], [-8.03302, -34.9032], [-8.03285, -34.90297], [-8.03283, -34.90295], [-8.03263, -34.90277], [-8.03243, -34.90263], [-8.03226, -34.90254], [-8.03207, -34.90243], [-8.03205, -34.90242], [-8.03171, -34.90225], [-8.03145, -34.90211], [-8.03131, -34.90201], [-8.03109, -34.90187], [-8.031, -34.90181], [-8.03077, -34.90163], [-8.03072, -34.90158], [-8.03051, -34.90136], [-8.03019, -34.90097], [-8.02984, -34.90058], [-8.02978, -34.90051], [-8.0297, -34.90043], [-8.02973, -34.90039], [-8.03009, -34.89989], [-8.03013, -34.89983], [-8.03048, -34.89929], [-8.03086, -34.89881], [-8.03102, -34.89861], [-8.03113, -34.89847], [-8.0312, -34.8984], [-8.03138, -34.8982], [-8.03143, -34.89816], [-8.03152, -34.89806], [-8.0321, -34.89749], [-8.03258, -34.89714], [-8.03276, -34.897], [-8.03302, -34.89683], [-8.03318, -34.89672], [-8.03338, -34.89659], [-8.03356, -34.8965], [-8.03364, -34.89645], [-8.03373, -34.8964], [-8.03461, -34.89592], [-8.035, -34.8957], [-8.0357, -34.89527], [-8.03584, -34.89518], [-8.03652, -34.89477], [-8.03673, -34.89462], [-8.03699, -34.89441], [-8.03705, -34.89437], [-8.03744, -34.89399], [-8.03769, -34.89408], [-8.0383, -34.89428], [-8.03931, -34.89461], [-8.04003, -34.89485], [-8.04029, -34.89476], [-8.041, -34.89446], [-8.04103, -34.89446], [-8.04146, -34.89382], [-8.04176, -34.89403], [-8.04208, -34.89426], [-8.04227, -34.89439], [-8.04153, -34.89509], [-8.04139, -34.89491], [-8.04049, -34.89582], [-8.04041, -34.89588], [-8.04032, -34.89592], [-8.04022, -34.89595], [-8.04018, -34.89595]], 'Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)': [[-8.05673, -34.89248], [-8.05719, -34.89121], [-8.05724, -34.89108], [-8.05735, -34.89109], [-8.05856, -34.89123], [-8.05885, -34.8899], [-8.05853, -34.88988], [-8.0578, -34.88993], [-8.05773, -34.88994], [-8.05769, -34.88994], [-8.05765, -34.88994], [-8.0576, -34.88994], [-8.05755, -34.88994], [-8.05752, -34.88994], [-8.05746, -34.88995], [-8.05657, -34.88995], [-8.05644, -34.88994], [-8.05631, -34.88991], [-8.05625, -34.88988], [-8.05626, -34.88952], [-8.05628, -34.88936], [-8.05631, -34.88919], [-8.05639, -34.88897], [-8.05656, -34.88869], [-8.05715, -34.88768], [-8.05743, -34.88719], [-8.05758, -34.88695], [-8.05762, -34.88688], [-8.05798, -34.88626], [-8.05829, -34.88571], [-8.05832, -34.88567], [-8.05834, -34.88561], [-8.05867, -34.88476], [-8.05913, -34.88355], [-8.05926, -34.88334], [-8.05928, -34.88332], [-8.05949, -34.88299], [-8.05976, -34.88258], [-8.06011, -34.88203], [-8.06123, -34.88274], [-8.06129, -34.88278], [-8.06135, -34.88282], [-8.06114, -34.88321], [-8.0611, -34.8833], [-8.06122, -34.88333], [-8.06146, -34.88287], [-8.06178, -34.88225], [-8.06201, -34.88179], [-8.06202, -34.88178], [-8.06207, -34.88166], [-8.0621, -34.8816], [-8.06214, -34.88153], [-8.06265, -34.8806], [-8.06267, -34.88057], [-8.06273, -34.88047], [-8.0628, -34.88034], [-8.06295, -34.88007], [-8.06317, -34.87968], [-8.06324, -34.87955], [-8.06334, -34.87938], [-8.06338, -34.87931], [-8.06341, -34.87925], [-8.06364, -34.87884], [-8.06367, -34.87877], [-8.06378, -34.87857], [-8.06369, -34.87856], [-8.06358, -34.87854], [-8.06306, -34.87845]]}

PONTOS_INICIAIS = [
    # --- OLINDA: ECOPONTOS / ECOESTAÇÕES E PONTOS DE ENTREGA VOLUNTÁRIA ---
    {
        "nome": "Ecoponto Bairro Novo (Orla)",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Vidro, Plástico, Papel, Metal",
        "endereco": "Av. Ministro Marcos Freire, próx. à Praça Duque de Caxias",
        "horario": "Seg a Sáb: 07h às 19h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "07:00",
        "hora_fim": "19:00",
        "observacoes": "Ponto de entrega voluntária para recicláveis secos limpos.",
        "latitude": -7.9986,
        "longitude": -34.8415,
        "rota_coordenadas": [],
    },
    {
        "nome": "Ecoestação Peixinhos",
        "cidade": "Olinda",
        "bairro": "Peixinhos",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Av. Presidente Kennedy, Peixinhos",
        "horario": "Seg a Sex: 08h às 16h | Sáb: 08h às 12h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Recebe até 1m³ de pequenos entulhos, restos de poda e volumosos por morador.",
        "latitude": -8.0128,
        "longitude": -34.8694,
        "rota_coordenadas": [],
    },
    {
        "nome": "PEV Sítio Histórico (Carmo)",
        "cidade": "Olinda",
        "bairro": "Carmo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Óleo de Cozinha, Eletrônicos",
        "endereco": "Praça do Carmo, s/n - Carmo",
        "horario": "Diariamente: 06h às 22h",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "06:00",
        "hora_fim": "22:00",
        "observacoes": "Óleo de cozinha usado deve ser entregue em garrafa PET bem fechada.",
        "latitude": -8.0175,
        "longitude": -34.8492,
        "rota_coordenadas": [],
    },
    {
        "nome": "Ecoestação Ouro Preto / Cohab",
        "cidade": "Olinda",
        "bairro": "Ouro Preto",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Poda, Eletrônicos",
        "endereco": "Rua Peixe Agulha, Ouro Preto",
        "horario": "Seg a Sex: 08h às 17h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex",
        "hora_inicio": "08:00",
        "hora_fim": "17:00",
        "observacoes": "Atende moradores de Ouro Preto, Jatobá e Cidade Tabajara.",
        "latitude": -7.9942,
        "longitude": -34.8648,
        "rota_coordenadas": [],
    },
    {
        "nome": "PEV Casa Caiada (Praça 12 de Março)",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Eletrônicos, Pilhas e Baterias",
        "endereco": "Rua Dr. Manoel de Barros Lima, Casa Caiada",
        "horario": "Seg a Sáb: 08h às 18h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "18:00",
        "observacoes": "Coleta seletiva em parceria com cooperativas de catadores de Olinda.",
        "latitude": -7.9825,
        "longitude": -34.8398,
        "rota_coordenadas": [],
    },
    # --- OLINDA: ROTAS E HORÁRIOS DE COLETA DOMICILIAR (GEOMETRIA REAL DE RUAS OSRM) ---
    {
        "nome": "Coleta Domiciliar - Rio Doce e Jardim Atlântico",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Rota: Terminal Rio Doce -> Av. Brasil -> Av. Fagundes Varela (Jardim Atlântico)",
        "horario": "Seg, Qua e Sex: 07h às 11h30",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "07:00",
        "hora_fim": "11:30",
        "observacoes": "Caminhão inicia no Terminal de Rio Doce às 07h e segue pelas ruas de Rio Doce até Jardim Atlântico.",
        "latitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Rio Doce e Jardim Atlântico"][0][0],
        "longitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Rio Doce e Jardim Atlântico"][0][1],
        "rota_coordenadas": ROTAS_REAIS_OSRM["Coleta Domiciliar - Rio Doce e Jardim Atlântico"],
    },
    {
        "nome": "Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Rota: Av. José Augusto Moreira (Casa Caiada) -> Av. Getúlio Vargas (Bairro Novo)",
        "horario": "Seg a Sáb: 18h30 às 23h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "18:30",
        "hora_fim": "23:00",
        "observacoes": "Coleta noturna diária percorrendo o corredor principal de Casa Caiada e Bairro Novo.",
        "latitude": ROTAS_REAIS_OSRM["Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada"][0][0],
        "longitude": ROTAS_REAIS_OSRM["Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada"][0][1],
        "rota_coordenadas": ROTAS_REAIS_OSRM["Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada"],
    },
    {
        "nome": "Coleta Domiciliar - Sítio Histórico e Varadouro",
        "cidade": "Olinda",
        "bairro": "Varadouro",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar, Recicláveis",
        "endereco": "Rota: Varadouro -> Av. Sigismundo Gonçalves -> Praça do Carmo -> Alto da Sé",
        "horario": "Ter, Qui e Sáb: 06h30 às 10h30",
        "dias_semana": "Ter,Qui,Sab",
        "hora_inicio": "06:30",
        "hora_fim": "10:30",
        "observacoes": "Caminhão compactador reduzido adaptado para percorrer as ladeiras históricas de Olinda.",
        "latitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Sítio Histórico e Varadouro"][0][0],
        "longitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Sítio Histórico e Varadouro"][0][1],
        "rota_coordenadas": ROTAS_REAIS_OSRM["Coleta Domiciliar - Sítio Histórico e Varadouro"],
    },
    # --- RECIFE: ECOPONTOS / ECOESTAÇÕES E ROTAS DE COLETA DOMICILIAR ---
    {
        "nome": "Ecoponto Centro (Santo Amaro / Boa Vista)",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Óleo de Cozinha, Eletrônicos",
        "endereco": "Rua do Sol, 100 - Centro, Recife",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ponto central de coleta seletiva e descarte consciente no centro do Recife.",
        "latitude": -8.0628,
        "longitude": -34.8813,
        "rota_coordenadas": [],
    },
    {
        "nome": "Ecoestação Campo Grande",
        "cidade": "Recife",
        "bairro": "Campo Grande",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Av. Agamenon Magalhães (próx. à divisa Recife/Olinda)",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação da EMLURB estrategicamente localizada entre Recife e Olinda.",
        "latitude": -8.0342,
        "longitude": -34.8781,
        "rota_coordenadas": [],
    },
    {
        "nome": "Ecoestação Torre",
        "cidade": "Recife",
        "bairro": "Torre",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Poda, Eletrônicos, Óleo de Cozinha",
        "endereco": "Rua Ciclovia República da Argélia, Torre",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Aceita resíduos recicláveis, móveis desmontados e pequenos volumes de obra.",
        "latitude": -8.0462,
        "longitude": -34.9102,
        "rota_coordenadas": [],
    },
    {
        "nome": "Ecoestação Imbiribeira",
        "cidade": "Recife",
        "bairro": "Imbiribeira",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Poda, Móveis Velhos",
        "endereco": "Av. Mascarenhas de Morais, Imbiribeira",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Atende a Zona Sul do Recife com descarte gratuito para moradores.",
        "latitude": -8.1095,
        "longitude": -34.9114,
        "rota_coordenadas": [],
    },
    {
        "nome": "Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)",
        "cidade": "Recife",
        "bairro": "Casa Amarela",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Rota: Estrada do Arraial (Casa Amarela) -> Tamarineira -> Espinheiro",
        "horario": "Seg, Qua e Sex: 19h às 23h",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "19:00",
        "hora_fim": "23:00",
        "observacoes": "Coleta regular noturna; disponha os sacos próximo ao horário de passagem.",
        "latitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)"][0][0],
        "longitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)"][0][1],
        "rota_coordenadas": ROTAS_REAIS_OSRM["Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)"],
    },
    {
        "nome": "Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar, Recicláveis",
        "endereco": "Rota: Av. Conde da Boa Vista -> Ponte Duarte Coelho -> Av. Guararapes (Santo Antônio)",
        "horario": "Diariamente: 20h às 23h50",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "20:00",
        "hora_fim": "23:50",
        "observacoes": "Rota noturna percorrendo exclusivamente a Av. Conde da Boa Vista e a Ponte Duarte Coelho.",
        "latitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)"][0][0],
        "longitude": ROTAS_REAIS_OSRM["Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)"][0][1],
        "rota_coordenadas": ROTAS_REAIS_OSRM["Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)"],
    },
    {
        "nome": "Ecoponto Repense Reuse - Praça do Parcão",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Têxteis (Roupas e Calçados), Plástico, Papel",
        "endereco": "Praça Vitoriano Regueira (Praça do Parcão), Bairro Novo",
        "horario": "Diariamente: 06h às 22h",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "06:00",
        "hora_fim": "22:00",
        "observacoes": "Ponto oficial da campanha municipal Repense Reuse de Olinda para economia circular e recicláveis.",
        "latitude": -8.0025,
        "longitude": -34.8422,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoponto Repense Reuse - Praça Dantas Barreto",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Têxteis, Papel, Plástico, Metal",
        "endereco": "Praça Dantas Barreto, Bairro Novo",
        "horario": "Diariamente: 06h às 22h",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "06:00",
        "hora_fim": "22:00",
        "observacoes": "Contêiner oficial da Prefeitura de Olinda para entrega voluntária de recicláveis e têxteis.",
        "latitude": -7.9945,
        "longitude": -34.8428,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoponto Repense Reuse - Parque Billy Jackson",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Têxteis, Plástico, Vidro, Metal",
        "endereco": "Parque Billy Jackson, Casa Caiada",
        "horario": "Diariamente: 06h às 21h",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "06:00",
        "hora_fim": "21:00",
        "observacoes": "Ponto oficial de coleta seletiva e reaproveitamento instalado no Parque Billy Jackson.",
        "latitude": -7.9818,
        "longitude": -34.8392,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoponto Repense Reuse - Av. das Garças (4ª Etapa)",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Papel, Plástico, Metal, Têxteis",
        "endereco": "Praça da Avenida das Garças, 4ª Etapa - Rio Doce",
        "horario": "Diariamente: 06h às 21h",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "06:00",
        "hora_fim": "21:00",
        "observacoes": "Atende moradores da 4ª Etapa e arredores de Rio Doce para descarte seletivo gratuito.",
        "latitude": -7.9575,
        "longitude": -34.8388,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Arruda (EMLURB)",
        "cidade": "Recife",
        "bairro": "Arruda",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Av. Professor José dos Anjos - Arruda",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB (RPA 2). Recebe gratuitamente até 1m³/dia de entulho, poda, móveis velhos e recicláveis.",
        "latitude": -8.0235,
        "longitude": -34.8915,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Nova Descoberta (EMLURB)",
        "cidade": "Recife",
        "bairro": "Nova Descoberta",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Rua Nova Descoberta, 1062 - Nova Descoberta",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB (RPA 3) para descarte correto de pequenos volumes de obra, volumosos e recicláveis.",
        "latitude": -8.0068,
        "longitude": -34.9255,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Santo Amaro / Jayme da Fonte (EMLURB)",
        "cidade": "Recife",
        "bairro": "Santo Amaro",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda, Eletrônicos",
        "endereco": "Av. Dr. Jayme da Fonte, 149 - Santo Amaro",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB na região central (Santo Amaro).",
        "latitude": -8.0485,
        "longitude": -34.881,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Torrões (EMLURB)",
        "cidade": "Recife",
        "bairro": "Torrões",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Rua Maestro Jones Johnson - Torrões",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB (RPA 4) atendendo Torrões, Cordeiro e Zona Oeste.",
        "latitude": -8.0598,
        "longitude": -34.9385,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Totó (EMLURB)",
        "cidade": "Recife",
        "bairro": "Totó",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Rua Onze de Agosto - Totó",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB (RPA 5) para recebimento gratuito de volumosos, podas e recicláveis.",
        "latitude": -8.0815,
        "longitude": -34.962,
        "rota_coordenadas": []
    },
    {
        "nome": "Ecoestação Ibura (EMLURB)",
        "cidade": "Recife",
        "bairro": "Ibura",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis, Entulho, Móveis Velhos, Poda",
        "endereco": "Rua Rio Tapado - Ibura",
        "horario": "Seg a Sáb: 08h às 16h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "08:00",
        "hora_fim": "16:00",
        "observacoes": "Ecoestação oficial da EMLURB (RPA 6) atendendo moradores do Ibura, Jordão e Cohab.",
        "latitude": -8.1195,
        "longitude": -34.938,
        "rota_coordenadas": []
    },
]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    raw_rota = d.get("rota_coordenadas")
    if isinstance(raw_rota, str) and raw_rota.strip():
        try:
            d["rota_coordenadas"] = json.loads(raw_rota)
        except Exception:
            d["rota_coordenadas"] = []
    elif not isinstance(raw_rota, list):
        d["rota_coordenadas"] = []
    return d


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pontos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cidade TEXT NOT NULL DEFAULT 'Olinda',
                bairro TEXT NOT NULL DEFAULT 'Centro',
                categoria TEXT NOT NULL DEFAULT 'Ecoponto',
                tipo TEXT NOT NULL,
                endereco TEXT NOT NULL,
                horario TEXT NOT NULL DEFAULT 'Seg a Sáb: 08h às 16h',
                dias_semana TEXT NOT NULL DEFAULT 'Seg,Ter,Qua,Qui,Sex,Sab',
                hora_inicio TEXT NOT NULL DEFAULT '08:00',
                hora_fim TEXT NOT NULL DEFAULT '16:00',
                observacoes TEXT NOT NULL DEFAULT '',
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                rota_coordenadas TEXT NOT NULL DEFAULT '[]'
            )
            """
        )

        colunas = [c["name"] for c in cursor.execute("PRAGMA table_info(pontos)").fetchall()]
        if "rota_coordenadas" not in colunas:
            cursor.execute("ALTER TABLE pontos ADD COLUMN rota_coordenadas TEXT NOT NULL DEFAULT '[]'")
            conn.commit()

        cursor.execute("SELECT COUNT(*) as total FROM pontos")
        total = cursor.fetchone()["total"]
        if total == 0:
            for item in PONTOS_INICIAIS:
                dados = dict(item)
                dados["rota_coordenadas"] = json.dumps(dados.get("rota_coordenadas", []))
                cursor.execute(
                    """
                    INSERT INTO pontos (
                        nome, cidade, bairro, categoria, tipo, endereco,
                        horario, dias_semana, hora_inicio, hora_fim, observacoes,
                        latitude, longitude, rota_coordenadas
                    ) VALUES (
                        :nome, :cidade, :bairro, :categoria, :tipo, :endereco,
                        :horario, :dias_semana, :hora_inicio, :hora_fim, :observacoes,
                        :latitude, :longitude, :rota_coordenadas
                    )
                    """,
                    dados,
                )
            conn.commit()
        else:
            # Garante que novos pontos reais de PONTOS_INICIAIS sejam adicionados se ainda não existirem no banco
            nomes_existentes = {
                r["nome"] for r in cursor.execute("SELECT nome FROM pontos").fetchall()
            }
            for item in PONTOS_INICIAIS:
                if item["nome"] not in nomes_existentes:
                    dados_novo = dict(item)
                    dados_novo["rota_coordenadas"] = json.dumps(dados_novo.get("rota_coordenadas", []))
                    cursor.execute(
                        """
                        INSERT INTO pontos (
                            nome, cidade, bairro, categoria, tipo, endereco,
                            horario, dias_semana, hora_inicio, hora_fim, observacoes,
                            latitude, longitude, rota_coordenadas
                        ) VALUES (
                            :nome, :cidade, :bairro, :categoria, :tipo, :endereco,
                            :horario, :dias_semana, :hora_inicio, :hora_fim, :observacoes,
                            :latitude, :longitude, :rota_coordenadas
                        )
                        """,
                        dados_novo,
                    )
            conn.commit()

            # Sincroniza as rotas padrão com a geometria real de rua (OSRM)
            for item in PONTOS_INICIAIS:
                if item.get("rota_coordenadas"):
                    cursor.execute(
                        """
                        UPDATE pontos
                        SET rota_coordenadas = ?, latitude = ?, longitude = ?, endereco = ?, observacoes = ?
                        WHERE nome = ?
                        """,
                        (
                            json.dumps(item["rota_coordenadas"]),
                            item["latitude"],
                            item["longitude"],
                            item["endereco"],
                            item["observacoes"],
                            item["nome"],
                        ),
                    )
            conn.commit()

        # Tabela de Denúncias de Descarte Irregular / Pontos Críticos
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS denuncias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                cidade TEXT NOT NULL DEFAULT 'Olinda',
                bairro TEXT NOT NULL,
                endereco TEXT NOT NULL,
                tipo_residuo TEXT NOT NULL DEFAULT 'Entulho / Lixo Misto',
                gravidade TEXT NOT NULL DEFAULT 'Crítico',
                descricao TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pendente',
                data_registro TEXT NOT NULL DEFAULT 'Hoje',
                confirmacoes INTEGER NOT NULL DEFAULT 1,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
            """
        )
        colunas_den = [c["name"] for c in cursor.execute("PRAGMA table_info(denuncias)").fetchall()]
        if "confirmacoes" not in colunas_den:
            cursor.execute("ALTER TABLE denuncias ADD COLUMN confirmacoes INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        if "nao_esta_mais" not in colunas_den:
            cursor.execute("ALTER TABLE denuncias ADD COLUMN nao_esta_mais INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "ultimo_voto_ainda_la_em" not in colunas_den:
            cursor.execute("ALTER TABLE denuncias ADD COLUMN ultimo_voto_ainda_la_em TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "ultimo_voto_recolhido_em" not in colunas_den:
            cursor.execute("ALTER TABLE denuncias ADD COLUMN ultimo_voto_recolhido_em TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "foto_base64" not in colunas_den:
            cursor.execute("ALTER TABLE denuncias ADD COLUMN foto_base64 TEXT NOT NULL DEFAULT ''")
            conn.commit()

        titulos_den_existentes = {
            r["titulo"] for r in cursor.execute("SELECT titulo FROM denuncias").fetchall()
        }
        for d_item in DENUNCIAS_INICIAIS:
            if d_item["titulo"] not in titulos_den_existentes:
                d_copy = dict(d_item)
                d_copy.setdefault("confirmacoes", 3)
                d_copy.setdefault("nao_esta_mais", 0)
                d_copy.setdefault("ultimo_voto_ainda_la_em", "")
                d_copy.setdefault("ultimo_voto_recolhido_em", "")
                d_copy.setdefault("foto_base64", "")
                cursor.execute(
                    """
                    INSERT INTO denuncias (
                        titulo, cidade, bairro, endereco, tipo_residuo,
                        gravidade, descricao, status, data_registro,
                        confirmacoes, nao_esta_mais, ultimo_voto_ainda_la_em, ultimo_voto_recolhido_em, foto_base64,
                        latitude, longitude
                    ) VALUES (
                        :titulo, :cidade, :bairro, :endereco, :tipo_residuo,
                        :gravidade, :descricao, :status, :data_registro,
                        :confirmacoes, :nao_esta_mais, :ultimo_voto_ainda_la_em, :ultimo_voto_recolhido_em, :foto_base64,
                        :latitude, :longitude
                    )
                    """,
                    d_copy,
                )
        conn.commit()

        # Tabela de Solicitações de Coleta de Volumosos / Cata-Treco
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS catatreco (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocolo TEXT NOT NULL,
                solicitante TEXT NOT NULL,
                cidade TEXT NOT NULL DEFAULT 'Olinda',
                bairro TEXT NOT NULL,
                endereco TEXT NOT NULL,
                itens_volumosos TEXT NOT NULL,
                turno_preferido TEXT NOT NULL DEFAULT 'Manhã (08h às 12h)',
                data_agendada TEXT NOT NULL DEFAULT 'Próxima semana',
                observacoes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Agendado',
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
            """
        )
        colunas_ct = [c["name"] for c in cursor.execute("PRAGMA table_info(catatreco)").fetchall()]
        if "foto_base64" not in colunas_ct:
            cursor.execute("ALTER TABLE catatreco ADD COLUMN foto_base64 TEXT NOT NULL DEFAULT ''")
            conn.commit()

        protocolos_existentes = {
            r["protocolo"] for r in cursor.execute("SELECT protocolo FROM catatreco").fetchall()
        }
        for ct_item in CATATRECO_INICIAIS:
            if ct_item["protocolo"] not in protocolos_existentes:
                ct_copy = dict(ct_item)
                ct_copy.setdefault("foto_base64", "")
                cursor.execute(
                    """
                    INSERT INTO catatreco (
                        protocolo, solicitante, cidade, bairro, endereco,
                        itens_volumosos, turno_preferido, data_agendada,
                        observacoes, status, foto_base64, latitude, longitude
                    ) VALUES (
                        :protocolo, :solicitante, :cidade, :bairro, :endereco,
                        :itens_volumosos, :turno_preferido, :data_agendada,
                        :observacoes, :status, :foto_base64, :latitude, :longitude
                    )
                    """,
                    ct_copy,
                )
        conn.commit()
    finally:
        conn.close()


init_db()


# Página principal e arquivos PWA gratuitos
@app.get("/")
def inicio():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/manifest.json")
def pwa_manifest():
    return FileResponse(BASE_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def pwa_service_worker():
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript")


# Health Check (Observabilidade)
@app.get("/health")
def health():
    conn = get_db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) as c FROM pontos").fetchone()["c"]
    finally:
        conn.close()
    return {
        "status": "ok",
        "aplicacao": "CittaLixo",
        "versao": "3.2.0",
        "cidades_atendidas": ["Olinda", "Recife"],
        "total_pontos": total,
    }


# Listar todos os pontos (com filtros opcionais gratuitos)
@app.get("/pontos", response_model=List[PontoResponse])
def listar_pontos(
    cidade: Optional[str] = Query(None, description="Filtrar por cidade (Olinda ou Recife)"),
    bairro: Optional[str] = Query(None, description="Filtrar por bairro"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria (Ecoponto ou Coleta Domiciliar)"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de resíduo"),
    dia_semana: Optional[str] = Query(None, description="Filtrar por dia da semana (Seg, Ter, Qua, Qui, Sex, Sab, Dom)"),
    busca: Optional[str] = Query(None, description="Busca textual em nome, endereço, bairro ou tipo"),
):
    query = "SELECT * FROM pontos WHERE 1=1"
    params: list = []

    if cidade:
        query += " AND LOWER(cidade) = LOWER(?)"
        params.append(cidade.strip())
    if bairro:
        query += " AND LOWER(bairro) LIKE LOWER(?)"
        params.append(f"%{bairro.strip()}%")
    if categoria:
        query += " AND LOWER(categoria) = LOWER(?)"
        params.append(categoria.strip())
    if tipo:
        query += " AND LOWER(tipo) LIKE LOWER(?)"
        params.append(f"%{tipo.strip()}%")
    if dia_semana:
        query += " AND LOWER(dias_semana) LIKE LOWER(?)"
        params.append(f"%{dia_semana.strip()}%")
    if busca:
        termo = f"%{busca.strip()}%"
        query += (
            " AND (LOWER(nome) LIKE LOWER(?) OR LOWER(endereco) LIKE LOWER(?) "
            "OR LOWER(bairro) LIKE LOWER(?) OR LOWER(tipo) LIKE LOWER(?))"
        )
        params.extend([termo, termo, termo, termo])

    query += " ORDER BY cidade ASC, bairro ASC, nome ASC"

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


# Buscar ponto por ID
@app.get("/pontos/{id}", response_model=PontoResponse)
def buscar_ponto(id: int):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM pontos WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ponto não encontrado",
            )
        return _row_to_dict(row)
    finally:
        conn.close()


# Criar ponto
@app.post("/pontos", response_model=PontoResponse, status_code=status.HTTP_201_CREATED)
def criar_ponto(ponto: PontoCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pontos (
                nome, cidade, bairro, categoria, tipo, endereco,
                horario, dias_semana, hora_inicio, hora_fim, observacoes,
                latitude, longitude, rota_coordenadas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ponto.nome,
                ponto.cidade,
                ponto.bairro,
                ponto.categoria,
                ponto.tipo,
                ponto.endereco,
                ponto.horario,
                ponto.dias_semana,
                ponto.hora_inicio,
                ponto.hora_fim,
                ponto.observacoes,
                ponto.latitude,
                ponto.longitude,
                json.dumps(ponto.rota_coordenadas or []),
            ),
        )
        conn.commit()
        novo_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM pontos WHERE id = ?", (novo_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# Atualizar ponto
@app.put("/pontos/{id}", response_model=PontoResponse)
def atualizar_ponto(id: int, ponto_atualizado: PontoCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        existente = cursor.execute("SELECT id FROM pontos WHERE id = ?", (id,)).fetchone()
        if not existente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ponto não encontrado",
            )

        cursor.execute(
            """
            UPDATE pontos
            SET nome = ?, cidade = ?, bairro = ?, categoria = ?, tipo = ?,
                endereco = ?, horario = ?, dias_semana = ?, hora_inicio = ?,
                hora_fim = ?, observacoes = ?, latitude = ?, longitude = ?,
                rota_coordenadas = ?
            WHERE id = ?
            """,
            (
                ponto_atualizado.nome,
                ponto_atualizado.cidade,
                ponto_atualizado.bairro,
                ponto_atualizado.categoria,
                ponto_atualizado.tipo,
                ponto_atualizado.endereco,
                ponto_atualizado.horario,
                ponto_atualizado.dias_semana,
                ponto_atualizado.hora_inicio,
                ponto_atualizado.hora_fim,
                ponto_atualizado.observacoes,
                ponto_atualizado.latitude,
                ponto_atualizado.longitude,
                json.dumps(ponto_atualizado.rota_coordenadas or []),
                id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pontos WHERE id = ?", (id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# Remover ponto
@app.delete("/pontos/{id}")
def remover_ponto(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        existente = cursor.execute("SELECT id FROM pontos WHERE id = ?", (id,)).fetchone()
        if not existente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ponto não encontrado",
            )

        cursor.execute("DELETE FROM pontos WHERE id = ?", (id,))
        conn.commit()
        return {"mensagem": "Ponto removido com sucesso", "id": id}
    finally:
        conn.close()


# --- ENDPOINTS DE DENÚNCIAS DE PONTOS CRÍTICOS / DESCARTE IRREGULAR ---

@app.get("/denuncias", response_model=List[DenunciaResponse])
def listar_denuncias(
    cidade: Optional[str] = Query(None, description="Filtrar por cidade (Olinda ou Recife)"),
    status_filtro: Optional[str] = Query(None, alias="status", description="Filtrar por status (Pendente ou Resolvido)"),
):
    query = "SELECT * FROM denuncias WHERE 1=1"
    params: list = []
    if cidade:
        query += " AND LOWER(cidade) = LOWER(?)"
        params.append(cidade.strip())
    if status_filtro:
        query += " AND LOWER(status) = LOWER(?)"
        params.append(status_filtro.strip())
    query += " ORDER BY CASE WHEN status = 'Pendente' THEN 0 ELSE 1 END, confirmacoes DESC, id DESC"

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/denuncias", response_model=DenunciaResponse, status_code=status.HTTP_201_CREATED)
def criar_denuncia(denuncia: DenunciaCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        agora_iso = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO denuncias (
                titulo, cidade, bairro, endereco, tipo_residuo,
                gravidade, descricao, status, data_registro, confirmacoes,
                nao_esta_mais, ultimo_voto_ainda_la_em, ultimo_voto_recolhido_em, foto_base64,
                latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                denuncia.titulo,
                denuncia.cidade,
                denuncia.bairro,
                denuncia.endereco,
                denuncia.tipo_residuo,
                denuncia.gravidade,
                denuncia.descricao,
                denuncia.status,
                denuncia.data_registro,
                denuncia.confirmacoes,
                denuncia.nao_esta_mais,
                denuncia.ultimo_voto_ainda_la_em or agora_iso,
                denuncia.ultimo_voto_recolhido_em,
                denuncia.foto_base64,
                denuncia.latitude,
                denuncia.longitude,
            ),
        )
        conn.commit()
        novo_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM denuncias WHERE id = ?", (novo_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.put("/denuncias/{id}/apoiar", response_model=DenunciaResponse)
def apoiar_denuncia(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Denúncia não encontrada",
            )
        novas_conf = (row["confirmacoes"] or 1) + 1
        agora_iso = datetime.now().isoformat()
        cursor.execute(
            "UPDATE denuncias SET confirmacoes = ?, ultimo_voto_ainda_la_em = ? WHERE id = ?",
            (novas_conf, agora_iso, id),
        )
        conn.commit()
        atualizado = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        return dict(atualizado)
    finally:
        conn.close()


@app.put("/denuncias/{id}/nao-esta-mais", response_model=DenunciaResponse)
def reportar_nao_esta_mais_denuncia(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Denúncia não encontrada",
            )
        novo_val = (row["nao_esta_mais"] or 0) + 1
        agora_iso = datetime.now().isoformat()
        cursor.execute(
            "UPDATE denuncias SET nao_esta_mais = ?, ultimo_voto_recolhido_em = ? WHERE id = ?",
            (novo_val, agora_iso, id),
        )
        conn.commit()
        atualizado = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        return dict(atualizado)
    finally:
        conn.close()


class DenunciaVotoPayload(BaseModel):
    voto_anterior: Optional[str] = None
    voto_novo: Optional[str] = None


@app.put("/denuncias/{id}/votar", response_model=DenunciaResponse)
def votar_denuncia_unico(id: int, payload: DenunciaVotoPayload):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Denúncia não encontrada",
            )
        conf = row["confirmacoes"] if row["confirmacoes"] is not None else 1
        limpo = row["nao_esta_mais"] if row["nao_esta_mais"] is not None else 0

        if payload.voto_anterior == "ainda_la":
            conf = max(0, conf - 1)
        elif payload.voto_anterior == "ja_recolhido":
            limpo = max(0, limpo - 1)

        ts_ainda = row["ultimo_voto_ainda_la_em"] or ""
        ts_limpo = row["ultimo_voto_recolhido_em"] or ""
        agora_iso = datetime.now().isoformat()

        if payload.voto_novo == "ainda_la":
            conf = conf + 1
            ts_ainda = agora_iso
        elif payload.voto_novo == "ja_recolhido":
            limpo = limpo + 1
            ts_limpo = agora_iso

        cursor.execute(
            "UPDATE denuncias SET confirmacoes = ?, nao_esta_mais = ?, ultimo_voto_ainda_la_em = ?, ultimo_voto_recolhido_em = ? WHERE id = ?",
            (conf, limpo, ts_ainda, ts_limpo, id),
        )
        conn.commit()
        atualizado = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        return dict(atualizado)
    finally:
        conn.close()


@app.put("/denuncias/{id}/resolver", response_model=DenunciaResponse)
def resolver_denuncia(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Denúncia não encontrada",
            )
        novo_status = "Resolvido" if row["status"] != "Resolvido" else "Pendente"
        cursor.execute("UPDATE denuncias SET status = ? WHERE id = ?", (novo_status, id))
        conn.commit()
        atualizado = cursor.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
        return dict(atualizado)
    finally:
        conn.close()


@app.delete("/denuncias/{id}")
def remover_denuncia(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT id FROM denuncias WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Denúncia não encontrada",
            )
        cursor.execute("DELETE FROM denuncias WHERE id = ?", (id,))
        conn.commit()
        return {"mensagem": "Denúncia removida com sucesso", "id": id}
    finally:
        conn.close()


# --- ENDPOINTS DE AGENDAMENTO DE COLETA DE VOLUMOSOS / CATA-TRECO ---

@app.get("/catatreco", response_model=List[CataTrecoResponse])
def listar_catatreco(
    cidade: Optional[str] = Query(None, description="Filtrar por cidade (Olinda ou Recife)"),
    status_filtro: Optional[str] = Query(None, alias="status", description="Filtrar por status (Agendado ou Recolhido)"),
):
    query = "SELECT * FROM catatreco WHERE 1=1"
    params: list = []
    if cidade:
        query += " AND LOWER(cidade) = LOWER(?)"
        params.append(cidade.strip())
    if status_filtro:
        query += " AND LOWER(status) = LOWER(?)"
        params.append(status_filtro.strip())
    query += " ORDER BY CASE WHEN status = 'Agendado' THEN 0 ELSE 1 END, id DESC"

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/catatreco", response_model=CataTrecoResponse, status_code=status.HTTP_201_CREATED)
def criar_catatreco(pedido: CataTrecoCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        prox_num = cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 as n FROM catatreco").fetchone()["n"]
        protocolo = f"CT-2026-{prox_num:03d}"
        cursor.execute(
            """
            INSERT INTO catatreco (
                protocolo, solicitante, cidade, bairro, endereco,
                itens_volumosos, turno_preferido, data_agendada,
                observacoes, status, foto_base64, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                protocolo,
                pedido.solicitante,
                pedido.cidade,
                pedido.bairro,
                pedido.endereco,
                pedido.itens_volumosos,
                pedido.turno_preferido,
                pedido.data_agendada,
                pedido.observacoes,
                pedido.status,
                pedido.foto_base64,
                pedido.latitude,
                pedido.longitude,
            ),
        )
        conn.commit()
        novo_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM catatreco WHERE id = ?", (novo_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.put("/catatreco/{id}/recolher", response_model=CataTrecoResponse)
def recolher_catatreco(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM catatreco WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento Cata-Treco não encontrado",
            )
        novo_status = "Recolhido" if row["status"] != "Recolhido" else "Agendado"
        cursor.execute("UPDATE catatreco SET status = ? WHERE id = ?", (novo_status, id))
        conn.commit()
        atualizado = cursor.execute("SELECT * FROM catatreco WHERE id = ?", (id,)).fetchone()
        return dict(atualizado)
    finally:
        conn.close()


@app.delete("/catatreco/{id}")
def remover_catatreco(id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT id FROM catatreco WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento Cata-Treco não encontrado",
            )
        cursor.execute("DELETE FROM catatreco WHERE id = ?", (id,))
        conn.commit()
        return {"mensagem": "Agendamento Cata-Treco removido com sucesso", "id": id}
    finally:
        conn.close()
