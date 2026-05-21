# Importamos nuestras propias funciones de los otros archivos
from src.config_gcp import obtener_rutas_actividad, leer_txt_bucket
from src.evaluador_ia import evaluar_tarea

def ejecutar_calificacion_local():
    print("--- 1. Buscando configuración en BigQuery... ---")
    ruta_ins, ruta_com = obtener_rutas_actividad(2, 'Actividades Colaborativas', 'A')
    
    if not ruta_ins or not ruta_com:
        print("Chale, no se encontraron las rutas en BigQuery.")
        return

    print("--- 2. Extrayendo contexto desde Cloud Storage... ---")
    instrucciones = leer_txt_bucket(ruta_ins)
    comentarios = leer_txt_bucket(ruta_com)
    
    # Tarea simulada para el caliz
    tarea_prueba_alumno = """
    Misión de la empresa elegida (Bimbo): Ser una empresa sustentable, altamente productiva y plenamente humana.
    Situación práctica a nivel nacional: Enfrenta el reto de la distribución logística eficiente ante el alza de combustibles.
    Escuela de administración aplicada: Se observa la escuela científica por la optimización de tiempos en sus rutas de entrega.
    """
    
    print("--- 3. Enviando a evaluar con Gemini... ---")
    resultado = evaluar_tarea(instrucciones, comentarios, tarea_prueba_alumno)
    
    print("\n================ RETROALIMENTACIÓN DE LA IA ================")
    print(resultado)

if __name__ == "__main__":
    ejecutar_calificacion_local()