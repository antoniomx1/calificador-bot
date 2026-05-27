import io
import os
import subprocess
import tempfile
from pypdf import PdfReader
from docx import Document

def extraer_texto_archivo(contenido_bytes: bytes, nombre_archivo: str) -> str:
    """
    Recibe los bytes del archivo y su nombre. 
    Detecta si es PDF, DOCX o DOC y extrae el texto puro.
    """
    nombre_archivo = nombre_archivo.lower()
    texto_extraido = ""

    # Caso 1: Es un PDF
    if nombre_archivo.endswith('.pdf'):
        stream = io.BytesIO(contenido_bytes)
        reader = PdfReader(stream)
        for pagina in reader.pages:
            texto_en_pagina = pagina.extract_text()
            if texto_en_pagina:
                texto_extraido += texto_en_pagina + "\n"
                
    # Caso 2: Es un Word (.docx)
    elif nombre_archivo.endswith('.docx'):
        stream = io.BytesIO(contenido_bytes)
        doc = Document(stream)
        for parrafo in doc.paragraphs:
            if parrafo.text:
                texto_extraido += parrafo.text + "\n"
                
    # Caso 3: Es un Word viejito (.doc)
    elif nombre_archivo.endswith('.doc'):
        # Creamos un archivo temporal físico en el contenedor para que antiword pueda leerlo
        with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as tmp:
            tmp.write(contenido_bytes)
            ruta_temporal = tmp.name

        try:
            # Ejecutamos antiword en la terminal pasándole la ruta del archivo temporal
            # El flag '-w 0' evita que rompa las líneas de texto por anchura de página
            resultado = subprocess.run(
                ['antiword', '-w', '0', ruta_temporal],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if resultado.returncode == 0:
                texto_extraido = resultado.stdout
            else:
                raise Exception(f"Error de antiword: {resultado.stderr}")
        finally:
            # Pase lo que pase, nos aseguramos de borrar el archivo temporal del disco
            if os.path.exists(ruta_temporal):
                os.remove(ruta_temporal)
                
    # Caso 4: Formato no soportado
    else:
        raise ValueError("Formato no soportado. El bot solo acepta .pdf, .docx y .doc")

    return texto_extraido.strip()