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
    "Sen uluslararası düzeyde görev yapan kıdemli bir Tenis Başhakemi ve Kural Uzmanısın. "
    "Sana sunulan 'RESMİ KURAL METNİ' dışına asla çıkma. Genel tenis ezberlerini ve varsayımlarını unut. "
    "Cevaplarını kesinlikle HİKAYELEŞTİRMEDEN, gereksiz laf kalabalığı yapmadan, net 2 ana başlık halinde yapılandır:\n\n"
    "### 1. SAHADA ANINDA VERİLECEK KARAR VE USUL\n"
    "- Hakemin/oyuncunun sahada o an atması gereken adımları madde madde (1, 2, 3...) kısa, net ve operasyonel olarak yaz.\n\n"
    "### 2. KURAL VE TALİMAT DAYANAĞI (Madde & Sayfa Referansı)\n"
    "- Bu kararın sunulan metindeki tam dayanağını belirt.\n"
    "- Varsa Belge Adı, Kural/Madde No, Başlık ve Sayfa Numarasını açıkça yaz.\n"
    "- Kitapçıktaki ilgili kural cümlesini/hükmünü tırnak içinde doğrudan alıntılayarak göster.\n"
    "- Metinde doğrudan yazmayan hiçbir ceza veya kuralı dışarıdan uydurma."
)

