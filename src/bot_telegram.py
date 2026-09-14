import os
import re
import json
import base64  # Para decodificar los mensajes que empuja Pub/Sub
from typing import Any
import requests
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1  # El cliente para el bus de mensajes

# Importaciones de tus propios módulos locales (fuente [source: 4])
from config_gcp import obtener_rutas_actividad, leer_txt_bucket
from evaluador_ia import evaluar_tarea
from lector_archivos import extraer_texto_archivo
from buscador_links import obtener_buscador, generar_mensaje_menu, normalizar_texto
from generador_comunicados import obtener_generador

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Estado conversacional en memoria para preguntas interactivas (chat_id -> dict)
ESTADOS_USUARIO: dict[int, dict[str, Any]] = {}

# --- CONFIGURACIÓN DE GCP PUB/SUB ---
# Inicializamos el cliente publicador
publicador_client = pubsub_v1.PublisherClient()
# Definimos la ruta oficial hacia tu tópico en el proyecto sentinela-mx
TOPIC_PATH = publicador_client.topic_path("sentinela-mx", "topico-evaluador")

def enviar_mensaje_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def enviar_documento_telegram(chat_id, contenido, nombre_archivo, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    if isinstance(contenido, str):
        contenido_bytes = contenido.encode("utf-8")
    else:
        contenido_bytes = contenido
    files = {"document": (nombre_archivo, contenido_bytes, "text/plain")}
    payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
    requests.post(url, data=payload, files=files)

def descargar_archivo_telegram(file_id):
    url_info = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    res_info = requests.get(url_info).json()
    if res_info.get("ok"):
        file_path = res_info["result"]["file_path"]
        url_descarga = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        res_bytes = requests.get(url_descarga)
        return res_bytes.content
    return None

# =====================================================================
# --- RUTA 1: EL PUBLICADOR (WEBHOOK ULTRA RÁPIDO PARA TELEGRAM) ---
# =====================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    datos = request.get_json()
    if not datos or "message" not in datos:
        return jsonify({"status": "no_message"}), 200

    mensaje = datos["message"]
    chat_id = mensaje["chat"]["id"]

    # --- CASO 1: EL DOCENTE MANDA UN ARCHIVO PARA CALIFICAR (PUB/SUB) ---
    if "document" in mensaje:
        documento = mensaje["document"]
        nombre_archivo = documento["file_name"]
        file_id = documento["file_id"]
        texto_recibido = mensaje.get("caption", "")
        
        # Expresión regular para validar Semana, Bloque y Modalidad
        patron = r"Semana:\s*(\d+)\s*\|\s*Bloque:\s*([A-Z])\s*\|\s*Modalidad:\s*([^|]+)"
        match = re.search(patron, texto_recibido, re.IGNORECASE)
        
        if match:
            paquete_datos = {
                "chat_id": chat_id,
                "file_id": file_id,
                "nombre_archivo": nombre_archivo,
                "semana": int(match.group(1)),
                "bloque": match.group(2).upper(),
                "modalidad": match.group(3).strip()
            }
            
            datos_en_bytes = json.dumps(paquete_datos).encode("utf-8")
            print(f"--- Publicando tarea del chat {chat_id} en Pub/Sub... ---")
            futuro_envio = publicador_client.publish(TOPIC_PATH, datos_en_bytes)
            futuro_envio.result()
            
            enviar_mensaje_telegram(chat_id, "📥 _¡Entrega recibida con éxito! Ya está en la fila. En un momento te llegará tu retroalimentación detallada..._")
            return jsonify({"status": "queued"}), 200
        else:
            mensaje_ayuda = (
                "👋 Mándame el archivo y en el *comentario* ponle:\n\n"
                "`Semana: 2 | Bloque: A | Modalidad: Actividades Colaborativas`\n\n"
                "_(O escribe *menu* para consultar opciones y enlaces)_"
            )
            enviar_mensaje_telegram(chat_id, mensaje_ayuda)
            return jsonify({"status": "invalid_caption"}), 200

    # --- CASO 2: EL DOCENTE ESCRIBE TEXTO (ASISTENTE DE LINKS, MENÚ Y COMUNICADOS) ---
    elif "text" in mensaje:
        texto_usuario = mensaje["text"].strip()
        t_norm = normalizar_texto(texto_usuario)

        # 0. Si el docente estaba respondiendo los datos de su clase en vivo (Interactivo)
        if chat_id in ESTADOS_USUARIO and ESTADOS_USUARIO[chat_id].get("accion") == "esperando_datos_clase":
            estado = ESTADOS_USUARIO.pop(chat_id)
            semana = estado["semana"]
            bloque = estado["bloque"]

            partes = re.split(r"\s*[-|]\s*", texto_usuario, maxsplit=1)
            horario = partes[0].strip()
            titulo = partes[1].strip() if len(partes) > 1 else None

            enviar_mensaje_telegram(chat_id, "⏳ _Generando invitación con Gemini y enlaces de Open Class... En unos segundos te llega el archivo._")
            try:
                generador = obtener_generador()
                invitacion = generador.generar_invitacion_clase(
                    bloque=bloque,
                    semana=semana,
                    horario_clase=horario,
                    titulo_sesion=titulo,
                )
                nombre_doc = f"invitacion_clase_semana_{semana}_bloque_{bloque.lower()}.txt"
                caption = (
                    f"🎥 *Invitación a Open Class Lista — Semana {semana} (Bloque {bloque})*\n\n"
                    f"_Incluye introducción temática con IA y enlace directo al tablero._"
                )
                enviar_documento_telegram(chat_id, invitacion, nombre_doc, caption=caption)
            except Exception as e:
                enviar_mensaje_telegram(chat_id, f"⚠️ Error al generar invitación: {e}")
            return jsonify({"status": "clase_generated"}), 200

        # Saludos o solicitud de menú
        if t_norm in ("/start", "start", "hola", "menu", "ayuda", "/help", "help", "buenos dias", "buenas tardes", "buenas noches"):
            enviar_mensaje_telegram(chat_id, generar_mensaje_menu())
            return jsonify({"status": "menu_sent"}), 200

        # 1. Comando: COMUNICADO OFICIAL SEMANAL (HTML en .txt)
        # Coincide con: "comunicado semana 2 a", "comunicado s3 d", "comunicado oficial semana 5 bloque d", etc.
        m_com = re.search(r"comunicado\s*(?:oficial\s*)?(?:semana\s*|s)?(\d+)(?:\s*(?:bloque\s*|del\s*)?([ad]))?", t_norm)
        if m_com:
            semana = int(m_com.group(1))
            bloque = (m_com.group(2) or ("a" if " a" in t_norm else "d" if " d" in t_norm else "d")).upper()
            try:
                generador = obtener_generador()
                html_comunicado = generador.generar_comunicado_oficial(bloque, semana)
                nombre_doc = f"comunicado_semana_{semana}_bloque_{bloque.lower()}.txt"
                caption = (
                    f"✅ *Comunicado Oficial Listo — Semana {semana} (Bloque {bloque})*\n\n"
                    f"📄 Código HTML oficial con enlaces incrustados de actividades, exámenes, Open Class y puntos extra.\n"
                    f"_Descarga el archivo y pega el código directo en Moodle._"
                )
                enviar_documento_telegram(chat_id, html_comunicado, nombre_doc, caption=caption)
            except Exception as e:
                enviar_mensaje_telegram(chat_id, f"⚠️ Error al generar comunicado: {e}")
            return jsonify({"status": "comunicado_generated"}), 200

        # 2. Comando: INFORMACIÓN DE CLASE (OPEN CLASS)
        # Coincide con: "informacion de clase semana 2 a", "clase semana 2 a", "invitacion clase semana 3 d"
        m_clase = re.search(r"(?:informacion\s+de\s+clase|info\s+clase|clase|invitacion\s+clase)\s*(?:semana\s*|s)?(\d+)(?:\s*(?:bloque\s*|del\s*)?([ad]))?", t_norm)
        if m_clase:
            semana = int(m_clase.group(1))
            bloque = (m_clase.group(2) or ("a" if " a" in t_norm else "d" if " d" in t_norm else "d")).upper()

            # Caso 1-shot (si el docente mandó horario en la misma línea con "|")
            resto = ""
            if "|" in texto_usuario:
                partes = texto_usuario.split("|", 1)
                resto = partes[1].strip()

            if resto:
                partes_resto = re.split(r"\s*[-|]\s*", resto, maxsplit=1)
                horario = partes_resto[0].strip()
                titulo = partes_resto[1].strip() if len(partes_resto) > 1 else None
                enviar_mensaje_telegram(chat_id, "⏳ _Generando invitación con Gemini y enlaces de Open Class..._")
                try:
                    generador = obtener_generador()
                    invitacion = generador.generar_invitacion_clase(
                        bloque=bloque,
                        semana=semana,
                        horario_clase=horario,
                        titulo_sesion=titulo,
                    )
                    nombre_doc = f"invitacion_clase_semana_{semana}_bloque_{bloque.lower()}.txt"
                    caption = (
                        f"🎥 *Invitación a Open Class Lista — Semana {semana} (Bloque {bloque})*\n\n"
                        f"_Incluye introducción temática generada con Gemini y enlace al aula._"
                    )
                    enviar_documento_telegram(chat_id, invitacion, nombre_doc, caption=caption)
                except Exception as e:
                    enviar_mensaje_telegram(chat_id, f"⚠️ Error al generar invitación: {e}")
                return jsonify({"status": "clase_generated"}), 200
            else:
                # Caso interactivo: preguntar día y hora
                generador = obtener_generador()
                info_tema = generador.obtener_tema_semana(bloque, semana)
                tema_nombre = info_tema.get("tema", "")

                ESTADOS_USUARIO[chat_id] = {
                    "accion": "esperando_datos_clase",
                    "semana": semana,
                    "bloque": bloque,
                }

                msg_pregunta = (
                    f"🗓️ *Invitación a Open Class — Semana {semana} (Bloque {bloque})*\n\n"
                    f"📌 *Tema registrado:* _{tema_nombre}_\n\n"
                    f"¿Cuándo y a qué hora es la clase en vivo? (y si quieres, incluye el título de la sesión):\n\n"
                    f"✍️ _Ejemplo:_ `Martes 15 de sept 18 hrs (HORACDMX) - {tema_nombre}`"
                )
                enviar_mensaje_telegram(chat_id, msg_pregunta)
                return jsonify({"status": "waiting_class_details"}), 200

        # 3. Consulta regular al buscador de enlaces
        respuesta_links, _ = obtener_buscador().buscar(texto_usuario)
        enviar_mensaje_telegram(chat_id, respuesta_links)

        return jsonify({"status": "text_processed"}), 200

    return jsonify({"status": "ok"}), 200

# =====================================================================
# --- RUTA 2: EL SUSCRIPTOR (TRABAJADOR ASÍNCRONO DE SEGUNDO PLANO) ---
# =====================================================================
@app.route('/procesar-retro', methods=['POST'])
def procesar_retro():
    sobre_mensaje = request.get_json()
    if not sobre_mensaje or "message" not in sobre_mensaje:
        return jsonify({"status": "bad request"}), 400
    
    try:
        # 1. Pub/Sub manda la data encriptada en Base64. Toca decodificarla.
        datos_base64 = sobre_mensaje["message"]["data"]
        datos_decodificados = base64.b64decode(datos_base64).decode("utf-8")
        tarea_meta = json.loads(datos_decodificados)
        
        chat_id = tarea_meta["chat_id"]
        file_id = tarea_meta["file_id"]
        nombre_archivo = tarea_meta["nombre_archivo"]
        semana = tarea_meta["semana"]
        bloque = tarea_meta["bloque"]
        modalidad = tarea_meta["modalidad"]
        
        print(f"--- Iniciando procesamiento pesado para el chat {chat_id} ---")
        
        # 2. Descargamos el archivo desde Telegram (fuente [source: 4])
        archivo_bytes = descargar_archivo_telegram(file_id)
        if not archivo_bytes:
            raise Exception("No se pudieron obtener los bytes de Telegram.")
        
        # 3. Extraemos el texto puro del documento (fuente [source: 4])
        tarea_alumno = extraer_texto_archivo(archivo_bytes, nombre_archivo)
        
        # 4. Buscamos las rutas en BigQuery (fuente [source: 4])
        ruta_ins, ruta_com = obtener_rutas_actividad(semana, modalidad, bloque)
        
        if not ruta_ins or not ruta_com:
            enviar_mensaje_telegram(chat_id, "❌ Error interno: No encontré la configuración de esta rúbrica en BigQuery.")
            return jsonify({"status": "config_not_found"}), 200
        
        # 5. Leemos las rúbricas desde Cloud Storage (fuente [source: 4])
        instrucciones = leer_txt_bucket(ruta_ins)
        comentarios = leer_txt_bucket(ruta_com)
        
        # 6. Llamamos a Gemini 2.5-Flash para el análisis perrón (fuente [source: 4, 6])
        print("--- Enviando a evaluar con Gemini... ---")
        retroalimentacion_pura = evaluar_tarea(instrucciones, comentarios, tarea_alumno)
        
        # 7. EXTRAEMOS LA NOTA PARA EL CIERRE DINÁMICO
        # Buscamos la línea de la calificación sugerida mediante regex
        match_calif = re.search(r"Calificación Sugerida:\s*(\d+(?:\.\d+)?)", retroalimentacion_pura, re.IGNORECASE)
        if match_calif:
            nota_final = float(match_calif.group(1))
        else:
            nota_final = 0.0
            
        # 8. Decidimos qué choro aventarle dependiendo de su calificación
        if nota_final >= 10.0:
            choro_cierre = "¡Muchas felicidades por tu excelente desempeño! Has cumplido con todos los criterios de manera sobresaliente. Te invito a mantener este gran nivel en las siguientes semanas de nuestro curso."
        elif nota_final >= 8.0:
            choro_cierre = "Buen trabajo. Te invito a tomar en cuenta estas pequeñas observaciones para robustecer aún más tus conocimientos y mantener un desempeño destacado en tus próximas entregas."
        else:
            choro_cierre = "Te invito a tomar en cuenta estas observaciones de manera puntual para corregir y robustecer este contenido, ya que será una base indispensable para tus próximas entregas."

        # 9. Ensamblamos la retro pura con la firma formal e inteligente que querías
        retroalimentacion_final = f"""{retroalimentacion_pura}

{choro_cierre}

¡Mucho éxito en tu proceso!

Saludos,
**Antonio Velázquez
Docente UTEL Universidad**"""
        
        # 10. Despachamos el resultado completo final al alumno (fuente [source: 4])
        enviar_mensaje_telegram(chat_id, retroalimentacion_final)
        
    except Exception as e:
        print(f"🚨 Error en el procesamiento asíncrono: {str(e)}")
        enviar_mensaje_telegram(chat_id, "⚠️ **Servicio Interrumpido** ⚠️\n\nHubo un detalle técnico al procesar tu archivo. Por favor reenvía tu documento.")
        
    # Le confirmamos el HTTP 200 a Pub/Sub para que borre el mensaje de la cola
    return jsonify({"status": "processed"}), 200

if __name__ == '__main__':
    puerto = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto, debug=True)