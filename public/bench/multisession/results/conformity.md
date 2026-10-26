# Respect des conventions par condition et par session

| Condition | Session | Livres | Strict | Tolerant | Echecs t1 | Echecs t2 | Echecs t3 strict | Echecs t3 tolerant | Echecs t4 | Point final |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 1 | 5 | 0 | 5 | 0 | 0 | 5 | 0 | 0 | 5 |
| A | 2 | 10 | 0 | 5 | 2 | 5 | 10 | 5 | 1 | 5 |
| A | 3 | 10 | 0 | 5 | 1 | 5 | 10 | 5 | 0 | 5 |
| A | 4 | 10 | 0 | 5 | 3 | 5 | 10 | 5 | 0 | 5 |
| A | 5 | 10 | 0 | 0 | 3 | 8 | 10 | 6 | 2 | 4 |
| B | 1 | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| B | 2 | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| B | 3 | 10 | 9 | 9 | 0 | 1 | 0 | 0 | 0 | 0 |
| B | 4 | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| B | 5 | 10 | 6 | 6 | 0 | 4 | 0 | 0 | 0 | 0 |

## Synthese

- A, session 1 : strict 0.0 % (0/5), tolerant 100.0 % (5/5)
- A, sessions 2-5 : strict 0.0 % (0/40), tolerant 37.5 % (15/40)
- B, session 1 : strict 100.0 % (10/10), tolerant 100.0 % (10/10)
- B, sessions 2-5 : strict 87.5 % (35/40), tolerant 87.5 % (35/40)

## Consigne suivie des la session 1 ?

- A : conformite stricte en session 1 = 0.0 % (0/5), donc inferieure a 50 %, la consigne n'a pas ete suivie des la session 1.
- B : conformite stricte en session 1 = 100.0 % (10/10), donc superieure ou egale a 50 %, la consigne a ete suivie des la session 1.

## Score de respect tolerant a la session 5 (tous modules)

- A : 0/10 modules tolerants, score 0.0 %
- B : 6/10 modules tolerants, score 60.0 %
- Difference B - A : 60.0 points de pourcentage
