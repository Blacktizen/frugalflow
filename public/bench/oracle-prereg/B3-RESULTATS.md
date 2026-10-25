# B3 pre-enregistre : resultats (night run, mesure du 25/10/2026, 02:18 a 02:38)

Pre-enregistrement : `B3-PREREG.md` (commit 385d0dd, avant toute mesure). Deviations : `B3-DEVIATIONS.md` (D1 a D5).
Moyen unique : the local model (qwen3.8-flash-next IQ3_XXS, effort medium). Aucun appel DeepSeek.

## Verdict selon le pre-enregistrement (lu par `report.py`, sans jugement)
**UTILE PROUVE**, au seuil exact et avec une reserve forte (voir "Fragilite").

| Metrique | Valeur | Seuil pre-enregistre |
|---|---|---|
| Taches valides / essais | 30 / 120 (4 rondes completes) | 30 taches, 4 reps |
| Annonces GREEN au 1er essai | 120 / 120 (0 RED, 0 sans annonce) | - |
| Faux verts C0 (GREEN + oracle rouge) | 12 / 120 = 10,0 % | >= 10 % |
| IC95 Wilson du taux | 5,8 % a 16,7 % | borne basse >= 5 % |
| 1re reponse qui passe l oracle (R0) | 90,0 % | - |
| Resolus en 3 essais au plus (R1) | 100 % (tous au 2e essai au plus) | echec C1 <= 2 % |
| Livraisons fausses avec l oracle (FG1) | 0 / 120 | - |
| Jetons C0 (1res reponses) / C1 (tout) | 228 853 / 254 957 | rapport <= 2,0 |
| Rapport de jetons C1 / C0 | 1,11 | <= 2,0 |
| Jetons par livraison correcte | 2 119 (C0) / 2 125 (C1) | - |
| Infra | 0 | - |

Duree de la mesure : 20 minutes pour 120 essais et 12 reprises. Jetons du modele local : 255 k pour la mesure ; environ 0,35 M
pour fabriquer le jeu (58 generations) et les 3 outils. Cout en dollars : 0.

## Ce qui produit les faux verts (par tache)
12 faux verts sur 5 taches seulement ; 25 taches : 0 faux vert sur 100 essais.
- t16 `parse_ranges` : 4 / 4. L oracle attend `ValueError` pour des espaces a l interieur d un intervalle ("1 - 3") ; l enonce dit seulement "espaces autour des elements permis". Oracle plausiblement trop strict.
- t20 `human_join` : 3 / 4. Le modele ecrit "a, b and c" au lieu de "a, b, and c" : l enonce est clair, vraie erreur du modele.
- t07 `flatten` : 2 / 4. Le modele rend `{'': {}}` pour un dict vide de premier niveau ; l enonce ne tranche pas ce cas. Oracle discutable.
- t19 `title_case` : 2 / 4. Petits mots dans les composes avec trait d union : vraie erreur, regle claire.
- t31 `normalize_path` : 1 / 4. `../../foo` ecrase en `foo` : vraie erreur.

## Fragilite (analyse apres coup, NON pre-enregistree, a lire comme telle)
- 12 / 120 = 10,0 % pile : le seuil est atteint sans marge. Un seul faux vert de moins aurait donne NON PROUVE.
- Les essais d une meme tache ne sont pas independants (4 essais par tache, 4 taches concentrent 11 faux verts sur 12). L IC de Wilson suppose l independance ; au niveau des taches, 5 / 30 = 16,7 % ont au moins un faux vert, et la borne basse reelle est plus large que 5,8 %.
- Si l on retire les deux taches dont l oracle est discutable (t16, puis t07), le meme script rend NON PROUVE : 8 / 116 = 6,9 % (IC 3,5 a 13,0), puis 6 / 112 = 5,4 % (IC 2,5 a 11,2). Je ne le retiens pas comme verdict (retirer apres coup est exactement ce que le pre-enregistrement interdit), mais il montre que le "utile prouve" repose sur deux oracles trop stricts.
- Ce qui tient dans tous les cas : quand le modele annonce GREEN a tort, l oracle le rattrape a chaque fois (12 / 12) au deuxieme essai, pour 11 % de jetons en plus. Le modele n annonce jamais RED (120 / 120 GREEN) : son annonce ne porte aucune information, donc la croire (C0) livre 7 a 10 % de code faux sur ce jeu.

## Limites
- Un seul modele, un seul quantifie, un jeu de 30 petites fonctions ecrites par un modele (les oracles aussi, controles seulement par le garde de validite : naive rouge, reference verte). Deux oracles sur trente sont plausiblement plus stricts que l enonce.
- Jeu en deux temps : 5 taches sur 35 exclues avant mesure, 3 generations au lieu de 2 (D1) pour atteindre 30.
- Le lanceur est celui du modele local tel que livre (4 autotests sur 5 verts a la mesure, D3 ; 5 sur 5 apres correction du faux delegue de l autotest, D6) et l enveloppe `delegate_wrap.py` corrige la lecture des jetons (D4). `report.py` et le lanceur sont dans le depot ; le verdict est rejouable.
- C1 est la boucle du lanceur (oracle + sortie renvoyee, 3 essais), pas un appel de `delegate.py --verify` lui-meme ; meme logique, pas le meme code.
- "Utile" signifie ici : ca attrape les faux verts a bas prix. Ca ne dit rien d un modele plus fort ni de taches plus grosses.

## Rejouer
```bash
R=public/bench/oracle-prereg
FRUGAL_REAL_DELEGATE=/path/to/your/delegate.py python3 $R/runner.py.partiel.py run --tasks $R/tasks \
  --ids $(ls $R/tasks | paste -sd, -) --reps 4 --out results.jsonl --delegate $R/delegate_wrap.py
python3 $R/report.py report --results results.jsonl --ids $(ls $R/tasks | paste -sd, -)
```
(L enveloppe attend un delegue dont la ligne de jetons est de la forme `[qwen ... tokens]` sur la sortie d erreur.)

## Ligne README proposee (non fusionnee)
> Oracle externe : sur 30 petites taches de code pre-enregistrees, le modele local annonce "tests verts" a tort 10 % du temps (12 / 120) ; l oracle le rattrape a chaque fois pour 11 % de jetons en plus. Le seuil est atteint sans marge et tient a deux oracles discutables : a lire comme "peu cher, plausiblement utile", pas comme "prouve".
