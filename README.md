# Gusty News AI™ — versión Vercel

Esta versión está preparada para que Vercel detecte FastAPI automáticamente mediante `app.py` en la raíz.

## Publicar

1. Sube **todos los archivos y la carpeta `static`** a la raíz del repositorio GitHub.
2. En Vercel, importa el repositorio.
3. Pulsa **Deploy**. No cambies Root Directory ni Framework Preset.

La web funciona en modo demostración sin clave.

## Activar OpenAI

En Vercel: **Settings → Environment Variables**

- Nombre: `OPENAI_API_KEY`
- Valor: tu clave

Después pulsa **Redeploy**.

> Nota: el historial usa almacenamiento temporal de Vercel. Para historial permanente se conectará una base de datos en la siguiente versión.
