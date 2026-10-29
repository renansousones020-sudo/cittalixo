from pathlib import Path
from typing import List, Optional
import json
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
        "e rotas/horários de coleta domiciliar em Recife e Olinda."
    ),
    version="2.1.0",
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
        description="Lista de coordenadas [[lat, lng], ...] que desenham o trajeto do caminhão no mapa",
    )


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
    # --- OLINDA: ROTAS E HORÁRIOS DE COLETA DOMICILIAR ---
    {
        "nome": "Coleta Domiciliar - Rio Doce e Jardim Atlântico",
        "cidade": "Olinda",
        "bairro": "Rio Doce",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Rota: Terminal Rio Doce -> Av. Brasil -> Av. Nápoles -> Av. Fagundes Varela (Jardim Atlântico)",
        "horario": "Seg, Qua e Sex: 07h às 11h30",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "07:00",
        "hora_fim": "11:30",
        "observacoes": "Caminhão inicia no Terminal de Rio Doce às 07h e segue pela Av. Brasil até Jardim Atlântico.",
        "latitude": -7.9672,
        "longitude": -34.8364,
        "rota_coordenadas": [
            [-7.9585, -34.8368],
            [-7.9628, -34.8366],
            [-7.9672, -34.8364],
            [-7.9718, -34.8375],
            [-7.9765, -34.8388],
            [-7.9802, -34.8395],
        ],
    },
    {
        "nome": "Coleta Domiciliar Noturna - Bairro Novo e Casa Caiada",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar",
        "endereco": "Rota: Av. José Augusto Moreira -> Av. Getúlio Vargas -> Praça 12 de Março -> Orla de Bairro Novo",
        "horario": "Seg a Sáb: 18h30 às 23h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "18:30",
        "hora_fim": "23:00",
        "observacoes": "Coleta noturna diária percorrendo o corredor principal de Casa Caiada e Bairro Novo.",
        "latitude": -7.9918,
        "longitude": -34.8427,
        "rota_coordenadas": [
            [-7.9815, -34.8412],
            [-7.9864, -34.8420],
            [-7.9918, -34.8427],
            [-7.9975, -34.8435],
            [-8.0032, -34.8442],
            [-8.0038, -34.8410],
            [-7.9986, -34.8408],
        ],
    },
    {
        "nome": "Coleta Domiciliar - Sítio Histórico e Varadouro",
        "cidade": "Olinda",
        "bairro": "Varadouro",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar, Recicláveis",
        "endereco": "Rota: Mercado Eufrásio Barbosa (Varadouro) -> Av. Sigismundo Gonçalves -> Carmo -> Alto da Sé -> Amparo",
        "horario": "Ter, Qui e Sáb: 06h30 às 10h30",
        "dias_semana": "Ter,Qui,Sab",
        "hora_inicio": "06:30",
        "hora_fim": "10:30",
        "observacoes": "Caminhão compactador reduzido adaptado para subir as ladeiras do Centro Histórico.",
        "latitude": -8.0156,
        "longitude": -34.8538,
        "rota_coordenadas": [
            [-8.0205, -34.8565],
            [-8.0178, -34.8548],
            [-8.0156, -34.8538],
            [-8.0172, -34.8492],
            [-8.0138, -34.8485],
            [-8.0112, -34.8515],
        ],
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
        "endereco": "Rota: Largo da Paz (Casa Amarela) -> Estrada do Arraial -> Tamarineira -> Av. Norte -> Espinheiro",
        "horario": "Seg, Qua e Sex: 19h às 23h",
        "dias_semana": "Seg,Qua,Sex",
        "hora_inicio": "19:00",
        "hora_fim": "23:00",
        "observacoes": "Coleta regular noturna; disponha os sacos próximo ao horário de passagem.",
        "latitude": -8.0285,
        "longitude": -34.9178,
        "rota_coordenadas": [
            [-8.0252, -34.9235],
            [-8.0285, -34.9178],
            [-8.0318, -34.9105],
            [-8.0355, -34.9022],
            [-8.0402, -34.8965],
        ],
    },
    {
        "nome": "Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "categoria": "Coleta Domiciliar",
        "tipo": "Orgânico / Domiciliar, Recicláveis",
        "endereco": "Rota: Av. Conde da Boa Vista -> Rua da Aurora -> Ponte Duarte Coelho -> Av. Guararapes",
        "horario": "Diariamente: 20h às 23h50",
        "dias_semana": "Dom,Seg,Ter,Qua,Qui,Sex,Sab",
        "hora_inicio": "20:00",
        "hora_fim": "23:50",
        "observacoes": "Rota noturna de alto fluxo comercial e residencial pelo eixo central do Recife.",
        "latitude": -8.0578,
        "longitude": -34.8875,
        "rota_coordenadas": [
            [-8.0558, -34.8962],
            [-8.0578, -34.8875],
            [-8.0565, -34.8812],
            [-8.0615, -34.8798],
            [-8.0642, -34.8780],
        ],
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

        # Migração automática caso a tabela já existisse sem a coluna rota_coordenadas
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
            # Atualiza os registros iniciais que ainda estavam com rota vazia
            for item in PONTOS_INICIAIS:
                if item.get("rota_coordenadas"):
                    cursor.execute(
                        """
                        UPDATE pontos
                        SET rota_coordenadas = ?, endereco = ?, observacoes = ?
                        WHERE nome = ? AND (rota_coordenadas = '[]' OR rota_coordenadas IS NULL)
                        """,
                        (
                            json.dumps(item["rota_coordenadas"]),
                            item["endereco"],
                            item["observacoes"],
                            item["nome"],
                        ),
                    )
            # Garante também que a nova rota do Centro do Recife exista
            existe_centro_rota = cursor.execute(
                "SELECT id FROM pontos WHERE nome = ?",
                ("Coleta Domiciliar - Centro do Recife (Boa Vista / Santo Antônio)",),
            ).fetchone()
            if not existe_centro_rota:
                ultimo = dict(PONTOS_INICIAIS[-1])
                ultimo["rota_coordenadas"] = json.dumps(ultimo["rota_coordenadas"])
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
                    ultimo,
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
