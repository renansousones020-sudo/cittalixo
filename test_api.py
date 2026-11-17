from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    dados = response.json()
    assert dados["status"] == "ok"
    assert dados["versao"] == "3.4.0"
    assert "Olinda" in dados["cidades_atendidas"]
    assert "Recife" in dados["cidades_atendidas"]
    assert dados["total_pontos"] >= 20


def test_listar_pontos():
    response = client.get("/pontos")

    assert response.status_code == 200
    pontos = response.json()
    assert isinstance(pontos, list)
    assert len(pontos) >= 2


def test_filtrar_pontos_por_cidade_categoria_e_dia_semana():
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

    resp_seg = client.get("/pontos", params={"dia_semana": "Seg"})
    assert resp_seg.status_code == 200
    pontos_seg = resp_seg.json()
    assert len(pontos_seg) >= 1
    assert all("Seg" in p["dias_semana"] for p in pontos_seg)


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


def test_ciclo_denuncias_ponto_critico_classificacao_e_resolucao_admin():
    # 1. Listar denúncias iniciais
    resp_list = client.get("/denuncias")
    assert resp_list.status_code == 200
    assert isinstance(resp_list.json(), list)
    assert len(resp_list.json()) >= 1

    # 2. Criar nova denúncia crítica
    nova_den = {
        "titulo": "Entulho na calçada de teste",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "endereco": "Av. Getúlio Vargas, 300",
        "tipo_residuo": "Entulho e restos de poda",
        "gravidade": "Crítico",
        "descricao": "Teste automatizado de ponto crítico",
        "status": "Pendente",
        "data_registro": "Hoje",
        "confirmacoes": 1,
        "nao_esta_mais": 0,
        "latitude": -7.9920,
        "longitude": -34.8425,
    }
    resp_create = client.post("/denuncias", json=nova_den)
    assert resp_create.status_code == 201
    criada = resp_create.json()
    den_id = criada["id"]
    assert criada["status"] == "Pendente"
    assert criada["confirmacoes"] == 1
    assert criada["nao_esta_mais"] == 0

    # 3. Classificar que ainda está lá ("Ainda está lá! +1")
    resp_upvote = client.put(f"/denuncias/{den_id}/apoiar")
    assert resp_upvote.status_code == 200
    assert resp_upvote.json()["confirmacoes"] == 2

    # 4. Classificar que já foi limpo ("Já foi limpo / Não está mais lá +1")
    resp_clean = client.put(f"/denuncias/{den_id}/nao-esta-mais")
    assert resp_clean.status_code == 200
    assert resp_clean.json()["nao_esta_mais"] == 1

    # 5. Marcar oficialmente como Resolvido (Admin)
    resp_resolve = client.put(f"/denuncias/{den_id}/resolver")
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == "Resolvido"

    # 6. Excluir denúncia (Admin)
    resp_del = client.delete(f"/denuncias/{den_id}")
    assert resp_del.status_code == 200


def test_ciclo_catatreco_agendamento_e_protocolo():
    # 1. Listar solicitações de Cata-Treco iniciais
    resp_list = client.get("/catatreco")
    assert resp_list.status_code == 200
    assert isinstance(resp_list.json(), list)
    assert len(resp_list.json()) >= 1

    # 2. Criar nova solicitação de Cata-Treco
    novo_ct = {
        "solicitante": "Morador Teste Automatizado",
        "cidade": "Recife",
        "bairro": "Boa Viagem",
        "endereco": "Av. Conselheiro Aguiar, 1500",
        "itens_volumosos": "1 sofá velho e 1 geladeira quebrada",
        "turno_preferido": "Manhã (08h às 12h)",
        "data_agendada": "Sexta-feira",
        "observacoes": "Deixar na calçada",
        "status": "Agendado",
        "latitude": -8.1180,
        "longitude": -34.8990,
    }
    resp_create = client.post("/catatreco", json=novo_ct)
    assert resp_create.status_code == 201
    criado = resp_create.json()
    ct_id = criado["id"]
    assert criado["status"] == "Agendado"
    assert criado["protocolo"].startswith("CT-2026-")

    # 3. Marcar como Recolhido (Admin)
    resp_rec = client.put(f"/catatreco/{ct_id}/recolher")
    assert resp_rec.status_code == 200
    assert resp_rec.json()["status"] == "Recolhido"

    # 4. Excluir agendamento de Cata-Treco (Admin)
    resp_del = client.delete(f"/catatreco/{ct_id}")
    assert resp_del.status_code == 200


