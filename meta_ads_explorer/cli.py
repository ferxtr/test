from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .analyzer import CreativeAnalyzer
from .config import Settings
from .models import Ad
from .scraper import SearchParams, extract_page_id_from_url, scrape_to_list
from .storage import Storage

app = typer.Typer(
    add_completion=False,
    help="Meta Ads Library Explorer — buscar, trackear y analizar anuncios con IA.",
)
console = Console()


def _store() -> Storage:
    return Storage(Settings.load().db_path)


def _settings() -> Settings:
    return Settings.load()


def _print_ads_table(ads: list[Ad]) -> None:
    table = Table(show_lines=False, header_style="bold cyan")
    table.add_column("ID", style="dim", overflow="fold", max_width=14)
    table.add_column("Página")
    table.add_column("Activo")
    table.add_column("CTA")
    table.add_column("Copy (primeros 60 ch.)")
    for ad in ads:
        body = (ad.body_text or "").replace("\n", " ")
        if len(body) > 60:
            body = body[:60] + "…"
        table.add_row(
            ad.ad_archive_id,
            ad.page_name or "—",
            "sí" if ad.is_active else "no",
            ad.cta_text or "—",
            body,
        )
    console.print(table)


@app.command()
def search(
    query: str = typer.Argument(..., help="Palabra clave o frase a buscar"),
    country: Optional[str] = typer.Option(None, "--country", "-c", help="Código ISO-2 (default: del .env)"),
    ad_type: str = typer.Option("all", "--ad-type"),
    active_status: str = typer.Option("active", "--status"),
    media_type: str = typer.Option("all", "--media"),
    max_ads: int = typer.Option(60, "--max", "-n"),
    store: bool = typer.Option(True, "--store/--no-store", help="Guardar resultados en SQLite"),
) -> None:
    """Buscar anuncios por palabra clave."""
    s = _settings()
    params = SearchParams(
        country=country or s.country,
        query=query,
        ad_type=ad_type,
        active_status=active_status,
        media_type=media_type,
    )
    console.print(f"[bold]Buscando[/bold] '{query}' en {params.country}…")
    ads = asyncio.run(scrape_to_list(params, max_ads, s.headless, s.scroll_delay))
    console.print(f"Encontrados [bold green]{len(ads)}[/bold green] anuncios.")
    if store:
        new, seen = _store().upsert_ads(ads)
        _store().log_search(query, params.country, ad_type, active_status, None, len(ads), params.to_url())
        console.print(f"DB: [green]+{new} nuevos[/green], {seen} actualizados.")
    _print_ads_table(ads[:30])


@app.command("page")
def scrape_page(
    page: str = typer.Argument(..., help="page_id numérico, o URL completa de Ad Library con view_all_page_id"),
    country: Optional[str] = typer.Option(None, "--country", "-c"),
    active_status: str = typer.Option("all", "--status"),
    max_ads: int = typer.Option(100, "--max", "-n"),
    track: bool = typer.Option(False, "--track", help="Agregar la página a la lista de tracking"),
    notes: Optional[str] = typer.Option(None, "--notes"),
) -> None:
    """Scrapear todos los anuncios de una página específica."""
    s = _settings()
    page_id = extract_page_id_from_url(page) or page
    if not page_id.isdigit():
        console.print(f"[red]page_id inválido:[/red] {page_id}")
        raise typer.Exit(1)

    params = SearchParams(country=country or s.country, page_id=page_id, active_status=active_status)
    console.print(f"[bold]Scrapeando página[/bold] {page_id}…")
    ads = asyncio.run(scrape_to_list(params, max_ads, s.headless, s.scroll_delay))
    console.print(f"Encontrados [bold green]{len(ads)}[/bold green] anuncios.")
    new, seen = _store().upsert_ads(ads)
    _store().log_search(None, params.country, "all", active_status, page_id, len(ads), params.to_url())
    console.print(f"DB: [green]+{new} nuevos[/green], {seen} actualizados.")

    if track:
        page_name = ads[0].page_name if ads else None
        _store().add_tracked_page(page_id, page_name, params.country, notes)
        console.print(f"[cyan]Trackeando[/cyan] {page_name or page_id}")

    _store().mark_page_checked(page_id)
    _print_ads_table(ads[:30])


