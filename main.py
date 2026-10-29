from pathlib import Path
from typing import List, Optional
import sqlite3
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cittalixo.db"

app = FastAPI(
    title="CittaLixo API - Recife & Olinda",
    description=(
        "API gratuita para consulta e gerenciamento de Ecopontos/Ecoestações "
        "e horários de coleta domiciliar em Recife e Olinda."
    ),
    version="2.0.0",
)


# Modelos de dados (Pydantic)
class PontoBase(BaseModel):
    nome: str = Field(..., min_length=2, description="Nome do ecoponto ou ponto de coleta")
    cidade: str = Field(default="Olinda", description="Cidade (Olinda ou Recife)")
    bairro: str = Field(default="Centro", description="Bairro do ponto")
    categoria: str = Field(
        default="Ecoponto",
        description="Categoria: 'Ecoponto' (ponto fixo) ou 'Coleta Domiciliar' (caminhão)",
    )
    tipo: str = Field(..., description="Tipos de resíduos aceitos (ex: Recicláveis, Eletrônicos, Entulho)")
    endereco: str = Field(..., description="Endereço ou referência da rua")
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
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude geográfica")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude geográfica")


class PontoCreate(PontoBase):
    pass


class PontoResponse(PontoBase):
    id: int


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
    },
    # --- OLINDA: HORÁRIOS DE COLETA DOMICILIAR ---
    {
        "nome": "Coleta Domiciliar - Rio Doce e Jardim Atlântico",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Av. Brasil e vias principais de Rio Doce",
        "horario": "Seg, Qua e Sex: 07h às 11h30",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "07:00",
        "hora_fim": "11:30",
        "observacoes": "Colocar o lixo ensacado até 1 hora antes da passagem do caminhão compactador.",
        "latitude": -7.9672,
        "longitude": -34.8364,
    },
    {
        "nome": "Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Av. Getúlio Vargas e transversais",
        "horario": "Seg a Sáb: 18h30 às 23h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "18:30",
        "hora_fim": "23:00",
        "observacoes": "Coleta noturna diária (exceto domingos) no corredor principal.",
        "latitude": -7.9918,
        "longitude": -34.8427,
    },
    {
        "nome": "Coleta Domiciliar - Sítio Histórico e Varadouro",
        "cidade": "Olinda",
        "bairro": "Varadouro",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar, Recicláveis",
        "endereco": "Av. Sigismundo Gonçalves e ladeiras do Centro Histórico",
        "horario": "Ter, Qui e Sáb: 06h30 às 10h30",
        "dias_semana": "Ter,Qui,Sab",
        "hora_inicio": "06:30",
        "hora_fim": "10:30",
        "observacoes": "Coleta mista com caminhão de menor porte nas ladeiras históricas.",
        "latitude": -8.0156,
        "longitude": -34.8538,
    },
    # --- RECIFE: ECOPONTOS / ECOESTAÇÕES E COLETA DOMICILIAR ---
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
    },
    {
        "nome": "Coleta Domiciliar - Zona Norte (Casa Amarela / Espinheiro)",
        "cidade": "Recife",
        "bairro": "Casa Amarela",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Estrada do Arraial e entorno",
        "horario": "Seg, Qua e Sex: 19h às 23h",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "19:00",
        "hora_fim": "23:00",
        "observacoes": "Coleta regular noturna; disponha os sacos próximo ao horário de passagem.",
        "latitude": -8.0285,
        "longitude": -34.9178,
    },
]


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
                longitude REAL NOT NULL
            )
            """
        )
        cursor.execute("SELECT COUNT(*) as total FROM pontos")
        total = cursor.fetchone()["total"]
        if total == 0:
            cursor.executemany(
                """
                INSERT INTO pontos (
                    nome, cidade, bairro, categoria, tipo, endereco,
                    horario, dias_semana, hora_inicio, hora_fim, observacoes,
                    latitude, longitude
                ) VALUES (
                    :nome, :cidade, :bairro, :categoria, :tipo, :endereco,
                    :horario, :dias_semana, :hora_inicio, :hora_fim, :observacoes,
                    :latitude, :longitude
                )
                """,
                PONTOS_INICIAIS,
            )
            conn.commit()
    finally:
        conn.close()


init_db()


# Página principal
@app.get("/")
def inicio():
    return FileResponse(BASE_DIR / "index.html")


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
        return [dict(row) for row in rows]
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
        return dict(row)
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
                latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()
        novo_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM pontos WHERE id = ?", (novo_id,)).fetchone()
        return dict(row)
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
                hora_fim = ?, observacoes = ?, latitude = ?, longitude = ?
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
                id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pontos WHERE id = ?", (id,)).fetchone()
        return dict(row)
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