def test_busca_sem_acento_votacao_unica_e_seguranca():
    # 1. Busca sem acento no backend (ex: 'sitio historico' encontra 'Sítio Histórico', 'torroes' encontra 'Torrões')
    resp_busca = client.get("/pontos", params={"busca": "torroes"})
    assert resp_busca.status_code == 200
    assert any("Torrões" in p["bairro"] or "Torrões" in p["nome"] for p in resp_busca.json())

    # 2. Rejeição de token de Admin inválido (403 Forbidden)
    resp_forb = client.delete("/pontos/1", headers={"X-Admin-Token": "token_invalido"})
    assert resp_forb.status_code == 403

    # 3. Validação de foto_base64 contra URI malicioso (422 Unprocessable Entity)
    den_invalida = {
        "titulo": "Teste foto maliciosa",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "endereco": "Rua Teste, 10",
        "foto_base64": "javascript:alert(1)",
        "latitude": -8.001,
        "longitude": -34.842,
    }
    assert client.post("/denuncias", json=den_invalida).status_code == 422

    # 4. Ciclo de voto único aberto (/denuncias/{id}/votar) com idempotência
    den_valida = {
        "titulo": "Teste votação única",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "endereco": "Rua do Sol, 50",
        "latitude": -8.062,
        "longitude": -34.881,
    }
    criada = client.post("/denuncias", json=den_valida).json()
    den_id = criada["id"]
    try:
        # Votar 'ainda_la'
        r1 = client.put(f"/denuncias/{den_id}/votar", json={"voto_anterior": None, "voto_novo": "ainda_la"}).json()
        assert r1["confirmacoes"] == 2
        assert r1["nao_esta_mais"] == 0

        # Idempotência se repetir o mesmo payload (voto_anterior == voto_novo)
        r_idem = client.put(f"/denuncias/{den_id}/votar", json={"voto_anterior": "ainda_la", "voto_novo": "ainda_la"}).json()
        assert r_idem["confirmacoes"] == 2

        # Trocar voto de 'ainda_la' para 'ja_recolhido'
        r2 = client.put(f"/denuncias/{den_id}/votar", json={"voto_anterior": "ainda_la", "voto_novo": "ja_recolhido"}).json()
        assert r2["confirmacoes"] == 1
        assert r2["nao_esta_mais"] == 1

        # Desfazer voto ('ja_recolhido' -> None)
        r3 = client.put(f"/denuncias/{den_id}/votar", json={"voto_anterior": "ja_recolhido", "voto_novo": None}).json()
        assert r3["confirmacoes"] == 1
        assert r3["nao_esta_mais"] == 0
    finally:
        client.delete(f"/denuncias/{den_id}", headers={"X-Admin-Token": "admin123"})


