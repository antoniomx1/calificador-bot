import io
from pypdf import PdfReader
from docx import Document

def extraer_texto_archivo(contenido_bytes: bytes, nombre_archivo: str) -> str:
    """
    Recibe los bytes del archivo y su nombre. 
    Detecta si es PDF o DOCX y extrae el texto puro.
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
                
    # Caso 3: Es un Word viejito (.doc) u otro formato
    else:
        raise ValueError("Formato no soportado. El bot solo acepta .pdf y .docx")

    return texto_extraido.strip()