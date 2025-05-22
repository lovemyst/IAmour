# Utilise une image Python officielle
FROM python:3.11-slim

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie les fichiers de l'application dans le conteneur
COPY . /app

# Met à jour pip et installe les dépendances uniquement depuis requirements.txt
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Expose le port utilisé par l'app Flask
EXPOSE 8080

# Commande pour démarrer l'application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
