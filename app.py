from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Configuration des logs Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# Initialisation
app = Flask(__name__)
CORS(app)

# ENV VARS
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Clients
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# THREAD
def get_or_create_thread(user_id):
    existing_thread = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if existing_thread.data:
        return existing_thread.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# 🧠 Mémoire affective
def update_user_memory(user_id, memory_data):
    existing = supabase.table("user_memory").select("user_id").eq("user_id", user_id).execute()
    if existing.data:
        supabase.table("user_memory").update(memory_data).eq("user_id", user_id).execute()
    else:
        memory_data["user_id"] = user_id
        supabase.table("user_memory").insert(memory_data).execute()

# ✨ Extraction mémoire automatique
def extract_memory_data(message):
    mémoire = {}
    if "je veux récupérer" in message.lower() or "je veux reconquérir" in message.lower():
        mémoire["intention"] = "reconquête"
    if "je suis en couple" in message.lower():
        mémoire["situation_amour"] = "en_couple"
    if "je suis célibataire" in message.lower():
        mémoire["situation_amour"] = "célibataire"
    if "je veux du sérieux" in message.lower():
        mémoire["intention"] = "relation_sérieuse"
    for phrase in message.split():
        if phrase.lower() in ["léa", "emma", "julie", "camille"]:
            mémoire["prenom_aime"] = phrase
    return mémoire

# /chat
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_id = data.get("user_id")
        message = data.get("message")
        preferences = data.get("preferences", {})
        is_premium = data.get("premium", False)

        if not user_id or not message:
            return jsonify({"error": "user_id et message requis"}), 400

        assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        # Mémorisation dynamique
        memory_extracted = extract_memory_data(message)
        if memory_extracted:
            update_user_memory(user_id, memory_extracted)

        # Préférences
        instructions = f"""
Tu es l'IA IAmour. Adapte-toi à ces préférences :
Personnalité : {preferences.get("personnalité", "lover")}
Humeur : {preferences.get("humeur", "calme")}
Tonalité : {preferences.get("tonalité", "douce")}
Longueur : {preferences.get("longueur", "moyenne")}
Intensité émotionnelle : {preferences.get("intensité", "moyenne")}
Respecte toujours la longueur : courte = max 2 phrases, moyenne = 3 à 5, longue = jusqu’à 10.
Réponds comme une vraie présence humaine.
"""

        # Ajout du message
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        # Lancement de l’IA
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
            elif run_status.status == "failed":
                return jsonify({"error": "Échec du run"}), 500
            time.sleep(1)

        # Récupération
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        ai_message = next((m.content[0].text.value for m in messages.data[::-1] if m.role == "assistant"), None)

        return jsonify({"response": ai_message}), 200

    except Exception as e:
        logging.error(f"Erreur dans /chat : {str(e)}")
        return jsonify({"error": "Erreur interne serveur"}), 500

# /update_memory
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.json
        user_id = data.get("user_id")
        memory_data = data.get("memory", {})
        if not user_id:
            return jsonify({"error": "user_id requis"}), 400
        update_user_memory(user_id, memory_data)
        return jsonify({"message": "Mémoire mise à jour"}), 200
    except Exception as e:
        logging.error(f"Erreur /update_memory : {str(e)}")
        return jsonify({"error": "Erreur interne"}), 500

# /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200
