import streamlit as st
import pandas as pd
import re
import urllib.parse
from supabase import create_client, Client
import google.generativeai as genai

# Sözlüğü ayrı dosyadan içe aktarıyoruz
from sozluk import TENNIS_SOZLugu

def supabase_baglantisi_kur():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

# Gemini API Yapılandırması
def yapay_zeka_ayarla():
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel('gemini-flash-latest')
        return model
    except Exception as e:
        st.error("Gemini API anahtarı ayarlanırken bir sorun oluştu.")
        return None

def hakem_panelini_ciz():
    st.title("Başhakem Dijital Asistanı")
    st.markdown("Kural arayın, kütüphaneyi inceleyin veya **bulduğunuz kuralı doğrudan Yapay Zekaya yorumlatın.**")
    st.markdown("---")

    try:
        supabase = supabase_baglantisi_kur()
    except Exception as e:
        st.error("Supabase bağlantı ayarları yüklenemedi. Lütfen Secrets bölümünü kontrol edin.")
        return
        
    ai_model = yapay_zeka_ayarla()

    sekme_arama, sekme_ai, sekme_indeks = st.tabs(["🔍 Kural Arama", "🤖 Genel AI Olay Çözücü", "📚 Belge İndeksi"])

    # ------------------ 1. KLASİK ARAMA VE MİKRO-AI SEKMESİ ------------------
    with sekme_arama:
        if 'aktif_kategori' not in st.session_state:
            st.session_state.aktif_kategori = "Kategori Seçilmedi"

        st.subheader("Kategori Seçin")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("ITF Kuralları", key="btn1", use_container_width=True): st.session_state.aktif_kategori = "ITF Kuralları"
            if st.button("Men's WTT", key="btn2", use_container_width=True): st.session_state.aktif_kategori = "Men's WTT"
            if st.button("Women's WTT", key="btn3", use_container_width=True): st.session_state.aktif_kategori = "Women's WTT"
            if st.button("WTT Juniors", key="btn4", use_container_width=True): st.session_state.aktif_kategori = "WTT Juniors"
                
        with col2:
            if st.button("WTT Masters", key="btn5", use_container_width=True): st.session_state.aktif_kategori = "WTT Masters"
            if st.button("Wheelchair Tour", key="btn6", use_container_width=True): st.session_state.aktif_kategori = "Wheelchair Tour"
            if st.button("Beach Tennis", key="btn7", use_container_width=True): st.session_state.aktif_kategori = "Beach Tennis"
            if st.button("Tennis Europe", key="btn8", use_container_width=True): st.session_state.aktif_kategori = "Tennis Europe"
                
        with col3:
            if st.button("ATP", key="btn9", use_container_width=True): st.session_state.aktif_kategori = "ATP"
            if st.button("WTA", key="btn10", use_container_width=True): st.session_state.aktif_kategori = "WTA"
            if st.button("Grand Slam", key="btn11", use_container_width=True): st.session_state.aktif_kategori = "Grand Slam"
                
        with col4:
            if st.button("TTF Ulusal", key="btn12", use_container_width=True): st.session_state.aktif_kategori = "TTF Ulusal"
            if st.button("Ulusal Diğer", key="btn13", use_container_width=True): st.session_state.aktif_kategori = "Ulusal Diğer"
            if st.button("Sık Sorulanlar", key="btn14", use_container_width=True): st.session_state.aktif_kategori = "Sık Sorulanlar"

        st.markdown("---")
        if st.button("Tüm Talimatlarda Aynı Anda Ara (Pro)", type="primary", use_container_width=True):
            st.session_state.aktif_kategori = "Tüm Talimatlar"
        st.markdown("---")
        
        if st.session_state.aktif_kategori == "Kategori Seçilmedi":
            st.warning("Lütfen arama yapmak istediğiniz talimat kategorisini seçin.")
        else:
            st.success(f"**Aktif Kategori:** {st.session_state.aktif_kategori}")
            
            # --- YENİ: BELGE BAZLI FİLTRELEME (GÖRÜNÜR BUTONLARLA) ---
            secilen_dosyalar = []
            
            try:
                # O kategoriye ait yüklenmiş benzersiz belge isimlerini çekiyoruz
                sorgu_belgeler = supabase.table("kural_icerikleri").select("dosya_adi")
                if st.session_state.aktif_kategori != "Tüm Talimatlar":
                    sorgu_belgeler = sorgu_belgeler.eq("kategori", st.session_state.aktif_kategori)
                
                belge_sonuc = sorgu_belgeler.execute().data
                mevcut_belgeler = sorted(list(set([row["dosya_adi"] for row in belge_sonuc])))
                
                if mevcut_belgeler:
                    st.markdown("###### Aramaya Dahil Edilecek Belgeler:")
                    tumunu_sec = st.toggle("Hepsini Seç / Kaldır", value=True, key="toggle_arama")
                    
                    # Belgeleri gizli açılır pencere yerine belirgin liste butonları olarak diziyoruz
                    for belge in mevcut_belgeler:
                        if st.checkbox(belge, value=tumunu_sec, key=f"chk_{belge}"):
                            secilen_dosyalar.append(belge)
                else:
                    st.warning("Bu kategoride kayıtlı belge bulunamadı.")
            except Exception as e:
                st.error("Belgeler yüklenirken hata oluştu.")
            
            # ---------------------------------------------------------
            
            if "arama_sonuclari" not in st.session_state:
                st.session_state.arama_sonuclari = None
            if "aranan_terimler" not in st.session_state:
                st.session_state.aranan_terimler = None

            aranan_kelime = st.chat_input("Aranacak kelimeyi yazın (veya mikrofona dokunun)...")
            
            if aranan_kelime:
                if not secilen_dosyalar and mevcut_belgeler:
                    st.error("Lütfen arama yapmak için en az bir belge işaretleyin!")
                else:
                    with st.chat_message("user"):
                        st.write(aranan_kelime)
                        
                    with st.spinner("Seçili belgelerde taranıyor..."):
                        try:
                            aranan_ilk = aranan_kelime.lower().strip()
                            aranan_ilk = re.sub(r'\s+', ' ', aranan_ilk)
                            temel_terimler = {aranan_ilk}
                            
                            for tr_key, en_list in TENNIS_SOZLugu.items():
                                if aranan_ilk == tr_key or aranan_ilk in en_list:
                                    temel_terimler.add(tr_key)
                                    temel_terimler.update(en_list)

                            aranacak_terimler = set()
                            for terim in temel_terimler:
                                aranacak_terimler.add(terim)
                                if ' ' in terim:
                                    aranacak_terimler.add(terim.replace(' ', ''))
                                    aranacak_terimler.add(terim.replace(' ', '-'))
                                if '-' in terim:
                                    aranacak_terimler.add(terim.replace('-', ''))
                                    aranacak_terimler.add(terim.replace('-', ' '))
                                    
                            aranacak_terimler_listesi = list(aranacak_terimler)
                            
                            sorgu = supabase.table("kural_icerikleri").select("dosya_adi, kategori, sayfa_no, dosya_url, icerik")
                            
                            # Sadece seçtiğimiz (işaretlediğimiz) dosyalar içinde ara
                            sorgu = sorgu.in_("dosya_adi", secilen_dosyalar)
                            
                            filtre_parcalari = [f"icerik.ilike.%{terim}%" for terim in aranacak_terimler_listesi]
                            sorgu = sorgu.or_(",".join(filtre_parcalari))
                            
                            st.session_state.arama_sonuclari = sorgu.execute().data
                            st.session_state.aranan_terimler = aranacak_terimler_listesi
                        except Exception as e:
                            st.error(f"Arama sırasında hata oluştu: {e}")

            if st.session_state.arama_sonuclari is not None:
                sonuclar = st.session_state.arama_sonuclari
                aranacak_terimler_listesi = st.session_state.aranan_terimler
                
                if sonuclar:
                    st.success(f"Bulunan ilgili sayfa sayısı: {len(sonuclar)}")
                    
                    for idx, kayit in enumerate(sonuclar):
                        sayfa_no = kayit.get('sayfa_no', 1)
                        st.markdown(f"**Belge:** {kayit['dosya_adi']} *({kayit['kategori']}) | Sayfa: {sayfa_no}*")
                        
                        pdf_url = kayit['dosya_url']
                        if isinstance(pdf_url, dict): pdf_url = pdf_url.get('publicUrl', '')
                        
                        metin = kayit['icerik']
                        metin_lower = metin.lower()
                        
                        bulunan_varyasyon = aranacak_terimler_listesi[0]
                        for varyasyon in aranacak_terimler_listesi:
                            if varyasyon in metin_lower:
                                bulunan_varyasyon = varyasyon
                                break
                        
                        if pdf_url:
                            url_kodlu_terim = urllib.parse.quote(f'"{bulunan_varyasyon}"')
                            hedefli_url = f"{pdf_url}?render=true#page={sayfa_no}&search={url_kodlu_terim}"
                            st.markdown(
                                f'''<a href="{hedefli_url}" target="_blank" 
                                style="background-color: #2e3034; color: #39ff14; padding: 8px 12px; border-radius: 6px; text-decoration: none; display: inline-block; margin-bottom: 10px; font-weight: bold; border: 1px solid #39ff14;">
                                ↗️ {sayfa_no}. Sayfayı Aç ve "{bulunan_varyasyon}" Kelimesini Vurgula
                                </a>''', 
                                unsafe_allow_html=True
                            )
                        
                        idx_text = metin_lower.find(bulunan_varyasyon)
                        if idx_text != -1:
                            baslangic = max(0, idx_text - 120)
                            bitis = min(len(metin), idx_text + 350)
                            kesit = metin[baslangic:bitis].replace("\n", " ")
                            pattern = re.compile(re.escape(bulunan_varyasyon), re.IGNORECASE)
                            vurgulu_kesit = pattern.sub(lambda m: f'<span style="background-color: #39ff14; color: #000000; font-weight: bold; padding: 2px 4px; border-radius: 3px;">{m.group(0)}</span>', kesit)
                            st.markdown(f"**İlgili Bağlam:**<br>...{vurgulu_kesit}...", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**İlgili Bağlam:**<br>...{metin[:300]}...", unsafe_allow_html=True)
                            
                        with st.expander(f"🤖 Sadece {sayfa_no}. Sayfayı Yapay Zekaya Yorumlat (Kota Dostu)"):
                            st.caption("Yapay zeka tüm kitabı okumak yerine sadece bu sayfadaki kurala bakarak sorunuzu cevaplar.")
                            ai_soru = st.text_input("Olayı kısaca anlatın:", key=f"soru_{idx}")
                            
                            if st.button("Bu Sayfaya Göre Analiz Et", key=f"analiz_{idx}"):
                                if not ai_soru:
                                    st.warning("Lütfen olayı yazın.")
                                elif not ai_model:
                                    st.error("Gemini API hazır değil.")
                                else:
                                    with st.spinner("AI bu kural maddesini okuyup kararı hazırlıyor..."):
                                        try:
                                            prompt = f"""
                                            Sen uluslararası yetkili bir Tenis Başhakemisin (Gold Badge).
                                            Sadece aşağıdaki spesifik kural metnine dayanarak olayı değerlendir.
                                            
                                            KURAL METNİ ({kayit['dosya_adi']} - Sayfa {sayfa_no}):
                                            {metin}
                                            
                                            HAKEMİN SORDUĞU OLAY:
                                            "{ai_soru}"
                                            
                                            GÖREVİN: 
                                            Bu spesifik kurala göre olayın ihlal olup olmadığını, hakemin hangi kararı vermesi gerektiğini net ve kısa bir dille açıkla.
                                            """
                                            cevap = ai_model.generate_content(prompt)
                                            st.success("🤖 **Yapay Zeka Kararı:**")
                                            st.markdown(cevap.text)
                                        except Exception as e:
                                            st.error(f"Yapay Zeka analizi sırasında hata oluştu: {e}")
                                            
                        st.markdown("---")
                else:
                    st.warning("Seçili belgelerde bu terime rastlanmadı.")

    # ------------------ 2. YAPAY ZEKA SEKMESİ (Geniş Çaplı Tarama) ------------------
    with sekme_ai:
        st.subheader("🤖 Genel Yapay Zeka Başhakem Yardımcısı")
        st.markdown("Soracağınız sorular, altta seçeceğiniz belgelere ait **en alakalı ilk 15 sayfayı** tarayarak cevaplanır.")
        
        if st.session_state.aktif_kategori == "Kategori Seçilmedi" or st.session_state.aktif_kategori == "Tüm Talimatlar":
            st.warning("Lütfen yukarıdaki Arama sekmesinden okutmak istediğiniz tek bir Kategori seçin.")
        elif not ai_model:
            st.warning("Gemini API hazır değil. Lütfen ayarlarınızı kontrol edin.")
        else:
            # AI sekmesinde de hangi belgeleri okutmak istediğinizi seçebiliyorsunuz
            ai_secilen_dosyalar = []
            try:
                sorgu_belgeler_ai = supabase.table("kural_icerikleri").select("dosya_adi").eq("kategori", st.session_state.aktif_kategori)
                belge_sonuc_ai = sorgu_belgeler_ai.execute().data
                mevcut_belgeler_ai = sorted(list(set([row["dosya_adi"] for row in belge_sonuc_ai])))
                
                if mevcut_belgeler_ai:
                    st.markdown("###### Yapay Zekaya Okutulacak Belgeler:")
                    tumunu_sec_ai = st.toggle("Hepsini Seç / Kaldır", value=True, key="toggle_ai")
                    
                    for belge in mevcut_belgeler_ai:
                        if st.checkbox(belge, value=tumunu_sec_ai, key=f"ai_chk_{belge}"):
                            ai_secilen_dosyalar.append(belge)
            except Exception as e:
                pass

            olay_metni = st.chat_input("Olayı anlatın...", key="ai_input_genel")
            
            if olay_metni:
                if not ai_secilen_dosyalar and mevcut_belgeler_ai:
                    st.error("Lütfen yapay zekanın okuması için en az bir belge işaretleyin!")
                else:
                    with st.chat_message("user"):
                        st.write(olay_metni)
                    
                    with st.chat_message("assistant"):
                        with st.spinner("Seçili kural sayfaları filtreleniyor ve yapay zeka analiz ediyor..."):
                            try:
                                kelimeler = [k.lower().strip() for k in olay_metni.split() if len(k) > 2]
                                sorgu = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen_dosyalar)
                                
                                if kelimeler:
                                    filtre_parcalari = [f"icerik.ilike.%{k}%" for k in kelimeler[:4]]
                                    sorgu = sorgu.or_(",".join(filtre_parcalari))
                                
                                response = sorgu.limit(15).execute()
                                
                                tum_metin = ""
                                if response.data:
                                    for satir in response.data:
                                        tum_metin += f"\n--- Sayfa {satir['sayfa_no']} ---\n{satir['icerik']}\n"
                                
                                if not tum_metin:
                                    yedek_resp = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen_dosyalar).limit(10).execute()
                                    for satir in yedek_resp.data:
                                        tum_metin += f"\n--- Sayfa {satir['sayfa_no']} ---\n{satir['icerik']}\n"
                                
                                prompt = f"""
                                Sen uluslararası yetkili bir Tenis Başhakemisin.
                                Sana resmi tenis kuralları dokümanından derlenen ilgili sayfaları veriyorum:
                                KURAL METİNLERİ:
                                {tum_metin}
                                
                                HAKEMİN SORDUĞU OLAY:
                                "{olay_metni}"
                                
                                GÖREVİN: Olayın ihlal olup olmadığını, verilecek kararı ve cezasını açıkla. Kararı dayandırdığın Sayfa Numarasını ekle.
                                """
                                
                                cevap = ai_model.generate_content(prompt)
                                st.markdown(cevap.text)
                                
                            except Exception as e:
                                st.error(f"Yapay Zeka analizi sırasında hata oluştu: {e}")

    # ------------------ 3. İNDEKS SEKMESİ ------------------
    with sekme_indeks:
        st.subheader("📚 Kayıtlı Belgeler Kütüphanesi")
        try:
            response = supabase.table("kural_icerikleri").select("dosya_adi, kategori, dosya_url").limit(10000).execute()
            if response.data:
                df = pd.DataFrame(response.data)
                df_unique = df.drop_duplicates(subset=["dosya_adi"]).reset_index(drop=True)
                
                siralama_turu = st.radio("Filtreleme Modu:", ["Alfabetik Sıralama", "Kategoriye Göre"], horizontal=True)
                
                if siralama_turu == "Alfabetik Sıralama":
                    df_unique = df_unique.sort_values(by="dosya_adi", ascending=True)
                    st.markdown("---")
                    for idx, row in df_unique.iterrows():
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.markdown(f"**{row['dosya_adi']}**")
                        with col2:
                            st.caption(f"📂 {row['kategori']}")
                        with col3:
                            doc_url = row['dosya_url']
                            if isinstance(doc_url, dict): doc_url = doc_url.get('publicUrl', '')
                            if doc_url: st.markdown(f"🔗 [Aç / İndir]({doc_url})")
                        st.markdown("---")
                else:
                    kategoriler_listesi = df_unique["kategori"].unique().tolist()
                    if kategoriler_listesi:
                        secilen_grup = st.selectbox("Görüntülenecek Kategoriyi Seçin:", kategoriler_listesi)
                        df_filtered = df_unique[df_unique["kategori"] == secilen_grup].sort_values(by="dosya_adi")
                        st.markdown("---")
                        if not df_filtered.empty:
                            for idx, row in df_filtered.iterrows():
                                col1, col2 = st.columns([4, 1])
                                with col1: st.markdown(f"**{row['dosya_adi']}**")
                                with col2:
                                    doc_url = row['dosya_url']
                                    if isinstance(doc_url, dict): doc_url = doc_url.get('publicUrl', '')
                                    if doc_url: st.markdown(f"🔗 [Aç / İndir]({doc_url})")
                                st.markdown("---")
                        else:
                            st.info("Bu kategoride kayıtlı belge bulunmuyor.")
            else:
                st.warning("Veritabanında henüz kayıtlı belge bulunmuyor.")
        except Exception as e:
            st.error(f"Arşiv yüklenirken hata oluştu: {e}")
