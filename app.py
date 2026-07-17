from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field, HttpUrl

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DB_PATH = Path(tempfile.gettempdir()) / "gusty_news.db"

app = FastAPI(title="Gusty News AI", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

DEFAULT_FEEDS = {
    "IA": "https://openai.com/news/rss.xml",
    "Japón": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "Negocios": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "Tecnología": "https://feeds.bbci.co.uk/news/technology/rss.xml",
}


class GenerateRequest(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    source_url: HttpUrl | None = None
    source_text: str = Field(default="", max_length=18000)
    category: str = Field(default="Actualidad", max_length=60)
    audience: str = Field(
        default="Público hispanohablante interesado en Japón, Perú, negocios e IA"
    )


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    category: str
    published: str | None = None


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            source_url TEXT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    }


@app.get("/api/news", response_model=list[NewsItem])
def collect_news(limit: int = 20) -> list[NewsItem]:
    limit = max(1, min(limit, 40))
    results: list[NewsItem] = []
    seen: set[str] = set()

    for category, feed_url in DEFAULT_FEEDS.items():
        parsed = feedparser.parse(feed_url)
        source_name = parsed.feed.get("title", category)
        for entry in parsed.entries[:8]:
            title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
            url = entry.get("link", "")
            key = re.sub(r"[^a-z0-9]", "", title.lower())
            if not title or not url or key in seen:
                continue
            seen.add(key)
            results.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=source_name,
                    category=category,
                    published=entry.get("published"),
                )
            )
            if len(results) >= limit:
                return results
    return results


def demo_payload(req: GenerateRequest) -> dict[str, Any]:
    title = req.title.strip()
    return {
        "headline": f"{title}: lo que cambia y por qué importa",
        "edition": req.category,
        "summary": "Modo demostración activo. Añade OPENAI_API_KEY en Vercel para generar el paquete editorial completo con IA.",
        "linkedin": f"📰 {title}\n\n¿Qué cambia realmente y cómo podría afectarnos? Gusty News™ analiza el contexto, el impacto y las oportunidades.\n\n¿Qué opinas?\n\n#Innovación #Negocios #Tecnología #Gusty",
        "facebook": f"📰 {title}\n\nNo se trata solo del titular: importa entender qué cambia, a quién beneficia y qué riesgos aparecen.\n\n¿Tú cómo lo ves? — Gusty™",
        "telegram": f"⚡ GUSTY NEWS | {req.category.upper()}\n\n{title}\n\nLectura rápida, contexto y consecuencias.\n\n— Gusty™",
        "x": f"{title}. La pregunta importante no es solo qué pasó, sino qué cambia a partir de ahora. ¿Qué opinas?",
        "tiktok_script": f"Atención: {title}. En menos de 30 segundos te explico qué pasó, por qué importa y qué podría venir después.",
        "image_prompt": f"Portada vertical 9:16 de periódico tecnológico premium, titular '{title}', estética sobria y disruptiva, azul editorial, alto contraste, marca Gusty™ discreta, sin logotipos de terceros.",
        "fact_check": [
            "Confirmar fecha y lugar",
            "Verificar cifras con dos fuentes",
            "Distinguir hechos de opinión",
        ],
    }


def generate_with_openai(req: GenerateRequest) -> dict[str, Any]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    instructions = """
Eres el editor principal de Gusty News™. Escribe en español claro, directo y verificable.
No inventes cifras, citas ni hechos. Si falta información, indícalo en fact_check.
Tono periodístico, moderno, sobrio y con energía. LinkedIn: máximo 4 hashtags.
TikTok: sin hashtags. Imagen: formato 9:16 y marca Gusty™ discreta.
Devuelve exclusivamente JSON válido con estas claves:
headline, edition, summary, linkedin, facebook, telegram, x, tiktok_script, image_prompt, fact_check.
fact_check debe ser una lista de cadenas.
""".strip()
    source = req.source_text.strip() or "No se proporcionó texto completo; trabaja solo con el título y señala los límites."
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=(
            f"Título: {req.title}\nCategoría: {req.category}\nAudiencia: {req.audience}\n"
            f"URL: {req.source_url or 'no indicada'}\nTexto fuente:\n{source}"
        ),
    )
    text = response.output_text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="La IA no devolvió un formato válido.") from exc


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict[str, Any]:
    payload = generate_with_openai(req) if os.getenv("OPENAI_API_KEY") else demo_payload(req)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with connect_db() as conn:
            cursor = conn.execute(
                "INSERT INTO posts (title, category, source_url, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (req.title, req.category, str(req.source_url or ""), json.dumps(payload, ensure_ascii=False), now),
            )
            post_id = cursor.lastrowid
    except sqlite3.Error:
        post_id = 0
    return {"id": post_id, "created_at": now, "demo": not bool(os.getenv("OPENAI_API_KEY")), **payload}


@app.get("/api/posts")
def list_posts(limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    try:
        with connect_db() as conn:
            rows = conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "source_url": row["source_url"],
            "created_at": row["created_at"],
            **json.loads(row["payload"]),
        }
        for row in rows
    ]
