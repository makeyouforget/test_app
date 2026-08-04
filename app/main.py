"""Notes — веб-приложение для хранения заметок.

Endpoints:
  GET    /                  HTML-страница со списком заметок
  POST   /notes             создание заметки из HTML-формы
  POST   /notes/{id}/delete удаление заметки из HTML-формы
  GET    /api/notes         список заметок (JSON)
  POST   /api/notes         создание заметки (JSON)
  DELETE /api/notes/{id}    удаление заметки
  GET    /healthz           liveness: жив ли процесс (БД не трогает)
  GET    /readyz            readiness: доступна ли БД
  GET    /slow?seconds=N    долгий запрос — для проверки graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__, db
from app.config import ConfigError, Settings, load_settings
from app.models import Note

log = logging.getLogger("notes")
templates = Jinja2Templates(directory="app/templates")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    _configure_logging(settings.log_level)
    log.info("starting %s v%s", settings.app_name, __version__)

    try:
        db.init_engine(settings)
    except Exception as exc:  # noqa: BLE001 — хотим увидеть причину в логах и упасть
        log.error("cannot reach database on startup: %s", exc)
        log.error(
            "the application does not wait for the database by itself — "
            "make sure it is started only when Postgres is ready to accept connections"
        )
        raise

    app.state.ready = True
    log.info("application is ready to serve requests")

    yield

    # Сюда попадаем после SIGTERM/SIGINT: uvicorn уже перестал принимать новые
    # соединения и дождался завершения активных запросов.
    app.state.ready = False
    log.info("shutdown signal received, draining for %ss", settings.shutdown_delay)
    await asyncio.sleep(settings.shutdown_delay)
    db.dispose_engine()
    log.info("shutdown complete")


def create_app() -> FastAPI:
    try:
        settings = load_settings()
    except ConfigError as exc:
        _configure_logging("INFO")
        log.error("configuration error: %s", exc)
        raise SystemExit(1) from exc

    app = FastAPI(title="Notes", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.ready = False
    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    # ---------- HTML ----------

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, session: Session = Depends(db.get_session)):
        notes = session.scalars(select(Note).order_by(Note.created_at.desc())).all()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"notes": notes, "version": __version__},
        )

    @app.post("/notes")
    def create_note_form(
        title: str = Form(...),
        body: str = Form(""),
        session: Session = Depends(db.get_session),
    ):
        title = title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        session.add(Note(title=title[:200], body=body.strip()))
        session.commit()
        return RedirectResponse(url="/", status_code=303)

    @app.post("/notes/{note_id}/delete")
    def delete_note_form(note_id: int, session: Session = Depends(db.get_session)):
        note = session.get(Note, note_id)
        if note is not None:
            session.delete(note)
            session.commit()
        return RedirectResponse(url="/", status_code=303)

    # ---------- JSON API ----------

    @app.get("/api/notes")
    def list_notes(session: Session = Depends(db.get_session)):
        notes = session.scalars(select(Note).order_by(Note.created_at.desc())).all()
        return [note.as_dict() for note in notes]

    @app.post("/api/notes", status_code=201)
    def create_note(payload: dict, session: Session = Depends(db.get_session)):
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        note = Note(title=title[:200], body=str(payload.get("body", "")).strip())
        session.add(note)
        session.commit()
        return note.as_dict()

    @app.delete("/api/notes/{note_id}", status_code=204)
    def delete_note(note_id: int, session: Session = Depends(db.get_session)):
        note = session.get(Note, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="note not found")
        session.delete(note)
        session.commit()
        return None

    # ---------- Health ----------

    @app.get("/healthz")
    def healthz():
        """Liveness. Отвечает, пока процесс жив; в БД не ходит."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz():
        """Readiness. 503, если БД недоступна или идёт остановка."""
        if not app.state.ready:
            return JSONResponse(
                status_code=503, content={"status": "shutting_down", "database": "unknown"}
            )
        try:
            db.ping()
        except Exception as exc:  # noqa: BLE001
            log.warning("readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503, content={"status": "error", "database": "unavailable"}
            )
        return {"status": "ok", "database": "ok"}

    # ---------- Утилита для демонстрации graceful shutdown ----------

    @app.get("/slow")
    async def slow(seconds: int = Query(5, ge=0, le=60)):
        log.info("slow request started (%ss)", seconds)
        await asyncio.sleep(seconds)
        log.info("slow request finished (%ss)", seconds)
        return {"slept": seconds}


app = create_app()
