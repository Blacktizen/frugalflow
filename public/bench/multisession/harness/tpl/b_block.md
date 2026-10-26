## Memoire du projet (FrugalFlow)
Ce projet a une memoire dans vault/ (regles : vault/SCHEMA.md). Le journal vault/log.md est scelle : on n y ecrit qu avec la commande ci-dessous.
- Au geste : apres chaque decision de convention et chaque exercice termine, ajoute une entree au journal :
  python3 {BIN}/journal_add.py --vault vault --title "<titre>" --field "Decision=<ce qui est decide ou fait>" --field "Why=<pourquoi>"
- Avant de finir : mets a jour vault/todo.md (ce qui reste, une ligne par tache), puis ferme la session :
  python3 {BIN}/session_digest.py --session <id> --vault vault
  ou <id> est le nom (sans .jsonl) du fichier le plus recent de $FRUGALFLOW_HOME/sessions/*/ (ls -t). Si le resultat n est pas SESSION HEALTHY, corrige ce qu il signale.
