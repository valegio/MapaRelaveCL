import os
import gdown
import streamlit as st
import geopandas as gpd
import pandas as pd
import requests
import folium
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium
from shapely.geometry import Point
from folium.plugins import MarkerCluster
from folium.plugins import FastMarkerCluster

# st.cache_data.clear()

# Configuración de la página
st.set_page_config(
    page_title='​ChileRelaves',
    layout='centered',
    page_icon="🔎​"
)

# Título y descripción
st.html("""
<div style="text-align: center; font-size: 40px">
    🔎MapaRelavesCL
</div>
""")
st.html("""
<div style="text-align: center;">
    ¿Estás cerca de algún relave?
</div>
""")
    
st.html("""
<div style="text-align: center;">
    Ingresa la dirección para verificar si estás cerca de algún relave.
</div>
""")

# Constantes
ORS_API_KEY = st.secrets['ORS_API_KEY']
DATA_FILES = {
    'relaves': 'Relaves_Chile.parquet',
    'regiones': 'Regiones_Chile.parquet'
}

# Diccionario de regiones
ROMANO_A_REGION = {
    "XV": "Región de Arica y Parinacota",
    "I": "Región de Tarapacá",
    "II": "Región de Antofagasta",
    "III": "Región de Atacama",
    "IV": "Región de Coquimbo",
    "V": "Región de Valparaíso",
    "RM": "Región Metropolitana de Santiago",
    "VI": "Región del Libertador Bernardo O'Higgins",
    "VII": "Región del Maule",
    "XVI": "Región de Ñuble",
    "VIII": "Región del Bío-Bío",
    "IX": "Región de La Araucanía",
    "XIV": "Región de Los Ríos",
    "X": "Región de Los Lagos",
    "XI": "Región de Aysén del Gral. Ibañez del Campo",
    "XII": "Región de Magallanes y Antártica Chilena"
}

# Funciones de utilidad
@st.cache_data(ttl=3600) 
def geocode(query):
    """Geocodifica una dirección usando OpenRouteService"""
    parameters = {
        'api_key': ORS_API_KEY,
        'text': query
    }

    response = requests.get(
        'https://api.openrouteservice.org/geocode/search',
        params=parameters
    )
    
    if response.status_code == 200:
        data = response.json()
        if data['features']:
            lon, lat = data['features'][0]['geometry']['coordinates']
            return (lat, lon)
    return None

# IDs de Google Drive para los archivos .parquet
DRIVE_FILE_IDS = {
    'Regiones_Chile': '1Cp_3R_VjV--bYgzwRF_dl8MwOtmincod',  
    'Relaves_Chile': '11V8HQvoDBZpkORoj9lhXB7vzr16XLYTn'    
}

@st.cache_data(persist=True)
def load_data(file_key):
    """Descarga y carga el archivo Parquet desde Google Drive"""
    file_name = f"{file_key}.parquet"
    file_id = DRIVE_FILE_IDS[file_key]
    
    # Descargar si no existe localmente
    if not os.path.exists(file_name):
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, file_name, quiet=False)
    
    # Cargar el Parquet
    return gpd.read_parquet(file_name)
 
@st.cache_data(ttl=3600, persist=True)
def get_crs_transformed(_gdf, epsg, cache_key=None):
    """Transforma el sistema de coordenadas con clave de caché única"""
    return _gdf.to_crs(epsg=epsg)

@st.cache_data(ttl=3600)  
def find_region_for_point(lat, lon, _regiones_gdf):
    """Encuentra la región para un punto dado"""
    regiones_gdf = _regiones_gdf.copy()
    punto_wgs84 = Point(lon, lat)
    
    for idx, region in regiones_gdf.iterrows():
        if punto_wgs84.within(region.geometry):
            return region
    return None

@st.cache_data(ttl=3600)
def calculate_distances_to_relaves(lat, lon, _relaves_region_utm, region_name):
    """Calcula distancias a relaves y retorna los más cercanos"""
    # Crear punto en UTM
    punto_utm = gpd.GeoDataFrame(
        geometry=[Point(lon, lat)], 
        crs="EPSG:4326"
    ).to_crs(epsg=32719).geometry.iloc[0]
    
    # Calcular distancias
    relaves_copy = _relaves_region_utm.copy()
    relaves_copy['distancia'] = relaves_copy.geometry.distance(punto_utm)
    relaves_copy = relaves_copy.sort_values('distancia')
    
    # Obtener los 10 más cercanos
    relaves_cercanos = relaves_copy.head(10).copy()
    relaves_cercanos['distancia_km'] = relaves_cercanos['distancia'] / 1000
    
    return relaves_cercanos

