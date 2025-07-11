from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Logs Railway visibles
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# App Flask
app = Flask(__name__)
CORS(app)

# Clés d’environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialisation des clients
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Gestion des threads utilisateurs
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# 💾 Mémoire affective
def update_user_memory(user_id, memory_data):
    supabase.table("user_memory").upsert({**memory_data, "user_id": user_id}).execute()

def extract_memory_data(message):
    result = {}
    if "je suis en couple" in message or "je suis célibataire" in message:
        result["situation_amoureuse"] = "couple" if "en couple" in message else "célibataire"
    if "je veux le/la reconquérir" in message:
        result["intention_relationnelle"] = "reconquête"
    if "je cherche l’amour" in message or "je veux trouver quelqu’un" in message:
        result["intention_relationnelle"] = "trouver l’amour"
    for word in message.split():
        if word.istitle() and len(word) <= 12:
            result["prenom_aime"] = word
    return result if result else None

# 📎 Lecture du fichier prompt maître
def load_prompt():
    try:
        with open("IAmour_V6_FINAL_ULTIMATE_LOVABLE++.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Prompt manquant. Merci de vérifier le fichier."

# ✅ Vérification de l’état du backend
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# 🔄 Mise à jour mémoire émotionnelle via frontend
@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.json
    user_id = data.get("user_id")
    memory_data = data.get("memory")
    if user_id and memory_data:
        update_user_memory(user_id, memory_data)
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "user_id or memory missing"}), 400

# 💬 Route principale d’interaction
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")
    is_premium = data.get("is_premium", False)
    preferences = data.get("preferences", {})
    if not user_id or not message:
        return jsonify({"error": "user_id and message required"}), 400

    # Thread et assistant
    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
    thread_id = get_or_create_thread(user_id)

    # 💡 Extraction mémoire
    memory_extracted = extract_memory_data(message)
    if memory_extracted:
        update_user_memory(user_id, memory_extracted)

    # 🔧 Construction des instructions dynamiques
    prompt = load_prompt()
    user_prefs = f"""
Tonalité: {preferences.get('tonalite', 'neutre')}
Intensité émotionnelle: {preferences.get('intensite', 'moyenne')}
Longueur: {preferences.get('longueur', 'moyenne')}
Humeur: {preferences.get('humeur', 'neutre')}
Personnalité IA: {preferences.get('personnalite', 'voix intérieure')}
"""
    instructions = f"### === Début : IAmour_V6_FINAL_ULTIMATE_LOVABLE++.txt === ###\n{prompt}\n\n### === Préférences de l’utilisateur === ###\n{user_prefs}"

    try:
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        # Attente de réponse (max 30s)
        for _ in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        final_message = messages.data[0].content[0].text.value
        return jsonify({"response": final_message}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
