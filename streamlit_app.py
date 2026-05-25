"""Meta Ads Explorer — interfaz web con Streamlit.

Correr con:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter

import pandas as pd
import streamlit as st

from meta_ads_explorer.analyzer import CreativeAnalyzer
from meta_ads_explorer.config import Settings
from meta_ads_explorer.models import Ad
from meta_ads_explorer.scraper import (
    SearchParams,
    extract_page_id_from_url,
    scrape_to_list,
)
from meta_ads_explorer.storage import Storage

st.set_page_config(
    page_title="Meta Ads Explorer",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_settings() -> Settings:
    return Settings.load()


@st.cache_resource
def get_storage() -> Storage:
    return Storage(get_settings().db_path)


def row_to_ad(r) -> Ad:
    return Ad(
        ad_archive_id=r["ad_archive_id"],
        page_id=r["page_id"],
        page_name=r["page_name"],
        body_text=r["body_text"],
        title=r["title"],
        caption=r["caption"],
        cta_text=r["cta_text"],
        cta_type=r["cta_type"],
        link_url=r["link_url"],
        publisher_platforms=json.loads(r["publisher_platforms"] or "[]"),
        images=json.loads(r["images"] or "[]"),
        videos=json.loads(r["videos"] or "[]"),
        is_active=bool(r["is_active"]) if r["is_active"] is not None else None,
        raw={},
    )


s = get_settings()
storage = get_storage()

st.sidebar.title("🎯 Meta Ads Explorer")
section = st.sidebar.radio(
    "Sección",
    [
        "🔍 Buscar",
        "📺 Páginas trackeadas",
        "🤖 Analizar con IA",
        "📊 Reporte",
        "📥 Exportar",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"📦 DB: `{s.db_path.name}`")
st.sidebar.caption(f"🌎 País default: `{s.country}`")
st.sidebar.caption(f"🤖 Modelo: `{s.claude_model}`")
if not s.anthropic_api_key:
    st.sidebar.warning("⚠️ Sin `ANTHROPIC_API_KEY`. El análisis con IA no va a funcionar — el resto sí.")


# ─────────────────────────── 🔍 BUSCAR ───────────────────────────
if section == "🔍 Buscar":
    st.header("🔍 Buscar anuncios en la Ad Library")
    st.caption(
        "Scrapea la biblioteca pública de Meta. Cada búsqueda lanza un Chrome real, "
        "scrollea durante 1-5 min y guarda lo que encuentre en la base local."
    )

    with st.form("search_form"):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            query = st.text_input("Palabra clave o frase", placeholder="ej: curso de inglés")
        with c2:
            country = st.text_input("País (ISO-2)", value=s.country, max_chars=2).upper()
        with c3:
            max_ads = st.number_input("Máx. anuncios", 10, 500, 60, 10)

        c4, c5, c6 = st.columns(3)
        with c4:
            ad_type = st.selectbox(
                "Tipo",
                ["all", "political_and_issue_ads", "employment_ads", "housing_ads", "credit_ads"],
            )
        with c5:
            active_status = st.selectbox("Estado", ["active", "inactive", "all"])
        with c6:
            media_type = st.selectbox("Media", ["all", "image", "video", "meme", "none"])

        submitted = st.form_submit_button("🔍 Buscar y guardar", type="primary")

    if submitted:
        if not query.strip():
            st.error("Escribí una palabra clave.")
        else:
            params = SearchParams(
                country=country, query=query, ad_type=ad_type,
                active_status=active_status, media_type=media_type,
            )
            with st.spinner(f"Scrapeando Ad Library ({country})… esto suele tardar 1-5 min"):
                try:
                    ads = asyncio.run(
                        scrape_to_list(params, int(max_ads), s.headless, s.scroll_delay)
                    )
                except Exception as e:
                    st.error(f"Falló el scraping: {e}")
                    ads = []

            if ads:
                new, seen = storage.upsert_ads(ads)
                storage.log_search(
                    query, country, ad_type, active_status, None, len(ads), params.to_url()
                )
                st.success(f"✅ {len(ads)} anuncios | 🆕 {new} nuevos | 🔁 {seen} actualizados")

                df = pd.DataFrame([{
                    "id": a.ad_archive_id,
                    "página": a.page_name,
                    "activo": "🟢" if a.is_active else "⚪",
                    "CTA": a.cta_text or "—",
                    "copy": (a.body_text or "")[:140],
                    "🖼": len(a.images),
                    "🎬": len(a.videos),
                } for a in ads])
                st.dataframe(df, use_container_width=True, height=320)

                st.markdown("### 👀 Vista previa de los primeros 5 anuncios")
                for ad in ads[:5]:
                    with st.expander(f"{'🟢' if ad.is_active else '⚪'} {ad.page_name} — {ad.ad_archive_id}"):
                        cols = st.columns([2, 3])
                        with cols[0]:
                            for img in ad.images[:2]:
                                try:
                                    st.image(img, width=280)
                                except Exception:
                                    st.caption(img)
                        with cols[1]:
                            st.write(ad.body_text or "_(sin copy)_")
                            st.caption(
                                f"**CTA:** {ad.cta_text or '—'}  ·  "
                                f"**Link:** {ad.link_url or '—'}  ·  "
                                f"**Plataformas:** {', '.join(ad.publisher_platforms) or '—'}"
                            )
            else:
                st.warning(
                    "0 resultados. Probá: bajar `headless` a false en `.env` para ver qué pasa, "
                    "cambiar la palabra clave, o esperar (Meta a veces rate-limitea)."
                )


# ─────────────────────── 📺 PÁGINAS TRACKEADAS ───────────────────────
elif section == "📺 Páginas trackeadas":
    st.header("📺 Páginas trackeadas")
    st.caption("Páginas que vas a re-scrapear seguido para detectar anuncios nuevos.")

    with st.expander("➕ Agregar nueva página", expanded=False):
        with st.form("add_page_form"):
            c1, c2 = st.columns([2, 1])
            with c1:
                new_page = st.text_input(
                    "`page_id` o URL completa de Ad Library",
                    placeholder="1234567890 o https://www.facebook.com/ads/library/?view_all_page_id=...",
                )
            with c2:
                new_country = st.text_input("País", value=s.country, max_chars=2).upper()
            new_notes = st.text_input("Notas (opcional)", placeholder="ej: competidor directo")
            max_initial = st.number_input("Cuántos ads scrapear ahora", 10, 300, 80, 10)
            add_submitted = st.form_submit_button("Agregar y scrapear", type="primary")

        if add_submitted:
            page_id = extract_page_id_from_url(new_page) or new_page.strip()
            if not page_id.isdigit():
                st.error("page_id inválido. Tiene que ser un número.")
            else:
                params = SearchParams(country=new_country, page_id=page_id, active_status="all")
                with st.spinner(f"Scrapeando página {page_id}…"):
                    try:
                        ads = asyncio.run(
                            scrape_to_list(params, int(max_initial), s.headless, s.scroll_delay)
                        )
                    except Exception as e:
                        st.error(f"Falló: {e}")
                        ads = []
                page_name = ads[0].page_name if ads else None
                storage.add_tracked_page(page_id, page_name, new_country, new_notes or None)
                if ads:
                    storage.upsert_ads(ads)
                storage.mark_page_checked(page_id)
                st.success(f"✅ {page_name or page_id} agregada · {len(ads)} anuncios guardados")
                st.rerun()

    pages = storage.list_tracked_pages()
    if not pages:
        st.info("No hay páginas trackeadas. Agregá una arriba ⬆️")
    else:
        for p in pages:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.subheader(p["page_name"] or p["page_id"])
                    st.caption(
                        f"`{p['page_id']}` · 🌎 {p['country']} · "
                        f"agregada {p['added_at'][:10]} · "
                        f"último check: {p['last_checked_at'][:16] if p['last_checked_at'] else 'nunca'}"
                    )
                    if p["notes"]:
                        st.markdown(f"📝 _{p['notes']}_")
                    diff = storage.diff_for_page(p["page_id"])
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Activos", diff["active"])
                    m2.metric("Inactivos", diff["inactive"])
                    m3.metric("Nuevos 7d", diff["new_last_7d"])
                with col2:
                    if st.button("🔄 Re-scrapear", key=f"rescrape_{p['page_id']}"):
                        params = SearchParams(
                            country=p["country"], page_id=p["page_id"], active_status="all"
                        )
                        with st.spinner("Re-scrapeando…"):
                            try:
                                ads = asyncio.run(
                                    scrape_to_list(params, 100, s.headless, s.scroll_delay)
                                )
                                new, _ = storage.upsert_ads(ads)
                                storage.mark_page_checked(p["page_id"])
                                st.toast(f"+{new} nuevos en {p['page_name'] or p['page_id']}")
                            except Exception as e:
                                st.error(f"Falló: {e}")
                        st.rerun()
                with col3:
                    if st.button("👁 Ver ads", key=f"view_{p['page_id']}"):
                        st.session_state["view_page_id"] = p["page_id"]

        pid = st.session_state.get("view_page_id")
        if pid:
            st.markdown("---")
            st.subheader(f"Anuncios de `{pid}`")
            ads = storage.ads_for_page(pid)
            st.caption(f"{len(ads)} anuncios guardados")
            for ad_row in ads[:30]:
                title = (
                    f"{'🟢' if ad_row['is_active'] else '⚪'} "
                    f"{ad_row['page_name'] or ad_row['ad_archive_id']} — "
                    f"{(ad_row['body_text'] or '')[:60]}"
                )
                with st.expander(title):
                    cols = st.columns([2, 3])
                    images = json.loads(ad_row["images"] or "[]")
                    with cols[0]:
                        for img in images[:2]:
                            try:
                                st.image(img, width=280)
                            except Exception:
                                st.caption(img)
                    with cols[1]:
                        st.write(ad_row["body_text"] or "_(sin copy)_")
                        st.caption(
                            f"CTA: {ad_row['cta_text'] or '—'} · "
                            f"Link: {ad_row['link_url'] or '—'}"
                        )


# ─────────────────────── 🤖 ANALIZAR CON IA ───────────────────────
elif section == "🤖 Analizar con IA":
    st.header("🤖 Análisis de creatividades con Claude")
    st.caption(
        "Claude mira las creatividades + el copy y devuelve ángulo, hook, audiencia, "
        "pain points, calidad estimada y red flags."
    )

    if not s.anthropic_api_key:
        st.error(
            "Falta `ANTHROPIC_API_KEY` en el archivo `.env`. Cargala y reiniciá la app."
        )
    else:
        with storage._conn() as c:
            pending = c.execute(
                """SELECT COUNT(*) AS n FROM ads a
                   LEFT JOIN analyses an ON an.ad_archive_id = a.ad_archive_id
                   WHERE an.id IS NULL"""
            ).fetchone()["n"]
            total_analyzed = c.execute(
                "SELECT COUNT(DISTINCT ad_archive_id) AS n FROM analyses"
            ).fetchone()["n"]

        c1, c2 = st.columns(2)
        c1.metric("⏳ Pendientes", pending)
        c2.metric("✅ Ya analizados", total_analyzed)

        col1, col2 = st.columns(2)
        with col1:
            limit = st.slider("¿Cuántos analizar ahora?", 1, 50, min(10, max(pending, 1)))
        with col2:
            max_images = st.slider("Imágenes por anuncio (más = más caro)", 1, 4, 2)

        if st.button("🚀 Analizar ahora", type="primary", disabled=pending == 0):
            analyzer = CreativeAnalyzer(s)
            rows = storage.unanalyzed_ads(int(limit))
            progress = st.progress(0)
            log_area = st.container()
            errors = 0
            for i, r in enumerate(rows):
                ad = row_to_ad(r)
                try:
                    result = analyzer.analyze(ad, max_images=int(max_images))
                    storage.save_analysis(ad.ad_archive_id, s.claude_model, result)
                    log_area.success(
                        f"✓ `{ad.ad_archive_id}` · **{result.get('angle','—')}** · "
                        f"{result.get('summary','')[:100]}"
                    )
                except Exception as e:
                    errors += 1
                    log_area.error(f"✗ `{ad.ad_archive_id}`: {e}")
                progress.progress((i + 1) / len(rows))
            st.success(f"Listo. {len(rows) - errors}/{len(rows)} anuncios analizados.")


# ─────────────────────────── 📊 REPORTE ───────────────────────────
elif section == "📊 Reporte":
    st.header("📊 Reporte agregado")

    pages = storage.list_tracked_pages()
    page_filter = st.selectbox(
        "Filtrar por página",
        ["(todas)"] + [f"{p['page_name'] or p['page_id']} | {p['page_id']}" for p in pages],
    )
    selected_pid = None if page_filter == "(todas)" else page_filter.rsplit("| ", 1)[-1]

    rows = storage.analyses_summary(selected_pid, 500)
    if not rows:
        st.info("No hay análisis aún. Andá a 🤖 Analizar con IA primero.")
    else:
        angles: Counter[str] = Counter()
        formats: Counter[str] = Counter()
        ad_types: Counter[str] = Counter()
        pain_points: Counter[str] = Counter()
        promises: Counter[str] = Counter()
        quality: list[int] = []
        for r in rows:
            try:
                a = json.loads(r["analysis_json"])
            except Exception:
                continue
            if x := a.get("angle"):
                angles[str(x)] += 1
            if x := a.get("format"):
                formats[str(x)] += 1
            if x := a.get("ad_type"):
                ad_types[str(x)] += 1
            for p in a.get("pain_points", []) or []:
                pain_points[str(p).lower()] += 1
            for pr in a.get("promises", []) or []:
                promises[str(pr).lower()] += 1
            q = a.get("estimated_quality")
            if isinstance(q, (int, float)):
                quality.append(int(q))

        c1, c2, c3 = st.columns(3)
        c1.metric("Análisis totales", len(rows))
        c2.metric(
            "Calidad promedio",
            f"{sum(quality)/len(quality):.1f}/10" if quality else "—",
        )
        c3.metric("Ángulos distintos", len(angles))

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🎯 Top ángulos")
            if angles:
                st.bar_chart(
                    pd.DataFrame(angles.most_common(10), columns=["ángulo", "n"]).set_index("ángulo")
                )
        with col2:
            st.subheader("🎞 Formatos")
            if formats:
                st.bar_chart(
                    pd.DataFrame(formats.most_common(), columns=["formato", "n"]).set_index("formato")
                )

        st.subheader("💢 Pain points recurrentes")
        if pain_points:
            st.bar_chart(
                pd.DataFrame(pain_points.most_common(15), columns=["pain", "n"]).set_index("pain")
            )

        st.subheader("🎁 Promesas recurrentes")
        if promises:
            st.bar_chart(
                pd.DataFrame(promises.most_common(15), columns=["promesa", "n"]).set_index("promesa")
            )


# ─────────────────────────── 📥 EXPORTAR ───────────────────────────
elif section == "📥 Exportar":
    st.header("📥 Exportar datos")
    with storage._conn() as c:
        rows = list(c.execute("SELECT * FROM ads ORDER BY first_seen_at DESC"))

    st.metric("Anuncios en la base", len(rows))
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df.head(50), use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar CSV completo",
                csv,
                "ads_export.csv",
                "text/csv",
                use_container_width=True,
            )
        with c2:
            json_str = df.to_json(orient="records", force_ascii=False, indent=2)
            st.download_button(
                "📥 Descargar JSON completo",
                json_str,
                "ads_export.json",
                "application/json",
                use_container_width=True,
            )
    else:
        st.info("No hay anuncios guardados todavía. Hacé una búsqueda primero.")