@st.cache_data(persist=True)
def create_full_map(_relaves_gdf):
    def create_icon_callback(icon_name="map-marker", markerColor="red"):
        return f"""\
            function (row) {{
                var icon, marker;
                icon = L.AwesomeMarkers.icon({{
                    icon: "{icon_name}", 
                    markerColor: "{markerColor}"
                }});
                marker = L.marker(new L.LatLng(row[0], row[1]));
                marker.setIcon(icon);
                return marker;
            }};
            """
        
    m = folium.Map(
        location=[-35.675147, -71.542969],
        zoom_start=5,
        tiles='OpenStreetMap'
    )
    
    # Preparar datos
    locations = list(zip(
        _relaves_gdf.geometry.y,
        _relaves_gdf.geometry.x
    ))
    
    popups = [
        f"<b>{row['NOMBRE INSTALACION']}</b><br>Región: {row['Region']}"
        for _, row in _relaves_gdf.iterrows()
    ]
    
    FastMarkerCluster(
        data=locations,
        popups=popups,
        name="Relaves",
        callback=create_icon_callback('map-marker', 'blue'),
        options={
            'disableClusteringAtZoom': 12,
            'maxClusterRadius': 40
        }
    ).add_to(m)
    
    return m
    
@st.cache_data(persist=True)
def initialize_data():
    """Inicializa todos los datos necesarios de una vez"""
    relaves_gdf = load_data('Relaves_Chile')
    regiones_gdf = load_data('Regiones_Chile')
    
    # Transformaciones de coordenadas
    relaves_gdf_utm = get_crs_transformed(relaves_gdf, 32719, cache_key="relaves_utm")
    regiones_gdf_utm = get_crs_transformed(regiones_gdf, 32719, cache_key="regiones_utm")
    relaves_gdf_wgs84 = get_crs_transformed(relaves_gdf, 4326, cache_key="relaves_wgs84")
    regiones_gdf_wgs84 = get_crs_transformed(regiones_gdf, 4326, cache_key="regiones_wgs84")

    
    return {
        'relaves_utm': relaves_gdf_utm,
        'regiones_utm': regiones_gdf_utm,
        'relaves_wgs84': relaves_gdf_wgs84,
        'regiones_wgs84': regiones_gdf_wgs84
    }

            
# Inicializar datos una sola vez
with st.spinner('Cargando datos geográficos...'):
    data = initialize_data()
    relaves_gdf_utm = data['relaves_utm']
    regiones_gdf_utm = data['regiones_utm']
    relaves_gdf_wgs84 = data['relaves_wgs84']
    regiones_gdf_wgs84 = data['regiones_wgs84']

relaves_gdf_wgs84['Region'] = relaves_gdf_wgs84['REGION '].map(ROMANO_A_REGION)
relaves_gdf_utm['Region'] = relaves_gdf_utm['REGION '].map(ROMANO_A_REGION)

# Interfaz de usuario
address = st.text_input('Ingresa una dirección en Chile:', 
                          placeholder="Ej: Av. Libertador Bernardo O'Higgins 123, Santiago")

