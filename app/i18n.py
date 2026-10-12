"""Translation.

The English text is the key. Miss a translation and you get English rather
than a bare identifier, and adding a string to a template needs no second edit
somewhere else.

Interface only. Repo names, descriptions, topics and readme text belong to
whoever wrote them.
"""
from __future__ import annotations

from contextvars import ContextVar

LANGS: dict[str, str] = {"en": "English", "fr": "Français"}
DEFAULT_LANG = "en"
COOKIE = "nullstar_lang"

THEMES = ("light", "dark")
THEME_COOKIE = "nullstar_theme"
DEFAULT_THEME = "light"

# French catalogue. Keys are the exact English source strings.
FR: dict[str, str] = {}


def add(pairs: dict[str, str]) -> None:
    FR.update(pairs)


# -- chrome and navigation ---------------------------------------------------
add({
    "Feed": "Flux",
    "Overlooked": "Signaux faibles",
    "Major publishers": "Éditeurs majeurs",
    "New accounts": "Nouveaux comptes",
    "Saved": "Favoris",
    "Statistics": "Statistiques",
    "Admin": "Administration",
    "Library": "Bibliothèque",
    "Sign in": "Connexion",
    "Join": "Inscription",
    "leave": "déconnexion",
    "Switch to dark": "Passer en thème sombre",
    "Switch to light": "Passer en thème clair",
    "Where to? Or type words to search the wire.":
        "Aller où ? Ou tapez des mots pour chercher.",
    "Cut by craft": "Par domaine",
    "Everything": "Tous les domaines",
    "Shortcuts": "Accès rapides",
    "Nobody has starred it": "Aucune étoile",
    "Landed today": "Arrivés aujourd'hui",
    "Scoring 80 and up": "Score de 80 et plus",
    "From brand new accounts": "Comptes récents",
    "Your views": "Vos filtres",
    "Reading as a guest": "Vous n'êtes pas connecté",
    "Everything here is open. An account only adds what is yours: keeping finds, "
    "hiding noise, notes and saved views.":
        "Tout est consultable librement. Un compte sert à mettre des projets de côté, "
        "masquer ce qui ne vous concerne pas, prendre des notes et enregistrer vos filtres.",
    "Make an account": "Créer un compte",
    "Guest mode": "Mode invité",
    "This account is for whoever runs the instance. Visitors never need one.":
        "Ce compte est celui de la personne qui administre l'instance. Les visiteurs "
        "n'en ont jamais besoin.",
    "An account only adds what is yours: saved projects, collections and notes.":
        "Un compte n'ajoute que ce qui vous appartient : projets mis de côté, "
        "collections et notes.",
})

# -- section headers ----------------------------------------------------------
add({
    "Security projects scoring well on substance that almost nobody has seen: "
    "recently created, five stars or fewer.":
        "Des projets de sécurité solides sur le fond que presque personne n'a vus : "
        "créés récemment, cinq étoiles ou moins.",
    "Recent releases from large technology companies, security vendors, research "
    "labs and national CERTs.":
        "Publications récentes des grands groupes technologiques, des éditeurs de "
        "sécurité, des laboratoires de recherche et des CERT nationaux.",
    "Security code from GitHub accounts opened in the last four months. Uneven by "
    "nature, occasionally excellent.":
        "Du code de sécurité provenant de comptes GitHub ouverts ces quatre derniers "
        "mois. Inégal par nature, parfois excellent.",
    "Everything you set aside to come back to.":
        "Tout ce que vous avez mis de côté pour y revenir.",
})