def gemini_modeli_ayarla():
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            system_instruction=HAKEM_ROL_TANIMI,
            generation_config={
                "temperature": 0.2,
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
        AŞAĞIDAKİ METNE KESİNLİKLE BAĞLI KAL:
        
        RESMİ KURAL METNİ:
        {baglam_metni}

        SAHADA YAŞANAN DURUM / SORU:
        "{olay_metni}"

        GÖREV:
        1. 'SAHADA ANINDA VERİLECEK KARAR VE USUL': Hikaye anlatmadan doğrudan uygulanacak adımları listele.
        2. 'KURAL VE TALİMAT DAYANAĞI': Sayfa no, madde no ve metindeki ilgili alıntıyı referans göster.
        """
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"⚠️ Gemini Hatası: {str(e)}"

def groq_ile_coz(client, baglam_metni, olay_metni):
    # Hesabınızdaki aktif ve erişilebilir modelleri dinamik olarak sorguluyoruz
    aktif_modeller = []
    try:
        modeller_cevap = client.models.list()
        for m in modeller_cevap.data:
            m_id = m.id.lower()
            # Ses, konuşma veya güvenlik modellerini filtrele; yalnızca metin modellerini al
            if not any(yasak in m_id for yasak in ["whisper", "tts", "guard", "safeguard", "orpheus"]):
                aktif_modeller.append(m.id)
    except Exception:
        aktif_modeller = []

    # Öncelikli denenecek güncel modeller
    oncelik_sirasi = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]

    # Hesaptaki modelleri öncelik sırasına göre diz
    denenecek_modeller = [m for m in oncelik_sirasi if m in aktif_modeller]
    # Hesaptaki diğer tüm metin modellerini de listenin sonuna yedek olarak ekle
    denenecek_modeller += [m for m in aktif_modeller if m not in denenecek_modeller]

    # Eğer liste çekilemediyse varsayılan listeyi doğrudan dene
    if not denenecek_modeller:
        denenecek_modeller = oncelik_sirasi

    son_hata = None
    for model_adi in denenecek_modeller:
        try:
            completion = client.chat.completions.create(
                model=model_adi,
                messages=[
                    {"role": "system", "content": HAKEM_ROL_TANIMI},
                    {
                        "role": "user",
                        "content": (
                            f"RESMİ KURAL METNİ:\n{baglam_metni}\n\n"
                            f"SAHADA YAŞANAN DURUM / SORU:\n{olay_metni}\n\n"
                            "GÖREV:\n"
                            "1. 'SAHADA ANINDA VERİLECEK KARAR VE USUL' başlığı altında hikayesiz, operasyonel adımları yaz.\n"
                            "2. 'KURAL VE TALİMAT DAYANAĞI' başlığı altında kural adı, madde no, sayfa no ve ilgili alıntıyı eksiksiz ver."
                        )
                    }
                ],
                temperature=0.2,
                max_tokens=900,
                stream=True
            )
            for chunk in completion:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return  # Başarılı şekilde yanıt akışı tamamlandı
        except Exception as e:
            son_hata = f"{model_adi} ({str(e)})"
            continue

    yield f"⚠️ Groq Hatası: Hesabınızda uygun model çalıştırılamadı. Detay: {son_hata}"

def arama_durumunu_sifirla():
    st.session_state.arama_sonuclari = None
    st.session_state.aranan_terimler = None
    st.session_state.son_aranan = ""

def hakem_panelini_ciz():
    st.markdown("""
        <style>
        .badge-cat {
            background-color: #1e293b;
            color: #38bdf8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid #0284c7;
        }
        .badge-page {
            background-color: #14532d;
            color: #4ade80;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid #16a34a;
        }
        .pdf-btn {
            background-color: #0f172a;
            color: #38bdf8 !important;
            padding: 7px 14px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
            border: 1px solid #0284c7;
            display: inline-block;
            transition: all 0.2s ease;
        }
        .pdf-btn:hover {
            background-color: #0284c7;
            color: #ffffff !important;
        }
        .snippet-box {
            background-color: #0b0f19;
            border-left: 3px solid #38bdf8;
            padding: 12px 16px;
            border-radius: 0 8px 8px 0;
            margin: 12px 0;
            font-family: monospace;
            font-size: 0.92rem;
            line-height: 1.6;
        }
        </style>
    """, unsafe_allow_html=True)

    try:
        supabase = supabase_baglantisi_kur()
    except Exception:
        st.error("Supabase bağlantı ayarları yüklenemedi. Secrets bölümünü kontrol edin.")
        return

    gemini_model = gemini_modeli_ayarla()
    groq_client = groq_istemcisi_ayarla()

    if 'aktif_kategori' not in st.session_state:
        st.session_state.aktif_kategori = "ITF Kuralları"
    if 'arama_sonuclari' not in st.session_state:
        st.session_state.arama_sonuclari = None
    if 'aranan_terimler' not in st.session_state:
        st.session_state.aranan_terimler = None
    if 'tam_kelime_modu' not in st.session_state:
        st.session_state.tam_kelime_modu = False
    if 'son_aranan' not in st.session_state:
        st.session_state.son_aranan = ""

    sekme_arama, sekme_ai, sekme_indeks = st.tabs(["🔍 Hızlı Kural Arama", "⚖️ Olay Çözücü AI", "📚 Belge Kütüphanesi"])

    # ==================== 1. KURAL ARAMA SEKMESİ ====================
    with sekme_arama:
        sonuclar_mevcut = st.session_state.arama_sonuclari is not None
        
        with st.expander("⚙️ Talimat Kategorisi & Belge Filtresi", expanded=not sonuclar_mevcut):
            st.markdown("###### Kategori Belirleyin:")
            kategoriler = [
                "ITF Kuralları", "Men's WTT", "Women's WTT", "WTT Juniors",
                "WTT Masters", "Wheelchair Tour", "Beach Tennis", "Tennis Europe",
                "ATP", "WTA", "Grand Slam", "TTF Ulusal", "Ulusal Diğer", "Sık Sorulanlar"
            ]
            
            c_cols = st.columns(4)
            for i, kat in enumerate(kategoriler):
                with c_cols[i % 4]:
                    is_active = (st.session_state.aktif_kategori == kat)
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(kat, key=f"kat_{kat}", use_container_width=True, type=btn_type):
                        st.session_state.aktif_kategori = kat
                        arama_durumunu_sifirla()
                        st.rerun()

            st.markdown("---")
            if st.button("🌐 Tüm Talimatlarda Aynı Anda Ara (Pro)", type="primary" if st.session_state.aktif_kategori == "Tüm Talimatlar" else "secondary", use_container_width=True):
                st.session_state.aktif_kategori = "Tüm Talimatlar"
                arama_durumunu_sifirla()
                st.rerun()

            secilen_dosyalar = []
            try:
                sorgu_belgeler = supabase.table("kural_icerikleri").select("dosya_adi")
                if st.session_state.aktif_kategori != "Tüm Talimatlar":
                    sorgu_belgeler = sorgu_belgeler.eq("kategori", st.session_state.aktif_kategori)
                
                belge_sonuc = sorgu_belgeler.execute().data
                mevcut_belgeler = sorted(list(set([row["dosya_adi"] for row in belge_sonuc])))

                if mevcut_belgeler:
                    st.markdown("###### Taranacak Belgeler:")
                    tumunu_sec = st.toggle("Tümünü Seç / Kaldır", value=True, key="toggle_dosyalar")
                    b_cols = st.columns(2)
                    for idx, b in enumerate(mevcut_belgeler):
                        with b_cols[idx % 2]:
                            if st.checkbox(b, value=tumunu_sec, key=f"chk_{b}"):
                                secilen_dosyalar.append(b)
                else:
                    st.info("Bu kategoriye ait henüz yüklenmiş belge bulunmuyor.")
            except Exception:
                st.error("Belgeler yüklenemedi.")

        col_info, col_reset = st.columns([4, 1])
        with col_info:
            st.markdown(f"Aktif Kategori: <span class='badge-cat'>{st.session_state.aktif_kategori}</span> ({len(secilen_dosyalar)} Belge Aktif)", unsafe_allow_html=True)
        with col_reset:
            if sonuclar_mevcut:
                if st.button("🗑️ Aramayı Sıfırla", use_container_width=True):
                    arama_durumunu_sifirla()
                    st.rerun()

        with st.form("arama_formu", clear_on_submit=False):
            f_col1, f_col2 = st.columns([5, 1])
            with f_col1:
                arama_metni = st.text_input(
                    "Aranacak terimi yazın:",
                    value=st.session_state.son_aranan,
                    placeholder='Örn: ayak hatası, toilet break veya tam kelime için: "or", "let"',
                    label_visibility="collapsed"
                )
            with f_col2:
                ara_tiklandi = st.form_submit_button("🔍 Ara", use_container_width=True, type="primary")

        if ara_tiklandi and arama_metni.strip():
            arama_durumunu_sifirla()
            st.session_state.son_aranan = arama_metni.strip()

            if not secilen_dosyalar and mevcut_belgeler:
                st.warning("Lütfen yukarıdaki filtreden en az bir belge seçin.")
            else:
                with st.spinner("İlgili kural sayfaları taranıyor..."):
                    try:
                        ham_metin = arama_metni.strip()
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
                            filtrelenmis = []
                            regex_kalip = re.compile(rf'\b{re.escape(aranan_ilk)}\b', re.IGNORECASE)
                            for k in ham_sonuclar:
                                if regex_kalip.search(k['icerik']):
                                    filtrelenmis.append(k)
                            st.session_state.arama_sonuclari = filtrelenmis
                        else:
                            st.session_state.arama_sonuclari = ham_sonuclar

                        st.session_state.aranan_terimler = aranacak_terimler_listesi
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sorgulama sırasında hata oluştu: {e}")

        if st.session_state.arama_sonuclari is not None:
            sonuclar = st.session_state.arama_sonuclari
            aranacak_terimler_listesi = st.session_state.aranan_terimler or []
            tam_kelime = st.session_state.tam_kelime_modu

            st.markdown("---")
            if sonuclar:
                st.markdown(f"#### 🎯 Bulunan İlgili Kural Sayfaları ({len(sonuclar)})")
                
                for idx, kayit in enumerate(sonuclar):
                    sayfa_no = kayit.get('sayfa_no', 1)
                    pdf_url = kayit['dosya_url']
                    if isinstance(pdf_url, dict):
                        pdf_url = pdf_url.get('publicUrl', '')

                    metin = kayit['icerik']
                    metin_lower = metin.lower()

                    bulunan_varyasyon = aranacak_terimler_listesi[0] if aranacak_terimler_listesi else ""
                    for varyasyon in aranacak_terimler_listesi:
                        if tam_kelime:
                            if re.search(rf'\b{re.escape(varyasyon)}\b', metin_lower):
                                bulunan_varyasyon = varyasyon
                                break
                        else:
                            if varyasyon in metin_lower:
                                bulunan_varyasyon = varyasyon
                                break

                    with st.container(border=True):
                        h_col1, h_col2 = st.columns([3, 2])
                        with h_col1:
                            st.markdown(
                                f"📄 **{kayit['dosya_adi']}** &nbsp; "
                                f"<span class='badge-cat'>{kayit['kategori']}</span> &nbsp; "
                                f"<span class='badge-page'>Sayfa {sayfa_no}</span>",
                                unsafe_allow_html=True
                            )
                        with h_col2:
                            if pdf_url:
                                url_kodlu = urllib.parse.quote(f'"{bulunan_varyasyon}"')
                                hedefli_url = f"{pdf_url}?render=true#page={sayfa_no}&search={url_kodlu}"
                                st.markdown(
                                    f"<div style='text-align: right;'><a href='{hedefli_url}' target='_blank' class='pdf-btn'>↗️ {sayfa_no}. Sayfayı Aç ve Vurgula</a></div>",
                                    unsafe_allow_html=True
                                )

                        if tam_kelime:
                            match = re.search(rf'\b{re.escape(bulunan_varyasyon)}\b', metin, re.IGNORECASE)
                            idx_text = match.start() if match else -1
                        else:
                            idx_text = metin_lower.find(bulunan_varyasyon)

                        if idx_text != -1:
                            baslangic = max(0, idx_text - 140)
                            bitis = min(len(metin), idx_text + 400)
                            kesit = metin[baslangic:bitis].replace("\n", " ")
                            
                            pattern = re.compile(rf'\b({re.escape(bulunan_varyasyon)})\b' if tam_kelime else re.escape(bulunan_varyasyon), re.IGNORECASE)
                            vurgulu = pattern.sub(lambda m: f"<span style='background-color: #38bdf8; color: #020617; font-weight: bold; padding: 2px 5px; border-radius: 4px;'>{m.group(0)}</span>", kesit)
                            st.markdown(f"<div class='snippet-box'>...{vurgulu}...</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div class='snippet-box'>...{metin[:350]}...</div>", unsafe_allow_html=True)

                        with st.expander("⚖️ Bu Sayfa Kuralını Yapay Zekaya Danış (Karar & Madde Dayanağı)"):
                            ai_soru = st.text_input("Sahada karşılaşılan pozisyonu veya tereddüdü yazın:", key=f"q_{idx}")
                            btn_c1, btn_c2 = st.columns(2)
                            
                            with btn_c1:
                                if st.button("⚡ Groq ile Çöz", key=f"btn_groq_{idx}", use_container_width=True):
                                    if not ai_soru:
                                        st.warning("Lütfen pozisyonu yazın.")
                                    elif not groq_client:
                                        st.error("Groq API anahtarı ayarlanmamış.")
                                    else:
                                        st.markdown("---")
                                        st.write_stream(groq_ile_coz(groq_client, metin, ai_soru))

                            with btn_c2:
                                if st.button("✨ Gemini ile Çöz", key=f"btn_gemini_{idx}", use_container_width=True):
                                    if not ai_soru:
                                        st.warning("Lütfen pozisyonu yazın.")
                                    elif not gemini_model:
                                        st.error("Gemini API anahtarı ayarlanmamış.")
                                    else:
                                        st.markdown("---")
                                        st.write_stream(gemini_ile_coz(gemini_model, metin, ai_soru))
            else:
                st.warning("Seçili belgelerde aranan terime ilişkin bir kayıt bulunamadı.")

    # ==================== 2. GENEL OLAY ÇÖZÜCÜ AI SEKMESİ ====================
    with sekme_ai:
        st.subheader("⚖️ Başhakem Olay ve Kural Danışmanı")
        st.caption("Doğrudan seçtiğiniz kategorideki kitapçıkları tarayarak operasyonel adım ve madde dayanağı üretir.")

        if st.session_state.aktif_kategori == "Kategori Seçilmedi" or st.session_state.aktif_kategori == "Tüm Talimatlar":
            st.warning("Lütfen arama sekmesinden taranacak tek bir kategori seçin.")
        else:
            ai_secilen = []
            try:
                sorgu_ai = supabase.table("kural_icerikleri").select("dosya_adi").eq("kategori", st.session_state.aktif_kategori)
                sonuclar_ai = sorgu_ai.execute().data
                dosyalar_ai = sorted(list(set([r["dosya_adi"] for r in sonuclar_ai])))
                if dosyalar_ai:
                    with st.expander("İncelenecek Belgeleri Düzenle", expanded=False):
                        for d in dosyalar_ai:
                            if st.checkbox(d, value=True, key=f"ai_chk_{d}"):
                                ai_secilen.append(d)
                else:
                    ai_secilen = []
            except Exception:
                ai_secilen = []

            genel_olay = st.text_area("Sahada yaşanan olayı detaylandırın:", height=110, placeholder="Örn: Raket elden fırlayıp fileye değerse ancak top daha önce rakip sahada iki kez sekmişse ne kararı verilir?")
            g1, g2 = st.columns(2)
            calistir_groq = g1.button("⚡ Groq ile Analiz Et", use_container_width=True, type="primary")
            calistir_gemini = g2.button("✨ Gemini ile Analiz Et", use_container_width=True)

            if (calistir_groq or calistir_gemini) and genel_olay:
                if not ai_secilen and dosyalar_ai:
                    st.error("Lütfen taranacak en az bir belge seçin.")
                else:
                    with st.spinner("Kurallar taranıyor ve analiz ediliyor..."):
                        kelimeler = [k.lower().strip() for k in genel_olay.split() if len(k) > 2]
                        sorgu = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen)

                        if kelimeler:
                            filtre_parcalari = [f"icerik.ilike.%{k}%" for k in kelimeler[:4]]
                            sorgu = sorgu.or_(",".join(filtre_parcalari))

                        resp = sorgu.limit(10).execute()
                        baglam = ""
                        if resp.data:
                            for row in resp.data:
                                baglam += f"\n--- Sayfa {row['sayfa_no']} ---\n{row['icerik']}\n"

                        if not baglam:
                            yedek = supabase.table("kural_icerikleri").select("sayfa_no, icerik").eq("kategori", st.session_state.aktif_kategori).in_("dosya_adi", ai_secilen).limit(5).execute()
                            for row in yedek.data:
                                baglam += f"\n--- Sayfa {row['sayfa_no']} ---\n{row['icerik']}\n"

                        st.markdown("---")
                        if calistir_groq:
                            if groq_client:
                                st.write_stream(groq_ile_coz(groq_client, baglam, genel_olay))
                            else:
                                st.error("Groq API anahtarı bulunamadı.")
                        elif calistir_gemini:
                            if gemini_model:
                                st.write_stream(gemini_ile_coz(gemini_model, baglam, genel_olay))
                            else:
                                st.error("Gemini API anahtarı bulunamadı.")

    # ==================== 3. BELGE KÜTÜPHANESİ SEKMESİ ====================
    with sekme_indeks:
        st.subheader("📚 Kayıtlı Belgeler Arşivi")
        try:
            response = supabase.table("kural_icerikleri").select("dosya_adi, kategori, dosya_url").limit(10000).execute()
            if response.data:
                df = pd.DataFrame(response.data)
                df_unique = df.drop_duplicates(subset=["dosya_adi"]).reset_index(drop=True)

                filtreleme = st.radio("Sıralama / Görünüm:", ["Alfabetik Sıralama", "Kategoriye Göre Grupla"], horizontal=True)

                if filtreleme == "Alfabetik Sıralama":
                    df_unique = df_unique.sort_values(by="dosya_adi", ascending=True)
                    st.markdown("---")
                    for idx, row in df_unique.iterrows():
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([4, 2, 1])
                            with c1:
                                st.markdown(f"📄 **{row['dosya_adi']}**")
                            with c2:
                                st.markdown(f"<span class='badge-cat'>{row['kategori']}</span>", unsafe_allow_html=True)
                            with c3:
                                doc_url = row['dosya_url']
                                if isinstance(doc_url, dict):
                                    doc_url = doc_url.get('publicUrl', '')
                                if doc_url:
                                    st.markdown(f"<a href='{doc_url}' target='_blank' class='pdf-btn'>Aç</a>", unsafe_allow_html=True)
                else:
                    kategoriler_listesi = df_unique["kategori"].unique().tolist()
                    if kategoriler_listesi:
                        secilen_grup = st.selectbox("Görüntülenecek Kategori:", kategoriler_listesi)
                        df_filtered = df_unique[df_unique["kategori"] == secilen_grup].sort_values(by="dosya_adi")
                        st.markdown("---")
                        if not df_filtered.empty:
                            for idx, row in df_filtered.iterrows():
                                with st.container(border=True):
                                    c1, c2 = st.columns([5, 1])
                                    with c1:
                                        st.markdown(f"📄 **{row['dosya_adi']}**")
                                    with c2:
                                        doc_url = row['dosya_url']
                                        if isinstance(doc_url, dict):
                                            doc_url = doc_url.get('publicUrl', '')
                                        if doc_url:
                                            st.markdown(f"<a href='{doc_url}' target='_blank' class='pdf-btn'>Aç</a>", unsafe_allow_html=True)
                        else:
                            st.info("Bu kategoride kayıtlı belge bulunmuyor.")
            else:
                st.warning("Veritabanında henüz kayıtlı belge bulunmuyor.")
        except Exception as e:
            st.error(f"Arşiv yüklenirken hata oluştu: {e}")
