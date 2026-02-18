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
Cole seus dados da planilha abaixo. O sistema aceita:
1. **Decimal Padrão:** `-19.55, -54.22`
2. **GPS/DMS:** `19°15'35.2"S 57°14'00.1"W`
3. **Excel BR:** `-19,55; -54,22`
""")

# --- CONSTANTES ---
UNPAVED_TYPES = ['unpaved', 'compacted', 'dirt', 'earth', 'gravel', 'fine_gravel', 'grass', 'ground', 'sand', 'wood', 'mud', 'clay', 'salt', 'ice', 'snow']

# Mapeamento de IDs numéricos do OpenRouteService para texto (caso a API retorne números sem nome)
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
    """Converte string 19°15'35.2"S para decimal"""
    # Troca vírgula decimal por ponto (ex: 35,2" -> 35.2")
    dms_str = dms_str.replace(',', '.')
    dms_str = dms_str.upper().strip()
    
    sign = -1 if 'S' in dms_str or 'W' in dms_str or 'O' in dms_str else 1
    
    # Regex para pegar números (graus, min, seg)
    parts = re.split(r'[^\d\.]+', dms_str)
    parts = [float(x) for x in parts if x]
    
    if len(parts) >= 3:
        return sign * (parts[0] + (parts[1] / 60) + (parts[2] / 3600))
    elif len(parts) >= 2: # Caso tenha só graus e minutos
        return sign * (parts[0] + (parts[1] / 60))
    elif len(parts) == 1:
        return sign * float(parts[0])
    return None

def limpar_e_converter(texto):
    """
    O 'Cérebro' que decide qual formato está sendo usado na célula
    """
    texto = str(texto).strip().upper()
    
    try:
        # CENÁRIO 1: Formato GPS/DMS (Tem letras S/N/W/E ou símbolo de grau)
        if any(c in texto for c in ['S', 'W', 'N', 'E', 'O', '°', 'º']):
            # Regex busca dois blocos de DMS
            padrao = r"[\d\.,]+[°º\s]+[\d\.,]+[′'\s]+[\d\.,]+[″\"\s]*[NSEWO]"
            matches = re.findall(padrao, texto)
            
            # Se achou 2 coordenadas (Lat e Lon)
            if len(matches) >= 2:
                lat = dms_para_decimal(matches[0])
                lon = dms_para_decimal(matches[1])
                return lat, lon
            
            # Se o Regex falhou mas tem letras, tenta dividir por espaço
            # Ex: 19 15 35 S 57 14 00 W
            # (Lógica complexa, melhor assumir que o regex pega 99% dos casos)
            pass

        # CENÁRIO 2: Decimal (Comum ou Excel BR)
        # Remove caracteres estranhos, mantém apenas números, vírgula, ponto e sinal de menos
        texto_limpo = texto.replace(';', ' ').replace(',', '.') # Troca vírgula decimal por ponto se for estilo BR
        
        # Se tiver vírgula separando as coordenadas (agora virou ponto na linha acima? Cuidado)
        # Melhor estratégia para decimal: Buscar todos os números float na string
        numeros = re.findall(r'-?\d+\.\d+|-?\d+', texto.replace(',', '.'))
        
        if len(numeros) >= 2:
            # Assume que os dois primeiros são Lat e Lon
            lat = float(numeros[0])
            lon = float(numeros[1])
            
            # Validação básica de latitude (não pode ser maior que 90)
            if abs(lat) <= 90 and abs(lon) <= 180:
                return lat, lon

    except Exception as e:
        pass
    
    return None, None