# -- filter bar ---------------------------------------------------------------
add({
    "order": "tri",
    "since": "période",
    "craft": "domaine",
    "from": "origine",
    "trait": "signal",
    "built in": "langage",
    "at least": "score min",
    "at most": "étoiles max",
    "read": "affichage",
    "any": "tous",
    "anyone": "toutes",
    "any score": "aucun",
    "any stars": "aucune",
    "all of it": "tout",
    "only what is new to me": "non vus seulement",
    "the beginning": "tout l'historique",
    "24h": "24 heures",
    "7d": "7 jours",
    "30d": "30 jours",
    "90d": "90 jours",
    "stars": "étoiles",
    "star": "étoile",
    "find": "résultat",
    "finds": "résultats",
    "start over": "tout réinitialiser",
    "apply": "appliquer",
    "more came in while you were reading. Show them.":
        "nouveaux projets sont arrivés pendant votre lecture. Les afficher.",
    "back": "précédent",
    "onward": "suivant",
    "No results.": "Aucun résultat.",
    "The collector last went out": "Dernière collecte",
    "Widen the window, or start over with the filters.":
        "Élargissez la période, ou réinitialisez les filtres.",
    "Nothing has been gathered yet.": "Rien n'a encore été collecté.",
    "Send the collector out from": "Lancez la collecte depuis",
    "the admin pages": "l'administration",
})

# -- one find -----------------------------------------------------------------
add({
    "by": "par",
    "a day": "par jour",
    "The author left no description.": "L'auteur n'a pas mis de description.",
    "overlooked": "peu visible",
    "major publisher": "éditeur majeur",
    "new account": "compte récent",
    "created today": "créé aujourd'hui",
    "rising fast": "en forte hausse",
    "Open on GitHub": "Ouvrir sur GitHub",
    "Save for later": "Mettre de côté",
    "Remove from saved": "Retirer des favoris",
    "Hide from my feed": "Masquer de mon flux",
    "Sign in to save this": "Connectez-vous pour le mettre de côté",
})

