import streamlit as st
import requests
import json
import time

# --- Configuração da Página ---
st.set_page_config(page_title="Lab de Teste Mutum: IMASUL", page_icon="🧪", layout="wide")

st.title("🧪 Diagnóstico de Conectividade - Mutum V2.0")
st.markdown("""
**Objetivo:** Simular exatamente a requisição que o Frontend faz, mas via **Python (Backend)**.
Se este teste funcionar, confirma que o erro de CORB é exclusivo do navegador e que a solução de Proxy é a correta.
""")

st.divider()

# --- 1. A Configuração (Cópia fiel do seu layers_environmental.js) ---
TARGET_URL = "http://cartografia.imasul.ms.gov.br/server/rest/services/LIMITES_ADMINISTRATIVOS/MapServer/0/query"
PARAMS = {
    "where": "1=1",
    "outFields": "*",
    "f": "geojson"  # <--- O formato que causa o CORB no navegador
}

st.subheader("1. Parâmetros da Requisição")
col1, col2 = st.columns(2)
with col1:
    st.code(f"URL: {TARGET_URL}", language="http")
with col2:
    st.json(PARAMS)

# --- 2. O Teste ---
st.subheader("2. Executando Teste de Conexão...")

if st.button("🚀 Disparar Requisição (Modo Python/Proxy)", type="primary"):
    
    start_time = time.time()
    
    try:
        with st.status("Conectando ao servidor do IMASUL...", expanded=True) as status:
            
            # Simulando um navegador real para evitar bloqueios simples de bot
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            st.write("📡 Enviando headers...", headers)
            
            # A REQUISIÇÃO REAL
            response = requests.get(TARGET_URL, params=PARAMS, headers=headers, timeout=15)
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                status.update(label="✅ Sucesso! Dados recebidos.", state="complete", expanded=False)
                
                # Processa o JSON
                data = response.json()
                features_count = len(data.get('features', []))
                
                st.success(f"Conexão estabelecida em {elapsed:.2f} segundos.")
                
                # --- 3. O Veredito ---
                st.divider()
                st.header("3. Veredito Técnico")
                
                col_a, col_b = st.columns([1, 2])
                
                with col_a:
                    st.metric(label="Status HTTP", value=response.status_code)
                    st.metric(label="Feições Encontradas", value=features_count)
                    
                    if features_count > 0:
                        st.info("💡 **Conclusão:** O servidor permite acesso a dados via Python! O problema no site atual é puramente bloqueio de navegador (CORS).")
                    else:
                        st.warning("⚠️ O JSON veio vazio. Verifique os parâmetros.")

                with col_b:
                    st.subheader("Amostra dos Dados (GeoJSON)")
                    st.json(data)
                    
            else:
                status.update(label="❌ Erro na resposta.", state="error")
                st.error(f"O servidor respondeu com erro: {response.status_code}")
                st.text(response.text)

    except Exception as e:
        st.error(f"❌ Falha crítica na conexão: {str(e)}")
