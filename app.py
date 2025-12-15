import streamlit as st
import google.generativeai as genai
import PyPDF2
from io import BytesIO

# Configuração da Página
st.set_page_config(page_title="Leitor de PDF com Gemini", page_icon="📄", layout="wide")

st.title("📄 Analisador de Documentos com Gemini")
st.markdown("Faça upload de um PDF e peça para a IA extrair e organizar as informações.")

# --- BARRA LATERAL (Configurações) ---
with st.sidebar:
    st.header("Configurações")
    api_key = st.text_input("Insira sua API Key do Google:", type="password")
    st.markdown("[Obtenha sua chave aqui](https://aistudio.google.com/app/apikey)")
    
    # Escolha do modelo (Flash é mais rápido/barato, Pro é mais inteligente)
    model_choice = st.selectbox("Escolha o Modelo:", ["gemini-1.5-flash", "gemini-1.5-pro"])

# --- FUNÇÕES ---

def extract_text_from_pdf(uploaded_file):
    """Extrai texto cru do PDF usando PyPDF2"""
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return None

def process_with_gemini(text_input, prompt_instructions):
    """Envia o texto e as instruções para o Gemini"""
    if not api_key:
        st.warning("Por favor, insira sua API Key na barra lateral.")
        return None
    
    genai.configure(api_key=api_key)
    
    # Configuração do modelo
    model = genai.GenerativeModel(model_choice)
    
    # Prompt estruturado
    full_prompt = f"""
    Você é um assistente especialista em análise de documentos.
    
    Abaixo está o conteúdo extraído de um arquivo PDF:
    ---
    {text_input}
    ---
    
    SEU OBJETIVO:
    {prompt_instructions}
    
    IMPORTANTE:
    - Responda de forma direta e organizada (use tabelas Markdown se houver dados tabulares).
    - Se a informação não estiver no texto, diga "Informação não encontrada".
    """
    
    with st.spinner('O Gemini está analisando o documento...'):
        try:
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            st.error(f"Erro na API do Gemini: {e}")
            return None

# --- INTERFACE PRINCIPAL ---

uploaded_file = st.file_uploader("Arraste seu PDF aqui", type=['pdf'])

if uploaded_file is not None:
    # 1. Extração do Texto
    pdf_text = extract_text_from_pdf(uploaded_file)
    
    if pdf_text:
        # Mostra um preview do texto (opcional, bom para debug)
        with st.expander("Ver texto extraído (Cru)"):
            st.text(pdf_text[:1000] + "...") # Mostra apenas os primeiros 1000 caracteres

        st.divider()

        # 2. Área de Prompt
        st.subheader("O que você deseja extrair?")
        
        # Sugestões rápidas
        col1, col2, col3 = st.columns(3)
        prompt_type = st.radio(
            "Exemplos de comando:",
            ["Resumir o documento", "Extrair tabela de dados", "Identificar datas e valores", "Comando Personalizado"],
            horizontal=True
        )

        user_prompt = ""
        if prompt_type == "Resumir o documento":
            user_prompt = "Faça um resumo executivo deste documento em tópicos."
        elif prompt_type == "Extrair tabela de dados":
            user_prompt = "Identifique quaisquer dados estruturados e apresente-os em uma tabela Markdown."
        elif prompt_type == "Identificar datas e valores":
            user_prompt = "Liste todas as datas importantes e valores monetários encontrados, explicando a que se referem."
        else:
            user_prompt = st.text_area("Digite sua instrução específica:", placeholder="Ex: Encontre o nome do contratante e a cláusula de rescisão...")

        # 3. Botão de Ação
        if st.button("Processar Documento", type="primary"):
            if user_prompt:
                result = process_with_gemini(pdf_text, user_prompt)
                if result:
                    st.success("Análise concluída!")
                    st.markdown(result)
            else:
                st.warning("Por favor, defina uma instrução.")
