# ♻️ CittaLixo v3.0.0 — Recife & Olinda

Aplicação web progressiva (PWA) e API REST **100% gratuita** para identificação de **Ecopontos / Ecoestações fixas**, visualização de **rotas reais e horários dos caminhões de coleta domiciliar**, mapeamento colaborativo de **pontos críticos de lixo acumulado (denúncias)** e **educação ambiental** nas cidades de **Olinda e Recife (PE)**.

---

## 📌 Histórico de Evolução e Versões

- **v1.0.0 (Original)**: Protótipo inicial em memória com apenas 1 ponto no Recife e `index.html` estático desconectado da API.
- **v2.0.0**: Integração completa Front-end/Back-end (`fetch('/pontos')`), banco de dados persistente SQLite (`cittalixo.db`), expansão para **Olinda e Recife**, filtros combinados, status em tempo real (*Aberto agora*), geolocalização GPS (*Perto de Mim* via Haversine) e geocodificação gratuita via Nominatim.
- **v3.0.0 (Versão Atual Completa)**:
  - 🛣️ **Rotas Reais nas Ruas (OSRM/OpenStreetMap)**: Traçado viário real sem atravessar casas ou rios, com **setas direcionais (`➤`)** e **animação do caminhão baseada no horário real do usuário** (com alerta transparente de simulação estimada).
  - ✏️ **CRUD Completo na Interface**: Botões de **Editar (`PUT`)** e **Excluir (`DELETE`)** diretamente em cada card.
  - ⚠️ **Aba Exclusiva de Denúncias de Lixo Acumulado**: Pino laranja crítico no mapa, filtro de pendentes/resolvidas e botão **Marcar como Resolvido** (`/denuncias`).
  - 📚 **Aba de Guia Rápido de Descarte + Mini-Quiz Interativo**.
  - 📊 **Dashboard de Estatísticas em Tempo Real** no topo da página.
  - 📱 **PWA (Progressive Web App)** com `manifest.json` e `sw.js` (funcionamento com cache offline e instalável no celular).
  - ⚡ **Script `iniciar_servidor.bat`** para ligar o servidor e abrir o navegador automaticamente com 1 clique.

---

## 🚀 Como Executar e Testar

### 1. Com 1 Clique no Windows (`iniciar_servidor.bat`)
Dê **dois cliques** em [`iniciar_servidor.bat`](./iniciar_servidor.bat). Ele inicia o Uvicorn na porta `8000` e abre `http://127.0.0.1:8000` no navegador.

### 2. Pelo Terminal Python
```bash
..\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload
```
- **Aplicação Web (Mapa Interativo)**: `http://127.0.0.1:8000`
- **Documentação Swagger UI**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/health`

### 3. Suítes de Testes Automatizados
```bash
# Testes de API e Banco SQLite (Pytest + FastAPI TestClient - 6 suítes incluindo pontos e denúncias)
..\.venv\Scripts\pytest.exe test_api.py -v

# Testes End-to-End de Interface no Navegador (Selenium Headless)
..\.venv\Scripts\python.exe testes_cittalixo.py
```

---

## 📄 Relatórios em PDF no Projeto

- [`Relatorio_Melhorias_e_Testes_CittaLixo.pdf`](./Relatorio_Melhorias_e_Testes_CittaLixo.pdf): Relatório completo de evolução (da v1.0.0 até a **v3.0.0**) e guia de testes.
- [`Relatorio_Fontes_e_Metodologia_CittaLixo.pdf`](./Relatorio_Fontes_e_Metodologia_CittaLixo.pdf): Fontes de dados geográficos, ambientais e metodologia de simulação.