@app.command()
def track(
    page_id: Optional[str] = typer.Argument(None, help="page_id a agregar; sin argumento muestra la lista"),
    name: Optional[str] = typer.Option(None, "--name"),
    country: Optional[str] = typer.Option(None, "--country", "-c"),
    notes: Optional[str] = typer.Option(None, "--notes"),
    remove: bool = typer.Option(False, "--remove", help="(no implementado: editá la DB)"),
) -> None:
    """Listar o agregar páginas trackeadas."""
    storage = _store()
    if page_id:
        storage.add_tracked_page(page_id, name, country or _settings().country, notes)
        console.print(f"[green]Trackeando[/green] {name or page_id}")

    rows = storage.list_tracked_pages()
    if not rows:
        console.print("[yellow]Sin páginas trackeadas todavía.[/yellow]")
        return

    table = Table(header_style="bold cyan", title="Páginas trackeadas")
    table.add_column("page_id")
    table.add_column("nombre")
    table.add_column("país")
    table.add_column("último check")
    table.add_column("notas")
    for r in rows:
        table.add_row(
            r["page_id"],
            r["page_name"] or "—",
            r["country"] or "—",
            r["last_checked_at"] or "nunca",
            r["notes"] or "",
        )
    console.print(table)


@app.command()
def snapshot(
    max_ads: int = typer.Option(80, "--max", "-n", help="Anuncios por página"),
    active_only: bool = typer.Option(True, "--active/--all"),
) -> None:
    """Re-scrapea todas las páginas trackeadas y registra cambios."""
    s = _settings()
    storage = _store()
    rows = storage.list_tracked_pages()
    if not rows:
        console.print("[yellow]No hay páginas trackeadas. Usá[/yellow] [cyan]mae track <page_id>[/cyan]")
        return

    for r in rows:
        params = SearchParams(
            country=r["country"] or s.country,
            page_id=r["page_id"],
            active_status="active" if active_only else "all",
        )
        console.print(f"\n[bold]→ {r['page_name'] or r['page_id']}[/bold]")
        ads = asyncio.run(scrape_to_list(params, max_ads, s.headless, s.scroll_delay))
        new, seen = storage.upsert_ads(ads)
        storage.mark_page_checked(r["page_id"])
        diff = storage.diff_for_page(r["page_id"])
        console.print(
            f"  {len(ads)} ads | [green]+{new} nuevos[/green] | activos={diff['active']} | "
            f"inactivos={diff['inactive']} | nuevos 7d={diff['new_last_7d']}"
        )


