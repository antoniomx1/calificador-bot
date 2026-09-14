"""Motor Generador de Comunicados Docentes e Invitaciones de Open Class (UTEL) para el Bot de Telegram."""

from __future__ import annotations

import csv
import logging
import os
import re
from pathlib import Path
from typing import Any

import openpyxl

logger = logging.getLogger("generador_comunicados")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMARIO_PATH = DATA_DIR / "temario.xlsx"
FALLBACK_TEMARIO_PATH = Path("/home/sil/comunicados_docente/temario.xlsx")


class GeneradorComunicados:
    """Clase principal para la carga de datos y ensamblado de comunicados docentes."""

    def __init__(
        self,
        temario_path: Path | str | None = None,
        data_dir: Path | str | None = None,
    ):
        self.temario_path = Path(temario_path) if temario_path else TEMARIO_PATH
        if not self.temario_path.exists() and FALLBACK_TEMARIO_PATH.exists():
            self.temario_path = FALLBACK_TEMARIO_PATH

        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.temario: dict[tuple[str, int], dict[str, str]] = {}
        self.actividades_por_curso: dict[int, list[dict[str, str]]] = {}

        self._cargar_temario()
        self._cargar_actividades()

    def _cargar_temario(self) -> None:
        """Lee 'temario.xlsx' y mapea (bloque, semana) -> {tema, comentarios}."""
        if not self.temario_path.exists():
            logger.warning(f"No se encontró el archivo de temario en: {self.temario_path}")
            return

        try:
            wb = openpyxl.load_workbook(self.temario_path, data_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue
                bloque_raw = row[0] if len(row) > 0 else ""
                sem_raw = row[1] if len(row) > 1 else ""
                tema_raw = row[2] if len(row) > 2 else ""
                com_raw = row[3] if len(row) > 3 else ""

                if bloque_raw is None or sem_raw is None:
                    continue

                bloque = str(bloque_raw).strip().upper()
                try:
                    semana = int(sem_raw)
                except (ValueError, TypeError):
                    continue

                tema = str(tema_raw).strip() if tema_raw else ""
                comentarios = str(com_raw).strip() if com_raw else ""

                self.temario[(bloque, semana)] = {
                    "tema": tema,
                    "comentarios": comentarios,
                }
            logger.info(f"Cargadas {len(self.temario)} semanas desde temario.xlsx.")
        except Exception as e:
            logger.error(f"Error al leer temario.xlsx: {e}")

    def _cargar_actividades(self) -> None:
        """Carga los CSVs de actividades para bloques A (446) y D (411)."""
        cursos_esperados = [(446, "a"), (411, "d")]
        for curso_id, bloque_str in cursos_esperados:
            csv_path = self.data_dir / f"curso_{curso_id}_bloque_{bloque_str}_actividades.csv"
            if not csv_path.exists():
                csv_path = self.data_dir / f"curso_{curso_id}_actividades.csv"

            if not csv_path.exists():
                logger.warning(f"No se localizó el CSV para curso {curso_id} en {csv_path}")
                continue

            actividades = []
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for r in reader:
                        clean = {k.strip(): (v.strip() if v else "") for k, v in r.items() if k}
                        actividades.append(clean)
                self.actividades_por_curso[curso_id] = actividades
                logger.info(f"Cargadas {len(actividades)} actividades de curso {curso_id}.")
            except Exception as e:
                logger.error(f"Error al leer CSV {csv_path}: {e}")

    def obtener_tema_semana(self, bloque: str, semana: int) -> dict[str, str]:
        """Recupera el tema y comentarios adicionales para una semana y bloque."""
        bloque_u = bloque.upper()
        res = self.temario.get((bloque_u, semana))
        if res:
            return res
        return {
            "tema": f"Contenido Semanal (Semana {semana})",
            "comentarios": "Revisión general de recursos y actividades de la semana.",
        }

    def obtener_links_semana(self, bloque: str, semana: int) -> dict[str, Any]:
        """Obtiene todos los enlaces relevantes de Moodle para esa semana y bloque."""
        bloque_u = bloque.upper()
        curso_id = 446 if bloque_u == "A" else 411
        actividades = self.actividades_por_curso.get(curso_id, [])

        links = {
            "curso_id": curso_id,
            "bloque": bloque_u,
            "semana": semana,
            "open_class": f"https://aula101.utel.edu.mx/local/openclass/index.php?id={curso_id}",
            "puntos_extras": f"https://aula101.utel.edu.mx/local/shortcut_links/puntosextra.php?id={curso_id}",
            "examen": "",
            "actividad": "",
            "trabajo_final": "",
            "ejecutiva": "",
            "competencias": "",
            "nombre_actividad": f"Actividad Semana {semana}",
            "nombre_foro": f"Foro {semana}",
        }

        patron_semana = re.compile(rf"\bsemana\s*{semana}\b", re.IGNORECASE)

        for act in actividades:
            cat = act.get("Categoria", "")
            desc = act.get("Actividad_Descriptiva", "")
            orig = act.get("Nombre_Original", "")
            sec = act.get("Semana_Seccion", "")
            url = act.get("Link", "")

            # Open Class
            if cat == "Open Class" and url:
                links["open_class"] = url
            # Puntos Extras
            if cat == "Puntos Extras" and "shortcut_links/puntosextra" in url:
                links["puntos_extras"] = url

            # Coincidencia con la semana
            if patron_semana.search(desc) or patron_semana.search(orig):
                if "modalidad de exámenes" in sec.lower() or cat == "Examen":
                    if "segunda vuelta" not in desc.lower() and "ejecutiv" not in sec.lower():
                        links["examen"] = url
                if "modalidad de actividades" in sec.lower() or cat in ("Tarea", "Foro"):
                    if "actividad" in desc.lower() or "semana" in desc.lower() or "foro" in desc.lower():
                        links["actividad"] = url
                        links["nombre_actividad"] = desc
                if "modalidad de trabajo final" in sec.lower() or "trabajo final" in desc.lower():
                    links["trabajo_final"] = url
                if "modalidad ejecutiva" in sec.lower() or "ejecutiv" in desc.lower():
                    links["ejecutiva"] = url
                if "competencias" in sec.lower():
                    links["competencias"] = url

        return links

    # =========================================================================
    # GENERADOR 1: COMUNICADO OFICIAL INSTITUCIONAL (HTML en .TXT)
    # =========================================================================
    def generar_comunicado_oficial(self, bloque: str, semana: int) -> str:
        """Genera el código HTML completo con los enlaces incrustados para Moodle."""
        bloque_u = bloque.upper()
        links = self.obtener_links_semana(bloque_u, semana)
        curso_id = links["curso_id"]
        open_class_url = links["open_class"]
        puntos_extras_url = links["puntos_extras"]
        examen_url = links["examen"] or f"https://aula101.utel.edu.mx/mod/quiz/index.php?id={curso_id}"
        actividad_url = links["actividad"] or f"https://aula101.utel.edu.mx/mod/assign/index.php?id={curso_id}"
        trabajo_final_url = links["trabajo_final"] or f"https://aula101.utel.edu.mx/mod/assign/index.php?id={curso_id}"

        # 1. Determinar estación y banners según la semana
        if semana <= 3:
            estacion_subtitulo = "⭐ Primera estación | Navegando hacia el saber ⭐"
            estacion_link_texto = "🚇 Navegando hacia el saber| Primera estación"
            banner_img = "https://i.pinimg.com/1200x/0b/7c/05/0b7c056e1a9b6ba742d919ab32e0666c.jpg"
        elif semana <= 6:
            estacion_subtitulo = "Bienvenidos a la segunda estación<br />“Descubriendo conocimientos”"
            estacion_link_texto = "🚇 Descubriendo conocimientos| Segunda estación"
            banner_img = "https://i.pinimg.com/originals/2a/ae/5f/2aae5fe0781a4fc8b10a91ff7d48aaf0.png"
        else:
            estacion_subtitulo = "🏆 Tercera estación | Consolidando el éxito 🏆"
            estacion_link_texto = "🚇 Consolidando el éxito| Tercera estación"
            banner_img = "https://i.pinimg.com/originals/2a/ae/5f/2aae5fe0781a4fc8b10a91ff7d48aaf0.png"

        # 2. Textos dinámicos de actividades
        if semana in (1, 3, 5):
            texto_actividad = f'<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><a href="{actividad_url}" target="_blank">Participa en el Foro de Semana {semana}</a></span></p>'
        else:
            texto_actividad = f'<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><a href="{actividad_url}" target="_blank">Realiza la Actividad de Semana {semana}</a></span></p>'

        texto_examen = f'<p><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;"><a href="{examen_url}" target="_blank">Realiza tu examen de semana {semana}.</a></span></p>'
        
        avance_num = (semana // 2) if semana > 1 else 1
        texto_tf = f'<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><a href="{trabajo_final_url}" target="_blank">Avance {avance_num} de Trabajo final [Clic aquí]</a></span></p>'
        texto_ejec = f'<p><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;"><a href="{examen_url}" target="_blank">Realiza tu examen de semana {semana}.</a></span></p>'

        # 3. Ensamblado del HTML oficial
        html = f"""<table style="width: 665px; height: 1480px;" border="0" align="center">
<tbody>
<tr style="height: 251.2px;">
<td style="width: 663.8px; height: 251.2px;"><img class="img-fluid align-bottom" style="display: block; margin-left: auto; margin-right: auto;" role="presentation" src="{banner_img}" alt="" width="658" height="243" /></td>
</tr>
<tr style="height: 1316.55px;">
<td style="width: 663.8px; height: 1316.55px;">
<p style="text-align: center;"><strong style="color: #000080; font-family: verdana, arial, helvetica, sans-serif; font-size: medium;">“Flexibilidad que se adapta a ti, éxito que se queda contigo"</strong></p>
<p style="text-align: center;"><span style="font-size: medium; color: #00c41c;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif;">Continuamos en la: </span></strong></span><br /><span style="font-size: medium; color: #00c41c;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif;"><strong> {estacion_subtitulo} </strong></span></strong></span></p>
<table style="margin-left: auto; margin-right: auto; width: 660px; height: 106px;" border="0" align="center">
<tbody>
<tr>
<td style="text-align: justify; width: 659px;">
<p style="text-align: left;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Queremos recordarte que cada recurso está diseñado para adaptarse a tus necesidades, fortalecer tus habilidades y enriquecer tu experiencia en nuestra comunidad global. 🌎</span></p>
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"> ➡️ Aquí te comparto la información más importante para esta semana:</span></p>
<p style="text-align: left;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">En esta <strong>semana {semana}</strong> de la materia <strong>Principios y perspectivas de la administración</strong> (Bloque {bloque_u}), preparé para ti material valioso que te permitirá desarrollar tu pensamiento crítico con situaciones relacionadas a los temas de esta semana, a continuación te comparto el link directo para visualizar el contenido:</span></p>
<p style="text-align: center;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small; color: #00c41c;">{estacion_link_texto}</span></strong><br /><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><a href="{actividad_url}" target="_blank"><strong>👉 Haz clic aquí para ingresar al contenido de la Semana {semana}</strong></a></span></p>
<p style="text-align: center;"><span style="color: #333399;"><strong><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;">Recuerda que tu participación suma hasta medio punto extra en tu calificación 🤩</span></strong></span></p>
</td>
</tr>
</tbody>
</table>
<table style="width: 661px; height: 242.2px; border: 3px solid #06b706;" border="3" align="center">
<tbody>
<tr style="height: 27.6px;">
<td style="text-align: center; border: 1px solid #06b706; width: 658.6px; height: 27.6px;" colspan="4">
<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Conforme a tu modalidad de evaluación realiza lo siguiente:</span></p>
</td>
</tr>
<tr style="height: 26.8px;">
<td style="text-align: center; border: 1px solid #06b706; width: 142.85px; height: 26.8px;">
<p><span style="color: #339966;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Actividades</span></strong></span></p>
</td>
<td style="text-align: center; border: 1px solid #06b706; width: 166.8px; height: 26.8px;"><span style="color: #339966;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Exámenes</span></strong></span></td>
<td style="text-align: center; border: 1px solid #06b706; width: 178.825px; height: 26.8px;"><span style="color: #339966;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Trabajo Final</span></strong></span></td>
<td style="text-align: center; border: 1px solid #06b706; width: 170.125px; height: 26.8px;"><span style="color: #339966;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Ejecutiva</span></strong></span></td>
</tr>
<tr style="height: 57.8px;">
<td style="text-align: center; border: 1px solid #06b706; width: 142.85px; height: 57.8px;">
{texto_actividad}
</td>
<td style="text-align: center; border: 1px solid #06b706; width: 166.8px; height: 57.8px;">
{texto_examen}
</td>
<td style="text-align: center; border: 1px solid #06b706; width: 178.825px; height: 57.8px;">
{texto_tf}
</td>
<td style="text-align: center; border: 1px solid #06b706; width: 170.125px; height: 57.8px;">
{texto_ejec}
</td>
</tr>
<tr style="height: 26.8px;">
<td style="text-align: center; border: 1px solid #06b706; width: 658.6px; height: 26.8px;" colspan="4"><strong><span style="font-size: small;">Programa de Éxito Académico y Profesional <a href="https://estudiantes.utel.edu.mx/">(PEAP)</a></span></strong></td>
</tr>
<tr style="height: 51.6px;">
<td style="text-align: center; border: 1px solid #06b706; width: 142.85px; height: 51.6px;"><span style="font-size: small;">Taller de apoyo académico</span></td>
<td style="text-align: center; border: 1px solid #06b706; width: 166.8px; height: 51.6px;"><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;">Asesorías Particulares</span></td>
<td style="text-align: center; border: 1px solid #06b706; width: 178.825px; height: 51.6px;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><a href="https://bit.ly/3KbhOVk">Talleres de Bienestar</a></span></td>
<td style="text-align: center; border: 1px solid #06b706; width: 170.125px; height: 51.6px;"><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;"><a href="https://bit.ly/3WJvjT9">Audiotaller</a></span></td>
</tr>
<tr style="height: 51.6px;">
<td style="text-align: center; border: 1px solid #06b706; width: 658.6px; height: 51.6px;" colspan="4"><span style="font-size: small; font-family: verdana, arial, helvetica, sans-serif;">🚀 ¡No te pierdas los <strong>Talleres de Impulso Universitario</strong> de esta semana!<br />👉 <a href="https://drive.google.com/file/d/17q2Nd0rJc8N6joCvwpImwz0kjhYbTx7C/view?usp=sharing">Únete dando clic aquí.</a></span></td>
</tr>
</tbody>
</table>
<br />
<table style="width: 645px; height: 147.4px; border: 3px solid #f4f905;" border="3" align="center">
<tbody>
<tr style="height: 147.4px;">
<td style="text-align: center; height: 147.4px; width: 642.6px;">
<table style="width: 142px; height: 134px;" border="0" align="left">
<tbody>
<tr>
<td style="width: 152.8px;"><img src="https://i.pinimg.com/736x/9a/00/a0/9a00a02de04a793be1983fc4a0a0c609.jpg" width="150" height="134" /></td>
</tr>
</tbody>
</table>
<p>.</p>
<p><span style="color: #ff6600;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><strong>¡Te invito a ingresar al calendario de open class!</strong></span></span></p>
<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Consulta el calendario de Open Class y elige el horario que mejor se adapte a ti:<br /><br /><a href="{open_class_url}" target="_blank" style="color: #ff6600; font-weight: bold; font-size: medium;">📅 👉 Haz clic aquí para entrar al Tablero de Open Class</a></span></p>
</td>
</tr>
</tbody>
</table>
<br />
<table style="width: 416px; height: 129px; border: 3px solid #f2bb0c;" border="3" align="center">
<tbody>
<tr style="height: 145.4px;">
<td style="width: 477.6px; height: 145.4px;">
<table border="0" align="left">
<tbody>
<tr>
<td><img src="https://i.pinimg.com/originals/21/e3/80/21e3807104faea19de64a3fe487d10ed.gif" width="162" height="139" /></td>
</tr>
</tbody>
</table>
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><strong>¡Puntos extras!</strong></span></p>
<p style="text-align: center;"></p>
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Autocalificables <a href="{puntos_extras_url}" target="_blank"><strong>"haz clic aquí"</strong></a></span></p>
</td>
</tr>
</tbody>
</table>
<br />
<table style="width: 651px; height: 182.8px;" border="0" align="center">
<tbody>
<tr style="height: 182.8px;">
<td style="height: 182.8px;">
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Para cualquier duda, puedes comunicarte con tu <strong>Gestor de Éxito Estudiantil.</strong> También puedes contactar a los números de atención para consultas relacionadas con colegiaturas, ajustes, procesos administrativos o documentos.</span></p>
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><img class="an1" src="https://fonts.gstatic.com/s/e/notoemoji/15.0/1f4de/72.png" alt="📞" width="17" height="17" loading="lazy" /> Teléfono y WhatsApp</span></p>
<p style="text-align: center;"><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">CDMX: +52 55 8977 0707</span><br /><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">Latam: +52 1 5592522986</span></p>
</td>
</tr>
</tbody>
</table>
<p style="text-align: center;"><span style="color: #000000;"><strong><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;">¡Éxito en tus evaluaciones!<br /></span></strong></span></p>
</td>
</tr>
<tr style="height: 146.8px;">
<td style="text-align: center; width: 663.8px; height: 146.8px;">
<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><strong>Cordialmente</strong></span></p>
<p><span style="font-family: verdana, arial, helvetica, sans-serif; font-size: small;"><strong>Docente Utel</strong></span></p>
<p><img style="text-align: start;" src="https://i.pinimg.com/564x/b5/3a/77/b53a775ede12d7a2049334f0f176c34c.jpg" width="139" height="48" /></p>
</td>
</tr>
<tr style="height: 78.8px;">
<td style="width: 663.8px; height: 78.8px;"><img style="display: block; margin-left: auto; margin-right: auto;" src="https://i.pinimg.com/564x/0c/16/fb/0c16fbed468fa687be4530c48fc66162.jpg" width="659" height="145" /></td>
</tr>
</tbody>
</table>"""
        return html

    # =========================================================================
    # GENERADOR 2: INVITACIÓN A OPEN CLASS (IA + DATOS DE CLASE)
    # =========================================================================
    def _obtener_cliente_ai(self):
        """Inicializa cliente Gemini (API Key local o Vertex AI en GCP)."""
        from google.genai import client

        # 1. Buscar en variable de entorno
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Fallback a .env local si existe
            for env_path in (BASE_DIR / ".env", Path("/home/sil/utel-calendar/extractor/.env")):
                if env_path.exists():
                    try:
                        for line in env_path.read_text(encoding="utf-8").splitlines():
                            if line.startswith("GEMINI_API_KEY="):
                                api_key = line.split("=", 1)[1].strip().strip("\"'")
                                break
                    except Exception:
                        pass
                if api_key:
                    break

        if api_key:
            try:
                return client.Client(api_key=api_key), "gemini-3.6-flash"
            except Exception as e:
                logger.warning(f"No se pudo inicializar con API key: {e}")

        # 2. En Cloud Run (GCP), usar Vertex AI
        try:
            return client.Client(vertexai=True, project="sentinela-mx", location="us-central1"), "gemini-2.5-flash"
        except Exception as e:
            logger.error(f"Error al conectar con Vertex AI: {e}")

        return None, None

    def redactar_choro_pedagogico(self, tema: str, comentarios: str, semana: int) -> str:
        """Usa Gemini para redactar la explicación introductoria amena al tema."""
        ai_client, model_name = self._obtener_cliente_ai()
        if not ai_client:
            return (
                f"En esta semana {semana} nos adentraremos en el fascinante tema de '{tema}'. "
                f"Analizaremos los conceptos clave y su aplicación práctica en el mundo empresarial moderno."
            )

        prompt = f"""
Actúa como Antonio Velázquez, docente apasionado y profesional de la asignatura 'Principios y perspectivas de la administración' en UTEL Universidad.
Tu objetivo es escribir un párrafo introductorio (choro pedagógico) para invitar a los alumnos a la clase en vivo (Open Class) de la Semana {semana}.

DATOS DEL TEMA:
- Tema oficial: {tema}
- Puntos clave y enfoque docente que debes abordar obligatoriamente: {comentarios}

REGLAS DE REDACCIÓN:
1. Máximo 2 párrafos concisos (entre 80 y 140 palabras en total).
2. Tono: Cercano, dinámico, profesional y motivador. Nada aburrido ni acartonado, pero sin perder el rigor universitario.
3. Conecta el tema con la realidad laboral o empresarial para despertar curiosidad e interés por conectarse a la clase en vivo.
4. NO incluyas saludo inicial (ej. 'Hola a todos') ni despedidas ni firmas, ya que esos bloques se añadirán automáticamente en la plantilla.
"""
        try:
            res = ai_client.models.generate_content(model=model_name, contents=prompt)
            return res.text.strip()
        except Exception as e:
            logger.error(f"Error generando texto con Gemini: {e}")
            return (
                f"En esta semana {semana} abordaremos '{tema}'. "
                f"Revisaremos puntos fundamentales como {comentarios}, analizando su impacto en las organizaciones actuales."
            )

    def generar_invitacion_clase(
        self,
        bloque: str,
        semana: int,
        horario_clase: str,
        titulo_sesion: str | None = None,
    ) -> str:
        """Genera el comunicado completo de invitación a la Open Class."""
        bloque_u = bloque.upper()
        tema_info = self.obtener_tema_semana(bloque_u, semana)
        tema = tema_info["tema"]
        comentarios = tema_info["comentarios"]

        links = self.obtener_links_semana(bloque_u, semana)
        open_class_url = links["open_class"]

        titulo_final = titulo_sesion.strip() if titulo_sesion else tema
        choro = self.redactar_choro_pedagogico(tema, comentarios, semana)

        mensaje = f"""Estimados alumnos,

Espero que se encuentren muy bien. Les doy una cordial bienvenida a nuestra sesión en vivo de esta semana.

{choro}

A continuación les comparto los detalles para que agenden nuestra clase:

📌 Tema / Sesión: {titulo_final}
🗓️ Fecha y Horario: {horario_clase}
🎓 Materia: Principios y perspectivas de la administración (Bloque {bloque_u} - Semana {semana})

🔗 Acceso a la Sesión (Tablero de Open Class):
👉 {open_class_url}

(Ingresen al enlace anterior para consultar el aula virtual y unirse en el horario indicado).

Agradezco mucho su compromiso y entusiasmo. ¡Nos vemos en clase!

Saludos cordiales,
Antonio Velázquez
Docente UTEL Universidad"""

        return mensaje


# Instancia singleton
_generador_instancia: GeneradorComunicados | None = None


def obtener_generador() -> GeneradorComunicados:
    global _generador_instancia
    if _generador_instancia is None:
        _generador_instancia = GeneradorComunicados()
    return _generador_instancia
