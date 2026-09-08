import streamlit as st
import pandas as pd
import re
import urllib.parse
from supabase import create_client, Client
import google.generativeai as genai
from groq import Groq

from sozluk import TENNIS_SOZLugu

def supabase_baglantisi_kur():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

HAKEM_ROL_TANIMI = (
    "Sen tenisi çok iyi bilen, oyunun ruhuna ve kuralların gerekçelerine hakim kıdemli bir tenis mentoru ve uluslararası bir başhakemsin. "
    "Karşında kuralı merak eden, kendini geliştirmek isteyen bir tenis sporcusu / oyuncusu var. "
    "Telsiz anonsu gibi kuru, emredici, telaşlı veya sadece ceza odaklı bir hakem üslubu KULLANMA. "
    "Tersine; son derece samimi, anlaşılır, öğretici ve profesyonel bir dille konuş. "
    "Kuralın sahada nasıl uygulandığını, bu kuralın neden var olduğunu (oyun adaletini nasıl sağladığını) "
    "ve sporcunun sahada benzer bir durumda ne beklemesi/nasıl davranması gerektiğini bir antrenör gibi açıkla. "
    "Gerekirse metindeki kural ve madde referansını da sporcuya rehberlik edecek şekilde nazikçe belirt."
)

def gemini_modeli_ayarla():
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            system_instruction=HAKEM_ROL_TANIMI,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 900
            }
        )
        return model
    except Exception:
        return None

def groq_istemcisi_ayarla():
    try:
        api_key = st.secrets["groq"]["api_key"].strip()
        return Groq(api_key=api_key)
    except Exception:
        return None

def gemini_ile_coz(model, baglam_metni, olay_metni):
    try:
        prompt = f"""
        Aşağıda resmi tenis talimatı/kural sayfasından bir kesit yer alıyor:
        RESMİ KURAL METNİ:
        {baglam_metni}

        SPORCUNUN MERAK ETTİĞİ OLAY / SORU:
        "{olay_metni}"

        GÖREV:
        Bu kuralı bir sporcunun kolayca kavrayabileceği şekilde; mantığını, oyundaki yerini ve sahada böyle bir durum olduğunda ne yaşanacağını açık, akıcı ve samimi bir dille anlat.
        """
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"⚠️ Gemini Hatası: {str(e)}"

def groq_ile_coz(client, baglam_metni, olay_metni):
    guncel_modeller = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b"
    ]
    
    son_hata = None
    for model_adi in guncel_modeller:
        try:
            completion = client.chat.completions.create(
                model=model_adi,
                messages=[
                    {"role": "system", "content": HAKEM_ROL_TANIMI},
                    {
                        "role": "user",
                        "content": (
                            f"RESMİ KURAL METNİ:\n{baglam_metni}\n\n"
                            f"SPORCUNUN MERAK ETTİĞİ OLAY / SORU:\n{olay_metni}\n\n"
                            f"GÖREV:\nBu kuralı bir sporcunun kolayca anlayabileceği şekilde; mantığını, sahadaki yansımasını ve bu kuralın arkasındaki nedeni samimi ve öğretici bir dille açıkla."
                        )
                    }
                ],
                temperature=0.4,
                max_tokens=900,
                stream=True
            )
            for chunk in completion:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return
        except Exception as e:
            son_hata = str(e)
            continue
            
    yield f"⚠️ Groq Hatası: {son_hata}"

