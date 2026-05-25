import io
import json
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
import PIL.Image

app = Flask(__name__)
CORS(app) # Esto permite que tus HTML se comuniquen con Python sin bloqueos

DB_NAME = "nexfin.db"

def inicializar_base_de_datos():
    """Crea la base de datos SQLite y la tabla si no existen."""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            nacimiento TEXT,
            curp TEXT,
            whatsapp TEXT,
            estado_civil TEXT,
            ocupacion TEXT,
            ingreso REAL,
            uso_credito TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conexion.commit()
    conexion.close()

def analizar_con_gemini(image_bytes, tipo_documento):
    """Envía la imagen a Gemini para verificar de forma estricta si es una INE o Selfie."""
    try:
        image = PIL.Image.open(io.BytesIO(image_bytes))
        
        prompt = f"""
        Analiza esta imagen adjunta para un proceso de validación biométrica.
        El usuario asegura que la foto corresponde a: "{tipo_documento}".
        
        Determina si la imagen coincide visualmente con lo solicitado de manera estricta:
        - Si es 'INE Frente' o 'INE Reverso', debe verse una identificación oficial mexicana (o simulación de credencial).
        - Si es una 'Selfie' (frente o perfiles), debe aparecer claramente un rostro humano reconocible.
        
        Responde EXCLUSIVAMENTE en formato JSON con la siguiente estructura:
        {{
            "valido": true o false,
            "motivo": "Explicación breve en español de lo que encontraste o por qué fue rechazada"
        }}
        """

        # Inicializa el cliente que buscará la API Key en el sistema
        client = genai.Client()
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        return {"valido": False, "motivo": f"Error al procesar imagen: {str(e)}"}

@app.route('/api/procesar-solicitud', methods=['POST'])
def procesar_solicitud():
    # 1. Recopilar los textos del formulario
    nombre = request.form.get('nombre')
    nacimiento = request.form.get('nacimiento')
    curp = request.form.get('curp')
    whatsapp = request.form.get('whatsapp')
    civil = request.form.get('civil')
    ocupacion = request.form.get('ocupacion')
    ingreso = request.form.get('ingreso')
    uso = request.form.get('uso')

    # 2. Mapear los archivos que vienen de las tarjetas de registro.html
    archivos_biometria = {
        'f1': 'INE Frente',
        'f2': 'INE Reverso',
        'f3': 'Selfie frente',
        'f4': 'Selfie perfil izquierdo',
        'f5': 'Selfie perfil derecho'
    }
    
    errores_ia = []

    # 3. Mandar cada imagen a revisión con Gemini
    for input_id, etiqueta in archivos_biometria.items():
        if input_id in request.files:
            file = request.files[input_id]
            if file.filename != '':
                image_bytes = file.read()
                resultado = analizar_con_gemini(image_bytes, etiqueta)
                
                # Si Gemini dice que la foto está mal, guardamos el porqué
                if not resultado.get('valido', False):
                    errores_ia.append(f"{etiqueta}: {resultado.get('motivo')}")
        else:
            errores_ia.append(f"Falta el archivo: {etiqueta}")

    # 4. Si hubo algún error en las fotos, frenamos todo y avisamos al usuario
    if errores_ia:
        return jsonify({
            "status": "error",
            "message": "La biometría falló la validación de IA",
            "detalles": errores_ia
        }), 422

    # 5. Si todo está perfecto, se guarda en la base de datos local SQLite
    try:
        conexion = sqlite3.connect(DB_NAME)
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO solicitudes (nombre, nacimiento, curp, whatsapp, estado_civil, ocupacion, ingreso, uso_credito)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nombre, nacimiento, curp, whatsapp, civil, ocupacion, ingreso, uso))
        conexion.commit()
        conexion.close()
        
        return jsonify({
            "status": "success",
            "message": "Identidad validada con éxito por la IA. Datos guardados en la base de datos."
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Error en base de datos: {str(e)}"}), 500

if __name__ == '__main__':
    inicializar_base_de_datos()
    print("Servidor listo en http://localhost:5000")
    app.run(port=5000, debug=True)