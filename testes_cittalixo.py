import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try:
    driver.get("http://127.0.0.1:8000")

    wait = WebDriverWait(driver, 10)

    # TESTE 1 - Verificar título
    titulo = wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
    assert titulo.text == "♻️ CittaLixo"
    print("✅ Teste 1 aprovado - Título")

    # TESTE 2 - Verificar mapa
    mapa = driver.find_element(By.ID, "map")
    assert mapa.is_displayed()
    print("✅ Teste 2 aprovado - Mapa")

    # TESTE 3 - Verificar carregamento dos cards dinâmicos da API (Olinda e Recife)
    wait.until(lambda d: len(d.find_elements(By.CLASS_NAME, "card")) >= 2)
    cards = driver.find_elements(By.CLASS_NAME, "card")
    assert len(cards) >= 2
    print(f"✅ Teste 3 aprovado - {len(cards)} Cards carregados da API")

    # TESTE 4 - Verificar Ecoponto Centro (Recife)
    assert "Ecoponto Centro" in driver.page_source
    print("✅ Teste 4 aprovado - Ecoponto Centro (Recife)")

    # TESTE 5 - Verificar endereço do Ecoponto Centro
    assert "Rua do Sol, 100" in driver.page_source
    print("✅ Teste 5 aprovado - Endereço Ecoponto Centro")

    # TESTE 6 - Verificar Ecoponto Bairro Novo (Olinda)
    assert "Ecoponto Bairro Novo" in driver.page_source
    print("✅ Teste 6 aprovado - Ecoponto Bairro Novo (Olinda)")

    # TESTE 7 - Verificar exibição de horários de funcionamento/coleta
    assert "Horários:" in driver.page_source or "Seg a Sáb" in driver.page_source
    print("✅ Teste 7 aprovado - Horários de coleta exibidos")

    print("\n🎉 Todos os testes passaram!")

finally:
    driver.quit()
