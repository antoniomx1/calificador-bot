from google.genai import client
from google.genai import types

def evaluar_tarea(instrucciones: str, comentarios: str, tarea_alumno: str):
    # Inicializa el cliente de Gemini (busca GEMINI_API_KEY en el entorno)
    ai_client = client.Client()
    
    system_instruction = f"""
    Eres un docente de nivel universitario experto en administración de organizaciones. 
    Tu tarea es evaluar la entrega de un alumno basándote estrictamente en los siguientes dos insumos:
    
    1. INSTRUCCIONES OFICIALES DE LA ACTIVIDAD:
    {instrucciones}
    
    2. MIS CRITERIOS DE EVALUACIÓN Y DETALLES EXTRA (A los que debes dar máxima prioridad):
    {comentarios}
    
    Sé profesional, asertivo y constructivo. Tu respuesta DEBE incluir:
    - Una calificación numérica del 0 al 10.
    - Una retroalimentación detallada desglosando qué hizo bien y en qué falló según los criterios.
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