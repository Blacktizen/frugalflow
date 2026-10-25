In this folder you will find the files listed below. Complete the work described next.

`bucket.py` classe `TokenBucket(capacity, refill_per_sec)` : demarre pleine ; `allow(now, cost=1)` avec now en
secondes (float) : recharge refill_per_sec * (now - dernier_now) jetons, plafonnee a capacity, puis accepte (rend True et
retire cost) si le solde est >= cost, sinon rend False SANS rien retirer. Si now recule, aucune recharge (le dernier
instant retenu ne recule pas). cost > capacity : toujours False. Le premier appel fixe l instant de reference.
