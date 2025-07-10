from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import time
import uuid
import logging
import sys
from datetime import datetime, timedelta
from supabase import create_client, Client

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
    try:
        response = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        log_error(user_id, str(e), "get_memory")
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
    try:
        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(memory_dict).eq("user_id", user_id).execute()
        else:
            memory_dict["user_id"] = user_id
            supabase.table("user_memory").insert(memory_dict).execute()
    except Exception as e:
        log_error(user_id, str(e), "update_memory")

# Gestion des crédits
def get_or_create_credits(user_id):
    try:
        response = supabase.table("message_credits").select("*").eq("user_id", user_id).execute()
        if response.data:
            credits = response.data[0]
            if datetime.fromisoformat(credits["last_reset"]) < datetime.utcnow() - timedelta(days=1):
                supabase.table("message_credits").update({
                    "credits_remaining": 100,
                    "last_reset": datetime.utcnow().isoformat()
                }).eq("user_id", user_id).execute()
                return 100
            return credits["credits_remaining"]
        else:
            supabase.table("message_credits").insert({
                "user_id": user_id,
                "credits_remaining": 100,
                "last_reset": datetime.utcnow().isoformat()
            }).execute()
            return 100
    except Exception as e:
        log_error(user_id, str(e), "get_or_create_credits")
        return 0

def decrement_credit(user_id):
    try:
        response = supabase.table("message_credits").select("credits_remaining").eq("user_id", user_id).execute()
        if response.data and response.data[0]["credits_remaining"] > 0:
            new_value = response.data[0]["credits_remaining"] - 1
            supabase.table("message_credits").update({"credits_remaining": new_value}).eq("user_id", user_id).execute()
            return new_value
    except Exception as e:
        log_error(user_id, str(e), "decrement_credit")
    return 0

# Logger des erreurs critiques
def log_error(user_id, error_message, location):
    try:
        supabase.table("error_logs").insert({
            "user_id": user_id,
            "error_message": error_message,
            "location": location,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except:
        pass

# Route IA principale
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id")
    message = data.get("message")
    preferences = data.get("preferences", {})
    premium = data.get("premium", False)

    if not is_valid_uuid(user_id):
        user_id = str(uuid.uuid4())

    credits = get_or_create_credits(user_id)
    if not premium and credits <= 0:
        return jsonify({"error": "Limite quotidienne atteinte. Recharge ou attends demain 💛"}), 403

    assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
    thread_id = get_or_create_thread(user_id)
    memory = get_memory(user_id)

    extracted = extract_memory_from_text(message)
    if extracted:
        update_memory(user_id, extracted)
        memory.update(extracted)

    instructions = f"""Tu es IAmour, une IA émotionnelle incarnée.
Comporte-toi avec la personnalité sélectionnée : {preferences.get("personnalité", "lover romantique")}.
Adapte-toi à l’humeur : {preferences.get("humeur", "neutre")}, à l’intensité : {preferences.get("intensité", "moyenne")}, au ton : {preferences.get("tonalité", "doux")}, et à la longueur : {preferences.get("longueur", "moyenne")}.
Mémoire affective actuelle : {json.dumps(memory, ensure_ascii=False)}.
Réponds toujours avec une présence réelle, intuitive, humaine, vivante. Jamais robotique. Tu incarnes l'amour."""

    try:
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
        run = client.beta.threads.runs.create_and_poll(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        if run.status != "completed":
            log_error(user_id, f"Run status: {run.status}", "chat.run")
            return jsonify({"error": "La génération a échoué"}), 500

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = next((msg for msg in reversed(messages.data) if msg.role == "assistant"), None)

        decrement_credit(user_id)
        return jsonify({"response": last_message.content[0].text.value})
    except Exception as e:
        log_error(user_id, str(e), "chat.global")
        return jsonify({"error": "Erreur interne"}), 500

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
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