# -- method page --------------------------------------------------------------
add({
    "Method": "Méthode",
    "How ranking works": "Comment le classement fonctionne",
    "Every number on this site comes from the rules below. They are read from the "
    "running configuration, not copied here, so this page cannot drift from what "
    "the collector actually does.":
        "Tous les chiffres de ce site viennent des règles ci-dessous. Elles sont lues "
        "dans la configuration en cours d'exécution, pas recopiées ici, donc cette page "
        "ne peut pas s'écarter de ce que le collecteur fait réellement.",
    "The question the score answers": "La question à laquelle le score répond",
    "If you only had ten minutes today, is this repository worth one of them?":
        "Si vous n'aviez que dix minutes aujourd'hui, ce dépôt en mérite-t-il une ?",
    "That is a different question from the one star counts answer. Sorting by "
    "popularity puts anything published this week at the bottom, which is exactly "
    "the part we are looking for. So relevance and age carry most of the weight "
    "here and popularity is deliberately capped.":
        "Ce n'est pas la question à laquelle répond le nombre d'étoiles. Trier par "
        "popularité place tout ce qui a été publié cette semaine en bas de liste, "
        "c'est-à-dire précisément ce que nous cherchons. La pertinence et l'ancienneté "
        "portent donc l'essentiel du poids, et la popularité est volontairement plafonnée.",
    "What the score is made of": "De quoi le score est composé",
    "maximum": "maximum",
    "points, minus penalties": "points, pénalités déduites",
    "Component": "Composante",
    "Weight": "Poids",
    "What it measures": "Ce qu'elle mesure",
    "default": "par défaut",
    "Relevance": "Pertinence",
    "Freshness": "Fraîcheur",
    "Origin": "Origine",
    "Substance": "Substance",
    "Momentum": "Dynamique",
    "Gem bonus": "Bonus de visibilité",
    "Noise penalty": "Pénalité de bruit",
    "How certain we are that this is security work at all.":
        "À quel point nous sommes certains qu'il s'agit bien de sécurité.",
    "Topics the author set, words in the name and description, and the readme. The "
    "readme counts for about a third of a description hit: a readme mentions plenty "
    "in passing, a description states intent.":
        "Les tags posés par l'auteur, les mots du nom et de la description, et le readme. "
        "Le readme compte pour environ un tiers d'une occurrence en description : un readme "
        "mentionne beaucoup de choses au passage, une description énonce une intention.",
    "How recently the repository appeared.": "À quel point le dépôt est récent.",
    "Two curves. Creation date halves every 21 days, last push halves every 10. "
    "Creation carries roughly two thirds of the weight.":
        "Deux courbes. La date de création est divisée par deux tous les 21 jours, la "
        "dernière activité tous les 10. La création porte environ deux tiers du poids.",
    "Who published it.": "Qui l'a publié.",
    "A curated list of organisations, plus account age and reach for everybody else. "
    "An account opened in the last four months is treated as new rather than unknown.":
        "Une liste d'organisations tenue à la main, puis l'ancienneté et l'audience du "
        "compte pour tous les autres. Un compte ouvert depuis moins de quatre mois est "
        "considéré comme récent plutôt qu'inconnu.",
    "Signs that work went into it.": "Les signes qu'un vrai travail a été fait.",
    "Description length, readme depth, topics, a licence, a homepage, repository size.":
        "Longueur de la description, profondeur du readme, tags, licence, site, taille du dépôt.",
    "Stars per day since creation.": "Étoiles par jour depuis la création.",
    "Compressed on a log scale and capped low on purpose. Without that cap, "
    "popularity would decide everything and nothing new would ever surface.":
        "Compressée sur une échelle logarithmique et plafonnée volontairement bas. Sans ce "
        "plafond, la popularité déciderait de tout et rien de nouveau ne remonterait jamais.",
    "A kicker for work nobody has seen.": "Un coup de pouce pour ce que personne n'a vu.",
    "Applies when relevance is high, the repository is recent and it has five stars "
    "or fewer. Also applies to a brand new account publishing security code.":
        "S'applique quand la pertinence est forte, que le dépôt est récent et qu'il a cinq "
        "étoiles ou moins. S'applique aussi à un compte tout neuf qui publie du code de sécurité.",
    "Subtracted, not added.": "Soustraite, pas ajoutée.",
    "Link collections, course material, forks, archived repositories, and entries "
    "with no description, no topics and no readme.":
        "Listes de liens, supports de cours, forks, dépôts archivés, et entrées sans "
        "description, sans tag et sans readme.",
    "How a project is read as security work":
        "Comment un projet est reconnu comme relevant de la sécurité",
    "There is no model involved. Each domain below carries a vocabulary of topics "
    "and phrases. A match on a topic the author set counts most, a match in the name "
    "or description counts next, a match in the readme counts least. The weight "
    "column is how strongly a hit in that domain argues the repository really is "
    "security work.":
        "Aucun modèle n'intervient. Chaque domaine ci-dessous porte un vocabulaire de tags "
        "et d'expressions. Une correspondance sur un tag posé par l'auteur compte le plus, "
        "une correspondance dans le nom ou la description ensuite, dans le readme le moins. "
        "La colonne de poids indique à quel point une correspondance dans ce domaine plaide "
        "pour qu'il s'agisse vraiment de sécurité.",
    "Domain": "Domaine",
    "Terms": "Termes",
    "What gets marked down": "Ce qui est pénalisé",
    "A penalty is subtracted from the total. These are the patterns that trigger one:":
        "Une pénalité est retranchée du total. Voici les motifs qui en déclenchent une :",
    "Reading lists and collections of links rather than a project":
        "Listes de lecture et collections de liens plutôt qu'un projet",
    "Course material, exercises and write-ups":
        "Supports de cours, exercices et comptes rendus",
    "Forks of somebody else's repository": "Forks du dépôt de quelqu'un d'autre",
    "Archived repositories": "Dépôts archivés",
    "No description, no topics and no readme": "Ni description, ni tag, ni readme",
    "Who published it": "Qui l'a publié",
    "The multiplier applied to the origin component.":
        "Le multiplicateur appliqué à la composante d'origine.",
    "An account nobody has classified still rises with its follower count, so a "
    "researcher we have not listed is not punished for it.":
        "Un compte que personne n'a classé monte quand même avec son nombre d'abonnés, "
        "donc un chercheur que nous n'avons pas répertorié n'en est pas pénalisé.",
    "Where the data comes from": "D'où viennent les données",
    "search": "requêtes de recherche",
    "org": "organisations suivies",
    "starred": "comptes dont on suit les étoiles",
    "user": "comptes suivis",
    "Maximum repository age": "Âge maximum du dépôt",
    "Minimum score to store": "Score minimum pour être gardé",
    "Search lookback": "Profondeur de recherche",
    "days": "jours",
    "A repository created longer ago than the maximum is skipped even if it was "
    "pushed to this morning. The point is work that did not exist last month, not "
    "long-running projects that received a commit.":
        "Un dépôt créé il y a plus longtemps que le maximum est ignoré, même s'il a reçu "
        "un commit ce matin. Ce qui nous intéresse, c'est ce qui n'existait pas le mois "
        "dernier, pas les projets de longue date qui viennent d'être modifiés.",
    "Sorting": "Tri",
    "What this site does not do": "Ce que ce site ne fait pas",
    "No analytics, no third-party script, no content delivery network.":
        "Aucune mesure d'audience, aucun script tiers, aucun CDN.",
    "Repository names, descriptions and readme text are shown as their authors wrote them.":
        "Les noms, descriptions et readme des dépôts sont affichés tels que leurs auteurs les ont écrits.",
    "No ranking is bought, and nobody can pay to appear.":
        "Aucun classement n'est acheté, et personne ne peut payer pour apparaître.",
    "Check it yourself": "Vérifiez par vous-même",
    "Every repository page shows its own arithmetic: each component, the points it "
    "contributed, and the exact terms that matched. If a rank looks wrong, that page "
    "will tell you why it happened.":
        "Chaque page de dépôt affiche son propre calcul : chaque composante, les points "
        "qu'elle a apportés, et les termes exacts qui ont correspondu. Si un classement "
        "paraît faux, cette page vous dira pourquoi.",
    "See the ranking": "Voir le classement",
    "The same rules as JSON": "Les mêmes règles en JSON",
})

