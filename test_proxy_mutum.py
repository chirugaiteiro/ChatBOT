import streamlit as st
import pandas as pd
import openrouteservice
from geopy.distance import geodesic
import re
import folium
from streamlit_folium import st_folium
import json

st.set_page_config(page_title="Roteirizador Híbrido", layout="wide")

st.title("🚛 Calculadora de Rota: Asfalto vs Chão")
st.markdown("""
**Instruções:**
Faça o upload da sua planilha (CSV ou Excel) contendo a coluna **Coordenadas** ou digite os dados manualmente.
O sistema aceita:
1. **Decimal Padrão:** `-19.55, -54.22`
2. **GPS/DMS:** `19°15'35.2"S 57°14'00.1"W`
3. **Excel BR:** `-19,55; -54,22`
""")

# --- CONSTANTES ---
UNPAVED_TYPES = ['unpaved', 'compacted', 'dirt', 'earth', 'gravel', 'fine_gravel', 'grass', 'ground', 'sand', 'wood', 'mud', 'clay', 'salt', 'ice', 'snow']

ORS_SURFACE_MAPPING = {
    0: "unknown", 1: "paved", 2: "unpaved", 3: "asphalt", 4: "concrete",
    5: "cobblestone", 6: "metal", 7: "wood", 8: "compacted", 9: "fine_gravel",
    10: "gravel", 11: "dirt", 12: "earth", 13: "ice", 14: "salt", 15: "sand",
    16: "woodchips", 17: "grass", 18: "grass_paver"
}

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurações")
    api_key = st.text_input("API Key (OpenRouteService):", type="password")

# --- FUNÇÕES DE LIMPEZA E CONVERSÃO ---
def dms_para_decimal(dms_str):
    dms_str = dms_str.replace(',', '.')
    dms_str = dms_str.upper().strip()
    sign = -1 if 'S' in dms_str or 'W' in dms_str or 'O' in dms_str else 1
    
    parts = re.split(r'[^\d\.]+', dms_str)
    parts = [float(x) for x in parts if x]
    
    if len(parts) >= 3:
        return sign * (parts[0] + (parts[1] / 60) + (parts[2] / 3600))
    elif len(parts) >= 2:
        return sign * (parts[0] + (parts[1] / 60))
    elif len(parts) == 1:
        return sign * float(parts[0])
    return None

def limpar_e_converter(texto):
    texto = str(texto).strip().upper()
    try:
        if any(c in texto for c in ['S', 'W', 'N', 'E', 'O', '°', 'º']):
            padrao = r"[\d\.,]+[°º\s]+[\d\.,]+[′'\s]+[\d\.,]+[″\"\s]*[NSEWO]"
            matches = re.findall(padrao, texto)
            if len(matches) >= 2:
                lat = dms_para_decimal(matches[0])
                lon = dms_para_decimal(matches[1])
                return lat, lon
            return None, None # Evita vazar para o validador decimal se for GMS mal formatado

        texto_limpo = texto.replace(';', ' ').replace(',', '.') 
        numeros = re.findall(r'-?\d+\.\d+|-?\d+', texto.replace(',', '.'))
        
        if len(numeros) >= 2:
            lat = float(numeros[0])
            lon = float(numeros[1])
            if abs(lat) <= 90 and abs(lon) <= 180:
                return lat, lon
    except Exception as e:
        pass
    return None, None

# --- FUNÇÃO DE GERAÇÃO DE MAPA ---
def gerar_mapa_folium(route, coords_ors):
    start_lat = coords_ors[0][1]
    start_lon = coords_ors[0][0]
    m = folium.Map(location=[start_lat, start_lon], zoom_start=12)

    extras = route['features'][0]['properties']['extras']['surface']
    geometry = route['features'][0]['geometry']['coordinates']
    
    lookup_surface = {}
    lookup_surface.update(ORS_SURFACE_MAPPING) 
    
    if 'summary' in extras:
        for item in extras['summary']:
            if 'name' in item: 
                lookup_surface[item['value']] = item['name']

    surface_segments = extras['values']
    
    for seg in surface_segments:
        start_idx, end_idx, surf_type = seg
        if isinstance(surf_type, int) and surf_type in lookup_surface:
            surf_type = lookup_surface[surf_type]
            
        segment_coords = [[c[1], c[0]] for c in geometry[start_idx : end_idx + 1]]
        
        eh_chao = surf_type in UNPAVED_TYPES
        color = '#8B4513' if eh_chao else '#555555'
        
        tipo_pt = "Chão (+9%)" if eh_chao else "Asfalto (+3%)"
        tooltip_text = f"Superfície: {surf_type} | Status: {tipo_pt}"

        folium.PolyLine(segment_coords, color=color, weight=5, opacity=0.8, tooltip=tooltip_text).add_to(m)

    for i, coord in enumerate(coords_ors):
        folium.Marker(
            location=[coord[1], coord[0]],
            tooltip=f"Ponto {i+1}",
            icon=folium.Icon(color="green" if i == 0 else "red" if i == len(coords_ors)-1 else "blue", icon="info-sign")
        ).add_to(m)

    bbox = route['bbox'] 
    m.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])
    
    legend_html = '''
     <div style="position: fixed; bottom: 50px; right: 50px; width: 130px; height: 90px; z-index:9999; font-size:14px; background-color: white; border:2px solid grey; border-radius:6px; padding: 10px; opacity: 0.9;">
     <b>Legenda</b><br>
     <i style="background: #555555; width: 18px; height: 18px; float: left; margin-right: 8px; opacity: 0.8;"></i> Asfalto<br>
     <i style="background: #8B4513; width: 18px; height: 18px; float: left; margin-right: 8px; opacity: 0.8;"></i> Chão
     </div>
     '''
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

