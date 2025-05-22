# Force rebuild - 17h10
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Clés d'environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
VECTOR_STORE_ID_FREE = os.getenv("VECTOR_STORE_ID_FREE")
VECTOR_STORE_ID_PREMIUM = os.getenv("VECTOR_STORE_ID_PREMIUM")

# Connexion OpenAI et Supabase
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")
    is_premium = data.get("isPremium", False)

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
    vector_store_id = VECTOR_STORE_ID_PREMIUM if is_premium else VECTOR_STORE_ID_FREE

    # Vérifie si un thread existe déjà pour cet utilisateur
    response = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        thread_id = response.data[0]["thread_id"]
    else:
        # Crée un nouveau thread
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Enregistre le thread dans Supabase
        supabase.table("threads").insert({
            "user_id": user_id,
            "thread_id": thread_id
        }).execute()

        # Amorçage style IAmour
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content="Active ton style IAmour : 🗨️ puis 💬, complice, humain, jamais robot. Utilise tes fichiers uniquement si c’est pertinent."
        )

    # Message utilisateur
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Lancer assistant avec file search spécifique
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        tool_resources={
            "file_search": {
                "vector_store_ids": [vector_store_id]
            }
        }
    )

    # Attente du résultat
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "L'assistant a échoué."}), 500
        time.sleep(1)
        attempts += 1

    if attempts == max_attempts:
        return jsonify({"error": "Temps d’attente dépassé."}), 504

    # Récupérer la réponse
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    return jsonify({"response": last_message})

# Exécution locale
if __name__ == '__main__':
    if os.getenv("RAILWAY_ENVIRONMENT") is None:
        app.run(debug=True)
