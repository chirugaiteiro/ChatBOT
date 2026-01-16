import streamlit as st
import requests
import json
import time

# --- Configuração da Página ---
st.set_page_config(page_title="Lab Mutum: Licenças IMASUL", page_icon="🏗️", layout="wide")

st.title("🧪 Diagnóstico de Conectividade: Licenças Ambientais")
st.markdown("""
**Alvo:** Base de Licenças Ambientais do IMASUL (Camada 16).
**Objetivo:** Verificar se o Python consegue baixar os DADOS brutos (GeoJSON).
Se funcionar aqui, o Proxy resolverá o problema de CORB no sistema principal.
""")

st.divider()

# --- 1. A Configuração ---
# O Arquiteto forneceu a URL base. O Engenheiro adiciona '/16/query' para acessar os dados.
BASE_URL = "https://www.pinms.ms.gov.br/arcgis/rest/services/IMASUL/licencas_ambientais/MapServer"
LAYER_ID = 16
TARGET_URL = f"{BASE_URL}/{LAYER_ID}/query"

# Parâmetros para pedir GeoJSON
PARAMS = {
    "where": "1=1",           # Pega tudo (filtro padrão)
    "outFields": "*",         # Pega todas as colunas
    "f": "geojson",           # O formato que o navegador costuma bloquear
    "resultRecordCount": 10   # LIMITA a 10 itens para o teste ser rápido e não travar
}

st.subheader("1. Configuração do Disparo")
col1, col2 = st.columns([2, 1])
with col1:
    st.info(f"📡 **URL Alvo:** `{TARGET_URL}`")
with col2:
    st.json(PARAMS)

# --- 2. O Teste ---
st.subheader("2. Executando Teste...")

if st.button("🚀 Disparar Requisição (Simular Proxy)", type="primary"):
    
    start_time = time.time()
    
    try:
        with st.status("Negociando com servidor do IMASUL...", expanded=True) as status:
            
            # Headers para "enganar" firewalls simples, parecendo um navegador
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MutumOS/Testing'
            }
            
            st.write("Enviando requisição...")
            
            # O DISPARO REAL
            response = requests.get(TARGET_URL, params=PARAMS, headers=headers, timeout=20)
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                # Tenta ler como JSON
                try:
                    data = response.json()
                    features = data.get('features', [])
                    count = len(features)
                    
                    if count > 0:
                        status.update(label="✅ SUCESSO! Dados capturados.", state="complete", expanded=False)
                        st.success(f"Conexão perfeita! Recebemos {count} registros em {elapsed:.2f}s.")
                        
                        # --- 3. Análise dos Dados ---
                        st.divider()
                        st.subheader("3. O que conseguimos ler?")
                        
                        # Mostra as propriedades do primeiro item para vermos os dados
                        primeiro_item = features[0]['properties']
                        st.write("**Exemplo de Dados (Propriedades do 1º registro):**")
                        st.dataframe(primeiro_item)
                        
                        st.success("""
                        **CONCLUSÃO DO ENGENHEIRO:**
                        O servidor aceita conexões externas de script! 
                        Isso confirma que podemos usar o Proxy para trazer esses dados para o mapa
                        e gerar popups com essas informações.
                        """)
                        
                    else:
                        status.update(label="⚠️ Resposta vazia.", state="error")
                        st.warning("O servidor respondeu 200 OK, mas não mandou nenhuma 'feature' (dado geográfico).")
                        st.json(data)

                except json.JSONDecodeError:
                    status.update(label="❌ Erro de Formato", state="error")
                    st.error("O servidor respondeu, mas não é um JSON válido. Provavelmente é HTML de erro.")
                    st.code(response.text[:500], language="html")
                    
            else:
                status.update(label="❌ Erro HTTP", state="error")
                st.error(f"Erro {response.status_code}: {response.reason}")

    except Exception as e:
        st.error(f"❌ Falha de Conexão: {str(e)}")