# --- PROCESSAMENTO DO LOTE ---
def processar_rota(client, dados_carga):
    coords_raw_list = dados_carga['Coordenada'].tolist()
    total_manual = dados_carga['KM Adicional'].fillna(0).sum()
    
    coords_ors = []
    coords_gmaps_orig = []
    
    for c_raw in coords_raw_list:
        lat, lon = limpar_e_converter(c_raw)
        
        if lat is None:
            # Corrigido: Retornando 8 valores para evitar ValueError (Unpacking Error)
            return None, None, None, None, None, None, None, f"Erro no formato da coordenada: {c_raw}"
            
        coords_ors.append([lon, lat])
        coords_gmaps_orig.append(f"{lat},{lon}")

    if len(coords_ors) < 2:
        return None, None, None, None, None, None, None, "Erro: Mínimo 2 pontos necessários para traçar uma rota."

    try:
        route = client.directions(
            coordinates=coords_ors,
            profile='driving-hgv',
            format='geojson',
            extra_info=['surface'],
        )
    except Exception as e:
        return None, None, None, None, None, None, None, f"Erro API: {e}"

    extras = route['features'][0]['properties']['extras']['surface']
    geometry = route['features'][0]['geometry']['coordinates']
    dist_paved = 0
    dist_unpaved = 0
    
    lookup_surface = {}
    lookup_surface.update(ORS_SURFACE_MAPPING) 
    
    if 'summary' in extras:
        for item in extras['summary']:
            if 'name' in item: 
                lookup_surface[item['value']] = item['name']

    debug_segments = []
    resumo_tipos = {} 
    
    for seg in extras['values']:
        start, end, surf = seg[0], seg[1], seg[2]
        
        if isinstance(surf, int) and surf in lookup_surface:
            surf = lookup_surface[surf]
            
        seg_d = 0
        for i in range(start, end):
            p1, p2 = geometry[i], geometry[i+1]
            seg_d += geodesic((p1[1], p1[0]), (p2[1], p2[0])).meters
        
        is_unpaved = surf in UNPAVED_TYPES
        
        if is_unpaved:
            dist_unpaved += seg_d
        else:
            dist_paved += seg_d
            
        surf_key = str(surf) if surf else "Não Informado (Assumido Asfalto)"
        if surf_key not in resumo_tipos:
            resumo_tipos[surf_key] = 0
        resumo_tipos[surf_key] += seg_d
            
        p_start = geometry[start] 
        p_end = geometry[end]     

        debug_segments.append({
            "Tag_Original": surf,
            "Classificacao_App": "Chão" if is_unpaved else "Asfalto",
            "Distancia_m": round(seg_d, 1),
            "Coord_Inicio": f"{p_start[1]:.5f}, {p_start[0]:.5f}",
            "Coord_Fim": f"{p_end[1]:.5f}, {p_end[0]:.5f}"
        })

    km_paved = dist_paved / 1000
    km_unpaved = dist_unpaved / 1000
    total = (km_unpaved * 1.09) + (km_paved * 1.03) + total_manual

    # Corrigido: Link funcional do Google Maps
    link = "https://www.google.com/maps/dir/" + "/".join(coords_gmaps_orig)
    
    detalhes = {
        "Asfalto (KM)": round(km_paved, 2),
        "Chão (KM)": round(km_unpaved, 2),
        "Adicional (KM)": round(total_manual, 2),
        "Custo Asfalto (+3%)": round(km_paved * 1.03, 2),
        "Custo Chão (+9%)": round(km_unpaved * 1.09, 2)
    }
    
    return total, link, detalhes, route, coords_ors, debug_segments, resumo_tipos, None

# --- INTERFACE ---
if 'dados_rota' not in st.session_state:
    st.session_state['dados_rota'] = None

