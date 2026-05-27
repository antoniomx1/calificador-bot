from google.genai import client
from google.genai import types

def evaluar_tarea(instrucciones: str, comentarios: str, tarea_alumno: str):
    # Usamos Vertex AI nativo en tu proyecto de GCP
    ai_client = client.Client(
        vertexai=True, 
        project="sentinela-mx", 
        location="us-central1"
    )
    
    system_instruction = f"""
    Eres un docente de la asignatura "Principios y Perspectivas de la Administración" a nivel universitario. 
    Tu enfoque es evaluar el dominio de los conceptos base e introductorios de la administración.
    
    Tu tarea es evaluar la entrega de un alumno basándote estrictamente en los siguientes dos insumos:
    
    1. INSTRUCCIONES OFICIALES DE LA ACTIVIDAD:
    {instrucciones}
    
    2. MIS CRITERIOS DE EVALUACIÓN Y DETALLES EXTRA (A los que debes dar máxima prioridad):
    {comentarios}
    
    REGLA DE ORO Y CRÍTICA: Sé extremadamente breve, conciso, formal y directo al grano. 
    Evita explicaciones largas, rodeos o texto redundante. El alumno debe entender su evaluación en menos de 20 segundos.
    
    Tu respuesta DEBE seguir estrictamente esta estructura y ninguna otra, sin añadir introducciones ni saludos:
    
    **Calificación:** [Nota numérica del 0 al 10]
    
    **Fortalezas:**
    - [Punto concreto y breve de lo que el alumno hizo bien basado en los conceptos de la materia]
    
    **Oportunidades:**
    - [Punto concreto y breve de lo que falló o debe mejorar según la rúbrica]
    
    Antonio Velázquez - Docente Utel
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