@app.command()
def analyze(
    page_id: Optional[str] = typer.Option(None, "--page-id"),
    ad_id: Optional[str] = typer.Option(None, "--ad-id"),
    limit: int = typer.Option(10, "--limit", "-n"),
    max_images: int = typer.Option(2, "--images", help="Imágenes a mandar al modelo por anuncio"),
) -> None:
    """Correr análisis con Claude sobre anuncios guardados (sólo los no analizados)."""
    s = _settings()
    storage = _store()
    analyzer = CreativeAnalyzer(s)

    if ad_id:
        row = storage.ad(ad_id)
        if not row:
            console.print(f"[red]No encuentro ad {ad_id} en la DB[/red]")
            raise typer.Exit(1)
        rows = [row]
    elif page_id:
        rows = storage.ads_for_page(page_id)[:limit]
    else:
        rows = storage.unanalyzed_ads(limit)

    if not rows:
        console.print("[yellow]Nada para analizar.[/yellow]")
        return

    console.print(f"Analizando [bold]{len(rows)}[/bold] anuncios con [cyan]{s.claude_model}[/cyan]…")
    for r in rows:
        ad = Ad(
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
        try:
            result = analyzer.analyze(ad, max_images=max_images)
        except Exception as e:
            console.print(f"  [red]✗[/red] {ad.ad_archive_id}: {e}")
            continue
        storage.save_analysis(ad.ad_archive_id, s.claude_model, result)
        angle = result.get("angle", "—")
        summary = result.get("summary", "")
        console.print(f"  [green]✓[/green] {ad.ad_archive_id} | [cyan]{angle}[/cyan] | {summary[:90]}")


@app.command()
def report(
    page_id: Optional[str] = typer.Option(None, "--page-id"),
    limit: int = typer.Option(100, "--limit", "-n"),
) -> None:
    """Reporte agregado de los análisis hechos: ángulos, hooks, formatos."""
    storage = _store()
    rows = storage.analyses_summary(page_id, limit)
    if not rows:
        console.print("[yellow]No hay análisis todavía. Corré[/yellow] [cyan]mae analyze[/cyan]")
        return

    angles: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    ad_types: Counter[str] = Counter()
    pain_points: Counter[str] = Counter()
    quality_scores: list[int] = []

    for r in rows:
        try:
            a = json.loads(r["analysis_json"])
        except json.JSONDecodeError:
            continue
        if angle := a.get("angle"):
            angles[angle] += 1
        if fmt := a.get("format"):
            formats[fmt] += 1
        if at := a.get("ad_type"):
            ad_types[at] += 1
        for p in a.get("pain_points", []) or []:
            pain_points[str(p).lower()] += 1
        q = a.get("estimated_quality")
        if isinstance(q, (int, float)):
            quality_scores.append(int(q))

    console.print(f"\n[bold]Reporte sobre {len(rows)} análisis[/bold]")
    if quality_scores:
        avg = sum(quality_scores) / len(quality_scores)
        console.print(f"  Calidad promedio: [bold]{avg:.1f}[/bold]/10")

    def _show(title: str, counter: Counter, top: int = 8) -> None:
        if not counter:
            return
        table = Table(title=title, header_style="bold cyan", show_edge=False)
        table.add_column("Valor")
        table.add_column("Conteo", justify="right")
        for value, count in counter.most_common(top):
            table.add_row(value, str(count))
        console.print(table)

    _show("Ángulos más usados", angles)
    _show("Formatos", formats)
    _show("Tipo de anuncio", ad_types)
    _show("Pain points recurrentes", pain_points, top=10)


@app.command("export")
def export_ads(
    output: str = typer.Argument(..., help="Ruta del archivo CSV o JSON a generar"),
    page_id: Optional[str] = typer.Option(None, "--page-id"),
) -> None:
    """Exportar anuncios guardados a CSV o JSON."""
    storage = _store()
    if page_id:
        rows = storage.ads_for_page(page_id)
    else:
        with storage._conn() as c:
            rows = list(c.execute("SELECT * FROM ads ORDER BY first_seen_at DESC"))

    if not rows:
        console.print("[yellow]Sin datos para exportar.[/yellow]")
        return

    data = [dict(r) for r in rows]
    if output.lower().endswith(".json"):
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    elif output.lower().endswith(".csv"):
        import csv
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
    else:
        console.print("[red]Formato no soportado. Usá .csv o .json[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Exportados {len(data)} anuncios a {output}[/green]")


@app.command()
def install_browser() -> None:
    """Atajo para 'playwright install chromium'."""
    import subprocess
    console.print("[bold]Instalando Chromium para Playwright…[/bold]")
    subprocess.run(["playwright", "install", "chromium"], check=False)


@app.command()
def web(
    port: int = typer.Option(8501, "--port", "-p"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Levantar la interfaz web (Streamlit) en el navegador."""
    import subprocess
    from pathlib import Path
    app_file = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    if not app_file.exists():
        console.print(f"[red]No encuentro {app_file}[/red]")
        raise typer.Exit(1)
    cmd = [
        "streamlit", "run", str(app_file),
        "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
    ]
    if not open_browser:
        cmd += ["--server.headless", "true"]
    console.print(f"[bold green]Abriendo Meta Ads Explorer en http://localhost:{port}[/bold green]")
    subprocess.run(cmd)


if __name__ == "__main__":
    app()
