import os
import re
import json
import base64  # Para decodificar los mensajes que empuja Pub/Sub
import requests
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1  # El cliente para el bus de mensajes

# Importaciones de tus propios módulos locales (fuente [source: 4])
from config_gcp import obtener_rutas_actividad, leer_txt_bucket
from evaluador_ia import evaluar_tarea
from lector_archivos import extraer_texto_archivo

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- CONFIGURACIÓN DE GCP PUB/SUB ---
# Inicializamos el cliente publicador
publicador_client = pubsub_v1.PublisherClient()
# Definimos la ruta oficial hacia tu tópico en el proyecto sentinela-mx
TOPIC_PATH = publicador_client.topic_path("sentinela-mx", "topico-evaluador")

def enviar_mensaje_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

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
    
    if "message" in datos and "document" in datos["message"]:
        chat_id = datos["message"]["chat"]["id"]
        documento = datos["message"]["document"]
        nombre_archivo = documento["file_name"]
        file_id = documento["file_id"]
        texto_recibido = datos["message"].get("caption", "")
        
        # Expresión regular para validar Semana, Bloque y Modalidad (fuente [source: 4])
        patron = r"Semana:\s*(\d+)\s*\|\s*Bloque:\s*([A-Z])\s*\|\s*Modalidad:\s*([^|]+)"
        match = re.search(patron, texto_recibido, re.IGNORECASE)
        
        if match:
            # 1. Empaquetamos los metadatos en un diccionario común y corriente
            paquete_datos = {
                "chat_id": chat_id,
                "file_id": file_id,
                "nombre_archivo": nombre_archivo,
                "semana": int(match.group(1)),
                "bloque": match.group(2).upper(),
                "modalidad": match.group(3).strip()
            }
            
            # 2. Pub/Sub exige recibir bytes, así que transformamos el JSON
            datos_en_bytes = json.dumps(paquete_datos).encode("utf-8")
            
            # 3. Publicamos la comanda en el tópico en milisegundos
            print(f"--- Publicando tarea del chat {chat_id} en Pub/Sub... ---")
            futuro_envio = publicador_client.publish(TOPIC_PATH, datos_en_bytes)
            futuro_envio.result()  # Confirma que GCP recibió el recado
            
            # 4. Le avisamos inmediatamente al alumno para calmar ansias
            enviar_mensaje_telegram(chat_id, "📥 _¡Entrega recibida con éxito! Ya está en la fila. En un momento te llegará tu retroalimentación detallada..._")
            
            # 5. Cortamos la comunicación devolviendo HTTP 200 a Telegram. Evita duplicaciones.
            return jsonify({"status": "queued"}), 200
            
        else:
            mensaje_ayuda = "👋 Mándame el archivo y en el *comentario* ponle:\n\n*Semana:* 2 | *Bloque:* A | *Modalidad:* Actividades Colaborativas"
            enviar_mensaje_telegram(chat_id, mensaje_ayuda)
            
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