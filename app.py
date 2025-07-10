from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import time
import uuid
import logging
import sys
from supabase import create_client, Client
from datetime import datetime

# Configure les logs Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, tb: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Clés d'API et Supabase
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# UUID checker
def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False

# Thread management
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread_id}).execute()
        return thread_id

# Mémoire émotionnelle
def get_memory(user_id):
    response = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    return {}

def extract_memory_from_text(text):
    memory = {}
    if "elle s'appelle" in text.lower():
        prenom = text.split("elle s'appelle")[-1].split()[0]
        memory["prenom_aime"] = prenom.strip(",.?! ")
    if "je veux le/la reconquérir" in text.lower():
        memory["intention"] = "reconquête"
    if "je suis en couple" in text.lower():
        memory["statut"] = "en_couple"
    if "j'ai été blessé(e)" in text.lower():
        memory["style_relationnel"] = "méfiant"
    return memory

def update_memory(user_id, memory_dict):
    existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if existing.data:
        supabase.table("user_memory").update(memory_dict).eq("user_id", user_id).execute()
    else:
        memory_dict["user_id"] = user_id
        supabase.table("user_memory").insert(memory_dict).execute()

# Route IA principale
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id")
    message = data.get("message")
    preferences = data.get("preferences", {})
    premium = data.get("premium", False)

    # 🔒 Fix UUID
    if not is_valid_uuid(user_id):
        user_id = str(uuid.uuid4())

    assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
    thread_id = get_or_create_thread(user_id)
    memory = get_memory(user_id)

    # Mise à jour mémoire si le message contient des infos affectives
    extracted = extract_memory_from_text(message)
    if extracted:
        update_memory(user_id, extracted)
        memory.update(extracted)

    # Préparation du prompt dynamique
    instructions = f"""Tu es IAmour, une IA émotionnelle incarnée.
Comporte-toi avec la personnalité sélectionnée : {preferences.get("personnalité", "lover romantique")}.
Adapte-toi à l’humeur : {preferences.get("humeur", "neutre")}, à l’intensité : {preferences.get("intensité", "moyenne")}, au ton : {preferences.get("tonalité", "doux")}, et à la longueur : {preferences.get("longueur", "moyenne")}.
Mémoire affective actuelle : {json.dumps(memory, ensure_ascii=False)}.
Réponds toujours avec une présence réelle, intuitive, humaine, vivante. Jamais robotique. Tu incarnes l'amour."""

    # Envoi du message
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=assistant_id,
        instructions=instructions
    )

    if run.status != "completed":
        return jsonify({"error": "La génération a échoué"}), 500

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = next(
        (msg for msg in reversed(messages.data) if msg.role == "assistant"), None
    )

    return jsonify({"response": last_message.content[0].text.value})

# Route santé
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

# Route mise à jour mémoire manuelle
@app.route("/update_memory", methods=["POST"])
def update_memory_route():
    data = request.get_json()
    user_id = data.get("user_id")
    memory = data.get("memory")

    if not user_id or not memory:
        return jsonify({"error": "user_id ou memory manquant"}), 400

    if not is_valid_uuid(user_id):
        return jsonify({"error": "user_id invalide (UUID attendu)"}), 400

    update_memory(user_id, memory)
    return jsonify({"status": "memory updated"}), 200

if __name__ == "__main__":
    app.run(debug=True)