if address:
    with st.spinner('Buscando ubicación y relaves cercanos...'):
        results = geocode(address)
        
        if results:
            lat, lon = results
            st.success(f'📍 Ubicación encontrada: {lat:.5f}, {lon:.5f}')
            
            # Buscar región 
            region_encontrada = find_region_for_point(lat, lon, regiones_gdf_wgs84)
            
            if region_encontrada is not None and 'Region' in region_encontrada:
                st.subheader(f"Región: {region_encontrada['Region']}")
                
                # Filtrar relaves de la región
                relaves_region_utm = relaves_gdf_utm[
                    relaves_gdf_utm['Region'] == region_encontrada['Region']
                ]
                relaves_region_wgs84 = relaves_gdf_wgs84[
                        relaves_gdf_wgs84['Region'] == region_encontrada['Region']
                ]
                    
                numero_relaves_region = len(relaves_region_wgs84)
                numero_relaves_total = len(relaves_gdf_wgs84)
                porcentaje_relaves = (numero_relaves_region/numero_relaves_total)*100
                
                if numero_relaves_region == 0:
                    st.warning(f"No se encontraron relaves registrados en la {region_encontrada['Region']}.")
                    
                else:
                    st.write(f"En la {region_encontrada['Region']} se registran {numero_relaves_region} relaves, que corresponde a un {porcentaje_relaves:.2f}% del catastro nacional")
                    
                    # Calcular distancias 
                    relaves_cercanos = calculate_distances_to_relaves(
                        lat, lon, relaves_region_utm, region_encontrada['Region']
                    )
                    
                    # Mostrar tabla con los más cercanos
                    st.subheader("Relaves más cercanos")
                    st.dataframe(
                        relaves_cercanos[[
                            'NOMBRE INSTALACION', 
                            'NOMBRE_EMPRESA_O_PRODUCTOR_MINERO',
                            'TIPO_DEPOSITO',
                            'distancia_km'
                        ]].rename(columns={
                            'NOMBRE INSTALACION': 'Nombre',
                            'NOMBRE_EMPRESA_O_PRODUCTOR_MINERO': 'Empresa',
                            'TIPO_DEPOSITO': 'Tipo',
                            'distancia_km': 'Distancia (km)'
                        }).style.format({'Distancia (km)': '{:.2f}'}),
                        height=200
                    )
                    
                    # Info del más cercano
                    relave_cercano = relaves_cercanos.iloc[0]
                    relave_cercano_wgs84 = relaves_gdf_wgs84[
                        relaves_gdf_wgs84['ID'] == relave_cercano['ID']
                    ].iloc[0]

                    with st.expander("🔍 Detalle del relave más cercano", expanded=True):
                        cols = st.columns([1, 1])
                        with cols[0]:
                            st.metric(
                                label="Distancia", 
                                value=f"{relave_cercano['distancia']:.0f} metros",
                                help="Distancia en línea recta desde la ubicación ingresada"
                            )
                        with cols[1]:
                            st.metric(
                                label="Tipo de depósito", 
                                value=relave_cercano['TIPO_DEPOSITO']
                            )
                        
                        st.markdown(f"""
                        - **Nombre**: {relave_cercano['NOMBRE INSTALACION']}  
                        - **Empresa**: {relave_cercano['NOMBRE_EMPRESA_O_PRODUCTOR_MINERO']}  
                        - **Faena**: {relave_cercano['NOMBRE_FAENA']}  
                        - **Recurso**: {relave_cercano['RECURSO ']}  
                        """)
                    
                    # Mapa
                    st.subheader("Mapa de ubicación")
                    
                    # Usar folium directamente
                    m = folium.Map(
                        location=[lat, lon],
                        zoom_start=12,
                        tiles='OpenStreetMap'
                    )
                    
                    # Añadir marcador de la dirección ingresada
                    folium.Marker(
                        [lat, lon],
                        popup=folium.Popup(f"<b>Dirección ingresada:</b><br>{address}", max_width=200),
                        tooltip="Tu ubicación",
                        icon=folium.Icon(color='green', icon='home', prefix='fa')
                    ).add_to(m)
                    
                    # Añadir marcador del relave más cercano
                    relave_lat = relave_cercano_wgs84.geometry.y
                    relave_lon = relave_cercano_wgs84.geometry.x
                    
                    
                    
                    # Añadir línea de conexión
                    folium.PolyLine(
                        locations=[[lat, lon], [relave_lat, relave_lon]],
                        color='blue',
                        weight=3,
                        opacity=0.8,
                        dash_array='10, 5',
                        popup=f"Distancia: {relave_cercano['distancia']:.0f} metros"
                    ).add_to(m)
                    
                    # Ajustar vista del mapa
                    bounds = [[lat, lon], [relave_lat, relave_lon]]
                    m.fit_bounds(bounds, padding=[20, 20])
                    
                    # Añadir otros relaves cercanos (limitado para rendimiento)
                    if len(relaves_cercanos) > 1:
                        for idx, relave in relaves_region_wgs84.iterrows():  
                                                 
                            folium.Marker(
                                [relave.geometry.y, relave.geometry.x],
                                tooltip=folium.Tooltip(
                                    f"<b>{relave['NOMBRE INSTALACION']}</b><br>"
                                    f"Región: {relave['Region']}<br>"
                                    f"Empresa: {relave['NOMBRE_EMPRESA_O_PRODUCTOR_MINERO']}",
                                    sticky=True  
                                ),
                                # tooltip=relave['NOMBRE INSTALACION'],
                                icon=folium.Icon(color='blue', icon='map-pin', prefix='fa')
                                ).add_to(m)

                    folium.CircleMarker(
                        [relave_lat, relave_lon],
                        # popup=folium.Popup(
                            # f"<b>{relave_cercano['NOMBRE INSTALACION']}</b><br>"
                            # f"Empresa: {relave_cercano['NOMBRE_EMPRESA_O_PRODUCTOR_MINERO']}<br>"
                            # f"Distancia: {relave_cercano['distancia']:.0f} metros",
                            # max_width=300
                        # ),
                        # tooltip="Relave más cercano",
                        # icon=folium.Icon(color='red', icon='industry', prefix='fa')
                    ).add_to(m)
                    
                    # Mostrar mapa
                    st_folium(m, width="100%", height=600, returned_objects=["last_object_clicked"])
                
            else:
                st.warning("No se encontró la región para esta ubicación. Asegúrate de ingresar una dirección en Chile.")
        else:
            st.error("No se pudo encontrar la ubicación. Por favor, verifica la dirección e intenta nuevamente.")

