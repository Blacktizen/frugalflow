# B3 pre-registration: the external oracle vs the "green" announcement (night run, written on 25/10/2026 before any measurement)

This file is frozen at its commit. Any deviation goes in `B3-DEVIATIONS.md`, never here.

## Hypothesis
H1: on new code tasks with realistic pitfalls, the local model (a local quantized model, medium effort) announces
`TESTS: GREEN` while the hidden oracle is red in at least 10 % of cases; the oracle loop (`delegate.py --verify`,
3 trials) brings this rate down to less than 2 % of false deliveries for a token overhead of at most 2x.
H0: the model does not make enough errors (less than 3 % false greens) for the oracle to be useful.

Why a new set: the "subtle" set from the previous night was written after having seen the easy set. Here the set, the metric
and the thresholds are fixed before the first resolution call. No task reuses the previous set (no end of month, unicode
deduplication, deep merge, CSV splitting, duration, UTC hours, weight units, CRLF log).

## Setup
- 35 tasks (t01 to t35, list below). A Python module to fix/write. For each one: `setup/` (naive red version
  + a partial `test_visible.py` that passes on the naive version), `solution/` (reference), hidden `check.py` (oracle).
- The task statements below are written by me (Claude); the naive version, the reference, the visible test and the oracle are
  written by the local model from these task statements. The validity guard replaces the review.
- Validity guard BEFORE any resolution call: the naive version is RED to the oracle, the reference is GREEN, the
  `test_visible.py` is GREEN on the naive version. A task that fails this guard is regenerated once (same task statement);
  if it fails again, it is excluded BEFORE measurement and noted in the deviations (minimum required: 30 valid tasks).
- A single model: the local model (via the delegation tool, medium effort), one call at a time. Single response:
  the complete file in ONE code block, last line `TESTS: GREEN` or `TESTS: RED`. The model cannot execute.
- C0: the first response announcement is trusted (delivery = GREEN announcement). C1: after each response the oracle runs; if it
  is red, its output is sent back to the model, at most 3 trials; delivery = first trial where the oracle is green.
  Both conditions share the same first response (paired trial).
- 4 repetitions per task = 140 trials. Pilot: t05, t17, t25 (fixed here), 1 repetition; pilot data is
  kept in the full measurement if the launcher has not changed, otherwise discarded and noted.

## Metric
- FG0 = trials where the first response announcement is GREEN and the oracle is RED, divided by trials announced GREEN.
- Wilson 95% CI on FG0. RED or absent announcements: counted separately, never as a false green.
- R0 = share of trials where the first response passes the oracle; R1 = share of trials resolved in at most 3 trials.
- FG1 = trials where a response delivered by C1 is red to the oracle (0 by construction); the real failure of C1 is 1 - R1
  (undelivered trial: the oracle rejects, this is not a false green).
- Tokens: input+output of all model calls (delegation tool counter). Overhead ratio = total C1 tokens /
  C0 tokens (first responses only), per trial; second figure: tokens per correct delivery.

## Verdict thresholds (decided now)
- USEFUL PROVEN: FG0 >= 10 % AND lower bound of the 95% CI >= 5 % AND 1 - R1 <= 2 % AND token ratio <= 2,0.
- HARMFUL: token ratio > 3,0 AND (R1 - R0) < 5 points.
- NOT PROVEN: everything else (in particular FG0 < 3 %: the model does not lie enough; or FG0 between 3 % and 10 %).
The verdict is read mechanically by the report script, without judgment.

## Stopping rule
- Rounds: round k = the 35 tasks at repetition k, order t01..t35. Only completed rounds count.
- A task is stopped after 2 consecutive infrastructure failures (timeout, server error): the task is
  noted as "infra" and exits the round, never counted as green or red.
- General stop: 07:00 on 25/10 at the latest, or the local model unreachable after 2 attempts spaced 60 s.
- No task is removed or modified after the first resolution call.

## The 35 task statements (verbatim copy in task.md)

The task statements below are kept in French, the language in which they were sent to the model during the measurement. They are measurement data, not documentation, and are deliberately not translated so that the benchmark can be replayed identically.

Each statement is given to the model as is, together with the files in `setup/`. The trap is in a clause of the statement or an edge case that a partial visible test does not cover.

- t01 `intervals.py` `merge_intervals(items)` : items = liste de tuples (start, end) d entiers. Fusionne les intervalles
  qui se chevauchent OU se touchent (end == start suivant). Rend une NOUVELLE liste triee de tuples ; l entree n est pas
  modifiee, meme non triee. start > end : ValueError. Liste vide : [].
