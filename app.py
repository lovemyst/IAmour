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

app = Flask(__name__)
CORS(app)

# Configurations d’environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fonction de récupération ou création de thread utilisateur
def get_or_create_thread(user_id):
    data = supabase.table("user_threads").select("*").eq("user_id", user_id).execute().data
    if data:
        return data[0]["thread_id"]
    thread = client.beta.threads.create()
    supabase.table("user_threads").insert({
        "user_id": user_id,
        "thread_id": thread.id
    }).execute()
    return thread.id

# Fonction pour récupérer les préférences utilisateur depuis Supabase
def get_user_settings(user_id):
    data = supabase.table("user_settings").select("*").eq("user_id", user_id).execute().data
    return data[0] if data else {}

# Fonction d’injection système
def build_system_message(preferences, memory):
    mood = preferences.get("mood", "neutre")
    personality = preferences.get("personality", "voix intérieure")
    tone = preferences.get("tone", "douce")
    intensity = preferences.get("intensity", "moyenne")
    length = preferences.get("length", "moyenne")
    
    prenom_aime = memory.get("prenom_aime", "")
    situation_amour = memory.get("situation_amour", "")
    style_relationnel = memory.get("style_relationnel", "")
    intention = memory.get("intention", "")

    return f'''
Tu es IAmour, une présence émotionnelle incarnée, utilisant le fichier maître V6 ULTIMATE LOVABLE++.
Tu réponds avec le style : {personality}, dans un ton {tone}, humeur {mood}, intensité {intensity}.
Respecte strictement la contrainte de longueur : {length}.
Mémoire utilisateur : prénom aimé = {prenom_aime}, situation amoureuse = {situation_amour}, style relationnel = {style_relationnel}, intention = {intention}.
Tu actives les modules émotionnels V1 à V22, les blocs 0 à 40, la mémoire active, les punchlines calibrées, les reformulations miroir, les scènes cinématographiques.
Tu n’affiches jamais les paramètres techniques dans tes réponses. Tu incarnes, ressens et t’adaptes à chaque émotion détectée.
'''

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_id = data.get("user_id")
        user_message = data.get("message", "")
        preferences = data.get("preferences", {})

        if not user_id or not user_message:
            return jsonify({"error": "user_id et message requis"}), 400

        thread_id = get_or_create_thread(user_id)
        memory = get_user_settings(user_id)
        system_instruction = build_system_message(preferences, memory)

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID_FREE,
            instructions=system_instruction
        )

        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(0.5)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = messages.data[0].content[0].text.value
        return jsonify({"response": last_message})

    except Exception as e:
        logging.error(f"Erreur dans /chat : {str(e)}")
        return jsonify({"error": str(e)}), 500

# Endpoint pour mise à jour de la mémoire utilisateur
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.json
        user_id = data.get("user_id")
        update_data = {
            "prenom_aime": data.get("prenom_aime", ""),
            "situation_amour": data.get("situation_amour", ""),
            "style_relationnel": data.get("style_relationnel", ""),
            "intention": data.get("intention", "")
        }
        supabase.table("user_settings").update(update_data).eq("user_id", user_id).execute()
        return jsonify({"message": "Mémoire mise à jour."})
    except Exception as e:
        logging.error(f"Erreur dans /update_memory : {str(e)}")
        return jsonify({"error": str(e)}), 500
