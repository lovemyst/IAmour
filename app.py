from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
from supabase import create_client, Client

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Clés d'environnement
openai.api_key = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

# Connexion à Supabase
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

    # Vérifie si un thread existe déjà pour cet utilisateur
    response = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        thread_id = response.data[0]["thread_id"]
    else:
        # Crée un nouveau thread
        thread = openai.beta.threads.create()
        thread_id = thread.id

        # Enregistre le thread dans Supabase
        supabase.table("threads").insert({
            "user_id": user_id,
            "thread_id": thread_id
        }).execute()

        print(f"Thread créé pour l'utilisateur {user_id}")

    # Envoie le message de l'utilisateur
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Lance l’assistant
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Attend la fin du traitement
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break

    # Récupère la dernière réponse
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    return jsonify({"response": last_message})

if __name__ == '__main__':
    app.run(debug=True)