# -- page titles --------------------------------------------------------------
add({
    "Account": "Compte",
    "Administration": "Administration",
    "Audit log": "Journal d'audit",
    "Change password": "Changer le mot de passe",
    "Collection runs": "Historique des collectes",
    "Create account": "Créer un compte",
    "Initial setup": "Première configuration",
    "Instance settings": "Réglages de l'instance",
    "Invites": "Invitations",
    "Scoring": "Scoring",
    "Sources": "Sources",
    "Users": "Utilisateurs",
    "Not found": "Introuvable",
})

# -- dropdowns ----------------------------------------------------------------
add({
    "Filter": "Filtrer",
    "Nothing matches": "Aucune correspondance",
})

# -- score bands --------------------------------------------------------------
add({
    "Must see": "À voir",
    "Strong": "Solide",
    "Worth a look": "À regarder",
    "Background": "Secondaire",
})

# -- publisher tiers ----------------------------------------------------------
add({
    "Big Tech": "Géant du web",
    "Security Vendor": "Éditeur sécurité",
    "Research Lab": "Labo de recherche",
    "Government / CERT": "État / CERT",
    "Community Org": "Organisation communautaire",
    "Known Researcher": "Chercheur connu",
    "New Account": "Compte récent",
    "Independent": "Indépendant",
    "Unclassified": "Non classé",
})