# --- FUNÇÃO DE GERAÇÃO DE MAPA (Separada para não pesar no session_state) ---
def gerar_mapa_folium(route, coords_ors):
    # Centraliza no primeiro ponto
    start_lat = coords_ors[0][1]
    start_lon = coords_ors[0][0]
    m = folium.Map(location=[start_lat, start_lon], zoom_start=12)

    # Desenha os segmentos coloridos (Asfalto vs Chão)
    extras = route['features'][0]['properties']['extras']['surface']
    geometry = route['features'][0]['geometry']['coordinates']
    
    # Cria mapa de tradução (ID numérico -> Nome texto) se existir 'summary'
    lookup_surface = {}
    lookup_surface.update(ORS_SURFACE_MAPPING) # Carrega fallback padrão primeiro
    
    if 'summary' in extras:
        for item in extras['summary']:
            if 'name' in item: # Verifica se a chave 'name' existe antes de acessar
                lookup_surface[item['value']] = item['name']

    surface_segments = extras['values']
    
    for seg in surface_segments:
        start_idx, end_idx, surf_type = seg
        
        # Traduz o ID para texto se necessário
        if isinstance(surf_type, int) and surf_type in lookup_surface:
            surf_type = lookup_surface[surf_type]
            
        # Extrai as coordenadas do segmento e inverte para [lat, lon]
        segment_coords = [[c[1], c[0]] for c in geometry[start_idx : end_idx + 1]]
        
        # Define cor: Cinza para asfalto, Marrom para chão
        # Lógica invertida: Se for tipo de chão conhecido, pinta de marrom. Se for asfalto ou DESCONHECIDO (None), pinta de cinza.
        eh_chao = surf_type in UNPAVED_TYPES
        color = '#8B4513' if eh_chao else '#555555'
        
        tipo_pt = "Chão (+9%)" if eh_chao else "Asfalto (+3%)"
        tooltip_text = f"Superfície: {surf_type} | Status: {tipo_pt}"

        folium.PolyLine(segment_coords, color=color, weight=5, opacity=0.8, tooltip=tooltip_text).add_to(m)

    # Adiciona marcadores
    for i, coord in enumerate(coords_ors):
        # coord vem como [lon, lat], folium usa [lat, lon]
        folium.Marker(
            location=[coord[1], coord[0]],
            tooltip=f"Ponto {i+1}",
            icon=folium.Icon(color="green" if i == 0 else "red" if i == len(coords_ors)-1 else "blue", icon="info-sign")
        ).add_to(m)

    # Ajusta o zoom para caber a rota inteira
    bbox = route['bbox'] # [min_lon, min_lat, max_lon, max_lat]
    m.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])
    
    # --- LEGENDA FLUTUANTE (HTML/CSS) ---
    legend_html = '''
     <div style="
     position: fixed; 
     bottom: 50px; right: 50px; width: 130px; height: 90px; 
     z-index:9999; font-size:14px;
     background-color: white;
     border:2px solid grey;
     border-radius:6px;
     padding: 10px;
     opacity: 0.9;
     ">
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
    
    # 1. Loop de Conversão
    for c_raw in coords_raw_list:
        lat, lon = limpar_e_converter(c_raw)
        
        if lat is None:
            return None, None, None, None, None, f"Erro formato: {c_raw}"
            
        coords_ors.append([lon, lat])
        coords_gmaps_orig.append(f"{lat},{lon}")

    if len(coords_ors) < 2:
        return None, None, None, None, None, "Erro: Mínimo 2 pontos necessários para traçar uma rota."

    # 3. Chama API
    try:
        route = client.directions(
            coordinates=coords_ors,
            profile='driving-hgv',
            format='geojson',
            extra_info=['surface'],
        )
    except Exception as e:
        return None, None, None, None, None, f"Erro API: {e}"

    # 4. Calcula KM
    extras = route['features'][0]['properties']['extras']['surface']
    geometry = route['features'][0]['geometry']['coordinates']
    dist_paved = 0
    dist_unpaved = 0
    
    # Cria mapa de tradução (ID numérico -> Nome texto) se existir 'summary'
    lookup_surface = {}
    lookup_surface.update(ORS_SURFACE_MAPPING) # Carrega fallback padrão primeiro
    
    if 'summary' in extras:
        for item in extras['summary']:
            if 'name' in item: # Verifica se a chave 'name' existe antes de acessar
                lookup_surface[item['value']] = item['name']

    debug_segments = []
    resumo_tipos = {} # Dicionário para agrupar totais por tipo (ex: 'asphalt': 50km, 'dirt': 10km)
    
    for seg in extras['values']:
        start, end, surf = seg[0], seg[1], seg[2]
        
        # Traduz o ID para texto se necessário (Isso corrige o erro dos números)
        if isinstance(surf, int) and surf in lookup_surface:
            surf = lookup_surface[surf]
            
        seg_d = 0
        for i in range(start, end):
            p1, p2 = geometry[i], geometry[i+1]
            seg_d += geodesic((p1[1], p1[0]), (p2[1], p2[0])).meters
        
        # Se o tipo de superfície estiver na lista de "chão", soma no unpaved.
        # Caso contrário (Asfalto, Concreto, ou None/Vazio), assume que é asfalto.
        is_unpaved = surf in UNPAVED_TYPES
        
        if is_unpaved:
            dist_unpaved += seg_d
        else:
            dist_paved += seg_d
            
        # Popula o resumo detalhado
        surf_key = str(surf) if surf else "Não Informado (Assumido Asfalto)"
        if surf_key not in resumo_tipos:
            resumo_tipos[surf_key] = 0
        resumo_tipos[surf_key] += seg_d
            
        # Captura coordenadas para facilitar a identificação do trecho
        p_start = geometry[start] # [lon, lat]
        p_end = geometry[end]     # [lon, lat]

        debug_segments.append({
            "Tag_Original": surf,
            "Classificacao_App": "Chão" if is_unpaved else "Asfalto",
            "Distancia_m": round(seg_d, 1),
            "Coord_Inicio": f"{p_start[1]:.5f}, {p_start[0]:.5f}",
            "Coord_Fim": f"{p_end[1]:.5f}, {p_end[0]:.5f}"
        })

    km_paved = dist_paved / 1000
    km_unpaved = dist_unpaved / 1000
    
    # Cálculo solicitado: (Chão * 1.09) + (Asfalto * 1.03) + Adicional
    total = (km_unpaved * 1.09) + (km_paved * 1.03) + total_manual

    # 5. Gera Link (Ghost Point se necessário)
    final_points = coords_gmaps_orig.copy()

    link = "https://www.google.com/maps/dir/" + "/".join(final_points)
    
    detalhes = {
        "Asfalto (KM)": round(km_paved, 2),
        "Chão (KM)": round(km_unpaved, 2),
        "Adicional (KM)": round(total_manual, 2),
        "Custo Asfalto (+3%)": round(km_paved * 1.03, 2),
        "Custo Chão (+9%)": round(km_unpaved * 1.09, 2)
    }
    
    # Retorna DADOS (route, coords_ors) em vez do objeto MAPA
    return total, link, detalhes, route, coords_ors, debug_segments, resumo_tipos, None

# --- INTERFACE ---
# Exemplo misturado na tela inicial para testar
df_template = pd.DataFrame({
    'Coordenada': [
        '-19.5724, -57.0289',           # Formato Decimal Ponto
        '-19,0069; -57,6523'            # Formato Decimal Vírgula
    ],
    'KM Adicional': [0.0, 5.0]
})

st.subheader("1. Cole os pontos da Rota")
edited_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)

# Inicializa o estado se não existir
if 'dados_rota' not in st.session_state:
    st.session_state['dados_rota'] = None

if st.button("🚀 Calcular Rota", type="primary"):
    if not api_key:
        st.error("Insira a API Key na barra lateral.")
    else:
        client = openrouteservice.Client(key=api_key)
        # Salva o resultado no session_state em vez de exibir direto
        st.session_state['dados_rota'] = processar_rota(client, edited_df)

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
        # Gera o mapa na hora da exibição usando os dados salvos
        mapa = gerar_mapa_folium(route_data, coords_data)
        st_folium(mapa, width=1000, height=500)
        
        # Novo bloco de Resumo Agrupado
        with st.expander("📊 Resumo por Tipo de Superfície (Tira-Teima)"):
            st.write("Abaixo, o total de KM encontrado para cada etiqueta específica do mapa:")
            
            # Converte o dicionário em DataFrame para exibir bonito
            df_resumo = pd.DataFrame(list(resumo_tipos.items()), columns=['Tipo de Superfície', 'Metros'])
            df_resumo['KM'] = (df_resumo['Metros'] / 1000).round(3)
            df_resumo = df_resumo[['Tipo de Superfície', 'KM']].sort_values(by='KM', ascending=False)
            
            st.dataframe(df_resumo, use_container_width=True)
        
        with st.expander("🔍 Detalhes Técnicos (Debug dos Segmentos)"):
            st.write("Visualização em Tabela:")
            st.dataframe(pd.DataFrame(debug_segments), use_container_width=True)
            
            st.write("📋 **Para análise de erro:** Copie o código abaixo e envie no chat:")
            st.code(json.dumps(debug_segments, indent=2, ensure_ascii=False), language='json')