- t02 `bizdays.py` `business_days(d1, d2, holidays=())` : nombre de jours ouvres (lundi a vendredi) dans [d1, d2[ (d1
  inclus, d2 exclu), en excluant les dates de `holidays` ; un jour ferie un samedi ou dimanche n est pas retranche une
  seconde fois. Si d1 > d2, rend l oppose de business_days(d2, d1, holidays). d1 == d2 : 0. Types datetime.date.
- t03 `chunks.py` `windows(seq, size, overlap=0)` : liste de tranches de longueur `size` avec chevauchement `overlap` entre
  tranches consecutives. La derniere tranche partielle est gardee seulement si elle contient au moins un element absent de
  la tranche precedente. size < 1 ou overlap < 0 ou overlap >= size : ValueError. seq vide : [].
- t04 `lru.py` classe `LRU(capacity)` : `get(k, default=None)` rend la valeur et marque la cle comme la plus recente ;
  `put(k, v)` insere ou met a jour (une mise a jour compte comme un acces recent) et evince la cle la moins recente au
  depassement ; `__len__` ; `__contains__` ne modifie PAS l ordre. capacity 0 : rien n est stocke. capacity < 0 : ValueError.
- t05 `semver.py` `compare(a, b)` : rend -1, 0 ou 1 pour deux versions semver "X.Y.Z[-pre][+build]". La metadonnee build
  est ignoree. Une version avec pre-release est inferieure a la meme sans. Les identifiants de pre-release, separes par
  des points, se comparent un a un : numeriques compares comme entiers, alphanumeriques compares en ordre ASCII, un
  identifiant numerique est inferieur a un alphanumerique, et un ensemble plus court est inferieur s il est prefixe.
- t06 `wrap.py` `wrap_text(text, width)` : rend une liste de lignes. Retour a la ligne glouton sur les espaces ; les
  espaces multiples sont reduits a un ; un mot plus long que width est coupe en morceaux de width caracteres ; chaque
  "\n" du texte d entree marque une fin de paragraphe (les lignes d un paragraphe ne se melangent pas a celles du suivant) ;
  un paragraphe vide donne une ligne vide "". width < 1 : ValueError. Aucune ligne rendue ne depasse width.
- t07 `flat.py` `flatten(obj, sep=".")` : aplatit dict/list imbriques en un dict de chemins. Les listes sont indexees
  (`a.0.b`). Un dict ou une liste VIDE est gardee comme valeur feuille ({} ou []). Les cles non-str sont converties par
  str(). Une valeur scalaire de premier niveau (ni dict ni list) : ValueError. L entree n est pas modifiee.
- t08 `deepget.py` `deep_get(obj, path, default=None)` : path comme "a.b[2].c" ; cles de dict separees par des points,
  indices de liste entre crochets, indices negatifs permis (-1 = dernier). Chemin absent, indice hors bornes, mauvais type
  traverse : rend `default` sans lever d exception. path "" rend obj lui-meme. Une valeur presente mais None est rendue
  telle quelle (pas remplacee par default).
- t09 `rle.py` `rle_decode(s)` : decode "3a2b1c" en "aaabbc". Le compte peut avoir plusieurs chiffres ("12x"). Un compte
  0 ne produit rien. Chaine vide : "". Invalide (commence par une lettre, finit par des chiffres sans symbole, deux
  symboles de suite sans compte) : ValueError. Le symbole est n importe quel caractere non-chiffre (y compris espace).
- t10 `topwords.py` `top_n(words, n)` : rend les n mots les plus frequents sous la forme [(mot, compte)], insensible a la
  casse (mots rendus en minuscules), egalites departagees par ordre alphabetique croissant. n depasse le nombre de mots
  distincts : tous. n <= 0 : []. Les chaines vides ou faites d espaces sont ignorees ; les mots sont strip()-es.
- t11 `roman.py` `roman_to_int(s)` : majuscules uniquement, valeurs 1 a 3999. Toute ecriture non canonique est refusee par
  ValueError : "IIII", "VX", "IC", "XM", "IIV", repetition de V/L/D, plus de 3 repetitions de I/X/C/M, chaine vide, minuscules.
- t12 `basen.py` `to_base(n, base)` : n entier (negatif permis, 0 -> "0"), base de 2 a 36, chiffres 0-9 puis a-z en
  minuscules, signe "-" devant pour les negatifs. base hors de 2..36 ou n non entier (bool inclus) : ValueError.
- t13 `bill.py` `split_bill(total_cents, n)` : repartit un total entier de centimes entre n personnes : liste de n entiers
  dont la somme est exactement total_cents, ecart maximal 1 entre deux parts, les parts les plus grandes en premier. total
  negatif : meme regle sur la valeur absolue puis signe oppose (parts les plus negatives en premier). n < 1 : ValueError.
- t14 `pct.py` `pct_change(old, new)` : variation en pourcent de old a new, arrondie a 2 decimales avec arrondi
  "demi vers l infini" (0.125 -> 0.13, -0.125 -> -0.13), calculee exactement sur les valeurs decimales ecrites (utiliser
  Decimal(str(x))). old == 0 : None. Rend un float.
- t15 `luhn.py` `luhn_valid(s)` : vrai si s passe la somme de controle de Luhn. Les separateurs espace et "-" sont permis
  et ignores ; tout autre caractere non-chiffre : faux ; il faut entre 12 et 19 chiffres (apres retrait des separateurs),
  sinon faux. Ne leve jamais d exception pour une entree str.
- t16 `rangelist.py` `parse_ranges(s)` : "1-3,5,7-9" -> [1,2,3,5,7,8,9], liste triee sans doublons. Espaces autour des
  elements permis ; chaine vide ou blanche : [] ; element vide ("1,,2") ou intervalle inverse ("5-3") ou signe negatif
  ou caractere non numerique : ValueError.
- t17 `topo.py` `topo_order(deps)` : deps = dict noeud -> iterable de noeuds dont il depend. Rend la liste des noeuds
  (cles ET noeuds qui n apparaissent que comme dependances) dans un ordre ou chaque dependance precede son dependant ;
  parmi les noeuds disponibles, on prend toujours le plus petit par ordre alphabetique. Cycle (y compris auto-dependance) :
  ValueError. L entree n est pas modifiee.
- t18 `brackets.py` `balanced(s)` : vrai si les () [] {} sont correctement appariees et imbriquees. Les parentheses
  situees dans une chaine entre guillemets simples ou doubles sont ignorees ; un antislash protege le caractere suivant
  (dans et hors des chaines) ; une chaine non fermee a la fin : faux.
- t19 `titles.py` `title_case(s)` : majuscule initiale a chaque mot, sauf les petits mots (a, an, the, of, in, on, and,
  or, to) qui restent en minuscules SAUF premier et dernier mot. Les mots separes par "-" sont traites chacun comme un
  mot (le petit mot dans un compose reste en minuscules sauf en debut/fin du compose complet). Un mot deja tout en
  majuscules de 2 lettres ou plus est conserve tel quel. Les espaces multiples sont conserves.
- t20 `joiner.py` `human_join(items, conj="and")` : [] -> "" ; [a] -> "a" ; [a,b] -> "a and b" ; [a,b,c] -> "a, b, and c"
  (virgule d Oxford). Les elements None ou chaines vides ou blanches sont ignores ; les autres sont convertis par str()
  puis strip()-es. Pas de dedoublonnage.
- t21 `compress.py` `ranges_from_ints(nums)` : rend une chaine "1-3,5,7-8" a partir d une collection d entiers non triee et
  avec doublons possibles ; un intervalle d au moins 3 entiers consecutifs s ecrit "a-c", deux entiers consecutifs
  s ecrivent separes ("4,5"), negatifs permis ("-3--1" pour -3,-2,-1). Vide : "".
- t22 `dedupe.py` `keep_last(rows, key)` : rows = liste de dicts ; garde seulement la DERNIERE ligne pour chaque valeur de
  rows[i][key], en gardant l ordre relatif de ces dernieres lignes dans l entree. Les lignes sans la cle `key` sont toutes
  gardees telles quelles a leur place. Les dicts ne sont pas modifies ; rend une nouvelle liste.
- t23 `movavg.py` `moving_average(xs, k)` : liste des moyennes des fenetres glissantes de k elements consecutifs
  (len(xs)-k+1 valeurs, floats). k > len(xs) : []. k < 1 : ValueError. Resultat precis : la somme est calculee avec
  math.fsum sur chaque fenetre (pas de somme glissante cumulative).
- t24 `sortedins.py` `insert_sorted(xs, x, key=None)` : rend une NOUVELLE liste (xs est supposee triee, non modifiee) avec x
  insere APRES tous les elements dont la cle est egale (stable) ; key optionnel s applique aux elements et a x.
- t25 `bucket.py` classe `TokenBucket(capacity, refill_per_sec)` : demarre pleine ; `allow(now, cost=1)` avec now en
  secondes (float) : recharge refill_per_sec * (now - dernier_now) jetons, plafonnee a capacity, puis accepte (rend True et
  retire cost) si le solde est >= cost, sinon rend False SANS rien retirer. Si now recule, aucune recharge (le dernier
  instant retenu ne recule pas). cost > capacity : toujours False. Le premier appel fixe l instant de reference.
- t26 `isoweek.py` `parse_iso_week(s)` : "2026-W01-1" (annee ISO, semaine, jour 1=lundi a 7=dimanche) -> datetime.date.
  La semaine 1 est celle qui contient le premier jeudi de l annee ; la semaine 53 n existe que pour certaines annees.
  Format invalide, semaine 0 ou inexistante, jour hors 1..7 : ValueError. Le jour est optionnel ("2026-W01") et vaut 1.
- t27 `redact.py` `redact_emails(text)` : remplace chaque adresse e-mail "local@example.com" par sa premiere lettre suivie de
  "***@example.com" (toujours trois etoiles, meme si la partie locale n a qu un caractere). Le reste du texte est intact.
  Un "@mot" sans domaine avec un point n est pas une adresse et reste inchange. Plusieurs adresses dans un texte : toutes.
- t28 `envexp.py` `env_expand(template, env)` : remplace `${VAR}` par env[VAR] (absent : chaine vide) ; `${VAR:-def}` par
  def si VAR est absent OU VIDE ; `$$` donne un `$` litteral ; un `$` isole ou `$VAR` sans accolades reste litteral. Pas
  d expansion recursive : la valeur substituee n est pas re-analysee. Accolade non fermee : ValueError.
- t29 `ragged.py` `transpose_ragged(rows, fill=None)` : transpose une liste de listes de longueurs differentes en completant
  par `fill`. [] -> [] ; [[]] -> [] ; les listes d entree ne sont pas modifiees ; rend des listes (pas des tuples).
- t30 `batching.py` `batch_by_weight(items, max_weight)` : items = liste de (nom, poids). Regroupe dans l ordre, sans
  reordonner, des lots successifs dont la somme des poids est <= max_weight (glouton : on ferme le lot quand le suivant
  deborderait). Un element plus lourd que max_weight forme un lot a lui seul. Poids 0 permis. Rend une liste de listes
  de noms. poids negatif ou max_weight <= 0 : ValueError.
- t31 `paths.py` `normalize_path(p)` : normalise un chemin POSIX sans utiliser os.path ni pathlib : fusionne "//", retire
  ".", resout "..". Absolu : ".." au-dessus de la racine reste a la racine. Relatif : les ".." de tete sont conserves.
  Slash final retire (sauf racine "/"). Resultat vide pour un relatif : ".". Entree "" : ".".
- t32 `boolparse.py` `parse_bool(v)` : accepte bool (rendu tel quel), les entiers 0 et 1 (pas 2), et les chaines (strip +
  casse ignoree) : yes/no, true/false, on/off, y/n, t/f, 1/0. Tout le reste (chaine vide, "maybe", 2, None, float 1.0,
  liste) : ValueError.
- t33 `hist.py` `histogram(values, edges)` : edges strictement croissants (au moins 2), sinon ValueError. Les cases sont
  [e0,e1[, [e1,e2[, ... et la DERNIERE est fermee [e_{n-2}, e_{n-1}]. Rend la liste des comptes ; les valeurs hors de
  [e0, e_last] sont ignorees. Les valeurs NaN sont ignorees.
- t34 `rot.py` `rot(text, n)` : decalage de Cesar des lettres ASCII a-z et A-Z (la casse est conservee), n quelconque
  (negatif, superieur a 26, 0). Tout autre caractere (accents, chiffres, ponctuation) reste intact.
- t35 `pager.py` `paginate(total, page, per_page)` : rend un dict {"page", "pages", "offset", "limit", "has_prev",
  "has_next"}. pages = max(1, ceil(total / per_page)). `page` hors bornes est ramene dans [1, pages] (jamais d erreur).
  offset = (page-1)*per_page ; limit = nombre reel d elements de cette page (la derniere peut etre plus courte ; 0 si
  total == 0). per_page < 1 ou total < 0 : ValueError.

## Procedure and deliverables
1. This file committed on the branch `bench-b3-prereg` (no push). 2. Generation of the 35 tasks by the local model, validity guard, commit of the set BEFORE the 1st resolution call. 3. Pilot 3 tasks, verified. 4. Complete measurement. 5. Report
`B3-RESULTS.md` ; set and scripts under `public/bench/oracle-prereg/` on the branch.