# -- domains ------------------------------------------------------------------
add({
    "Exploit Development": "Développement d'exploits",
    "Offensive / Red Team": "Offensif et red team",
    "Malware Analysis": "Analyse de malwares",
    "Reverse Engineering": "Rétro-ingénierie",
    "Detection Engineering": "Ingénierie de détection",
    "Threat Intelligence": "Renseignement sur les menaces",
    "DFIR / Forensics": "Forensique et réponse à incident",
    "Application Security": "Sécurité applicative",
    "Cloud & Container": "Cloud et conteneurs",
    "Network Security": "Sécurité réseau",
    "OSINT & Recon": "OSINT et reconnaissance",
    "Cryptography": "Cryptographie",
    "AI / LLM Security": "Sécurité de l'IA",
    "Supply Chain": "Chaîne d'approvisionnement",
    "Mobile Security": "Sécurité mobile",
    "Hardware / IoT": "Matériel et IoT",
    "Fuzzing & VR": "Fuzzing et recherche de vulnérabilités",
    "Identity & Access": "Identité et accès",
    "Privacy & Anonymity": "Vie privée et anonymat",
    "Security Tooling": "Outillage sécurité",
})

# -- sort options and signals -------------------------------------------------
add({
    "Interest score": "Score d'intérêt",
    "Newest discovery": "Découverte la plus récente",
    "Repo creation date": "Date de création du dépôt",
    "Last push": "Dernière activité",
    "Stars": "Étoiles",
    "Star velocity": "Vitesse d'acquisition d'étoiles",
    "Most underrated": "Les plus sous-cotés",
    "Hidden gem": "Signal faible",
    "Under the radar": "Peu visible",
    "New account": "Compte récent",
    "Major publisher": "Éditeur majeur",
    "Just created": "Créé aujourd'hui",
    "Trending": "En hausse",
    "High relevance": "Très pertinent",
})

# -- repository page --------------------------------------------------------
add({
    "found": "trouvé", "written in": "écrit en",
    "today,": "aujourd'hui,", "when we found it.": "quand nous l'avons trouvé.",
    "Read it on GitHub": "Le lire sur GitHub", "Its own page": "Son site",
    "Keep this": "Garder", "Sign in to keep it": "Se connecter pour le garder",
    "More from": "Plus de",
    "What the author says": "Ce que dit l'auteur",
    "first": "les", "characters of the readme": "premiers caractères du readme",
    "How it earned": "Comment il a obtenu",
    "Created": "Créé", "days ago, last touched": "jours, dernière activité il y a",
    "days ago, gathering": "jours, il gagne",
    "stars a day.": "étoiles par jour.",
    "Lifted for being overlooked:": "Remonté parce qu'il passe inaperçu :",
    "Marked down for:": "Pénalisé pour :",
    "Read as security work because of": "Lu comme un travail de sécurité à cause de",
    "No working shown for this one. Recompute from the workshop.":
        "Aucun détail de calcul pour celui-ci. Recalculez depuis l'atelier.",
    "Your note": "Votre note",
    "What is worth remembering here?": "Qu'est-ce qui mérite d'être retenu ici ?",
    "Save it": "Enregistrer",
    "The numbers": "Les chiffres",
    "Stars": "Étoiles", "Forks": "Forks", "Open issues": "Tickets ouverts",
    "Licence": "Licence", "Size": "Taille", "Last push": "Dernière poussée",
    "Owner followers": "Abonnés du propriétaire", "Owner repos": "Dépôts du propriétaire",
    "Account opened": "Compte ouvert", "none stated": "non précisée", "unknown": "inconnu",
    "How we found it": "Comment nous l'avons trouvé",
    "Tagged by the author": "Étiqueté par l'auteur",
    "What has changed": "Ce qui a changé",
    "Also from": "Aussi de",
})

