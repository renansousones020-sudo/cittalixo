from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    dados = response.json()
    assert dados["status"] == "ok"
    assert "Olinda" in dados["cidades_atendidas"]
    assert "Recife" in dados["cidades_atendidas"]
    assert dados["total_pontos"] >= 1


def test_listar_pontos():
    response = client.get("/pontos")

    assert response.status_code == 200
    pontos = response.json()
    assert isinstance(pontos, list)
    assert len(pontos) >= 2


def test_filtrar_pontos_por_cidade_e_categoria():
    resp_olinda = client.get("/pontos", params={"cidade": "Olinda"})
    assert resp_olinda.status_code == 200
    pontos_olinda = resp_olinda.json()
    assert len(pontos_olinda) >= 1
    assert all(p["cidade"] == "Olinda" for p in pontos_olinda)

    resp_recife = client.get("/pontos", params={"cidade": "Recife"})
    assert resp_recife.status_code == 200
    pontos_recife = resp_recife.json()
    assert len(pontos_recife) >= 1
    assert all(p["cidade"] == "Recife" for p in pontos_recife)

    resp_coleta = client.get("/pontos", params={"categoria": "Coleta Domiciliar"})
    assert resp_coleta.status_code == 200
    assert all(p["categoria"] == "Coleta Domiciliar" for p in resp_coleta.json())


def test_ciclo_completo_crud_e_unicidade_id():
    novo_ponto = {
        "nome": "Ecoponto Teste Olinda",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "categoria": "Ecoponto",
        "tipo": "Eletrônicos, Recicláveis",
        "endereco": "Av. José Augusto Moreira, 500",
        "horario": "Seg a Sex: 08h às 17h",
        "dias_semana": "Seg,Ter,Qua,Qui,Sex",
        "hora_inicio": "08:00",
        "hora_fim": "17:00",
        "observacoes": "Ponto de teste automatizado",
        "latitude": -7.9850,
        "longitude": -34.8410,
    }

    # 1. Criar ponto (201 Created)
    resp_create = client.post("/pontos", json=novo_ponto)
    assert resp_create.status_code == 201
    criado = resp_create.json()
    ponto_id = criado["id"]
    assert criado["nome"] == "Ecoponto Teste Olinda"
    assert criado["cidade"] == "Olinda"
    assert criado["horario"] == "Seg a Sex: 08h às 17h"

    # 2. Buscar ponto por ID (200 OK)
    resp_get = client.get(f"/pontos/{ponto_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == ponto_id

    # 3. Atualizar ponto (200 OK)
    novo_ponto["nome"] = "Ecoponto Teste Olinda Atualizado"
    novo_ponto["horario"] = "Seg a Sáb: 07h às 18h"
    resp_update = client.put(f"/pontos/{ponto_id}", json=novo_ponto)
    assert resp_update.status_code == 200
    assert resp_update.json()["nome"] == "Ecoponto Teste Olinda Atualizado"
    assert resp_update.json()["horario"] == "Seg a Sáb: 07h às 18h"

    # 4. Deletar ponto (200 OK)
    resp_delete = client.delete(f"/pontos/{ponto_id}")
    assert resp_delete.status_code == 200

    # 5. Verificar que busca após deleção retorna 404 Not Found
    resp_missing = client.get(f"/pontos/{ponto_id}")
    assert resp_missing.status_code == 404


def test_ponto_inexistente_retorna_404():
    assert client.get("/pontos/999999").status_code == 404
    assert client.delete("/pontos/999999").status_code == 404