def test_validacao_geografica_e_moderacao_admin():
    # 1. Rejeita coordenada no meio do Oceano Atlântico (422 Unprocessable Entity)
    ponto_oceano = {
        "nome": "Ponto em Alto Mar",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis",
        "endereco": "Oceano Atlântico",
        "latitude": -8.0010,
        "longitude": -34.7800,
    }
    resp_oceano = client.post("/pontos", json=ponto_oceano)
    assert resp_oceano.status_code == 422

    # 2. Rejeita coordenada fora da Região Metropolitana de Olinda/Recife (ex: São Paulo)
    den_fora = {
        "titulo": "Denúncia fora de cobertura",
        "cidade": "Recife",
        "bairro": "Boa Vista",
        "endereco": "Av. Paulista, 1000",
        "latitude": -23.5614,
        "longitude": -46.6558,
    }
    resp_fora = client.post("/denuncias", json=den_fora)
    assert resp_fora.status_code == 422

    # 3. Envio de cidadão (X-User-Role: usuario) entra com aprovado_admin = 0 até o Admin aprovar
    sugestao_cidadao = {
        "nome": "PEV Sugerido pelo Morador",
        "cidade": "Olinda",
        "bairro": "Casa Caiada",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis e Óleo",
        "endereco": "Av. Carlos de Lima Cavalcanti, 500",
        "latitude": -7.9855,
        "longitude": -34.8412,
    }
    resp_sug = client.post("/pontos", json=sugestao_cidadao, headers={"X-User-Role": "usuario"})
    assert resp_sug.status_code == 201
    ponto_sug = resp_sug.json()
    ponto_sug_id = ponto_sug["id"]
    try:
        assert ponto_sug["aprovado_admin"] == 0

        # Filtrar apenas aprovados não deve incluir o pendente
        aprovados = client.get("/pontos", params={"aprovado_admin": 1}).json()
        assert all(p["id"] != ponto_sug_id for p in aprovados)

        # Admin aprova o ponto sugerido
        resp_aprov = client.put(f"/pontos/{ponto_sug_id}/aprovar", headers={"X-Admin-Token": "admin123"})
        assert resp_aprov.status_code == 200
        assert resp_aprov.json()["aprovado_admin"] == 1
    finally:
        client.delete(f"/pontos/{ponto_sug_id}", headers={"X-Admin-Token": "admin123"})


def test_perfis_usuario_moderador_e_admin_com_senhas_especiais():
    from urllib.parse import quote

    # 1. Login livre para Usuário
    r_user = client.post("/auth/login", json={"perfil": "usuario", "senha": ""})
    assert r_user.status_code == 200
    assert r_user.json()["perfil"] == "usuario"

    # 2. Login Moderador com senha segura contendo 'ç' e caracteres especiais
    senha_mod = "M0d#CittaLix0!ç26"
    r_mod = client.post("/auth/login", json={"perfil": "moderador", "senha": senha_mod})
    assert r_mod.status_code == 200
    assert r_mod.json()["perfil"] == "moderador"

    # 3. Senha incorreta para Moderador ou Admin deve retornar 401
    assert client.post("/auth/login", json={"perfil": "moderador", "senha": "errada"}).status_code == 401
    assert client.post("/auth/login", json={"perfil": "admin", "senha": senha_mod}).status_code == 401

    # 4. Login Admin com senha segura contendo 'ç' e '@'
    senha_adm = "Adm@CittaLix0#ç2026!"
    r_adm = client.post("/auth/login", json={"perfil": "admin", "senha": senha_adm})
    assert r_adm.status_code == 200
    assert r_adm.json()["perfil"] == "admin"

    # 5. Moderador pode aprovar sugestão, mas NÃO pode deletar ponto oficial (403 Forbidden)
    sugestao = {
        "nome": "PEV Teste Moderador",
        "cidade": "Olinda",
        "bairro": "Bairro Novo",
        "categoria": "Ecoponto",
        "tipo": "Recicláveis",
        "endereco": "Av. Getúlio Vargas, 100",
        "latitude": -7.9950,
        "longitude": -34.8420,
    }
    criado = client.post("/pontos", json=sugestao, headers={"X-User-Role": "usuario"}).json()
    pid = criado["id"]
    try:
        assert criado["aprovado_admin"] == 0
        # Moderador aprova com cabeçalho codificado (suportando 'ç')
        r_aprov_mod = client.put(f"/pontos/{pid}/aprovar", headers={"X-Admin-Token": quote(senha_mod)})
        assert r_aprov_mod.status_code == 200
        assert r_aprov_mod.json()["aprovado_admin"] == 1

        # Moderador tenta excluir ponto -> bloqueado com 403
        r_del_mod = client.delete(f"/pontos/{pid}", headers={"X-Admin-Token": quote(senha_mod)})
        assert r_del_mod.status_code == 403
    finally:
        # Admin exclui ponto -> permitido com 200
        r_del_adm = client.delete(f"/pontos/{pid}", headers={"X-Admin-Token": quote(senha_adm)})
        assert r_del_adm.status_code == 200