# -- dashboard --------------------------------------------------------------
add({
    "The shape of it": "Les tendances",
    "What the collector has been pulling in, and from where.":
        "Ce que le collecteur ramène, et d'où.",
    "Held": "En base", "repositories in all": "dépôts au total",
    "This week": "Cette semaine", "newly found": "nouvellement trouvés",
    "Yesterday on": "Depuis hier",
    "Worth the time": "Vaut le temps", "scoring 65 or better": "score 65 ou mieux",
    "Thirty days of arrivals": "Trente jours d'arrivées",
    "busiest day held": "jour le plus chargé",
    "Who is publishing": "Qui publie", "Which craft": "Quelle spécialité",
    "Written in": "Écrit en", "Best of the week": "Le meilleur de la semaine",
    "see them all": "voir tout",
    "Nothing in the last seven days.": "Rien ces sept derniers jours.",
    "The collector": "Le collecteur", "new": "nouveaux",
    "It has not gone out yet.": "Il n'est pas encore sorti.",
    "Movement": "Mouvements", "no description": "aucune description",
})

# -- account ----------------------------------------------------------------
add({
    "Account": "Compte", "Profile": "Profil", "Role": "Rôle",
    "Member since": "Membre depuis", "Last sign-in": "Dernière connexion",
    "Change password": "Changer le mot de passe",
    "Active sessions": "Sessions actives",
    "Address": "Adresse", "Client": "Client", "Started": "Depuis",
    "Last seen": "Vue la dernière fois", "this device": "cet appareil",
    "Revoke": "Révoquer", "API keys": "Clés d'API",
    "Name": "Nom", "Prefix": "Préfixe", "Created": "Créée",
    "Last used": "Dernier usage", "never": "jamais",
    "No API keys yet.": "Aucune clé d'API pour l'instant.",
    "Create key": "Créer une clé",
    "Revoke this API key?": "Révoquer cette clé d'API ?",
    "New API key created, copy it now, it is never shown again.":
        "Nouvelle clé d'API créée. Copiez-la maintenant, elle ne sera plus jamais affichée.",
    "copy key": "copier la clé",
    "Feeds &amp; export": "Flux et export",
    "Any filter from the radar works as a query string here.":
        "N'importe quel filtre du fil fonctionne ici en paramètre d'URL.",
    "Focus search": "Aller à la recherche",
    "Go to radar": "Aller au fil", "Hidden gems": "Trésors enfouis",
    "Dashboard": "Tableau", "Bookmarks": "Gardés",
    "Current password": "Mot de passe actuel",
    "New password": "Nouveau mot de passe",
    "Confirm new password": "Confirmer le nouveau mot de passe",
    "Update password": "Mettre à jour",
    "All other sessions will be signed out.":
        "Toutes vos autres sessions seront déconnectées.",
    "At least 12 characters, mixed case, one digit.":
        "Au moins 12 caractères, majuscules et minuscules, un chiffre.",
    "Your password was set by an administrator. Choose your own before continuing.":
        "Votre mot de passe a été défini par un administrateur. Choisissez le vôtre avant de continuer.",
})

