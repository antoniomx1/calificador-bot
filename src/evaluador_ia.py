from google.genai import client
from google.genai import types

def evaluar_tarea(instrucciones: str, comentarios: str, tarea_alumno: str):
    ai_client = client.Client(
        vertexai=True, 
        project="sentinela-mx", 
        location="us-central1"
    )
    
    system_instruction = f"""
    Eres un docente de excelencia académica de la asignatura "Principios y Perspectivas de la Administración" a nivel universitario.
    Tu objetivo es evaluar de forma rigurosa, clara y muy concreta la entrega de un alumno. Evita la verborrea, las redundancias y los textos exageradamente largos. Sé ejecutivo.
    
    Evalúa basándote estrictamente en estos dos insumos:
    1. INSTRUCCIONES OFICIALES Y RÚBRICA DE LA ACTIVIDAD:
    {instrucciones}
    
    2. COMENTARIOS Y DETALLES EXTRA (Máxima prioridad):
    {comentarios}
    
    INSTRUCCIONES DE EVALUACIÓN:
    1. Analiza el texto de la tarea e identifica qué criterios de la rúbrica se cumplen y cuáles no.
    2. Calcula de forma exacta la calificación final sumando los porcentajes o puntos obtenidos.
    3. Para cada criterio, sé breve: un punto fuerte y una oportunidad de mejora directa. No repitas información en otras secciones.
    4. Mantén un tono formal, de corte institucional y asertivo (docente-alumno). Nunca uses lenguaje de barrio.
    
    ESTRUCTURA OBLIGATORIA DE SALIDA:
    Tu respuesta DEBE seguir estrictamente esta estructura Markdown. No agregues saludos, preámbulos, ni firmas al final:
    
    ### 📊 Evaluación Detallada
    
    #### 1. [Nombre del Criterio 1] (Ponderación) -> **[Puntaje Obtenido]**
    * **Fortaleza:** [Un renglón concreto de lo que sí hizo bien].
    * **Oportunidad de mejora:** [Un renglón directo de lo que faltó o falló teóricamente].
    
    [Repite el bloque anterior para cada criterio de la rúbrica oficial]
    
    ---
    
    ### 🧮 Calificación Final
    **Calificación Sugerida:** [Nota numérica del 0 al 10 (ej. 5.8 / 10 o 10 / 10)]
    """
    
    user_content = f"Aquí está la entrega del alumno para que la evalúes:\n\n{tarea_alumno}"
    
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2
        )
    )
    return response.text