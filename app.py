from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Configuration pour Railway (logs visibles)
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Clés API et configuration environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Gestion des threads OpenAI
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data and len(response.data) > 0:
        return response.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# 🔧 Route de santé
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "OK"}), 200

# 🧠 Route pour mettre à jour la mémoire utilisateur (Supabase)
@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.get_json()
    user_id = data.get("user_id")
    memory = {
        "prenom_aime": data.get("prenom_aime"),
        "situation_amoureuse": data.get("situation_amoureuse"),
        "intention_relationnelle": data.get("intention_relationnelle"),
        "style_relationnel": data.get("style_relationnel")
    }

    response = supabase.table("user_settings").upsert({
        "user_id": user_id,
        **memory
    }).execute()
    return jsonify({"status": "memory updated", "data": response.data}), 200

# 💬 Route principale pour converser avec l'IA
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id")
    message = data.get("message")
    preferences = data.get("preferences", {})

    # Récupération du bon assistant
    assistant_id = ASSISTANT_ID_PREMIUM if data.get("is_premium") else ASSISTANT_ID_FREE

    # Récupération du thread
    thread_id = get_or_create_thread(user_id)

    # Injection dynamique des préférences dans le prompt
    dynamic_instructions = f"""
Tu es l’IA IAmour. Adapte-toi immédiatement aux préférences suivantes :
Tonalité : {preferences.get("tonalite")}
Intensité émotionnelle : {preferences.get("intensite")}
Longueur : {preferences.get("longueur")}
Humeur : {preferences.get("humeur")}
Personnalité : {preferences.get("personnalite")}
Réponds toujours de manière incarnée, émotionnelle et fidèle à la demande de l’utilisateur.
    """.strip()

    try:
        # Création du message
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        # Lancement de l'exécution avec prompt dynamique
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=dynamic_instructions
        )

        # Attente de la complétion
        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status in ["completed", "failed", "cancelled"]:
                break
            time.sleep(1)

        # Récupération du dernier message IA
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = next(
            (m for m in reversed(messages.data) if m.role == "assistant"),
            {"content": [{"text": {"value": "Je n’ai pas pu générer de réponse."}}]}
        )
        final_text = last_message["content"][0]["text"]["value"]
        return jsonify({"response": final_text}), 200

    except Exception as e:
        logging.error(f"Erreur dans /chat : {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