def hakem_panelini_ciz():
    st.title("Başhakem Dijital Asistanı")
    st.markdown("Kural arayın, talimatları inceleyin veya **merak ettiğiniz kuralı Yapay Zekaya anlattırın.**")
    st.caption('💡 **İpucu:** Tam kelime aramak için tırnak içine alabilirsiniz: `"or"`, `"let"`')
    st.markdown("---")

    try:
        supabase = supabase_baglantisi_kur()
    except Exception:
        st.error("Supabase bağlantı ayarları yüklenemedi. Lütfen Secrets bölümünü kontrol edin.")
        return

    gemini_model = gemini_modeli_ayarla()
    groq_client = groq_istemcisi_ayarla()

    sekme_arama, sekme_ai, sekme_indeks = st.tabs(["🔍 Kural Arama", "🤖 Genel Kural Danışmanı", "📚 Belge İndeksi"])

    # ------------------ 1. ARAMA VE ÇİFT YAPAY ZEKA DESTEĞİ ------------------
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

            secilen_dosyalar = []
            try:
                sorgu_belgeler = supabase.table("kural_icerikleri").select("dosya_adi")
                if st.session_state.aktif_kategori != "Tüm Talimatlar":
                    sorgu_belgeler = sorgu_belgeler.eq("kategori", st.session_state.aktif_kategori)

                belge_sonuc = sorgu_belgeler.execute().data
                mevcut_belgeler = sorted(list(set([row["dosya_adi"] for row in belge_sonuc])))

                if mevcut_belgeler:
                    st.markdown("###### Aramaya Dahil Edilecek Belgeler:")
                    tumunu_sec = st.toggle("Hepsini Seç / Kaldır", value=True, key="toggle_arama")
                    for belge in mevcut_belgeler:
                        if st.checkbox(belge, value=tumunu_sec, key=f"chk_{belge}"):
                            secilen_dosyalar.append(belge)
                else:
                    st.warning("Bu kategoride kayıtlı belge bulunamadı.")
            except Exception:
                st.error("Belgeler yüklenirken hata oluştu.")

            if "arama_sonuclari" not in st.session_state:
                st.session_state.arama_sonuclari = None
            if "aranan_terimler" not in st.session_state:
                st.session_state.aranan_terimler = None
            if "tam_kelime_modu" not in st.session_state:
                st.session_state.tam_kelime_modu = False

            aranan_ham = st.chat_input('Aranacak kelimeyi yazın (Tam kelime için: "or")...')

            if aranan_ham:
                if not secilen_dosyalar and mevcut_belgeler:
                    st.error("Lütfen arama yapmak için en az bir belge işaretleyin!")
                else:
                    with st.chat_message("user"):
                        st.write(aranan_ham)

                    with st.spinner("Seçili belgelerde taranıyor..."):
                        try:
                            ham_metin = aranan_ham.strip()
                            tam_kelime = False
                            if (ham_metin.startswith('"') and ham_metin.endswith('"')) or \
                               (ham_metin.startswith("'") and ham_metin.endswith("'")):
                                tam_kelime = True
                                aranan_ilk = ham_metin[1:-1].lower().strip()
                            else:
                                aranan_ilk = ham_metin.lower().strip()

                            aranan_ilk = re.sub(r'\s+', ' ', aranan_ilk)
                            st.session_state.tam_kelime_modu = tam_kelime

                            temel_terimler = {aranan_ilk}

                            # Tek yönlü sözlük: Sadece kullanıcı Türkçe girdiğinde İngilizceler eklenir
                            if not tam_kelime:
                                for tr_key, en_list in TENNIS_SOZLugu.items():
                                    if aranan_ilk == tr_key:
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
                            sorgu = sorgu.in_("dosya_adi", secilen_dosyalar)
                            
                            filtre_parcalari = [f"icerik.ilike.%{terim}%" for terim in aranacak_terimler_listesi]
                            sorgu = sorgu.or_(",".join(filtre_parcalari))

                            ham_sonuclar = sorgu.execute().data

                            if tam_kelime:
                                filtrelenmis_sonuclar = []
                                regex_kalip = re.compile(rf'\b{re.escape(aranan_ilk)}\b', re.IGNORECASE)
                                for k in ham_sonuclar:
                                    if regex_kalip.search(k['icerik']):
                                        filtrelenmis_sonuclar.append(k)
                                st.session_state.arama_sonuclari = filtrelenmis_sonuclar
                            else:
                                st.session_state.arama_sonuclari = ham_sonuclar

                            st.session_state.aranan_terimler = aranacak_terimler_listesi
                        except Exception as e:
                            st.error(f"Arama sırasında hata oluştu: {e}")

            if st.session_state.arama_sonuclari is not None:
                sonuclar = st.session_state.arama_sonuclari
                aranacak_terimler_listesi = st.session_state.aranan_terimler
                tam_kelime = st.session_state.tam_kelime_modu

                if sonuclar:
                    st.success(f"Bulunan ilgili sayfa sayısı: {len(sonuclar)}")

                    for idx, kayit in enumerate(sonuclar):
                        sayfa_no = kayit.get('sayfa_no', 1)
                        st.markdown(f"**Belge:** {kayit['dosya_adi']} *({kayit['kategori']}) | Sayfa: {sayfa_no}*")

                        pdf_url = kayit['dosya_url']
                        if isinstance(pdf_url, dict):
                            pdf_url = pdf_url.get('publicUrl', '')

                        metin = kayit['icerik']
                        metin_lower = metin.lower()

                        bulunan_varyasyon = aranacak_terimler_listesi[0]
                        for varyasyon in aranacak_terimler_listesi:
                            if tam_kelime:
                                if re.search(rf'\b{re.escape(varyasyon)}\b', metin_lower):
                                    bulunan_varyasyon = varyasyon
                                    break
                            else:
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

                        if tam_kelime:
                            match = re.search(rf'\b{re.escape(bulunan_varyasyon)}\b', metin, re.IGNORECASE)
                            idx_text = match.start() if match else -1
                        else:
                            idx_text = metin_lower.find(bulunan_varyasyon)

                        if idx_text != -1:
                            baslangic = max(0, idx_text - 120)
                            bitis = min(len(metin), idx_text + 350)
                            kesit = metin[baslangic:bitis].replace("\n", " ")
                            
                            if tam_kelime:
                                pattern = re.compile(rf'\b({re.escape(bulunan_varyasyon)})\b', re.IGNORECASE)
                            else:
                                pattern = re.compile(re.escape(bulunan_varyasyon), re.IGNORECASE)
                                
                            vurgulu_kesit = pattern.sub(lambda m: f'<span style="background-color: #39ff14; color: #000000; font-weight: bold; padding: 2px 4px; border-radius: 3px;">{m.group(0)}</span>', kesit)
                            st.markdown(f"**İlgili Bağlam:**<br>...{vurgulu_kesit}...", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**İlgili Bağlam:**<br>...{metin[:300]}...", unsafe_allow_html=True)

                        # Sporcu odaklı soru/öğrenme alanı
                        st.markdown(f"**🎾 {sayfa_no}. Sayfa Kuralını Sporcu Bakışıyla Yorumlat**")
                        ai_soru = st.text_input("Kural hakkında merak ettiğiniz durumu veya senaryoyu yazın:", key=f"soru_{idx}")

                        btn_col1, btn_col2 = st.columns(2)

                        with btn_col1:
                            if st.button("⚡ Groq ile Kuralı Açıkla", key=f"groq_{idx}", use_container_width=True):
                                if not ai_soru:
                                    st.warning("Lütfen merak ettiğiniz durumu yazın.")
                                elif not groq_client:
                                    st.error("Groq API anahtarı ayarlanmamış.")
                                else:
                                    st.success("🎾 **Mentor Açıklaması (Groq):**")
                                    st.write_stream(groq_ile_coz(groq_client, metin, ai_soru))

                        with btn_col2:
                            if st.button("✨ Gemini ile Kuralı Açıkla", key=f"gemini_{idx}", use_container_width=True):
                                if not ai_soru:
                                    st.warning("Lütfen merak ettiğiniz durumu yazın.")
                                elif not gemini_model:
                                    st.error("Gemini API anahtarı ayarlanmamış.")
                                else:
                                    st.success("🎾 **Mentor Açıklaması (Gemini):**")
                                    st.write_stream(gemini_ile_coz(gemini_model, metin, ai_soru))

                        st.markdown("---")
                else:
                    st.warning("Seçili belgelerde bu terime rastlanmadı.")

    # ------------------ 2. GENEL YAPAY ZEKA SEKMESİ ------------------
    with sekme_ai:
        st.subheader("🎾 Tenis Kural Danışmanı")
        st.markdown("Kafanıza takılan bir kuralı veya maç senaryosunu yazın; bir sporcunun en rahat anlayacağı şekilde anlatalım.")

        if st.session_state.aktif_kategori == "Kategori Seçilmedi" or st.session_state.aktif_kategori == "Tüm Talimatlar":
            st.warning("Lütfen arama sekmesinden taranacak tek bir kategori belirleyin.")
        else:
            ai_secilen_dosyalar = []
            try:
                sorgu_belgeler_ai = supabase.table("kural_icerikleri").select("dosya_adi").eq("kategori", st.session_state.aktif_kategori)
                belge_sonuc_ai = sorgu_belgeler_ai.execute().data
                mevcut_belgeler_ai = sorted(list(set([row["dosya_adi"] for row in belge_sonuc_ai])))

                if mevcut_belgeler_ai:
                    st.markdown("###### İncelenecek Talimatlar:")
                    tumunu_sec_ai = st.toggle("Tümünü Seç / Kaldır", value=True, key="toggle_ai")
                    for belge in mevcut_belgeler_ai:
                        if st.checkbox(belge, value=tumunu_sec_ai, key=f"ai_chk_{belge}"):
                            ai_secilen_dosyalar.append(belge)
            except Exception:
                pass

            genel_olay = st.text_area("Merak ettiğiniz durumu detaylandırın (Örn: Servis atarken top tavana değerse ne olur?):", height=100)
            g_col1, g_col2 = st.columns(2)

            calistir_groq = g_col1.button("⚡ Groq ile Detaylı Anlat", use_container_width=True, type="primary")
            calistir_gemini = g_col2.button("✨ Gemini ile Detaylı Anlat", use_container_width=True)

            if (calistir_groq or calistir_gemini) and genel_olay:
                if not ai_secilen_dosyalar and mevcut_belgeler_ai:
                    st.error("Lütfen incelenecek en az bir belge seçin.")
                else:
                    with st.spinner("Kurallar taranıyor ve derleniyor..."):
                        kelimeler = [k.lower().strip() for k in genel_olay.split() if len(k) > 2]
                        sorgu = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen_dosyalar)

                        if kelimeler:
                            filtre_parcalari = [f"icerik.ilike.%{k}%" for k in kelimeler[:4]]
                            sorgu = sorgu.or_(",".join(filtre_parcalari))

                        response = sorgu.limit(10).execute()

                        baglam_metni = ""
                        if response.data:
                            for satir in response.data:
                                baglam_metni += f"\n--- Sayfa {satir['sayfa_no']} ---\n{satir['icerik']}\n"

                        if not baglam_metni:
                            yedek = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen_dosyalar).limit(5).execute()
                            for satir in yedek.data:
                                baglam_metni += f"\n--- Sayfa {satir['sayfa_no']} ---\n{satir['icerik']}\n"

                        if calistir_groq:
                            if groq_client:
                                st.success("🎾 **Mentor Açıklaması (Groq):**")
                                st.write_stream(groq_ile_coz(groq_client, baglam_metni, genel_olay))
                            else:
                                st.error("Groq API anahtarı bulunamadı.")
                        elif calistir_gemini:
                            if gemini_model:
                                st.success("🎾 **Mentor Açıklaması (Gemini):**")
                                st.write_stream(gemini_ile_coz(gemini_model, baglam_metni, genel_olay))
                            else:
                                st.error("Gemini API anahtarı bulunamadı.")

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
                            if isinstance(doc_url, dict):
                                doc_url = doc_url.get('publicUrl', '')
                            if doc_url:
                                st.markdown(f"🔗 [Aç / İndir]({doc_url})")
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
                                with col1:
                                    st.markdown(f"**{row['dosya_adi']}**")
                                with col2:
                                    doc_url = row['dosya_url']
                                    if isinstance(doc_url, dict):
                                        doc_url = doc_url.get('publicUrl', '')
                                    if doc_url:
                                        st.markdown(f"🔗 [Aç / İndir]({doc_url})")
                                st.markdown("---")
                        else:
                            st.info("Bu kategoride kayıtlı belge bulunmuyor.")
            else:
                st.warning("Veritabanında henüz kayıtlı belge bulunmuyor.")
        except Exception as e:
            st.error(f"Arşiv yüklenirken hata oluştu: {e}")