# Mostrar datos generales si no se ha buscado una dirección
if not address:
    st.markdown("---")
    st.subheader("Datos generales de relaves en Chile")
    
    cols = st.columns(3)
    with cols[0]:
        st.metric("Total de relaves", len(relaves_gdf_wgs84))
    with cols[1]:
        st.metric("Regiones con relaves", relaves_gdf_wgs84['REGION'].nunique())
    with cols[2]:
        st.metric("Empresas mineras", relaves_gdf_wgs84['NOMBRE_EMPRESA_O_PRODUCTOR_MINERO'].nunique())
    
    # Mapa general optimizado
    st.subheader("Mapa general de relaves mineros")
    
    # Obtener mapa cacheado (con todos los relaves)
    m_general = create_full_map(relaves_gdf_wgs84)

    map_output = st_folium(
        m_general,
        width='100%',
        height=500,
        key = 'mapa_principal',
        returned_objects=[]
    )
  
st.subheader("Fuente de datos")
st.markdown("""
    - Servicio Nacional de Geología y Minería (SERNAGEOMIN), 
    Catastro de Depósitos de Relaves en Chile (2024)
    """)
    
# Footer
st.markdown("---")

# Columnas para el footer
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown("""
    **Desarrollado por**  
    Valentina Giovanetti  
    """)
    
with col2:
    st.markdown("""
        [Contacto](mailto:valentina.giovanetti@ug.uchile.cl)  
    [Linkedin](https://www.linkedin.com/in/valentinagiovanetti/)  
    """)

# Estilo CSS adicional
st.markdown("""
<style>
footer {visibility: hidden;}
.st-emotion-cache-1q7spjk {
    padding-bottom: 1rem;
}

/* Estilos responsive para móviles */
@media screen and (max-width: 768px) {
    .st-emotion-cache-1q7spjk {
        padding: 1rem 0.5rem;
    }
    .st-emotion-cache-1v7f65g {
        font-size: 1.2rem;
    }
}
</style>
""", unsafe_allow_html=True)

footer = """
<div style='
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    background-color: white;
    color: #555;
    text-align: center;
    padding: 10px;
    border-top: 1px solid #eee;
    font-family: Arial, sans-serif;
    z-index: 1000;
'>
    <div style='font-size: 0.9rem;'>
        <span>Desarrollado por <strong>Valentina Giovanetti</strong></span> •
        <span><a href="https://www.linkedin.com/in/valentinagiovanetti/" target="_blank" style='color: #0077B5; text-decoration: none;'>LinkedIn</a></span> •
        <span>Creado con <img src="https://streamlit.io/images/brand/streamlit-mark-color.png" width="12" style='vertical-align: middle;'> <strong>Streamlit</strong></span>
    </div>
</div>
"""

st.html(footer)
