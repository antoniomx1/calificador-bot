from google.cloud import bigquery
from google.cloud import storage

def obtener_rutas_actividad(semana: int, modalidad: str, bloque: str):
    client = bigquery.Client(project='sentinela-mx')
    query = """
        SELECT ruta_instrucciones, ruta_comentarios 
        FROM `sentinela-mx.utel.cat_actividades`
        WHERE semana = @semana 
          AND modalidad = @modalidad 
          AND bloque = @bloque
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("semana", "INT64", semana),
            bigquery.ScalarQueryParameter("modalidad", "STRING", modalidad),
            bigquery.ScalarQueryParameter("bloque", "STRING", bloque),
        ]
    )
    query_job = client.query(query, job_config=job_config)
    results = list(query_job.result())
    
    if results:
        row = results[0]
        return row.ruta_instrucciones, row.ruta_comentarios
    return None, None

def leer_txt_bucket(ruta_gcs: str):
    if not ruta_gcs:
        return None
        
    client = storage.Client(project='sentinela-mx')
    ruta_limpia = ruta_gcs.replace("gs://", "")
    partes = ruta_limpia.split("/", 1)
    
    nombre_bucket = partes[0]
    ruta_archivo = partes[1]
    
    bucket = client.bucket(nombre_bucket)
    blob = bucket.blob(ruta_archivo)
    
    return blob.download_as_text(encoding='utf-8')