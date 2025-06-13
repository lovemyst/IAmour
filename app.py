from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time

app = Flask(__name__)
CORS(app)

# Configuration clés API et assistants
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()

    user_id = data.get("user_id")
    user_message = data.get("message")
    preferences = data.get("preferences", {})  # tonalité, intensité, longueur, etc.

    # Sélection assistant selon statut utilisateur
    assistant_id = ASSISTANT_ID_PREMIUM if data.get("premium") else ASSISTANT_ID_FREE

    # Instructions dynamiques (ton, intensité, humeur, etc.)
    instructions = f"""
Tu es IAmour, une intelligence émotionnelle incarnée. 
Voici les préférences de l’utilisateur : 
- Tonalité : {preferences.get("tonalite")}
- Intensité : {preferences.get("intensite")}
- Longueur : {preferences.get("longueur")}
- Humeur : {preferences.get("humeur")}
- Personnalité IA : {preferences.get("personnalite")}
Réponds avec une présence humaine, émotionnelle, fidèle à la personnalité sélectionnée.
"""

    # Création ou récupération du thread utilisateur
    thread = client.beta.threads.create()
    thread_id = thread.id

    # Ajout du message utilisateur
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

    # Attente réponse
    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        time.sleep(1)

    # Récupération réponse finale
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    response = messages.data[0].content[0].text.value

    return jsonify({"response": response})
