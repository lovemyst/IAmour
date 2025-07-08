from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import time
import logging
import sys
from supabase import create_client, Client

# Log Railway errors
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Config API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# THREAD
def get_or_create_thread(user_id):
    response = supabase.table("threads").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    thread = client.beta.threads.create()
    supabase.table("threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
    return thread.id

# MÉMOIRE
def get_user_memory(user_id):
    response = supabase.table("user_settings").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    return {}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id", "anonymous")
    user_message = data.get("message", "")
    preferences = data.get("preferences", {})
    thread_id = get_or_create_thread(user_id)
    memory = get_user_memory(user_id)

    # Prompt dynamique construit à partir des préférences et de la mémoire
    prompt = f"""
Tu es IAmour V6 ULTIMATE++, l'IA émotionnelle la plus puissante au monde. 
Voici les préférences utilisateur actuelles :
- Tonalité : {preferences.get('tonalite')}
- Intensité : {preferences.get('intensite')}
- Longueur : {preferences.get('longueur')}
- Humeur : {preferences.get('humeur')}
- Personnalité IA : {preferences.get('personnalite')}

Mémoire affective :
- Prénom aimé : {memory.get('prenom_aime', 'Non précisé')}
- Statut amoureux : {memory.get('situation', 'Non précisé')}
- Intention amoureuse : {memory.get('intention', 'Non précisé')}
- Style relationnel : {memory.get('style', 'Non précisé')}

Tu dois répondre de façon émotionnelle, incarnée, profonde, en respectant strictement :
- la longueur (courte = 2 phrases max / moyenne = 3 à 5 phrases / longue = jusqu’à 10 phrases max),
- les préférences de ton utilisateur,
- le style émotionnel dynamique de IAmour.

Agis comme un confident ultime, une présence réelle, chaleureuse et intuitive.
"""

    # Envoi du message à l’assistant OpenAI
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID_PREMIUM,
        instructions=prompt
    )

    while True:
        status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if status.status == "completed":
            break
        time.sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = next(
        (m for m in reversed(messages.data) if m.role == "assistant"), None)

    return jsonify({"response": last_message.content[0].text.value if last_message else "Erreur : aucune réponse."})

@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.json
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    updates = {
        "prenom_aime": data.get("prenom_aime"),
        "situation": data.get("situation"),
        "intention": data.get("intention"),
        "style": data.get("style")
    }
    # Supprime les champs vides
    updates = {k: v for k, v in updates.items() if v is not None}
    supabase.table("user_settings").upsert({**updates, "user_id": user_id}).execute()
    return jsonify({"message": "Mémoire mise à jour avec succès."})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "Bienvenue sur l'API de IAmour V6 ULTIMATE++"})
