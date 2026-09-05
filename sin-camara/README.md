# SIN CÁMARA — landing

Landing de venta de una sola página. HTML estático, sin build, sin dependencias.
Todo el CSS va inline en el `<head>` de `index.html`.

## Configuración

Arriba de todo en el `<head>` de `index.html`:

```js
window.CHECKOUT_URL  = "#";   // link de Hotmart o Shopify
window.META_PIXEL_ID = "";    // ID del pixel
```

- `CHECKOUT_URL` se asigna como `href` de todos los botones `[data-buy]`.
- Si `META_PIXEL_ID` tiene valor, se carga el pixel de Meta, se dispara `PageView`
  al cargar e `InitiateCheckout` **solo** al clic en los botones de compra.

## El video del hero

Los dos bloques `.phone` (hero y cierre) son placeholders 9:16. Para poner el video real,
reemplazar el contenido del div por:

```html
<video src="/video.mp4" autoplay muted loop playsinline></video>
```

## La grilla de la franja mostaza

Los seis bloques 9:16 de la franja mostaza van con **frames de videos reales hechos con
el método**. Quedan en navy plano hasta que existan esos videos. No llenarlos con
imágenes generadas: el argumento central de la página es que todo lo que se ve está
producido así.

## Imágenes del producto

Van en `public/img/`: `cover.png`, `bundle.png`, `item-1.png` … `item-6.png`, `og.png`.
Se generan con la API de OpenAI (`gpt-image-1`) con `OPENAI_API_KEY` en `.env`.
Mientras no existan, los `<img>` se autoeliminan (`onerror`) y queda el placeholder navy.

## Deploy

Vercel, framework preset **Other**, sin build step. Cada push a `main` despliega.