# -- sign in / sign up ------------------------------------------------------
add({
    "Come back in": "Reconnexion",
    "Sign in to find your saved projects, collections and notes.":
        "Connectez-vous pour retrouver vos projets mis de côté, vos collections et vos notes.",
    "Password": "Mot de passe",
    "No account?": "Pas de compte ?", "Make one": "Créez-en un",
    "This instance is closed. Ask whoever runs it for an invitation.":
        "Cette instance est fermée. Demandez une invitation à son administrateur.",
    "Claim it": "Prendre la main",
    "Nobody has an account here yet. The first one made becomes the":
        "Personne n'a encore de compte ici. Le premier créé devient",
    "administrator": "administrateur",
    ", and from then on only that account can let anyone else in.":
        ", et ensuite lui seul peut laisser entrer quelqu'un d'autre.",
    "Pick a name": "Choisissez un nom",
    "Three to thirty two characters. Letters, digits, dash, underscore.":
        "De trois à trente-deux caractères. Lettres, chiffres, tiret, tiret bas.",
    "Twelve characters at least, with an upper case, a lower case and a digit.":
        "Douze caractères au minimum, avec une majuscule, une minuscule et un chiffre.",
    "Twelve characters at least, mixed case, one digit.":
        "Douze caractères au minimum, majuscules et minuscules, un chiffre.",
    "Once more": "Encore une fois",
    "Take the keys": "Prendre les clés",
    "Make an account": "Créer un compte",
    "You are using an invitation.": "Vous utilisez une invitation.",
    "A name and a password. That is all we ask.":
        "Un nom et un mot de passe. C'est tout ce que nous demandons.",
    "This instance only takes people who were invited.":
        "Cette instance n'accepte que les personnes invitées.",
    "Back to sign in": "Retour à la connexion",
    "Make it": "Créer",
    "Already have one?": "Vous en avez déjà un ?",
    "Somebody shipped it this morning.": "Quelqu'un l'a publié ce matin.",
    "Nobody has seen it yet.": "Personne ne l'a encore vu.",
    "Every other way of finding code ranks by how many people already know about it, "
    "which buries anything published today. This one ranks by what the work is and how "
    "new it is, so a proof of concept with no stars, from an account opened last week, "
    "sits above a framework with forty thousand.":
        "Partout ailleurs, le code est classé selon le nombre de gens qui le connaissent "
        "déjà, ce qui enterre tout ce qui naît aujourd'hui. Ici le classement tient à la "
        "nature du travail et à sa nouveauté : une preuve de concept sans étoile, publiée "
        "par un compte ouvert la semaine dernière, passe devant un framework à quarante mille.",
    "unauthenticated remote code execution, with a working proof":
        "exécution de code à distance sans authentification, avec preuve fonctionnelle",
    "signed driver abused to hand out kernel privileges":
        "pilote signé détourné pour accorder les privilèges noyau",
    "offensive toolkit, written from scratch, first commit today":
        "boîte à outils offensive, écrite de zéro, premier commit aujourd'hui",
    "vendor lab releases its internal tooling":
        "un laboratoire éditeur publie son outillage interne",
    "no stars": "aucune étoile",
    "Back to the wire": "Retour au fil",
})


# -- library, collections, sharing ------------------------------------------
add({
    "Library": "Bibliothèque",
    "Your library": "Votre bibliothèque",
    "What you kept, how you filed it, and whose work you follow.":
        "Ce que vous avez gardé, comment vous l'avez classé, et qui vous suivez.",
    "Collections": "Collections",
    "folders of your own": "vos propres dossiers",
    "Unfiled": "Non classés",
    "kept but in no folder": "gardés mais dans aucun dossier",
    "Notes": "Notes",
    "things you wrote down": "choses que vous avez notées",
    "A find can sit in several.": "Une trouvaille peut être dans plusieurs.",
    "No collections yet. Make one and start filing.":
        "Aucune collection pour l'instant. Créez-en une et commencez à classer.",
    "Following": "Suivis",
    "Their new work is flagged in the wire.":
        "Leurs nouveautés sont signalées dans le fil.",
    "Follow the people whose work you never want to miss.":
        "Suivez les gens dont vous ne voulez jamais rater le travail.",
    "A GitHub account, for instance trailofbits":
        "Un compte GitHub, par exemple trailofbits",
    "Follow": "Suivre",
    "Stop following": "Ne plus suivre",
    "New collection": "Nouvelle collection",
    "What goes in it": "Ce qu'on y met",
    "Optional": "Facultatif",
    "For instance: to try this weekend": "Par exemple : à tester ce week-end",
    "Colour": "Couleur",
    "shared": "partagée",
    "shared by link": "partagée par lien",
    "Shared by link": "Partagée par lien",
    "Anybody with this link can read it": "Toute personne avec ce lien peut la lire",
    "copy link": "copier le lien",
    "new link": "nouveau lien",
    "Make a new link and kill the old one?":
        "Créer un nouveau lien et désactiver l'ancien ?",
    "in here": "dedans",
    "Share by link": "Partager par lien",
    "Stop sharing": "Ne plus partager",
    "Delete": "Supprimer",
    "Delete this collection? The repositories stay in your library.":
        "Supprimer cette collection ? Les dépôts restent dans votre bibliothèque.",
    "Why did you file this?": "Pourquoi l'avoir classé ici ?",
    "save": "enregistrer",
    "Nothing filed here yet.": "Rien de classé ici pour l'instant.",
    "Open any find and file it from its page, or from the wire.":
        "Ouvrez une trouvaille et classez-la depuis sa page, ou depuis le fil.",
    "Rename or recolour": "Renommer ou recolorer",
    "Save": "Enregistrer",
    "File it under": "Classer dans",
    "A collection shared by": "Une collection partagée par",
    "See the wire": "Voir le fil",
    "Nullstar watches GitHub for new security work and ranks it by what it is, "
    "not by how many people already know about it.":
        "Nullstar surveille GitHub à la recherche de nouveaux travaux de sécurité et les "
        "classe selon ce qu'ils sont, pas selon le nombre de gens qui les connaissent déjà.",
    "Order added": "Ordre d'ajout",
    "My own order": "Mon propre ordre",
    "Interest score": "Score d'intérêt",
    "Repository age": "Âge du dépôt",
})


