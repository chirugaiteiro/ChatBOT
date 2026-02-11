import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

# Configuração da página
st.set_page_config(page_title="Roteirizador Simples", page_icon="🗺️", layout="wide")

st.title("🗺️ Planejador de Rotas com Distância")
st.markdown("Insira as coordenadas de origem e destino para gerar a rota e calcular a distância.")

# --- Barra Lateral para Inputs ---
with st.sidebar:
    st.header("📍 Coordenadas")
    
    st.subheader("Origem (Ponto A)")
    # Valores padrão (Ex: Av. Paulista, SP)
    lat_origem = st.number_input("Latitude Origem", value=-23.561684, format="%.6f")
    lon_origem = st.number_input("Longitude Origem", value=-46.655981, format="%.6f")

    st.subheader("Destino (Ponto B)")
    # Valores padrão (Ex: Parque Ibirapuera, SP)
    lat_destino = st.number_input("Latitude Destino", value=-23.587416, format="%.6f")
    lon_destino = st.number_input("Longitude Destino", value=-46.657634, format="%.6f")

    btn_calcular = st.button("Gerar Rota 🚗", type="primary")

# --- Função para buscar a rota (Backend) ---
def get_route(lat_start, lon_start, lat_end, lon_end):
    # OSRM usa ordem Longitude, Latitude
    loc_start = f"{lon_start},{lat_start}"
    loc_end = f"{lon_end},{lat_end}"
    
    # URL da API pública do OSRM (Serviço de roteamento gratuito)
    url = f"http://router.project-osrm.org/route/v1/driving/{loc_start};{loc_end}?overview=full&geometries=geojson"
    
    try:
        r = requests.get(url)
        data = r.json()
        
        if data.get("code") != "Ok":
            return None, None
            
        # Extrair a rota (geometria) e a distância
        route_geometry = data["routes"][0]["geometry"]
        distance_meters = data["routes"][0]["distance"]
        
        return route_geometry, distance_meters
    except Exception as e:
        st.error(f"Erro ao conectar com serviço de rotas: {e}")
        return None, None

# --- Lógica Principal ---
if btn_calcular:
    with st.spinner("Calculando a melhor rota..."):
        geometry, distance = get_route(lat_origem, lon_origem, lat_destino, lon_destino)
    
    if geometry and distance is not None:
        # Converter metros para quilômetros
        km = distance / 1000
        
        # 1. Exibir Métricas
        col1, col2 = st.columns(2)
        col1.metric("Distância Total", f"{km:.2f} km")
        col2.metric("Status", "Rota Encontrada ✅")
        
        # 2. Criar o Mapa
        # Centralizar o mapa na média das coordenadas
        center_lat = (lat_origem + lat_destino) / 2
        center_lon = (lon_origem + lon_destino) / 2
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
        
        # Adicionar Marcador de Origem
        folium.Marker(
            [lat_origem, lon_origem], 
            popup="Origem", 
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m)
        
        # Adicionar Marcador de Destino
        folium.Marker(
            [lat_destino, lon_destino], 
            popup="Destino", 
            icon=folium.Icon(color="red", icon="stop")
        ).add_to(m)
        
        # Desenhar a Linha da Rota (GeoJSON)
        folium.GeoJson(
            geometry,
            name="Rota",
            style_function=lambda x: {'color': 'blue', 'weight': 5, 'opacity': 0.7}
        ).add_to(m)
        
        # Renderizar o mapa no Streamlit
        st_folium(m, width=None, height=500)
        
    else:
        st.error("Não foi possível encontrar uma rota entre esses pontos. Verifique se são acessíveis por carro.")
else:
    # Mostra um mapa inicial apenas para não ficar vazio
    st.info("Insira as coordenadas na barra lateral e clique em 'Gerar Rota'.")
    m = folium.Map(location=[-23.5505, -46.6333], zoom_start=10)
    st_folium(m, width=None, height=500)
