# Calificador-Bot-Asincrono

Este repositorio contiene la arquitectura de datos y el código fuente de un sistema automatizado y asíncrono diseñado para la evaluación y retroalimentación de entregas académicas a nivel universitario. El sistema procesa documentos enviados por los usuarios a través de una interfaz de mensajería instantánea, consulta configuraciones dinámicas en Google Cloud Platform (GCP) y genera un desglose analítico estructurado utilizando Inteligencia Artificial Generativa.

---

## 1. Características Principales

- **Arquitectura Orientada a Eventos (Pub/Sub):** Desacopla la recepción de la entrega del procesamiento pesado. Responde al webhook en milisegundos, mitigando el riesgo de reintentos duplicados por timeout de la API origen.
- **Mitigación de Cold Starts:** Configuración con un margen de confirmación de 60 segundos en las suscripciones Push para soportar los arranques en frío de contenedores serverless durante periodos de inactividad.
- **Evaluación Estructurada con GenAI:** Integración nativa con Vertex AI (modelo gemini-2.5-flash) mediante un prompt regulado bajo metodologías pedagógicas para evitar respuestas redundantes.
- **Cierre Dinámico e Inteligente:** Lógica basada en expresiones regulares en Python que analiza la nota final asignada por la IA para inyectar mensajes de cierre contextuales según el desempeño del alumno.
- **Extracción Multi-formato:** Soporte para parsing de archivos estructurados en formatos .pdf, .docx y .doc (ejecutando utilerías del sistema operativo como antiword dentro del contenedor).
- **Pipeline de CI/CD Automatizado:** Ciclo de despliegue continuo integrado mediante triggers de Cloud Build conectados directamente al repositorio de control de versiones.

---

## 2. Arquitectura de Componentes en GCP

El flujo de información y la persistencia se encuentran orquestados a través de los siguientes módulos:

- **Webhook de Entrada:** Recibe el documento adjunto del alumno y los metadatos de validación (Periodo, Módulo, Tipo de Entrega).
- **Cloud Run (Ruta Publicadora):** Endpoint expuesto que valida la estructura del mensaje, empaqueta los datos en bytes, los publica en la cola y retorna un HTTP 200 inmediato.
- **Cloud Pub/Sub:** Actúa como bus de mensajería asíncrono (Tópico y Suscripción Push) garantizando la entrega de la comanda y la persistencia temporal de los mensajes en fila.
- **BigQuery:** Repositorio de metadatos dinámicos que asocia las variables de la entrega con las rutas específicas de almacenamiento de las rúbricas.
- **Cloud Storage:** Almacenamiento de objetos que resguarda los archivos planos (.txt) con las instrucciones oficiales y los criterios de evaluación.
- **Cloud Run (Ruta Trabajadora):** Endpoint privado invocado por la suscripción Push de Pub/Sub para procesar la descarga del archivo, extraer el texto, llamar a Vertex AI y notificar al alumno.

---

## 3. Estructura del Proyecto

```text
calificador-bot/
├── Dockerfile                  # Entorno de ejecución (Python 3.11-slim + paquetes linux indispensables)
├── requirements.txt            # Congelador de dependencias fijas del entorno
├── bot_telegram.py             # Lógica central Flask y declaración de endpoints de la arquitectura
└── src/
    ├── evaluador_ia.py         # Configuración del cliente de Vertex AI y prompt de evaluación ejecutiva
    ├── config_gcp.py           # Capa de abstracción para conexiones a BigQuery y Cloud Storage
    └── lector_archivos.py      # Módulo extractor de texto plano para múltiples extensiones binarias
```

---

## 4. Flujo de Git y Despliegue Continuo (CI/CD)

El ciclo de vida del software está completamente automatizado. Para actualizar el sistema en la nube desde el entorno local, se ejecuta la secuencia estándar de control de versiones:

1. Se realizan las modificaciones pertinentes en el entorno local de desarrollo.
2. Se confirman los cambios y se empujan a la rama principal:
   ```bash
   git add .
   git commit -m "feat: optimizacion del pipeline asincrono y prompt ejecutivo"
   git push origin main
   ```
3. El trigger enlazado de Cloud Build detecta el commit de manera automática, compila la nueva imagen utilizando el Dockerfile y actualiza el servicio de Cloud Run de manera transparente y sin tiempo de inactividad (Zero-Downtime).

---

## 5. Protocolo de Entrada Requerido

Para asegurar el correcto parsing de metadatos por parte del motor de expresiones regulares, el archivo adjunto enviado por el usuario debe incluir de manera obligatoria la siguiente estructura de texto en su descripción:

```text
Semana: [Número] | Bloque: [Letra] | Modalidad: [Nombre de la Categoría]
```

