import streamlit as st
import pdfplumber
import io
import pandas as pd
import unicodedata
import re
from supabase import create_client, Client

def supabase_baglantisi_kur():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

# Türkçe karakterleri ve boşlukları temizleyerek Supabase uyumlu hale getiren fonksiyon
def dosya_adini_duzenle(dosya_adi):
    if "." in dosya_adi:
        isim, uzanti = dosya_adi.rsplit(".", 1)
    else:
        isim, uzanti = dosya_adi, "pdf"
        
    tr_harfler = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    isim = isim.translate(tr_harfler)
    
    isim = unicodedata.normalize('NFKD', isim).encode('ascii', 'ignore').decode('utf-8')
    isim = re.sub(r'[^a-zA-Z0-9_-]', '_', isim)
    isim = re.sub(r'_+', '_', isim).strip('_')
    
    return f"{isim}.{uzanti}".lower()

st.title("Yönetim Paneli")
st.markdown("PDF kural kitapçıklarını yükleyin ve mevcut arşivinizi yönetin.")

if 'admin_giris' not in st.session_state:
    st.session_state.admin_giris = False

if not st.session_state.admin_giris:
    sifre = st.text_input("Admin Şifresi:", type="password")
    if st.button("Giriş Yap", type="primary"):
        if sifre == st.secrets["ADMIN_PASS"]:
            st.session_state.admin_giris = True
            st.rerun()
        else:
            st.error("Hatalı şifre!")
else:
    st.success("Giriş başarılı!")
    st.markdown("---")
    
    try:
        supabase = supabase_baglantisi_kur()
    except Exception as e:
        st.error("Supabase bağlantı ayarları (Secrets) yüklenemedi.")
        st.stop()
    
    sekme1, sekme2 = st.tabs(["Yeni Belge Yükle", "Alfabetik Belge Arşivi"])
    
    with sekme1:
        kategoriler = [
            "ITF Kuralları", "Men's WTT", "Women's WTT", "WTT Juniors", 
            "WTT Masters", "Wheelchair Tour", "Beach Tennis", "Tennis Europe", 
            "ATP", "WTA", "Grand Slam", "TTF Ulusal", "Ulusal Diğer", "Sık Sorulanlar"
        ]
        secilen_kategori = st.radio("Belgelerin Kategorisini Seçin:", kategoriler, horizontal=True)
        
        yuklenen_dosyalar = st.file_uploader("PDF Belgeleri Seçin", type=["pdf"], accept_multiple_files=True)
        
        if st.button("Belgeleri Yükle ve Sayfa Sayfa İşle", type="primary"):
            if yuklenen_dosyalar:
                toplam_sayfa_kaydi = 0
                
                for dosya in yuklenen_dosyalar:
                    orijinal_ad = dosya.name
                    temiz_dosya_adi = dosya_adini_duzenle(orijinal_ad)
                    dosya_verisi = dosya.read()
                    
                    try:
                        # 1. Veritabanındaki eski metin kayıtlarını temizle
                        supabase.table("kural_icerikleri").delete().eq("dosya_adi", temiz_dosya_adi).execute()
                        
                        # 2. ÜZERİNE YAZMA (UPSERT) KOMUTU EKLENDİ! 
                        # Bu sayede depoda eski/hayalet dosya varsa bile 409 hatası vermeyip acımasızca ezecek.
                        file_options = {
                            "content-type": "application/pdf",
                            "x-upsert": "true"  # İşte 409 hatasını tarihe gömen sihirli satır!
                        }
                        
                        supabase.storage.from_("Belgeler").upload(
                            path=temiz_dosya_adi, 
                            file=dosya_verisi, 
                            file_options=file_options
                        )
                        
                        res_url = supabase.storage.from_("Belgeler").get_public_url(temiz_dosya_adi)
                        dosya_url = res_url.get('publicUrl') if isinstance(res_url, dict) else str(res_url)
                        
                        with pdfplumber.open(io.BytesIO(dosya_verisi)) as pdf:
                            for sayfa_index, sayfa in enumerate(pdf.pages):
                                metin = sayfa.extract_text()
                                if metin and metin.strip():
                                    sayfa_no = sayfa_index + 1
                                    
                                    supabase.table("kural_icerikleri").insert({
                                        "dosya_adi": temiz_dosya_adi,
                                        "kategori": secilen_kategori,
                                        "sayfa_no": sayfa_no,
                                        "icerik": metin,
                                        "dosya_url": dosya_url
                                    }).execute()
                                    
                                    toplam_sayfa_kaydi += 1
                                    
                        st.success(f"'{orijinal_ad}' başarıyla işlendi (Toplam {len(pdf.pages)} sayfa).")
                    except Exception as e:
                        st.warning(f"'{orijinal_ad}' işlenirken hata oluştu: {e}")
                
                if toplam_sayfa_kaydi > 0:
                    st.success(f"İşlem tamamlandı! Toplam {toplam_sayfa_kaydi} sayfalık veri tabanı kaydı oluşturuldu.")
            else:
                st.warning("Lütfen en az bir PDF seçin.")
                
    with sekme2:
        st.subheader("Yüklenmiş Belgeler Arşivi")
        try:
            response = supabase.table("kural_icerikleri").select("dosya_adi, kategori, dosya_url").limit(10000).execute()
            
            if response.data:
                df = pd.DataFrame(response.data)
                df_unique = df.drop_duplicates(subset=["dosya_adi"]).sort_values(by="dosya_adi", ascending=True).reset_index(drop=True)
                
                st.info(f"Toplam Benzersiz Belge Sayısı: **{len(df_unique)}**")
                
                for idx, row in df_unique.iterrows():
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                    dosya_adi_sil = row['dosya_adi']
                    
                    with col1:
                        st.markdown(f"**{idx+1}. {dosya_adi_sil}**")
                    with col2:
                        st.caption(f"Kategori: {row['kategori']}")
                    with col3:
                        doc_url = row['dosya_url']
                        if isinstance(doc_url, dict): doc_url = doc_url.get('publicUrl', '')
                        if doc_url: st.markdown(f"[Aç / İndir]({doc_url})")
                    with col4:
                        if st.button("Sil", key=f"sil_{dosya_adi_sil}"):
                            supabase.table("kural_icerikleri").delete().eq("dosya_adi", dosya_adi_sil).execute()
                            try:
                                supabase.storage.from_("Belgeler").remove([dosya_adi_sil])
                            except:
                                pass
                            st.success(f"{dosya_adi_sil} sistemden tamamen silindi!")
                            st.rerun()
                            
                    st.markdown("---")
            else:
                st.warning("Veritabanında henüz belge yok.")
        except Exception as e:
            st.error(f"Hata: {e}")
