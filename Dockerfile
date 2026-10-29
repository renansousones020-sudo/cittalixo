# 1. Usa uma imagem oficial do Python ultra leve (Alpine ou Slim)
FROM python:3.11-slim

# 2. Define a pasta dentro do container onde o código vai ficar
WORKDIR /app

# 3. Copia a lista de dependências para dentro do container
COPY requirements.txt .

# 4. Instala as dependências dentro do container sem salvar cache (para ficar mais leve)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia todo o restante do seu código (incluindo o index.html e o arquivo .py)
COPY . .

# 6. Expõe a porta 8000 (padrão que vamos usar para a API)
EXPOSE 8000

# 7. Comando para ligar a API usando o Uvicorn quando o container iniciar
# Substitua "main:app" pelo nome do seu arquivo. Se o seu arquivo se chamar "api.py", mude para "api:app"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]