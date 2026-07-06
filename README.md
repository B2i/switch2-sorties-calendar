# Calendrier automatique des sorties Nintendo Switch / Switch 2

Ce dépôt contient un script qui scrape régulièrement quelques sites de
précommandes (alertetgo.com, chocobonplan.com) et met à jour un fichier
`sorties_switch2.ics`. Ce fichier peut ensuite être suivi par Google Agenda
(ou tout autre client compatible) via un abonnement par URL, qui se
rafraîchit tout seul toutes les 12-24h.

## Mise en place (une seule fois)

1. **Crée un nouveau dépôt GitHub**, public (nécessaire pour que l'URL brute
   soit accessible sans authentification) :
   - Va sur https://github.com/new
   - Choisis un nom, par exemple `switch-calendar`
   - Coche "Public"
   - Clique sur "Create repository"

2. **Envoie les fichiers de ce dossier dans le dépôt.**
   Deux façons de faire :

   **a) Via l'interface web GitHub (le plus simple, sans rien installer) :**
   - Sur la page du nouveau dépôt, clique sur "uploading an existing file"
   - Glisse-dépose tous les fichiers de ce dossier (en conservant la structure
     `.github/workflows/update-calendar.yml`)
   - Valide avec "Commit changes"

   **b) Via git en ligne de commande :**
   ```bash
   cd switch-calendar
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/TON_PSEUDO/switch-calendar.git
   git push -u origin main
   ```

3. **Vérifie que l'Action tourne bien.**
   - Va dans l'onglet "Actions" de ton dépôt GitHub
   - Tu dois voir le workflow "Mise à jour du calendrier Switch"
   - Clique dessus puis sur "Run workflow" pour le tester manuellement tout
     de suite (au lieu d'attendre le lundi suivant)
   - Vérifie que ça se termine en vert ✅. Si ça échoue (rouge ❌), ouvre le
     log pour voir l'erreur — la structure HTML d'un des sites scrapés a pu
     changer, ce qui demandera d'ajuster `scrape.py`

4. **Récupère l'URL brute du fichier ICS :**
   ```
   https://raw.githubusercontent.com/TON_PSEUDO/switch-calendar/main/sorties_switch2.ics
   ```

5. **Abonne Google Agenda à cette URL :**
   - Va sur https://calendar.google.com sur ordinateur (pas possible depuis
     l'app mobile)
   - Clique sur l'icône ⚙️ Paramètres > "Ajouter un agenda" > "À partir de
     l'URL"
   - Colle l'URL brute ci-dessus
   - Clique sur "Ajouter l'agenda"

Google Agenda revérifiera cette URL automatiquement toutes les 12 à 24h. À
chaque fois que l'Action GitHub tourne (chaque lundi) et détecte de
nouvelles sorties, elles apparaîtront automatiquement dans ton agenda, sans
aucune manipulation de ta part.

## Fonctionnement du scraper

- `scrape.py` relit d'abord le fichier `.ics` existant pour ne **jamais rien
  écraser** : il ajoute uniquement les nouvelles sorties détectées.
- Il essaie d'extraire un titre de jeu et une date depuis le texte visible
  de chaque page (regex sur les formats `JJ/MM/AAAA` et `JJ mois AAAA`).
- Chaque source est protégée par un `try/except` : si un site est
  inaccessible ou a changé de structure, les autres sources continuent de
  fonctionner normalement.

## Limites connues

- **Ce scraper est un best-effort.** Il n'a pas pu être testé en conditions
  réelles avant la mise en place (accès réseau restreint côté génération).
  La première exécution ("Run workflow" manuel) permettra de voir s'il
  détecte correctement les sorties ou s'il faut ajuster les sélecteurs dans
  `scrape.py`.
- Les nouvelles sorties ajoutées automatiquement n'ont pas d'emoji
  spécifique au jeu (seulement 🎮) — tu peux les éditer à la main dans le
  fichier si tu veux les personnaliser, le scraper ne les touchera plus
  ensuite (il ne modifie jamais un événement déjà présent).
- Si un site change complètement son gabarit HTML, le scraper peut ne plus
  rien détecter pour cette source (mais ne cassera pas le fichier existant).

## Ajuster la fréquence

Pour changer la fréquence de mise à jour, modifie la ligne `cron` dans
`.github/workflows/update-calendar.yml`. Par exemple pour tous les jours à
6h UTC : `0 6 * * *`.
