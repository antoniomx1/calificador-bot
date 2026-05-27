import os
import re
import requests
import threading # <-- NUEVO: Importamos threading para los procesos de fondo
from flask import Flask, request, jsonify

from config_gcp import obtener_rutas_actividad, leer_txt_bucket
from evaluador_ia import evaluar_tarea
from lector_archivos import extraer_texto_archivo

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

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

# --- NUEVO: Esta función se va a ejecutar "tras bambalinas" ---
def procesar_entrega_fondo(chat_id, file_id, nombre_archivo, semana, modalidad, bloque):
    enviar_mensaje_telegram(chat_id, "⏳ _Descargando archivo y jalando rúbricas de GCP..._")
    try:
        archivo_bytes = descargar_archivo_telegram(file_id)
        if not archivo_bytes:
            raise Exception("No se pudieron obtener los bytes de Telegram.")
        
        tarea_alumno = extraer_texto_archivo(archivo_bytes, nombre_archivo)
        ruta_ins, ruta_com = obtener_rutas_actividad(semana, modalidad, bloque)
        
        if not ruta_ins or not ruta_com:
            enviar_mensaje_telegram(chat_id, "❌ No encontré esa configuración en BigQuery.")
            return
        
        instrucciones = leer_txt_bucket(ruta_ins)
        comentarios = leer_txt_bucket(ruta_com)
        
        enviar_mensaje_telegram(chat_id, "🤖 _Evaluando con Gemini 2.5-Flash... Aguanta un piano..._")
        retroalimentacion = evaluar_tarea(instrucciones, comentarios, tarea_alumno)
        enviar_mensaje_telegram(chat_id, retroalimentacion)
        
    except Exception as e:
        print(f"🚨 Error interno: {str(e)}")
        mensaje_error = (
            "⚠️ **Servicio Interrumpido** ⚠️\n\n"
            "Los servidores andan saturados, caón. Aguanta unos minutos y vuelve a reenviar."
        )
        enviar_mensaje_telegram(chat_id, mensaje_error)

@app.route('/webhook', methods=['POST'])
def webhook():
    datos = request.get_json()
    
    if "message" in datos and "document" in datos["message"]:
        chat_id = datos["message"]["chat"]["id"]
        documento = datos["message"]["document"]
        nombre_archivo = documento["file_name"]
        file_id = documento["file_id"]
        texto_recibido = datos["message"].get("caption", "")
        
        patron = r"Semana:\s*(\d+)\s*\|\s*Bloque:\s*([A-Z])\s*\|\s*Modalidad:\s*([^|]+)"
        match = re.search(patron, texto_recibido, re.IGNORECASE)
        
        if match:
            semana = int(match.group(1))
            bloque = match.group(2).upper()
            modalidad = match.group(3).strip()
            
            # --- NUEVO: Lanzamos la chamba pesada al hilo secundario ---
            hilo = threading.Thread(target=procesar_entrega_fondo, args=(chat_id, file_id, nombre_archivo, semana, modalidad, bloque))
            hilo.start()
            
        else:
            mensaje_ayuda = "👋 Mándame el archivo y en el *comentario* ponle:\n\n*Semana:* 2 | *Bloque:* A | *Modalidad:* Actividades Colaborativas"
            enviar_mensaje_telegram(chat_id, mensaje_ayuda)
            
    # --- LA CLAVE: El servidor le contesta inmediatamente el 200 OK a Telegram ---
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    puerto = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto, debug=True)