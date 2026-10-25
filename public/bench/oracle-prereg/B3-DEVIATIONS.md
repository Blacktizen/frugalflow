# B3 : deviations au pre-enregistrement (hors B3-PREREG.md, qui ne bouge pas)

D1 (02:05, avant tout appel de resolution) : le garde de validite a ecarte 15 taches sur 35 a la 1re generation, puis 8
encore apres la 2e (t02 t04 t12 t17 t18 t26 t28 t34), soit 27 taches valides pour un minimum pre-enregistre de 30. Le
pre-enregistrement autorise UNE regeneration. Une 3e regeneration (meme enonce, meme consigne de generation) des 8 taches
restantes est faite pour atteindre 30 ; c est une deviation, decidee avant toute mesure du modele sur les taches, et qui ne
touche ni l enonce, ni la metrique, ni les seuils. Les taches encore invalides apres cette 3e generation sont exclues.
D2 : les taches pilotes pre-enregistrees (t05, t17, t25) : t17 est invalide a la 2e generation ; si elle reste exclue, le
pilote prend la tache valide suivante dans l ordre numerique (t19).
D3 (02:20) : le lanceur `runner.py` livre par le modele local (2 essais, verification rouge) passe 4 epreuves d autotest sur 5 ; la
5e echoue a cause d un defaut du faux delegue de l AUTOTEST (il n importe pas os), pas du lanceur. Regle "apres 2 echecs,
arret du point" : le lanceur n est pas redelegue, il est utilise tel que livre, sous le nom `runner.py.partiel.py`
(conserve ainsi dans le depot, rien n est renomme a la main).
D4 (02:25) : le pilote (t05, t19, t25) a montre que le lanceur lit les jetons sur la sortie standard alors que l outil de
delegation les imprime sur la sortie d erreur : jetons 0. Correctif sans toucher au lanceur : une enveloppe
`delegate_wrap.py` (modele local, autotest 3/3) passee par `--delegate`. Les donnees du pilote sans jetons sont jetees
(`pilot_notokens.jsonl`, conservees pour memoire, hors mesure) et le pilote est rejoue avec l enveloppe.
D5 : le pilote remplace t17 (invalide) par t19 (voir D2).

D6 (25/10, after the measurement, audit-fixes branch): the 5th autotest of `runner.py.partiel.py` failed because the fake
"nofence" delegate of the AUTOTEST itself imported `sys` but not `os` (D3). One word fixed in that fake (`import sys, os`);
the autotest now passes 5/5. The runner code that produced the published results is unchanged (the fake is used only by
`--autotest`), so the B3 figures are not affected.
