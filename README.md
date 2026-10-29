# ♻️ CittaLixo — Recife & Olinda

Aplicação web e API REST 100% gratuita para identificação de **Ecopontos / Ecoestações fixas** e consulta de **horários de coleta domiciliar** nas cidades de **Olinda e Recife (PE)**.

## ✨ Funcionalidades

- 🗺️ **Mapa Interativo (Leaflet + OpenStreetMap)**: Visualização gratuita de pontos fixos de descarte (marcadores verdes) e rotas/horários de coleta domiciliar (marcadores azuis).
- 🌴🌉 **Filtro por Cidade (Olinda e Recife)**, modalidade (`Ecoponto` ou `Coleta Domiciliar`), tipo de resíduo (`Recicláveis`, `Eletrônicos`, `Entulho`, `Óleo de Cozinha`, `Orgânico`) e busca por bairro/rua.
- 🕒 **Status em Tempo Real**: Indica automaticamente se o ponto está **Aberto agora** ou com **Coleta em andamento** com base no dia da semana e horário.
- 📍 **Perto de Mim (GPS)**: Ordena os pontos pela distância em km até a localização atual do morador (usando fórmula de Haversine no navegador, sem custos de API).
- ➕ **Cadastro Colaborativo com Geocodificação Gratuita**: Permite cadastrar novos pontos clicando direto no mapa ou buscando o endereço gratuitamente via **OpenStreetMap Nominatim**.
- 💾 **Banco de Dados SQLite (`cittalixo.db`)**: Persistência local nativa do Python, já pré-populada com pontos de Olinda e Recife.

## 🚀 Como Executar

### 1. Localmente com Python
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Acesse no navegador: `http://127.0.0.1:8000` (Documentação Swagger da API em `http://127.0.0.1:8000/docs`).

### 2. Com Docker
```bash
docker build -t cittalixo .
docker run -p 8000:8000 cittalixo
```

## 🧪 Como Rodar os Testes

```bash
# Testes automatizados da API (FastAPI TestClient + Pytest)
pytest test_api.py -v

# Testes E2E de interface (Selenium Headless - com o servidor rodando na porta 8000)
python testes_cittalixo.py
```

