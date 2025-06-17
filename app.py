from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time

app = Flask(__name__)
CORS(app)

# Configuration des clés API et assistants
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        user_message = data.get("message")
        preferences = data.get("preferences", {})  # tonalité, intensité, longueur, etc.

        # Sélection de l'assistant selon le statut utilisateur
        assistant_id = ASSISTANT_ID_PREMIUM if data.get("premium") else ASSISTANT_ID_FREE

        # Construction des instructions dynamiques
        instructions = f"""
Tu es IAmour, une intelligence émotionnelle incarnée.
Voici les préférences de l’utilisateur :
- Tonalité : {preferences.get("tonalite")}
- Intensité émotionnelle : {preferences.get("intensite")}
- Longueur : {preferences.get("longueur")}
- Humeur actuelle : {preferences.get("humeur")}
- Personnalité IA : {preferences.get("personnalite")}
Réponds avec chaleur, humanité, et cohérence avec la personnalité sélectionnée.
"""

        # Création d’un nouveau thread
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Ajout du message utilisateur au thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Lancement du run
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )

        # Attente de la réponse
        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        # Récupération de la réponse finale
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