st.subheader("1. Entrada de Dados")
aba_upload, aba_manual = st.tabs(["📂 Upload de Planilha", "✍️ Inserção Manual"])

df_para_processar = None

with aba_upload:
    arquivo_upload = st.file_uploader("Faça upload da sua planilha (CSV ou Excel)", type=["csv", "xlsx"])
    if arquivo_upload:
        try:
            # Tenta ler como CSV ou Excel dependendo da extensão
            if arquivo_upload.name.endswith('.csv'):
                df_upload = pd.read_csv(arquivo_upload)
                # Se o CSV usar ponto e vírgula como separador (padrão do Excel BR), corrige a leitura
                if len(df_upload.columns) == 1:
                    arquivo_upload.seek(0)
                    df_upload = pd.read_csv(arquivo_upload, sep=';')
            else:
                df_upload = pd.read_excel(arquivo_upload)
            
            # Procura por uma coluna chamada 'Coordenadas' ou 'Coordenada' ignorando maiúsculas e minúsculas
            col_coords = [col for col in df_upload.columns if 'coordenada' in col.lower()]
            
            if not col_coords:
                st.error("⚠️ A planilha precisa ter uma coluna chamada 'Coordenadas'.")
            else:
                st.success(f"Planilha carregada com sucesso! ({len(df_upload)} linhas identificadas)")
                with st.expander("Visualizar dados importados"):
                    st.dataframe(df_upload.head())
                
                # Prepara o DataFrame final que será enviado para o processador
                df_para_processar = pd.DataFrame()
                df_para_processar['Coordenada'] = df_upload[col_coords[0]].dropna()
                
                if 'KM Adicional' in df_upload.columns:
                    df_para_processar['KM Adicional'] = pd.to_numeric(df_upload['KM Adicional'], errors='coerce').fillna(0)
                else:
                    df_para_processar['KM Adicional'] = 0.0
                    
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")

with aba_manual:
    df_template = pd.DataFrame({
        'Coordenada': ['-19.5724, -57.0289', '-19,0069; -57,6523'],
        'KM Adicional': [0.0, 5.0]
    })
    st.write("Cole seus pontos abaixo (útil para testes rápidos):")
    edited_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)
    
    # Se o usuário não fez upload, usa a inserção manual como fonte de dados
    if df_para_processar is None:
        df_para_processar = edited_df

if st.button("🚀 Calcular Rota", type="primary"):
    if not api_key:
        st.error("Insira a API Key na barra lateral.")
    elif df_para_processar is None or df_para_processar.empty:
        st.warning("Insira dados válidos na tabela ou faça upload de uma planilha.")
    else:
        with st.spinner("Traçando rota no servidor... Isso pode levar alguns segundos dependendo da distância."):
            client = openrouteservice.Client(key=api_key)
            st.session_state['dados_rota'] = processar_rota(client, df_para_processar)

# Verifica se existe resultado salvo na memória e exibe
if st.session_state['dados_rota']:
    total, link, detalhes, route_data, coords_data, debug_segments, resumo_tipos, erro = st.session_state['dados_rota']
    
    st.divider()
    if erro:
        st.error(erro)
    else:
        st.subheader("📋 Resultado Final")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Calculado (KM)", f"{total:.2f}")
        c2.metric("Asfalto (Base)", f"{detalhes['Asfalto (KM)']} km")
        c3.metric("Chão (Base)", f"{detalhes['Chão (KM)']} km")
        
        st.write("### Detalhamento")
        st.json(detalhes)
        
        st.success("Rota gerada com sucesso!")
        st.markdown(f"**🗺️ Abrir Rota no Google Maps**")
        st.markdown(f"[Clique aqui para abrir no Google Maps]({link})")
        
        st.subheader("📍 Mapa Interativo")
        mapa = gerar_mapa_folium(route_data, coords_data)
        st_folium(mapa, width=1000, height=500)
        
        with st.expander("📊 Resumo por Tipo de Superfície (Tira-Teima)"):
            st.write("Abaixo, o total de KM encontrado para cada etiqueta específica do mapa:")
            df_resumo = pd.DataFrame(list(resumo_tipos.items()), columns=['Tipo de Superfície', 'Metros'])
            df_resumo['KM'] = (df_resumo['Metros'] / 1000).round(3)
            df_resumo = df_resumo[['Tipo de Superfície', 'KM']].sort_values(by='KM', ascending=False)
            st.dataframe(df_resumo, use_container_width=True)
        
        with st.expander("🔍 Detalhes Técnicos (Debug dos Segmentos)"):
            st.write("Visualização em Tabela:")
            st.dataframe(pd.DataFrame(debug_segments), use_container_width=True)
            st.write("📋 **Para análise de erro:** Copie o código abaixo e envie no chat:")
            st.code(json.dumps(debug_segments, indent=2, ensure_ascii=False), language='json')
