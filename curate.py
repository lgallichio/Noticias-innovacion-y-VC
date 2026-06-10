#!/usr/bin/env python3
"""
Agente de curaduría de noticias — Clubes de VC e Innovación UDESA.

Pipeline diario:
  1. Lee fuentes de sources.yaml y baja los feeds RSS.
  2. Filtra artículos de las últimas HORAS_VENTANA horas y deduplica.
  3. Manda los candidatos a Claude para curar (top N + resumen en español).
  4. Renderiza docs/index.html (GitHub Pages) y archiva la edición del día.

Uso local:
  export ANTHROPIC_API_KEY=sk-ant-...
  pip install -r requirements.txt
  python curate.py
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import yaml
from anthropic import Anthropic

# ------------------------------------------------------------------ config

ROOT = Path(__file__).parent
HORAS_VENTANA = 36          # cuántas horas hacia atrás mirar
MAX_CANDIDATOS = 120        # techo de artículos que se mandan a curar
TOP_N = 10                  # artículos en el digest final
MODEL = "claude-sonnet-4-6"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")

CRITERIOS = """\
Sos el curador de noticias del club de Venture Capital e Innovación de la
Universidad de San Andrés (UdeSA). Tu audiencia: estudiantes y jóvenes
profesionales interesados en VC, private equity, startups e innovación,
con foco especial en Argentina y LatAm.

Criterios de selección, en orden de prioridad:
1. Rondas de inversión, exits, M&A y lanzamientos de fondos en LatAm.
2. Noticias del ecosistema argentino (ARCAP, Endeavor, aceleradoras, regulación).
3. Tendencias globales de VC/PE con implicancias claras para la región.
4. Innovación y tecnología con ángulo de negocio (no gadgets de consumo).

Descartá: clickbait, notas de opinión sin datos, contenido promocional,
duplicados del mismo hecho (elegí la mejor fuente), y noticias sin
relevancia para alguien que estudia el ecosistema emprendedor."""

# ------------------------------------------------------------------ ingesta


def cargar_fuentes() -> list[dict]:
    with open(ROOT / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["fuentes"]


def limpiar_html(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def fetch_articulos(fuentes: list[dict]) -> list[dict]:
    corte = datetime.now(timezone.utc) - timedelta(hours=HORAS_VENTANA)
    articulos = []
    for fuente in fuentes:
        try:
            feed = feedparser.parse(fuente["rss"])
        except Exception as e:  # red caída, feed roto, etc.
            print(f"  [warn] {fuente['nombre']}: {e}", file=sys.stderr)
            continue
        for entry in feed.entries:
            fecha_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if fecha_struct:
                fecha = datetime.fromtimestamp(time.mktime(fecha_struct), tz=timezone.utc)
                if fecha < corte:
                    continue
            else:
                fecha = None  # sin fecha: lo dejamos pasar, Claude decide
            articulos.append(
                {
                    "fuente": fuente["nombre"],
                    "peso": fuente.get("peso", 1),
                    "titulo": limpiar_html(entry.get("title", ""))[:300],
                    "resumen": limpiar_html(entry.get("summary", ""))[:500],
                    "link": entry.get("link", ""),
                    "fecha": fecha.isoformat() if fecha else "",
                }
            )
        print(f"  {fuente['nombre']}: ok")
    return articulos


def deduplicar(articulos: list[dict]) -> list[dict]:
    vistos, unicos = set(), []
    for a in articulos:
        clave_titulo = re.sub(r"\W+", "", a["titulo"].lower())[:80]
        h = hashlib.md5((a["link"] or clave_titulo).encode()).hexdigest()
        if h in vistos or clave_titulo in vistos:
            continue
        vistos.update({h, clave_titulo})
        unicos.append(a)
    # las fuentes con más peso van primero (sesgo suave en la curaduría)
    unicos.sort(key=lambda a: -a["peso"])
    return unicos[:MAX_CANDIDATOS]


# ---------------------------------------------------------------- curaduría


def curar(candidatos: list[dict]) -> dict:
    client = Anthropic()  # usa ANTHROPIC_API_KEY del entorno
    lista = "\n".join(
        f"[{i}] ({a['fuente']}) {a['titulo']} — {a['resumen'][:200]} | {a['link']}"
        for i, a in enumerate(candidatos)
    )
    prompt = f"""{CRITERIOS}

Hoy es {datetime.now(TZ).strftime('%A %d/%m/%Y')}. Estos son los artículos
candidatos de las últimas {HORAS_VENTANA} horas:

{lista}

Elegí los {TOP_N} mejores y respondé SOLO con JSON válido (sin markdown,
sin texto extra) con esta forma exacta:

{{
  "titular_del_dia": "una línea que capture el tema más importante del día",
  "items": [
    {{
      "indice": 0,
      "categoria": "Rondas | Fondos | Exits/M&A | Ecosistema AR | LatAm | Global | Tendencias",
      "titulo_es": "título reescrito en español, claro y sin clickbait",
      "resumen": "2-3 oraciones en español con los datos concretos (montos, inversores, etapa)",
      "por_que_importa": "1 oración: por qué le importa a un estudiante del club"
    }}
  ]
}}

"indice" es el número entre corchetes del artículo elegido. Ordená los items
de más a menos relevante."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text.strip()
    texto = re.sub(r"^```(json)?|```$", "", texto, flags=re.MULTILINE).strip()
    data = json.loads(texto)
    # reconectar cada item con su artículo original (link, fuente)
    for item in data["items"]:
        original = candidatos[item["indice"]]
        item["link"] = original["link"]
        item["fuente"] = original["fuente"]
    return data


# ------------------------------------------------------------------ render


def render_html(digest: dict, fecha: datetime) -> str:
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    items_html = []
    for i, item in enumerate(digest["items"], 1):
        items_html.append(f"""
      <article class="item">
        <div class="item-meta">
          <span class="num">{i:02d}</span>
          <span class="cat">{item['categoria']}</span>
          <span class="src">{item['fuente']}</span>
        </div>
        <h2><a href="{item['link']}" target="_blank" rel="noopener">{item['titulo_es']}</a></h2>
        <p class="resumen">{item['resumen']}</p>
        <p class="importa"><span>Por qué importa</span> {item['por_que_importa']}</p>
      </article>""")
    return (
        template.replace("{{FECHA}}", fecha.strftime("%A %d de %B, %Y").capitalize())
        .replace("{{TITULAR}}", digest["titular_del_dia"])
        .replace("{{ITEMS}}", "\n".join(items_html))
        .replace("{{TIMESTAMP}}", fecha.strftime("%H:%M ART"))
    )


# -------------------------------------------------------------------- main


def main() -> None:
    print("1/4 Leyendo fuentes…")
    fuentes = cargar_fuentes()
    print("2/4 Bajando feeds…")
    articulos = deduplicar(fetch_articulos(fuentes))
    print(f"    {len(articulos)} candidatos únicos")
    if not articulos:
        sys.exit("Sin artículos: revisar feeds en sources.yaml")

    print("3/4 Curando con Claude…")
    digest = curar(articulos)

    print("4/4 Renderizando HTML…")
    ahora = datetime.now(TZ)
    html = render_html(digest, ahora)
    docs = ROOT / "docs"
    (docs / "index.html").write_text(html, encoding="utf-8")
    (docs / "archive" / f"{ahora:%Y-%m-%d}.html").write_text(html, encoding="utf-8")
    (docs / "digest.json").write_text(
        json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Listo: {len(digest['items'])} noticias → docs/index.html")


if __name__ == "__main__":
    main()
