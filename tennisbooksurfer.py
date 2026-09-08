import streamlit as st
from ui_hakem_paneli import hakem_panelini_ciz

# Sayfa yapılandırması - Dosyadaki İLK Streamlit komutu olmalıdır
st.set_page_config(
    page_title="Başhakem Dijital Asistanı",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def main():
    # Uygulama açıldığı an doğrudan Hakem Sorgu Paneli ekrana gelir
    hakem_panelini_ciz()

if __name__ == "__main__":
    main()
