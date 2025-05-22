# Utilise une image Python légère
FROM python:3.11-slim

# Dossier de travail
WORKDIR /app

# Installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Lancer le serveur Flask via Gunicorn
CMD ["gunicorn", "app:app"]