def normalise(code: str | None) -> str:
    code = (code or "").strip().lower()[:5]
    if code in LANGS:
        return code
    if code[:2] in LANGS:
        return code[:2]
    return DEFAULT_LANG


def pick(request, user=None) -> str:
    """A choice beats the account, which beats the browser."""
    cookie = request.cookies.get(COOKIE)
    if cookie and normalise(cookie) == cookie.strip().lower()[:2]:
        if cookie.strip().lower()[:2] in LANGS:
            return cookie.strip().lower()[:2]
    stored = (getattr(user, "prefs", None) or {}).get("lang") if user else None
    if stored and stored in LANGS:
        return stored
    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        code = normalise(part.split(";")[0])
        if code != DEFAULT_LANG or part.strip().lower().startswith("en"):
            return code
    return DEFAULT_LANG


AGO = {
    "fr": {
        "never": "jamais", "just now": "à l'instant", "future": "à venir",
        "m": "il y a {n} min", "h": "il y a {n} h", "d": "il y a {n} j",
        "mo": "il y a {n} mois", "y": "il y a {n} ans",
    },
    "en": {
        "never": "never", "just now": "just now", "future": "in the future",
        "m": "{n}m ago", "h": "{n}h ago", "d": "{n}d ago",
        "mo": "{n}mo ago", "y": "{n}y ago",
    },
}


# Macros imported with {% from %} do not see the calling context, and the live
# stream renders them with no request at all. Both still need the language, so
# it rides along here instead of through the template context.
current_lang: ContextVar[str] = ContextVar("nullstar_lang", default=DEFAULT_LANG)


def ago_words(lang: str | None = None) -> dict:
    return AGO.get(lang or current_lang.get(), AGO["en"])


def translate(text: str, lang: str) -> str:
    if lang == "fr":
        return FR.get(text, text)
    return text


def translator(lang: str):
    """What the templates get as `t`."""
    def t(text: str, **kwargs) -> str:
        out = translate(text, lang)
        return out.format(**kwargs) if kwargs else out

    return t


def normalise_theme(code: str | None) -> str:
    code = (code or "").strip().lower()
    return code if code in THEMES else DEFAULT_THEME


def pick_theme(request, user=None) -> str:
    """A choice beats the account, which beats light.

    Worked out server side and written onto the html tag, so the page does not
    paint light and then jump to dark the way a localStorage toggle does.
    """
    cookie = request.cookies.get(THEME_COOKIE)
    if cookie in THEMES:
        return cookie
    stored = (getattr(user, "prefs", None) or {}).get("theme") if user else None
    if stored in THEMES:
        return stored
    return DEFAULT_THEME
