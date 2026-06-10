# Digest VC · Club de VC e Innovación · UdeSA

Agente de curaduría diaria de noticias de VC, PE, startups e innovación con
foco en Argentina y LatAm. Corre gratis en GitHub Actions y publica en
GitHub Pages. Sin servidor.

## Cómo funciona

```
sources.yaml ──► curate.py ──► Claude API ──► docs/index.html ──► GitHub Pages
   (fuentes)      (RSS +         (curaduría      (digest del día
                   dedupe)        + resúmenes)    + archivo)
```

## Setup (15 minutos)

1. **Crear el repo** en GitHub y subir estos archivos.
2. **API key**: en el repo → Settings → Secrets and variables → Actions →
   New repository secret → nombre `ANTHROPIC_API_KEY`, valor tu key de
   console.anthropic.com.
3. **GitHub Pages**: Settings → Pages → Source: "Deploy from a branch" →
   Branch `main`, carpeta `/docs`.
4. **Probar**: pestaña Actions → "Digest diario" → Run workflow. En ~2 min
   el digest queda en `https://<usuario>.github.io/<repo>/`.

A partir de ahí corre solo todos los días a las 07:00 ART.

## Probar localmente

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python curate.py
open docs/index.html
```

## Mantenimiento

- **Agregar/quitar fuentes**: editar `sources.yaml`. Verificar que la URL de
  RSS responda (pegarla en el navegador).
- **Ajustar criterios de curaduría**: editar la constante `CRITERIOS` en
  `curate.py`. Es el alma del agente; vale la pena iterarlo con feedback
  de los miembros del club.
- **Cantidad de noticias**: `TOP_N` en `curate.py`.

## Fuentes sin RSS (ARCAP y otras)

ARCAP no publica feed RSS. Opciones, de simple a elaborada:
1. Generar un feed con [RSS.app](https://rss.app) o
   [FetchRSS](https://fetchrss.com) apuntando a su página de novedades y
   pegar esa URL en `sources.yaml`.
2. Escribir un mini-scraper (requests + BeautifulSoup) que devuelva la misma
   estructura que `fetch_articulos` y sumarlo al pipeline.

## Roadmap sugerido

- [ ] **v1** (esto): digest web diario automático.
- [ ] **v1.1**: validar criterios 1-2 semanas con feedback del club.
- [ ] **v2 — email**: conectar [Buttondown](https://buttondown.com) o
  [Resend](https://resend.com): el mismo script manda el HTML por mail a la
  lista de suscriptores (un POST extra al final de `main()`).
- [ ] **v3**: página de archivo navegable, sección semanal "deal de la
  semana", métricas de clics.

## Costo

GitHub Actions + Pages: gratis. API de Claude: ~120 artículos/día con
Sonnet sale del orden de centavos de dólar por edición.
