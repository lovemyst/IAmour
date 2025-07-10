from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys
import uuid

# Configuration pour Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Configuration OpenAI et Supabase
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vérification ou création d’un thread utilisateur
def get_or_create_thread(user_id):
    thread_data = supabase.table("threads").select("thread_id").eq("user_id", user_id).limit(1).execute()
    if thread_data.data:
        return thread_data.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("threads").insert({
            "user_id": user_id,
            "thread_id": thread.id,
            "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }).execute()
        return thread.id

# Extraction mémoire affective depuis un message utilisateur
def extract_memory_info(message):
    fields = {
        "prenom_aime": ["s’appelle", "prénom", "elle s'appelle", "il s'appelle"],
        "situation_amour": ["rupture", "en couple", "célibataire", "séparation"],
        "style_relationnel": ["je suis anxieux", "je suis évitant", "dépendant affectif", "attachement", "style relationnel"],
        "intention": ["je veux trouver l’amour", "je veux l’oublier", "je veux me reconstruire", "je veux draguer", "je veux comprendre"]
    }
    memory = {}
    for key, keywords in fields.items():
        for kw in keywords:
            if kw.lower() in message.lower():
                memory[key] = message
                break
    return memory

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        message = data.get("message", "")
        user_id = data.get("user_id")
        preferences = data.get("preferences", {})
        premium = data.get("premium", False)

        if not user_id:
            return jsonify({"error": "user_id manquant"}), 400

        assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        memory_update = extract_memory_info(message)
        if memory_update:
            existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
            if existing.data:
                supabase.table("user_memory").update(memory_update).eq("user_id", user_id).execute()
            else:
                memory_update["user_id"] = user_id
                supabase.table("user_memory").insert(memory_update).execute()

        instructions = f"""Tu es IAmour, l’IA de l’amour. Adapte-toi à chaque utilisateur.
Tonalité : {preferences.get('tonalite')}
Intensité : {preferences.get('intensite')}
Longueur : {preferences.get('longueur')}
Personnalité IA : {preferences.get('personnalite')}
Humeur utilisateur : {preferences.get('humeur')}"""

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )

        timeout = time.time() + 20
        while time.time() < timeout:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = next((m for m in reversed(messages.data) if m.role == "assistant"), None)
        if not last_message:
            return jsonify({"error": "Aucune réponse générée"}), 500

        return jsonify({"response": last_message.content[0].text.value})

    except Exception as e:
        logging.error(f"Erreur dans /chat : {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.json
        user_id = data.get("user_id")
        updates = data.get("memory", {})

        if not user_id or not updates:
            return jsonify({"error": "Données manquantes"}), 400

        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(updates).eq("user_id", user_id).execute()
        else:
            updates["user_id"] = user_id
            supabase.table("user_memory").insert(updates).execute()

        return jsonify({"status": "ok"})

    except Exception as e:
        logging.error(f"Erreur dans /update_memory : {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)
