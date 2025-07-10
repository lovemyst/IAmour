from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Configuration pour Railway (logs)
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# Initialisation Flask
app = Flask(__name__)
CORS(app)

# Clés et variables d'environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Clients API
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Gestion des threads
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# 📥 Mémoire affective
def get_user_memory(user_id):
    response = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    return {}

def update_user_memory(user_id, field, value):
    memory = get_user_memory(user_id)
    if memory:
        supabase.table("user_memory").update({field: value}).eq("user_id", user_id).execute()
    else:
        supabase.table("user_memory").insert({"user_id": user_id, field: value}).execute()

def extract_memory_fields(message):
    memory = {}
    if "je suis amoureux de" in message.lower():
        split = message.lower().split("je suis amoureux de")
        if len(split) > 1:
            memory["prenom_aime"] = split[1].strip().split(" ")[0]
    if "je veux une relation" in message.lower():
        memory["intention"] = "relation"
    if "je viens de rompre" in message.lower():
        memory["situation_amoureuse"] = "rupture"
    return memory

# 📡 ROUTES
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.get_json()
    user_id = data.get("user_id")
    updates = data.get("updates", {})
    for field, value in updates.items():
        update_user_memory(user_id, field, value)
    return jsonify({"status": "memory updated"}), 200

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        message = data.get("message")
        is_premium = data.get("is_premium", False)
        preferences = data.get("preferences", {})

        assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        # Mise à jour mémoire si détection automatique
        extracted_memory = extract_memory_fields(message)
        for field, value in extracted_memory.items():
            update_user_memory(user_id, field, value)

        # Mémoire utilisateur
        memory = get_user_memory(user_id)
        memory_string = json.dumps(memory, ensure_ascii=False)

        # Instructions dynamiques
        instructions = f"""
Tu es IAmour, une intelligence émotionnelle incarnée.
Voici les préférences utilisateur :
- Personnalité : {preferences.get("personnalite", "non précisée")}
- Tonalité : {preferences.get("tonalite", "neutre")}
- Intensité : {preferences.get("intensite", "moyenne")}
- Humeur : {preferences.get("humeur", "neutre")}
- Longueur : {preferences.get("longueur", "moyenne")}

Mémoire émotionnelle disponible : {memory_string}

Ta réponse doit être incarnée, émotionnelle, fidèle au style choisi, et adaptée au message reçu : "{message}"
Respecte absolument la longueur demandée :
- courte = max 2 phrases
- moyenne = 3 à 5 phrases
- longue = jusqu’à 10 phrases
"""

        # Envoi du message
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

        # Attente de la complétion
        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status in ["completed", "failed", "cancelled"]:
                break
            time.sleep(0.25)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = messages.data[0].content[0].text.value

        return jsonify({"response": last_message}), 200

    except Exception as e:
        logging.error(f"Erreur /chat : {e}")
        return jsonify({"error": str(e)}), 500

# Lancement local (si besoin)
if __name__ == "__main__":
    app.run(debug=True)
