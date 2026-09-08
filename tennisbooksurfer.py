import streamlit as st
from ui_hakem_paneli import hakem_panelini_ciz

# 1. Sayfa ayarı: İlk açılışta yan menü kapalı ve tam genişlik
st.set_page_config(
    page_title="Başhakem Dijital Asistanı",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def main():
    # Uygulama açıldığı an doğrudan Hakem Arama Paneli çizilir
    hakem_panelini_ciz()

if __name__ == "__main__":
    main()
