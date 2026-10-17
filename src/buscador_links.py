"""Módulo buscador y asistente de enlaces de cursos UTEL para el Bot de Telegram."""

from __future__ import annotations

import csv
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger("buscador_links")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONSOLIDADO_PATH = DATA_DIR / "cursos_consolidados.csv"


def normalizar_texto(texto: str) -> str:
    """Elimina acentos y pasa a minúsculas para búsquedas flexibles."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    limpio = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return limpio.lower().strip()


class BuscadorCursos:
    """Índice en memoria para resolver consultas de enlaces docentes en milisegundos."""

    def __init__(self, csv_path: Path | str | None = None):
        self.csv_path = Path(csv_path) if csv_path else CONSOLIDADO_PATH
        self.actividades: list[dict[str, str]] = []
        self._cargar_actividades()

    def _cargar_actividades(self) -> None:
        """Carga los CSVs desde GCS (gs://calificador/cursos/cursos_consolidados.csv) o local."""
        contenido = None
        try:
            from google.cloud import storage
            client = storage.Client(project="sentinela-mx")
            bucket = client.bucket("calificador")
            blob = bucket.blob("cursos/cursos_consolidados.csv")
            if blob.exists():
                contenido = blob.download_as_text(encoding="utf-8-sig")
                logger.info("Cargadas actividades directamente desde GCS (gs://calificador/cursos/cursos_consolidados.csv)")
        except Exception as e:
            logger.warning(f"No se pudo leer de GCS: {e}. Usando archivos locales.")

        if contenido:
            import io
            reader = csv.DictReader(io.StringIO(contenido), delimiter=";")
            self._procesar_filas(reader)
            return

        rutas_a_cargar: list[Path] = []
        if self.csv_path.exists():
            rutas_a_cargar.append(self.csv_path)
        elif DATA_DIR.exists():
            rutas_a_cargar = list(DATA_DIR.glob("curso_*_actividades.csv"))

        if not rutas_a_cargar:
            logger.warning(f"No se encontraron archivos CSV de cursos en {DATA_DIR}")
            return

        for ruta in rutas_a_cargar:
            try:
                with open(ruta, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    self._procesar_filas(reader)
            except Exception as e:
                logger.error(f"Error al cargar {ruta}: {e}")

    def _procesar_filas(self, reader: Any) -> None:
        for row in reader:
            clean_row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
            search_blob = " ".join([
                clean_row.get("Categoria", ""),
                clean_row.get("Actividad_Descriptiva", ""),
                clean_row.get("Nombre_Original", ""),
                clean_row.get("Semana_Seccion", ""),
                clean_row.get("Bloque", ""),
                f"bloque {clean_row.get('Bloque', '')}",
                clean_row.get("Nombre_Curso", ""),
                clean_row.get("Fecha", ""),
            ])
            clean_row["_norm_search"] = normalizar_texto(search_blob)
            self.actividades.append(clean_row)

        logger.info(f"Cargadas {len(self.actividades)} actividades en el buscador.")

    def buscar(self, query: str) -> tuple[str, list[dict[str, str]]]:
        """Busca actividades relevantes a partir de la consulta del usuario."""
        q_norm = normalizar_texto(query)
        if not q_norm or not self.actividades:
            return (
                "⚠️ No encontré cursos cargados en la base de datos local. "
                "Por favor verifica que existan los archivos en la carpeta `data/`.",
                [],
            )

        # 1. Detectar filtro de bloque (A o D)
        bloque_filtro = ""
        if re.search(r"\bbloque\s*a\b|\bdel\s*a\b", q_norm):
            bloque_filtro = "A"
        elif re.search(r"\bbloque\s*d\b|\bdel\s*d\b", q_norm):
            bloque_filtro = "D"
        elif q_norm.endswith(" a"):
            bloque_filtro = "A"
        elif q_norm.endswith(" d"):
            bloque_filtro = "D"

        # 2. Atajos directos frecuentes
        # 2.1 Tablero de Open Class
        if "open class" in q_norm or "openclass" in q_norm:
            matches = [
                a for a in self.actividades
                if a.get("Categoria") == "Open Class"
                and (not bloque_filtro or a.get("Bloque") == bloque_filtro)
            ]
            return self._formatear_resultados("🎥 Tablero de Open Class (Clases en Vivo)", matches), matches

        # 2.2 Calificador de Tareas / Pendientes
        if any(k in q_norm for k in ("calificador", "evaluar", "pendientes", "libro de calif")):
            matches = [
                a for a in self.actividades
                if a.get("Categoria") == "Calificador / Seguimiento"
                and (not bloque_filtro or a.get("Bloque") == bloque_filtro)
            ]
            return self._formatear_resultados("📊 Calificador y Seguimiento Docente", matches), matches

        # 2.3 Entregas Extemporáneas
        if "extemporan" in q_norm:
            matches = [
                a for a in self.actividades
                if "extempor" in a.get("_norm_search", "")
                and (not bloque_filtro or a.get("Bloque") == bloque_filtro)
            ]
            return self._formatear_resultados("⏰ Entregas Extemporáneas", matches), matches

        # 2.4 Puntos Extras
        if "punto extra" in q_norm or "puntos extra" in q_norm:
            matches = [
                a for a in self.actividades
                if "puntos extra" in a.get("_norm_search", "")
                and (not bloque_filtro or a.get("Bloque") == bloque_filtro)
            ]
            return self._formatear_resultados("🎁 Puntos Extra", matches[:6]), matches

        # 3. Búsqueda por palabras clave con ponderación (Scoring)
        tokens = [t for t in q_norm.split() if t not in ("de", "la", "el", "los", "las", "en", "para", "un", "una", "del")]
        candidatos: list[tuple[int, dict[str, str]]] = []

        for act in self.actividades:
            if bloque_filtro and act.get("Bloque") != bloque_filtro:
                continue

            target_blob = act.get("_norm_search", "")
            score = 0
            for token in tokens:
                if token in target_blob:
                    # Dar mayor peso si coincide en el nombre de la actividad
                    if token in normalizar_texto(act.get("Actividad_Descriptiva", "")):
                        score += 3
                    elif token in normalizar_texto(act.get("Categoria", "")):
                        score += 2
                    else:
                        score += 1

            if score > 0:
                candidatos.append((score, act))

        # Ordenar por mayor puntaje
        candidatos.sort(key=lambda x: x[0], reverse=True)
        top_matches = [c[1] for c in candidatos[:5]]

        if not top_matches:
            return (
                f"🤔 No encontré enlaces que coincidan exactamente con: *{query}*.\n\n"
                "💡 *Prueba escribiendo algo como:*\n"
                "• `foro 1 bloque a`\n"
                "• `examen 3 bloque d`\n"
                "• `open class`\n"
                "• `calificador`\n"
                "• `extemporaneas`\n\n"
                "_(Escribe *menu* para ver todas las opciones)_",
                [],
            )

        titulo_seccion = f"🔍 Encontré estos enlaces para '{query}':"
        return self._formatear_resultados(titulo_seccion, top_matches), top_matches

    def _formatear_resultados(self, encabezado: str, items: list[dict[str, str]]) -> str:
        """Da formato en Markdown limpio para Telegram."""
        if not items:
            return f"{encabezado}\n\nNo se encontraron actividades registradas."

        lineas = [f"*{encabezado}*\n"]
        for idx, it in enumerate(items, start=1):
            categoria = it.get("Categoria", "Actividad")
            nombre = it.get("Actividad_Descriptiva") or it.get("Nombre_Original", "Enlace")
            bloque = it.get("Bloque", "")
            bloque_str = f" `[Bloque {bloque}]`" if bloque else ""
            seccion = it.get("Semana_Seccion", "")
            fecha = it.get("Fecha", "")
            url = it.get("Link", "")

            icono = "📝"
            if categoria == "Open Class":
                icono = "🎥"
            elif categoria == "Foro":
                icono = "💬"
            elif categoria == "Examen":
                icono = "📋"
            elif categoria == "Calificador / Seguimiento":
                icono = "📊"
            elif categoria == "Entrega Extemporánea":
                icono = "⏰"
            elif categoria == "Puntos Extras":
                icono = "🎁"

            bloque_linea = f"{icono} *{nombre}*{bloque_str}\n"
            if seccion:
                bloque_linea += f"   📁 _{seccion}_\n"
            if fecha:
                bloque_linea += f"   📅 {fecha}\n"
            bloque_linea += f"   🔗 [Ir a Moodle]({url})\n"

            lineas.append(bloque_linea)

        lineas.append("\n_(💡 Escribe *menu* para ver opciones)_")
        return "\n".join(lineas)


# Instancia global en memoria
_buscador_instancia: BuscadorCursos | None = None


def obtener_buscador() -> BuscadorCursos:
    global _buscador_instancia
    if _buscador_instancia is None:
        _buscador_instancia = BuscadorCursos()
    return _buscador_instancia


def generar_mensaje_menu() -> str:
    """Genera el mensaje principal de bienvenida y ayuda del asistente docente."""
    return (
        "👋 *¡Hola! Soy tu asistente docente UTEL.*\n\n"
        "¿Qué deseas hacer hoy?\n\n"
        "1️⃣ *Calificar entrega de alumno:*\n"
        "Envíame el archivo (`.pdf` o `.docx`) y en el comentario ponle:\n"
        "`Semana: 2 | Bloque: A | Modalidad: Actividades Colaborativas`\n\n"
        "2️⃣ *Consultar links y recursos de tus cursos:*\n"
        "Escríbeme directamente lo que buscas, por ejemplo:\n"
        "• `foro 1 bloque a`\n"
        "• `examen 3 bloque d`\n"
        "• `open class`\n"
        "• `calificador` _(tareas pendientes por evaluar)_\n"
        "• `extemporaneas`\n"
        "• `puntos extra`\n\n"
        "3️⃣ *Generar comunicados semanales (.txt):*\n"
        "• `comunicado semana 2 a` _(código oficial Moodle con enlaces)_\n"
        "• `informacion de clase semana 2 a` _(invitación con choro pedagógico IA)_"
    )
