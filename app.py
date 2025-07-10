from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# 🔐 Clés et clients
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Récupérer ou créer un thread utilisateur
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    thread = client.beta.threads.create()
    supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
    return thread.id

# 🔍 Extraire une mémoire simple à partir du message
def extract_memory_from_message(message):
    memory = {}
    if "prénom" in message.lower():
        memory["prenom_aime"] = message.split("prénom")[1].split()[0]
    if "rupture" in message.lower():
        memory["situation_amoureuse"] = "rupture"
    return memory

# 💬 Route principale de chat
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")
    preferences = data.get("preferences", {})
    premium = data.get("premium", False)

    if not user_id or not message:
        return jsonify({"error": "user_id and message required"}), 400

    thread_id = get_or_create_thread(user_id)

    # Ajout du message utilisateur
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    # Mémoire émotionnelle
    memory_data = extract_memory_from_message(message)
    for key, value in memory_data.items():
        supabase.table("user_memory").upsert({
            "user_id": user_id,
            "key": key,
            "value": value
        }).execute()

    # Assistant utilisé
    assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE

    # Instructions dynamiques (préférences Lovable)
    instructions = f"""
Tu es IAmour, l’IA émotionnelle.
Personnalité : {preferences.get("personnalite", "")}
Tonalité : {preferences.get("tonalite", "")}
Intensité : {preferences.get("intensite", "")}
Longueur : {preferences.get("longueur", "")}
Humeur : {preferences.get("humeur", "")}
Adapte-toi avec sensibilité et profondeur.
"""

    # Lancer le run
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        instructions=instructions
    )

    # Attente de réponse
    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        time.sleep(1)

    if run_status.status != "completed":
        return jsonify({"error": f"Run failed: {run_status.status}"}), 500

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last = next((m for m in reversed(messages.data) if m.role == "assistant"), None)

    return jsonify({
        "response": last.content[0].text.value if last else "Aucune réponse générée"
    })

# 🧠 Mémoire manuelle
@app.route("/update_memory", methods=["POST"])
def update_memory():
    data = request.json
    user_id = data.get("user_id")
    key = data.get("key")
    value = data.get("value")
    if not user_id or not key or not value:
        return jsonify({"error": "Champs manquants"}), 400
    supabase.table("user_memory").upsert({
        "user_id": user_id,
        "key": key,
        "value": value
    }).execute()
    return jsonify({"success": True})

# ✅ Ping health
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200
