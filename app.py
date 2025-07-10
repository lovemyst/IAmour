from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# 🔧 Logging Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# 🚀 Flask init
app = Flask(__name__)
CORS(app, origins=["https://lovable.app"])

# 🔐 Clés API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 🔌 Clients
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🧠 Lecture du prompt maître
def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

PROMPT_MASTER = read_file("IAmour_V6_FINAL_ULTIMATE_LOVABLE++.txt")

# 🧵 Thread
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    thread = client.beta.threads.create()
    supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
    return thread.id

# 🧠 Mise à jour mémoire émotionnelle
def update_user_memory(user_id, memory_data):
    existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if existing.data:
        supabase.table("user_memory").update(memory_data).eq("user_id", user_id).execute()
    else:
        supabase.table("user_memory").insert({**memory_data, "user_id": user_id}).execute()

# 🔍 Extraction mémoire depuis message
def extract_emotional_memory(message):
    memory = {}
    if "je l’aime" in message or "je pense encore à" in message:
        memory["prenom_aime"] = message.split()[-1].strip(".!? ")
    if "je veux oublier" in message:
        memory["intention_relation"] = "oublier"
    if "j’aimerais me remettre avec" in message:
        memory["intention_relation"] = "reconquête"
    if "je suis en couple" in message:
        memory["situation_amoureuse"] = "en_couple"
    elif "je suis célibataire" in message:
        memory["situation_amoureuse"] = "celibataire"
    return memory

# ✅ ROUTE /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ✅ ROUTE /update_memory
@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.json
    user_id = data.get("user_id")
    memory = data.get("memory", {})
    if not user_id or not memory:
        return jsonify({"error": "Missing user_id or memory"}), 400
    update_user_memory(user_id, memory)
    return jsonify({"status": "memory updated"}), 200

# ✅ ROUTE /chat
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        message = data.get("message", "")
        user_id = data.get("user_id")
        preferences = data.get("preferences", {})
        is_premium = data.get("premium", False)

        if not message or not user_id:
            return jsonify({"error": "Missing message or user_id"}), 400

        thread_id = get_or_create_thread(user_id)
        assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE

        # 🔁 Préférences UI
        tonalite = preferences.get("tonalite", "neutre")
        intensite = preferences.get("intensite", "moyenne")
        longueur = preferences.get("longueur", "moyenne")
        humeur = preferences.get("humeur", "neutre")
        personnalite = preferences.get("personnalite", "neutre")

        # 🔍 Mémoire auto
        memory_extracted = extract_emotional_memory(message)
        if memory_extracted:
            update_user_memory(user_id, memory_extracted)

        # 🧠 Injection préférences dans le message système
        pref_injection = f"""[PREFERENCES UTILISATEUR] Personnalité: {personnalite}, Tonalité: {tonalite}, Intensité: {intensite}, Longueur: {longueur}, Humeur: {humeur}."""
        system_message = {"role": "system", "content": f"{PROMPT_MASTER}\n\n{pref_injection}"}

        # 🔁 Ajout messages dans le thread
        client.beta.threads.messages.create(thread_id, role="user", content=message)

        # 🧠 Création du run
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=system_message["content"]
        )

        # 🧾 Récupération de la réponse
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = messages.data[0].content[0].text.value
        return jsonify({"response": last_message}), 200

    except openai.RateLimitError:
        return jsonify({"error": "Trop de requêtes. Patiente un peu."}), 429
    except Exception as e:
        logging.error(f"Erreur backend : {str(e)}")
        return jsonify({"error": "Erreur serveur"}), 500
