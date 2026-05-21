import os
import re
import requests
from flask import Flask, request, jsonify

from config_gcp import obtener_rutas_actividad, leer_txt_bucket
from evaluador_ia import evaluar_tarea
# Importamos tu nuevo extractor de archivos
from lector_archivos import extraer_texto_archivo

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

def enviar_mensaje_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def descargar_archivo_telegram(file_id):
    """Va a los servidores de Telegram por la ruta del archivo y baja sus bytes"""
    url_info = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    res_info = requests.get(url_info).json()
    
    if res_info.get("ok"):
        file_path = res_info["result"]["file_path"]
        url_descarga = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        res_bytes = requests.get(url_descarga)
        return res_bytes.content
    return None

@app.route('/webhook', methods=['POST'])
def webhook():
    datos = request.get_json()
    
    # Validamos si mandaste un documento
    if "message" in datos and "document" in datos["message"]:
        chat_id = datos["message"]["chat"]["id"]
        documento = datos["message"]["document"]
        nombre_archivo = documento["file_name"]
        file_id = documento["file_id"]
        
        # El formato ahora viaja en el texto que acompaña al archivo (caption)
        texto_recibido = datos["message"].get("caption", "")
        
        print(f"--- Procesando archivo {nombre_archivo} del chat {chat_id} ---")
        
        patron = r"Semana:\s*(\d+)\s*\|\s*Bloque:\s*([A-Z])\s*\|\s*Modalidad:\s*([^|]+)"
        match = re.search(patron, texto_recibido, re.IGNORECASE)
        
        if match:
            semana = int(match.group(1))
            bloque = match.group(2).upper()
            modalidad = match.group(3).strip()
            
            enviar_mensaje_telegram(chat_id, "⏳ _Descargando archivo y jalando rúbricas de GCP..._")
            
            try:
                # 1. Bajamos los bytes desde Telegram
                archivo_bytes = descargar_archivo_telegram(file_id)
                if not archivo_bytes:
                    raise Exception("No se pudieron obtener los bytes de Telegram.")
                
                # 2. Extraemos el texto puro (.pdf o .docx)
                tarea_alumno = extraer_texto_archivo(archivo_bytes, nombre_archivo)
                
                # 3. Vamos a BigQuery por las rutas del bucket
                ruta_ins, ruta_com = obtener_rutas_actividad(semana, modalidad, bloque)
                
                if not ruta_ins or not ruta_com:
                    enviar_mensaje_telegram(chat_id, "❌ No encontré esa configuración en BigQuery.")
                    return jsonify({"status": "error"}), 200
                
                # 4. Leemos los textos del bucket
                instrucciones = leer_txt_bucket(ruta_ins)
                comentarios = leer_txt_bucket(ruta_com)
                
                enviar_mensaje_telegram(chat_id, "🤖 _Evaluando con Gemini 2.5-Flash... Aguanta un piano..._")
                
                # 5. Mandamos a calificar el texto extraído
                retroalimentacion = evaluar_tarea(instrucciones, comentarios, tarea_alumno)
                
                enviar_mensaje_telegram(chat_id, retroalimentacion)
                
            except Exception as e:
                enviar_mensaje_telegram(chat_id, f"❌ Tronó el desmadre: {str(e)}")
        else:
            mensaje_ayuda = (
                "👋 ¡Qué tranza! Mándame el archivo (.pdf o .docx) y en el *comentario del archivo* ponle:\n\n"
                "*Semana:* 2 | *Bloque:* A | *Modalidad:* Actividades Colaborativas"
            )
            enviar_mensaje_telegram(chat_id, mensaje_ayuda)
            
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    puerto = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto, debug=True)